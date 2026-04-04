"""
agents/reporter.py
Agent7 Reporter Agent

Collects all pipeline outputs and writes a human-readable daily_report.md file.
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class ReporterAgent:
    """Generates daily_report.md from all pipeline outputs."""

    def run(
        self,
        selected_products:  list[dict[str, Any]],
        listings:           list[dict[str, Any]],
        price_df:           pd.DataFrame,
        stock_df:           pd.DataFrame,
        order_actions:      list[dict[str, Any]],
        redlines:           list[dict[str, Any]],
        out_dir:            str,
        catalog:            pd.DataFrame,
    ) -> str:

        logger.info("[ReporterAgent] Compiling daily report...")
        today = datetime.today().strftime("%A, %d %B %Y")
        now   = datetime.today().strftime("%Y-%m-%d %H:%M")

        action_counts: dict[str, int] = {}
        for a in order_actions:
            action_counts[a["action"]] = action_counts.get(a["action"], 0) + 1

        qa_counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
        for r in redlines:
            qa_counts[r["verdict"]] = qa_counts.get(r["verdict"], 0) + 1

        total_orders       = len(order_actions)
        fulfil_count       = action_counts.get("FULFIL", 0)
        backorder_count    = action_counts.get("BACKORDER", 0)
        substitute_count   = action_counts.get("SUBSTITUTE", 0)
        unknown_count      = action_counts.get("UNKNOWN_SKU", 0)

        # Estimated revenue (AU prices * qty for FULFIL orders)
        price_map = price_df.set_index("supplier_sku")["price_au"].to_dict() if not price_df.empty else {}
        estimated_revenue = 0.0
        for a in order_actions:
            if a["action"] == "FULFIL":
                p = price_map.get(a["sku"], 0)
                estimated_revenue += p * a.get("quantity", 1)

        # Build report
        lines = []

        lines += [
            f"# Daily Operations Report",
            f"",
            f"**Generated:** {now}  ",
            f"**Report Date:** {today}",
            f"",
            f"---",
            f"",
        ]

        # Section 1 - Product Selection
        lines += [
            f"## 1. Product Selection",
            f"",
            f"**{len(selected_products)} SKUs** selected from supplier catalogue (criteria: stock ≥ 10, margin ≥ 25%).",
            f"",
            f"| SKU | Name | Category | Cost | Stock | Lead Days |",
            f"|-----|------|----------|------|-------|-----------|",
        ]
        for p in selected_products:
            lines.append(
                f"| {p['supplier_sku']} | {p['name']} | {p['category']} "
                f"| ${float(p['cost_price']):.2f} | {p['stock']} | {p['supplier_lead_days']}d |"
            )
        lines += ["", "---", ""]

        # Section 2 - Listings
        lines += [
            f"## 2. Shopify Listing Generation",
            f"",
            f"**{len(listings)} listings** generated via LLM.",
            f"",
        ]
        for l in listings:
            lines += [
                f"### {l['title']}  *(SKU: {l['supplier_sku']})*",
                f"",
                f"**SEO Title:** {l.get('seo_title', '')}  ",
                f"**Description:** {l.get('description', '')}  ",
                f"**Tags:** {', '.join(l.get('tags', []))}",
                f"",
            ]
        lines += ["---", ""]

        # Section 3 - Pricing
        lines += [
            f"## 3. Pricing & Stock Sync",
            f"",
            f"All prices calculated using the formula: `P ≥ (cost + shipping + $0.30) / (0.721 − GST_rate)`, rounded up to nearest $0.50.",
            f"",
            f"| SKU | Name | AU Price | Non-AU Price | Compare At | AU Margin | Stock | Reorder? |",
            f"|-----|------|----------|-------------|------------|-----------|-------|---------|",
        ]
        for _, row in price_df.iterrows():
            sku       = row["supplier_sku"]
            stock_row = stock_df[stock_df["supplier_sku"] == sku]
            reorder   = stock_row["reorder_flag"].values[0] if not stock_row.empty else "—"
            stk       = stock_row["shopify_stock"].values[0] if not stock_row.empty else "—"
            lines.append(
                f"| {sku} | {row['name']} | ${row['price_au']:.2f} | ${row['price_non_au']:.2f} "
                f"| ${row['compare_at']:.2f} | {row['margin_au_pct']}% | {stk} | {reorder} |"
            )
        lines += ["", "---", ""]

        # Section 4 - Order Routing
        lines += [
            f"## 4. Order Routing",
            f"",
            f"**{total_orders} orders** processed.",
            f"",
            f"| Action | Count |",
            f"|--------|-------|",
            f"|  FULFIL | {fulfil_count} |",
            f"|  BACKORDER | {backorder_count} |",
            f"|  SUBSTITUTE | {substitute_count} |",
            f"|  UNKNOWN SKU | {unknown_count} |",
            f"",
            f"**Estimated Revenue (fulfilled orders):** ${estimated_revenue:.2f} AUD",
            f"",
            f"### Order Details",
            f"",
            f"| Order ID | SKU | Qty | Country | Action | Reason |",
            f"|----------|-----|-----|---------|--------|--------|",
        ]
        for a in order_actions:
            lines.append(
                f"| {a['order_id']} | {a['sku']} | {a['quantity']} | {a['country']} "
                f"| {a['action']} | {a.get('reason', '')} |"
            )
        lines += ["", "---", ""]

        # Section 5 - QA
        lines += [
            f"## 5. Listing QA Review",
            f"",
            f"| Verdict | Count |",
            f"|---------|-------|",
            f"|  PASS | {qa_counts['PASS']} |",
            f"|   WARN | {qa_counts['WARN']} |",
            f"|  FAIL | {qa_counts['FAIL']} |",
            f"",
        ]
        for r in redlines:
            if r["verdict"] != "PASS":
                lines += [
                    f"**{r['supplier_sku']}** — {r['verdict']}",
                    "",
                ]
                for issue in r.get("issues", []):
                    lines.append(f"- {issue}")
                if r.get("notes"):
                    lines.append(f"*Notes: {r['notes']}*")
                lines.append("")
        lines += ["---", ""]

        # Section 6-— Alerts
        alerts = []
        for _, row in stock_df.iterrows():
            if row["reorder_flag"] == "YES":
                alerts.append(f"-   **{row['supplier_sku']} — {row['name']}**: only {row['shopify_stock']} units remaining. Reorder suggested.")
        if backorder_count > 0:
            alerts.append(f"-  **{backorder_count} order(s) on backorder** — review supplier lead times.")
        if unknown_count > 0:
            alerts.append(f"-  **{unknown_count} order(s) with unknown SKUs** — manual review required.")
        if qa_counts["FAIL"] > 0:
            alerts.append(f"-  **{qa_counts['FAIL']} listing(s) failed QA** — do not publish until resolved.")

        lines += [f"## 6. Alerts & Recommendations", ""]
        if alerts:
            lines += alerts
        else:
            lines.append(" No critical alerts. All systems nominal.")
        lines += ["", "---", ""]

        # Footer
        lines += [
            f"*Report auto-generated by Shopify Dropshipping Ops Agent.*",
            f"*Pipeline: ProductSourcing → Listing → PricingStock → OrderRouting → QA → Reporter*",
        ]

        report = "\n".join(lines)
        path   = f"{out_dir}/daily_report.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)

        logger.info("[ReporterAgent] daily_report.md written to %s", path)
        return report
