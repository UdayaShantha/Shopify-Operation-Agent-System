"""
agents/qa.py
Agent6 QA Agent  (LLM based, uses secondary LLM provider)

Spot-checks each listing for:
  - Unverifiable superlative claims ("world's best", "guaranteed to cure")
  - Specification mismatches vs the raw product data
  - Missing critical info (dimensions, compatibility, material)
  - Misleading SEO claims

Output: list of redline dicts  -  listing_redlines.json
Each redline has:
  supplier_sku, verdict (enum- PASS | WARN | FAIL), issues (list of strings), notes
"""

from __future__ import annotations
import json
import logging
from typing import Any

from app.llm.provider import get_provider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a strict e-commerce QA editor reviewing Shopify product listings.
Your job is to identify problems in product copy:
  1. OVER-CLAIMS: superlatives or unverifiable claims (e.g. "world's best", "guaranteed", "clinically proven")
  2. SPEC MISMATCH: listing contradicts the raw product data
  3. MISSING INFO: important attributes absent (material, compatibility, size)
  4. MISLEADING SEO: title/meta stuffed with irrelevant keywords

Verdicts:
  PASS - no issues
  WARN - minor issues, can publish with edits
  FAIL - serious issues, must not publish

Return a JSON array only. No markdown fences. No extra text."""

USER_TEMPLATE = """Review each listing against its product data. Return a JSON array where each element has:
  supplier_sku, verdict, issues (array of strings), notes (string)

Data:
{data_json}"""


class QAAgent:
    """LLM-powered QA reviewer for product listings."""

    def __init__(self):
        self._llm = get_provider("qa")
        logger.info("[QAAgent] Using provider: %s", type(self._llm).__name__)

    def run(
        self,
        listings: list[dict[str, Any]],
        selected_products: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:

        logger.info("[QAAgent] Running QA on %d listings...", len(listings))

        # Build combined data: listing + raw product side by side
        prod_map = {p["supplier_sku"]: p for p in selected_products}
        combined = []
        for listing in listings:
            sku  = listing["supplier_sku"]
            prod = prod_map.get(sku, {})
            combined.append({
                "supplier_sku":    sku,
                "raw_name":        prod.get("name", ""),
                "raw_description": prod.get("description", ""),
                "raw_brand":       prod.get("brand", ""),
                "raw_category":    prod.get("category", ""),
                "listing_title":   listing.get("title", ""),
                "listing_bullets": listing.get("bullets", []),
                "listing_desc":    listing.get("description", ""),
                "seo_title":       listing.get("seo_title", ""),
                "seo_description": listing.get("seo_description", ""),
            })

        user_prompt = USER_TEMPLATE.format(data_json=json.dumps(combined, indent=2))
        raw = self._llm.complete_json(SYSTEM_PROMPT, user_prompt, max_tokens=2000)

        if isinstance(raw, dict):
            for v in raw.values():
                if isinstance(v, list):
                    raw = v
                    break

        redlines = []
        for item in raw:
            redlines.append({
                "supplier_sku": item.get("supplier_sku", "UNKNOWN"),
                "verdict":      item.get("verdict", "PASS"),
                "issues":       item.get("issues", []),
                "notes":        item.get("notes", ""),
            })

        passes = sum(1 for r in redlines if r["verdict"] == "PASS")
        warns  = sum(1 for r in redlines if r["verdict"] == "WARN")
        fails  = sum(1 for r in redlines if r["verdict"] == "FAIL")
        logger.info("[QAAgent] Results — PASS:%d  WARN:%d  FAIL:%d", passes, warns, fails)

        return redlines
