"""
agents/order_routing.py
Agent5  Order Routing Agent 

For each order decides:
  FULFIL      - item in stock, dispatch normally
  BACKORDER   - item exists but insufficient stock
  SUBSTITUTE  - SKU not found in selected catalogue (suggest alternative)
  UNKNOWN_SKU - SKU not in supplier catalogue at all

Also generates a customer-facing email for each action.
Output: list of order action dicts  -  order_actions.json
"""

from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Email templates for customers

def _email_fulfil(order: dict, product_name: str, dispatch_date: str, lead_days: int) -> str:
    return f"""Subject: Your order {order['order_id']} is confirmed!

Hi there,

Great news! Your order for **{product_name}** (Qty: {order['quantity']}) has been confirmed and will be dispatched by {dispatch_date}.

Estimated delivery: {lead_days}–{lead_days + 3} business days after dispatch.

Order ID: {order['order_id']}
Product : {product_name}
Quantity: {order['quantity']}

Thank you for shopping with us!

Best regards,
Shofiy Team"""


def _email_backorder(order: dict, product_name: str, restock_date: str) -> str:
    return f"""Subject: Update on your order {order['order_id']}

Hi there,

Thank you for your order. Unfortunately, **{product_name}** is currently low in stock and your order (Qty: {order['quantity']}) has been placed on backorder.

Expected restock date: {restock_date}
We will dispatch your item as soon as stock is available.

Order ID: {order['order_id']}

We apologise for any inconvenience. You may reply to this email to cancel for a full refund.

Best regards,
Shofiy Team"""


def _email_substitute(order: dict, original_sku: str, alt_name: str, alt_sku: str) -> str:
    return f"""Subject: Alternative product available for order {order['order_id']}

Hi there,

We're sorry — the product you ordered (SKU: {original_sku}) is not currently available.

We'd like to offer you a substitute:
   {alt_name} (SKU: {alt_sku})

Please reply to accept the substitute or request a full refund.

Order ID: {order['order_id']}

Best regards,
Shofiy Team"""


def _email_unknown(order: dict) -> str:
    return f"""Subject: Issue with your order {order['order_id']}

Hi there,

We were unable to locate the product in your order (SKU: {order['sku']}).
Our team will review and contact you within 1 business day.

Order ID: {order['order_id']}

We apologise for the inconvenience.

Best regards,
Shofiy Team"""


class OrderRoutingAgent:
    """Routes each order to an action and generates a customer email."""

    def run(
        self,
        orders: pd.DataFrame,
        catalog: pd.DataFrame,
        selected_products: list[dict[str, Any]],
        stock_df: pd.DataFrame,
    ) -> list[dict[str, Any]]:

        logger.info("[OrderRoutingAgent] Processing %d orders...", len(orders))

        today = datetime.today()

        # Build lookup structures
        selected_skus  = {p["supplier_sku"] for p in selected_products}
        catalog_map    = catalog.set_index("supplier_sku").to_dict("index")
        stock_map      = stock_df.set_index("supplier_sku")["shopify_stock"].to_dict()
        lead_map       = stock_df.set_index("supplier_sku")["lead_days"].to_dict()

        # Build a quick substitute index: category  first available selected SKU
        category_alt: dict[str, dict] = {}
        for p in selected_products:
            cat = p["category"]
            if cat not in category_alt:
                category_alt[cat] = p

        actions = []

        for _, order in orders.iterrows():
            order_dict = order.to_dict()
            sku        = order["sku"]
            qty        = int(order["quantity"])
            country    = order["customer_country"]

            if sku not in catalog_map:
                # SKU completely unknown
                action = {
                    "order_id":    order["order_id"],
                    "sku":         sku,
                    "quantity":    qty,
                    "country":     country,
                    "action":      "UNKNOWN_SKU",
                    "reason":      f"SKU {sku} not found in supplier catalogue.",
                    "email":       _email_unknown(order_dict),
                }
                logger.warning("  %s  UNKNOWN_SKU  %s", order["order_id"], sku)

            elif sku not in selected_skus:
                # SKU exists in catalogue but was not selected — find substitute
                cat      = catalog_map[sku].get("category", "")
                alt_prod = category_alt.get(cat)

                if alt_prod:
                    action = {
                        "order_id":       order["order_id"],
                        "sku":            sku,
                        "quantity":       qty,
                        "country":        country,
                        "action":         "SUBSTITUTE",
                        "reason":         f"SKU {sku} not in active listings. Substitute offered.",
                        "substitute_sku": alt_prod["supplier_sku"],
                        "substitute_name":alt_prod["name"],
                        "email":          _email_substitute(order_dict, sku, alt_prod["name"], alt_prod["supplier_sku"]),
                    }
                    logger.info("  %s  SUBSTITUTE  %s → %s", order["order_id"], sku, alt_prod["supplier_sku"])
                else:
                    action = {
                        "order_id": order["order_id"],
                        "sku":      sku,
                        "quantity": qty,
                        "country":  country,
                        "action":   "UNKNOWN_SKU",
                        "reason":   f"SKU {sku} not active and no substitute found.",
                        "email":    _email_unknown(order_dict),
                    }

            else:
                # SKU is selected — check stock
                available = stock_map.get(sku, 0)
                lead_days = int(lead_map.get(sku, 7))

                if available >= qty:
                    dispatch = (today + timedelta(days=1)).strftime("%d %b %Y")
                    action   = {
                        "order_id":      order["order_id"],
                        "sku":           sku,
                        "quantity":      qty,
                        "country":       country,
                        "action":        "FULFIL",
                        "stock_before":  available,
                        "stock_after":   available - qty,
                        "dispatch_date": dispatch,
                        "reason":        "Stock available.",
                        "email":         _email_fulfil(
                            order_dict,
                            catalog_map[sku]["name"],
                            dispatch,
                            lead_days,
                        ),
                    }
                    # Deduct stock for subsequent orders in same run
                    stock_map[sku] = available - qty
                    logger.info("  %s  FULFIL  %s  qty=%d  stock_remaining=%d",
                                order["order_id"], sku, qty, stock_map[sku])
                else:
                    restock = (today + timedelta(days=lead_days + 2)).strftime("%d %b %Y")
                    action  = {
                        "order_id":      order["order_id"],
                        "sku":           sku,
                        "quantity":      qty,
                        "country":       country,
                        "action":        "BACKORDER",
                        "stock_available": available,
                        "restock_date":  restock,
                        "reason":        f"Only {available} units in stock, {qty} ordered.",
                        "email":         _email_backorder(
                            order_dict,
                            catalog_map[sku]["name"],
                            restock,
                        ),
                    }
                    logger.info("  %s  BACKORDER  %s  avail=%d  needed=%d",
                                order["order_id"], sku, available, qty)

            actions.append(action)

        counts = {}
        for a in actions:
            counts[a["action"]] = counts.get(a["action"], 0) + 1
        logger.info("[OrderRoutingAgent] Done. Summary: %s", counts)

        return actions
