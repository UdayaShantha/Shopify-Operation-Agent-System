# Shopify Dropshipping Operational Agent System

A **multi-agent hierarchical system** that automates Shopify dropshipping operations end-to-end — from product selection through to daily reporting. Built for the Coderra AI Engineer assessment.

---

## Architecture

```
                        ┌─────────────────────┐
                        │    Manager Agent     │
                        │  (Orchestrator)      │
                        └────────┬────────────┘
                                 │ controls
          ┌──────────────────────┼───────────────────────┐
          │                      │                        │
          ▼                      ▼                        ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ Product Sourcing │  │  Listing Agent   │  │ Pricing & Stock  │
│    Agent         │  │   (LLM — Llama3) │  │    Agent         │
│  (Deterministic) │  └──────────────────┘  │  (Deterministic) │
└──────────────────┘                        └──────────────────┘
          │                      │                        │
          ▼                      ▼                        ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Order Routing   │  │    QA Agent      │  │  Reporter Agent  │
│    Agent         │  │  (LLM — Gemini)  │  │ (Deterministic)  │
│  (Deterministic) │  └──────────────────┘  └──────────────────┘
└──────────────────┘
```

### Multi-LLM Assignment

| Agent           | Provider         | Reason                                      |
|-----------------|------------------|---------------------------------------------|
| Listing Agent   | Ollama           | Strong creative copywriting capability      |
| QA Agent        | Google Gemini    | Independent second opinion; free tier       |
| All others      | No LLM needed    | Deterministic logic / formula-based         |

---

## Agents

| # | Agent                  | Type          | Responsibility                                              |
|---|------------------------|---------------|-------------------------------------------------------------|
| 1 | **Manager Agent**      | Orchestrator  | Controls pipeline order, tracks state, saves all outputs    |
| 2 | **Product Sourcing**   | Deterministic | Selects top 10 SKUs with stock ≥ 10 and margin ≥ 25%       |
| 3 | **Listing Agent**      | LLM (Llama3)  | Generates titles, bullets, descriptions, tags, SEO          |
| 4 | **Pricing & Stock**    | Deterministic | Calculates prices via formula, outputs CSVs                 |
| 5 | **Order Routing**      | Deterministic | Fulfil / backorder / substitute + customer emails           |
| 6 | **QA Agent**           | LLM (Gemini)  | Spot-checks listings for over-claims, outputs redlines      |
| 7 | **Reporter Agent**     | Deterministic | Aggregates all outputs into `daily_report.md`               |

---

## Pricing Formula

For each product, find the minimum price **P** (rounded up to nearest $0.50) where margin ≥ 25%:

```
Platform fee  = 0.029 × P + $0.30
GST           = 0.10  × P   (Australian customers only)
Landed cost   = cost_price + shipping_cost + platform_fee + GST

Margin = (P − landed_cost) / P ≥ 0.25

Solving for P:
  P ≥ (cost_price + shipping_cost + $0.30) / (0.721 − GST_rate)

  Non-AU:  denominator = 0.721
  AU:      denominator = 0.621
```

---

## Setup ($0 Run)

### Option A — Anthropic + Gemini Free Tiers (Recommended)

```bash
# 1. Clone and enter directory
git clone <your-repo-url>
cd shopify_ops_agent

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set API keys (free tiers — no credit card required)
#    Gemini free tier:    https://aistudio.google.com
export GEMINI_API_KEY=your_key_here

# 5. Run the pipeline
python -m app run \
  --catalog data/supplier_catalog.csv \
  --orders  data/orders.csv \
  --out     out/
```

### Option B — Fully Local / $0 with Ollama (No API Key)

```bash
# 1. Install Ollama: https://ollama.ai
curl -fsSL https://ollama.ai/install.sh | sh

# 2. Pull two free models
ollama pull llama3
ollama pull mistral

# 3. Run pipeline with local models
export LISTING_PROVIDER=ollama
export QA_PROVIDER=ollama
export OLLAMA_MODEL=llama3

python -m app run \
  --catalog data/supplier_catalog.csv \
  --orders  data/orders.csv \
  --out     out/
```

### Option C — Mock/Offline Mode (Zero Dependencies)

If no API keys or Ollama are available, the system **automatically falls back** to a
`MockProvider` that returns structurally valid outputs. The entire deterministic pipeline
(selection, pricing, order routing, reporting) still runs fully and correctly.

```bash
python -m app run \
  --catalog data/supplier_catalog.csv \
  --orders  data/orders.csv \
  --out     out/
# No environment variables needed — mock mode activates automatically
```

