"""
agents/pricing_stock.py
Agent4 Pricing & Stock Agent

For each selected product computes:
  - retail price for non-AU customers  (no GST)
  - retail price for AU customers      (includes 10% GST)
  - recommended Shopify listing price  (AU price, conservative)
  - compare_at price                   (10% above listing, creates "sale" feel)

Outputs:
  price_update.csv - SKU, prices, margin
  stock_update.csv - SKU, supplier_stock, shopify_stock (= supplier_stock)
"""

from __future__ import annotations
import logging
import math
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def _round_up_50(value: float) -> float:
    """Round up to nearest $0.50."""
    return math.ceil(value / 0.50) * 0.50


def calculate_price(cost: float, shipping: float, is_au: bool) -> float:
    """
    Minimum price P satisfying margin >= 25%.

    Derivation:
      fee      = 0.029 * P + 0.30
      gst      = 0.10  * P  (AU only, else 0)
      landed   = cost + shipping + fee + gst
      margin   = (P - landed) / P >= 0.25
      
      P * (1 - 0.029 - gst_rate - 0.25) >= cost + shipping + 0.30
      P >= (cost + shipping + 0.30) / (0.721 - gst_rate)
    """
    gst_rate  = 0.10 if is_au else 0.0
    denom     = 0.721 - gst_rate          # 0.621 for AU, 0.721 for non-AU
    raw_price = (cost + shipping + 0.30) / denom
    return _round_up_50(raw_price)


def actual_margin(price: float, cost: float, shipping: float, is_au: bool) -> float:
    fee    = 0.029 * price + 0.30
    gst    = 0.10  * price if is_au else 0.0
    landed = cost + shipping + fee + gst
    return round((price - landed) / price, 4)


class PricingStockAgent:
    """Deterministic pricing and stock sync agent."""

    def run(
        self,
        selected_products: list[dict[str, Any]],
        out_dir: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        logger.info("[PricingStockAgent] Calculating prices for %d SKUs...", len(selected_products))

        price_rows = []
        stock_rows = []

        for p in selected_products:
            sku      = p["supplier_sku"]
            cost     = float(p["cost_price"])
            shipping = float(p["shipping_cost"])
            stock    = int(p["stock"])

            price_non_au = calculate_price(cost, shipping, is_au=False)
            price_au     = calculate_price(cost, shipping, is_au=True)

            # Use AU price as Shopify listing price (highest; covers all markets)
            listing_price   = price_au
            compare_at      = _round_up_50(listing_price * 1.10)   # "was" price

            margin_au     = actual_margin(listing_price, cost, shipping, is_au=True)
            margin_non_au = actual_margin(price_non_au,  cost, shipping, is_au=False)

            logger.debug(
                "  %s  cost=%.2f  ship=%.2f  AU=%.2f (%.1f%%)  non-AU=%.2f (%.1f%%)",
                sku, cost, shipping,
                listing_price, margin_au * 100,
                price_non_au,  margin_non_au * 100,
            )

            price_rows.append({
                "supplier_sku":    sku,
                "name":            p["name"],
                "cost_price":      cost,
                "shipping_cost":   shipping,
                "price_au":        listing_price,
                "price_non_au":    price_non_au,
                "compare_at":      compare_at,
                "margin_au_pct":   round(margin_au * 100, 2),
                "margin_non_au_pct": round(margin_non_au * 100, 2),
            })

            stock_rows.append({
                "supplier_sku":   sku,
                "name":           p["name"],
                "supplier_stock": stock,
                "shopify_stock":  stock,          # 1-to-1 sync
                "lead_days":      p["supplier_lead_days"],
                "reorder_flag":   "YES" if stock < 20 else "NO",
            })

        price_df = pd.DataFrame(price_rows)
        stock_df = pd.DataFrame(stock_rows)

        price_df.to_csv(f"{out_dir}/price_update.csv", index=False)
        stock_df.to_csv(f"{out_dir}/stock_update.csv", index=False)

        logger.info("[PricingStockAgent] price_update.csv and stock_update.csv written.")
        return price_df, stock_df
