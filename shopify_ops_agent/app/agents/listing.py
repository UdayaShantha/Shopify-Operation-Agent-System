"""
agents/listing.py
Agent3 Listing Agent  (LLM based one)

For each selected product generates:
  - title          : SEO-friendly product title (max 70 chars)
  - bullets        : 5 benefit-focused bullet points
  - description    : 80-120 word HTML-free description
  - tags           : up to 8 Shopify tags
  - seo_title      : meta title (max 70 chars)
  - seo_description: meta description (max 160 chars)

Calls the LLM in a single batched prompt (all SKUs at once) to minimise
"""

from __future__ import annotations
import json
import logging
from typing import Any

from app.llm.provider import get_provider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Shopify product copywriter.
Your task: generate engaging, accurate, SEO-optimised product listing content.
Rules:
- Never make claims that cannot be verified from the product data.
- Do not use superlatives like "best ever", "world's #1", "guaranteed to cure".
- Write in plain English, no HTML tags.
- Title max 70 characters.
- Description 80-120 words.
- seo_title max 70 characters.
- seo_description max 160 characters.
- Return a JSON array only. No markdown fences. No extra text."""

USER_TEMPLATE = """Generate listing content for each product below.
Return a JSON array where each element has:
  supplier_sku, title, bullets (array of 5 strings), description, tags (array of strings, max 8), seo_title, seo_description

Products:
{products_json}"""


class ListingAgent:
    """Generates Shopify listing content using an LLM."""

    def __init__(self):
        self._llm = get_provider("listing")
        logger.info("[ListingAgent] Using provider: %s", type(self._llm).__name__)

    def run(self, selected_products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        logger.info("[ListingAgent] Generating listings for %d products...", len(selected_products))

        # Build a compact product summary for the prompt (keep tokens low)
        compact = [
            {
                "supplier_sku": p["supplier_sku"],
                "name":         p["name"],
                "category":     p["category"],
                "description":  p["description"],
                "brand":        p["brand"],
            }
            for p in selected_products
        ]

        user_prompt = USER_TEMPLATE.format(products_json=json.dumps(compact, indent=2))

        raw = self._llm.complete_json(SYSTEM_PROMPT, user_prompt, max_tokens=3000)

        # Normalise: handle both array-root and dict-with-array-value responses
        if isinstance(raw, dict):
            # Try to find the list inside
            for v in raw.values():
                if isinstance(v, list):
                    raw = v
                    break

        listings: list[dict] = []
        sku_map = {p["supplier_sku"]: p for p in selected_products}

        for item in raw:
            sku = item.get("supplier_sku", "UNKNOWN")
            listings.append({
                "supplier_sku":      sku,
                "title":             item.get("title", sku_map.get(sku, {}).get("name", "")),
                "bullets":           item.get("bullets", []),
                "description":       item.get("description", ""),
                "tags":              item.get("tags", []),
                "seo_title":         item.get("seo_title", ""),
                "seo_description":   item.get("seo_description", ""),
            })

        logger.info("[ListingAgent] Generated %d listings.", len(listings))
        return listings