---

## CLI Reference

```bash
python -m app run [OPTIONS]

Required:
  --catalog PATH     Path to supplier_catalog.csv
  --orders  PATH     Path to orders.csv

Optional:
  --out DIR                Output directory (default: out/)
  --log LEVEL              Logging level: DEBUG | INFO | WARNING (default: INFO)
  --provider-listing STR   LLM for Listing Agent:   gemini | ollama
  --provider-qa      STR   LLM for QA Agent:        gemini | ollama
  --provider-reporter STR  LLM for Reporter Agent:  gemini | ollama
```

### Example with debug logging and custom providers:

```bash
python -m app run \
  --catalog data/supplier_catalog.csv \
  --orders  data/orders.csv \
  --out     out/ \
  --log     DEBUG \
  --provider-listing  llama3 \
  --provider-qa       gemini
```

---

## Output Files

All files are written to the `--out` directory:

| File                   | Format   | Description                                             |
|------------------------|----------|---------------------------------------------------------|
| `selection.json`       | JSON     | 10 selected SKUs with full product data                 |
| `listings.json`        | JSON     | LLM-generated titles, bullets, descriptions, SEO, tags  |
| `price_update.csv`     | CSV      | AU & non-AU prices, margins, compare-at prices          |
| `stock_update.csv`     | CSV      | Synced stock levels, lead days, reorder flags           |
| `order_actions.json`   | JSON     | Per-order decisions + customer email text               |
| `listing_redlines.json`| JSON     | QA verdicts (PASS / WARN / FAIL) with issue details     |
| `daily_report.md`      | Markdown | Human-readable summary of all pipeline outputs          |

---

## Data Format

### `supplier_catalog.csv` (required columns)

```
supplier_sku, name, category, cost_price, stock, weight_kg,
length_cm, width_cm, height_cm, image_url, description,
brand, shipping_cost, supplier_lead_days
```

### `orders.csv` (required columns)

```
order_id, sku, quantity, customer_country, order_date
```

---

## Project Structure

```
shopify_ops_agent/
├── app/
│   ├── __init__.py
│   ├── __main__.py          ← CLI entry point
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── manager.py       ← Agent 1: Orchestrator
│   │   ├── product_sourcing.py  ← Agent 2
│   │   ├── listing.py       ← Agent 3 (LLM)
│   │   ├── pricing_stock.py ← Agent 4
│   │   ├── order_routing.py ← Agent 5
│   │   ├── qa.py            ← Agent 6 (LLM)
│   │   └── reporter.py      ← Agent 7
│   └── llm/
│       ├── __init__.py
│       └── provider.py      ← Multi-LLM abstraction layer
├── data/
│   ├── supplier_catalog.csv ← 35 SKUs
│   └── orders.csv           ← 20 sample orders
├── out/                     ← Generated outputs (git-ignored)
├── requirements.txt
└── README.md
```

---

## Design Decisions

**Why is the Pricing Agent deterministic?**
Pricing requires 100% reproducibility. Any randomness would break the ≥25% margin guarantee. A pure mathematical formula is auditable, testable, and never hallucinates numbers.

**Why batch LLM calls?**
All 10 products are sent to the Listing Agent in a single API call. This is cheaper, faster, and maintains consistent tone across all listings compared to 10 separate calls.

**Why does the system fall back to MockProvider?**
Reliability. The deterministic pipeline (5 out of 7 agents) runs perfectly without any LLM. If API keys are unavailable, the system still produces all 7 output files with valid structure — just with placeholder listing content.

**How is JSON validated?**
`complete_json()` in the provider layer strips markdown fences, attempts `json.loads()`, and retries once with an explicit "JSON only" instruction before raising a `ValueError`.

---

## Testing

```bash
# Run with mock mode (no API keys needed)
python -m app run --catalog data/supplier_catalog.csv --orders data/orders.csv --out out/

# Verify all 7 output files exist
ls -la out/

# Check pricing correctness for one SKU manually:
# SKU020: cost=$4.00, shipping=$1.50
# P >= (4.00 + 1.50 + 0.30) / 0.621 = $9.18 → rounds to $9.50
# AU margin = (9.50 - 4.00 - 1.50 - (0.029*9.50+0.30) - 0.10*9.50) / 9.50
#           = (9.50 - 4.00 - 1.50 - 0.5755 - 0.95) / 9.50
#           = 2.4745 / 9.50 = 26.05% ✓
```
