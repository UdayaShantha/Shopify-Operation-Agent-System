"""
agents/manager.py
Agent1  Manager Agent

Orchestrates the full pipeline in order:
  1. ProductSourcingAgent  
  2. ListingAgent          
  3. PricingStockAgent    
  4. OrderRoutingAgent     
  5. QAAgent               
  6. ReporterAgent         

Tracks pipeline state; on failure saves partial outputs and re-raises.
"""

from __future__ import annotations
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.agents.product_sourcing import ProductSourcingAgent
from app.agents.listing          import ListingAgent
from app.agents.pricing_stock    import PricingStockAgent
from app.agents.order_routing    import OrderRoutingAgent
from app.agents.qa               import QAAgent
from app.agents.reporter         import ReporterAgent

logger = logging.getLogger(__name__)


@dataclass
class PipelineState:
    """Tracks progress and outputs of the pipeline run."""
    started_at:        str = ""
    completed_at:      str = ""
    status:            str = "PENDING"   # PENDING | RUNNING | COMPLETE | FAILED
    last_stage:        str = ""
    selected_products: list = field(default_factory=list)
    listings:          list = field(default_factory=list)
    order_actions:     list = field(default_factory=list)
    redlines:          list = field(default_factory=list)
    errors:            list = field(default_factory=list)


class ManagerAgent:
    """Orchestrates the full Shopify dropshipping ops pipeline."""

    def __init__(self, out_dir: str):
        self.out_dir = out_dir
        self.state   = PipelineState()
        os.makedirs(out_dir, exist_ok=True)

    # Public entry point

    def run(self, catalog_path: str, orders_path: str) -> PipelineState:
        self.state.started_at = datetime.now().isoformat()
        self.state.status     = "RUNNING"
        t0                    = time.time()

        logger.info("=" * 60)
        logger.info("Manager Agent starting pipeline")
        logger.info("  Catalog : %s", catalog_path)
        logger.info("  Orders  : %s", orders_path)
        logger.info("  Output  : %s", self.out_dir)
        logger.info("=" * 60)

        try:
            catalog, orders = self._load_data(catalog_path, orders_path)

            # Stage 1: Product Sourcing 
            self._stage("product_sourcing")
            selected = ProductSourcingAgent().run(catalog)
            self.state.selected_products = selected
            self._save_json("selection.json", selected)

            # Stage 2: Listing Generation
            self._stage("listing")
            listings = ListingAgent().run(selected)
            self.state.listings = listings
            self._save_json("listings.json", listings)

            # Stage 3: Pricing & Stock 
            self._stage("pricing_stock")
            price_df, stock_df = PricingStockAgent().run(selected, self.out_dir)

            # Stage 4: Order Routing 
            self._stage("order_routing")
            order_actions = OrderRoutingAgent().run(orders, catalog, selected, stock_df)
            self.state.order_actions = order_actions
            self._save_json("order_actions.json", order_actions)

            # Stage 5: QA
            self._stage("qa")
            redlines = QAAgent().run(listings, selected)
            self.state.redlines = redlines
            self._save_json("listing_redlines.json", redlines)

            # Stage 6: Reporter 
            self._stage("reporter")
            ReporterAgent().run(
                selected_products = selected,
                listings          = listings,
                price_df          = price_df,
                stock_df          = stock_df,
                order_actions     = order_actions,
                redlines          = redlines,
                out_dir           = self.out_dir,
                catalog           = catalog,
            )

            elapsed = time.time() - t0
            self.state.status       = "COMPLETE"
            self.state.completed_at = datetime.now().isoformat()
            logger.info("=" * 60)
            logger.info("Pipeline COMPLETE in %.1fs", elapsed)
            logger.info("Outputs written to: %s", self.out_dir)
            logger.info("=" * 60)

        except Exception as exc:
            self.state.status = "FAILED"
            self.state.errors.append(str(exc))
            logger.error("Pipeline FAILED at stage '%s': %s", self.state.last_stage, exc, exc_info=True)
            raise

        return self.state

    # Helpers to perform

    def _stage(self, name: str):
        self.state.last_stage = name
        logger.info("── Stage: %s ──", name.upper().replace("_", " "))

    def _save_json(self, filename: str, data: Any):
        path = os.path.join(self.out_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info("  Saved %s", path)

    @staticmethod
    def _load_data(catalog_path: str, orders_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        if not Path(catalog_path).exists():
            raise FileNotFoundError(f"Catalog not found: {catalog_path}")
        if not Path(orders_path).exists():
            raise FileNotFoundError(f"Orders not found: {orders_path}")

        catalog = pd.read_csv(catalog_path)
        orders  = pd.read_csv(orders_path)

        # Validate required columns (All are okay or not)
        required_catalog = {"supplier_sku", "name", "category", "cost_price", "stock",
                            "shipping_cost", "supplier_lead_days", "description", "brand"}
        required_orders  = {"order_id", "sku", "quantity", "customer_country", "order_date"}

        missing_c = required_catalog - set(catalog.columns)
        missing_o = required_orders  - set(orders.columns)
        if missing_c:
            raise ValueError(f"Catalog missing columns: {missing_c}")
        if missing_o:
            raise ValueError(f"Orders missing columns: {missing_o}")

        logger.info("Loaded catalog: %d rows | orders: %d rows", len(catalog), len(orders))
        return catalog, orders
