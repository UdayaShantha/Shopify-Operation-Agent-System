"""
agents/product_sourcing.py
Agent2 Product Sourcing Agent

Selects the top 10 SKUs (products) from the supplier catalogue that meet:
    Conditions :
        stock >= 10
        margin >= 25%  (using the same pricing formula as the Pricing Agent)

Selection ranking: highest margin first, then highest stock.
Output: list of selected product dicts.
"""

from __future__ import annotations
import logging
import math
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

MIN_STOCK = 10
MIN_MARGIN = 0.25
TOP_N = 10


def _min_price(cost: float, shipping: float, is_au: bool = False) -> float:
    """
    Compute the minimum retail price P that yields >= 25% margin.

    Platform fee = 0.029 * P + 0.30
    GST          = 0.10  * P  (AU only)
    Landed cost  = cost + shipping + fee + GST

    Margin = (P - landed_cost) / P >= 0.25
    => P - (cost + shipping + 0.029*P + 0.30 + gst_rate*P) >= 0.25 * P
    => P * (1 - 0.029 - gst_rate - 0.25) >= cost + shipping + 0.30
    => P >= (cost + shipping + 0.30) / (0.721 - gst_rate)   [non-AU]
    => P >= (cost + shipping + 0.30) / (0.621)              [AU]
    """
    gst_rate = 0.10 if is_au else 0.0
    denominator = 1 - 0.029 - gst_rate - MIN_MARGIN
    if denominator <= 0:
        raise ValueError("Pricing denominator is non-positive — check formula constants.")
    raw_p = (cost + shipping + 0.30) / denominator
    # Round up to nearest $0.50
    return math.ceil(raw_p / 0.50) * 0.50


def _actual_margin(price: float, cost: float, shipping: float, is_au: bool = False) -> float:
    """Return actual margin given a retail price."""
    fee = 0.029 * price + 0.30
    gst = 0.10 * price if is_au else 0.0
    landed = cost + shipping + fee + gst
    return (price - landed) / price


class ProductSourcingAgent:
    """Picks the best 10 SKUs from the catalogue."""

    def run(self, catalog: pd.DataFrame) -> list[dict[str, Any]]:
        logger.info("[ProductSourcingAgent] Evaluating %d SKUs...", len(catalog))

        rows = []
        for _, row in catalog.iterrows():
            cost     = float(row["cost_price"])
            shipping = float(row["shipping_cost"])
            stock    = int(row["stock"])

            if stock < MIN_STOCK:
                logger.debug("  SKIP %s — stock %d < %d", row["supplier_sku"], stock, MIN_STOCK)
                continue

            # Use non-AU pricing to find baseline margin (worst case for AU)
            price  = _min_price(cost, shipping, is_au=False)
            margin = _actual_margin(price, cost, shipping, is_au=False)

            if margin < MIN_MARGIN:
                logger.debug("  SKIP %s — margin %.1f%% < 25%%", row["supplier_sku"], margin * 100)
                continue

            rows.append({
                **row.to_dict(),
                "_min_price_non_au": price,
                "_margin_non_au":    round(margin, 4),
            })

        if not rows:
            logger.warning("[ProductSourcingAgent] No SKUs met the criteria!")
            return []

        # Sort: highest margin first, then highest stock
        rows.sort(key=lambda r: (-r["_margin_non_au"], -r["stock"]))
        selected = rows[:TOP_N]

        # Clean up internal keys
        for r in selected:
            r.pop("_min_price_non_au", None)
            r.pop("_margin_non_au",    None)

        logger.info("[ProductSourcingAgent] Selected %d SKUs.", len(selected))
        for s in selected:
            logger.info("  ✓ %s  %s  stock=%s", s["supplier_sku"], s["name"], s["stock"])

        return selected
