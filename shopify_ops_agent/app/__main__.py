"""
app/__main__.py
CLI entry point.

Usage:
  python -m app run --catalog data/supplier_catalog.csv --orders data/orders.csv --out out/

Options:
  --catalog   Path to supplier_catalog.csv
  --orders    Path to orders.csv
  --out       Output directory (default: out/)
  --log       Log level: DEBUG | INFO | WARNING (default: INFO)
  --provider-listing   LLM provider for Listing Agent  (anthropic | gemini | ollama)
  --provider-qa        LLM provider for QA Agent
  --provider-reporter  LLM provider for Reporter Agent
"""

import argparse
import logging
import os
import sys


def _configure_logging(level: str):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


def _run(args: argparse.Namespace):
    # Apply provider overrides before importing agents (env vars read at import)
    if args.provider_listing:
        os.environ["LISTING_PROVIDER"]  = args.provider_listing
    if args.provider_qa:
        os.environ["QA_PROVIDER"]       = args.provider_qa
    if args.provider_reporter:
        os.environ["REPORTER_PROVIDER"] = args.provider_reporter

    # Late import so env vars are set first
    from app.agents.manager import ManagerAgent

    manager = ManagerAgent(out_dir=args.out)
    state   = manager.run(
        catalog_path=args.catalog,
        orders_path=args.orders,
    )

    print("\n" + "=" * 55)
    print(f"  Pipeline status : {state.status}")
    print(f"  Started         : {state.started_at}")
    print(f"  Completed       : {state.completed_at}")
    print(f"  Output dir      : {args.out}")
    print("=" * 55)

    if state.status == "COMPLETE":
        print("\n  Files written:")
        for fname in [
            "selection.json", "listings.json",
            "price_update.csv", "stock_update.csv",
            "order_actions.json", "listing_redlines.json",
            "daily_report.md",
        ]:
            fpath = os.path.join(args.out, fname)
            exists = "✓" if os.path.exists(fpath) else "✗"
            print(f"    {exists}  {fpath}")
        print()
        sys.exit(0)
    else:
        print("\n  Errors:")
        for e in state.errors:
            print(f"    • {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="python -m app",
        description="Shopify Dropshipping Ops Agent — multi-agent pipeline",
    )
    sub = parser.add_subparsers(dest="command")

    # run subcommand
    run_p = sub.add_parser("run", help="Execute the full pipeline")
    run_p.add_argument("--catalog", required=True,  help="Path to supplier_catalog.csv")
    run_p.add_argument("--orders",  required=True,  help="Path to orders.csv")
    run_p.add_argument("--out",     default="out/",  help="Output directory (default: out/)")
    run_p.add_argument("--log",     default="INFO",  help="Log level (default: INFO)")
    run_p.add_argument("--provider-listing",  default=None, help="LLM provider for Listing Agent")
    run_p.add_argument("--provider-qa",       default=None, help="LLM provider for QA Agent")
    run_p.add_argument("--provider-reporter", default=None, help="LLM provider for Reporter Agent")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    _configure_logging(args.log)

    if args.command == "run":
        _run(args)


if __name__ == "__main__":
    main()
