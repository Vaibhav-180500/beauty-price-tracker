# Day 2 — Tracking Plan (MVP locked from CSV, two‑retailer per SKU)

**CSV source**: `sku_registry_top30.csv` with **30 SKUs** × **3 retailers** ⇒ **60 priority PDPs**.

## 1) Objective
Capture price and availability from a fixed **Top‑30** basket (10 Haircare, 10 Skincare, 10 Makeup), with **two retailers per SKU** (prestige ↔ Sephora FR + Amazon FR; mass ↔ Carrefour FR + Amazon FR). Keep load low and stay within BigQuery **Sandbox**.

## 2) Data contracts (seed)
Seed schema (already in your CSV):
```
sku_id,category,subcategory,brand,product_name,size_value,size_unit,variant_id,retailer,product_url,currency
```
Rules:
- `sku_id` is the durable key for analytics.
- `variant_id` pins a single shade/option for makeup and a single size for haircare/skincare.
- One row per **(sku_id, retailer)**.

## 3) Ingestion (batch, Sandbox‑friendly)
- **Politeness:** 1 request every 12–20s per domain, single thread, timeout 10s, retries 2 (2s→4s), clear UA. Back off on 403/429.
- **Fetch & parse:** `requests + BeautifulSoup` using selectors from `ingestion/selectors.yml`.
- **Output per run:** write a CSV `raw_price_checks_YYYYMMDD_HH.csv` with:
  - `ts_utc, sku_id, retailer, url, price, currency, in_stock, parse_version, status`
- **Load job:** append into `bpt_dbt.raw_price_checks` (partition by date). No streaming/DML (Sandbox).

## 4) Cadence & coverage
- **Priority set:** **60 PDPs** (Top‑30 × 2 retailers) every **6h** at **00:30, 06:30, 12:30, 18:30 Europe/Paris**, ±20% jitter.
- **Rest basket:** add ~240 PDPs to reach ~300 total, **daily** at **03:00**, ±20% jitter.
- **Freshness SLOs:** priority ≤ **6h**, rest ≤ **24h** (≥95% pages).

## 5) Event logic
- **Price events**: emit `price_up|price_down` when `abs(new−prev)/prev ≥ 0.01` for a given `(sku_id, retailer)`.
- **Availability events**: emit `oos|restock` on `in_stock` transitions.
- **Debounce**: if multiple samples same hour, keep last per `(sku_id, retailer, hour)`.

## 6) Normalization & category specifics
- **Haircare/Skincare**: compute `unit_price_eur_per_100` when `size_unit ∈ {ml,g}`, using `size_value` from the seed.
- **Makeup**: comparisons at **variant** level; keep `unit_price_eur_per_100 = NULL` unless meaningful.

## 7) dbt models (v0.1)
- **staging**: `stg_raw_price_checks` (type coercion + basic dedupe).
- **dims**: `dim_product` (from seed), `dim_retailer` (from distict retailers).
- **facts**: `fact_price_sampled`, `fact_availability_sampled`.
- **marts**: `price_events`, `oos_hours_by_sku_daily`.

Tests:
- `not_null` on keys and critical fields.
- `unique` on `(sku_id, retailer, ts_hour)` post‑dedupe.
- `relationships` raw → dims.
- **freshness**: priority mart ≤ 6h; rest ≤ 24h.

## 8) Monitoring
- **Block rate** per domain (<2%).
- **Freshness** vs SLOs by page.
- **Unit‑price completeness** for Haircare/Skincare.
- **Row volumes** vs baseline.

## 9) Weekly “discovery assistant” (human‑in‑the‑loop)
- **Score** each priority SKU over last 7 days:
  - `price_event_rate`, `oos_hours_norm`, `price_volatility`, `parse_success`, `freshness_penalty`, `age_weeks`.
- **Propose** one swap **per category**: replace the **lowest‑scoring** SKU (guardrails: age ≥ 3 weeks, parse_success ≥ 0.95) with an **approved candidate**.
- **Approval queue**: maintain `docs/candidates.csv` (or Airtable) with mapping to ≥2 retailers; status → `ready_for_approval` → `approved`.
- **Execution**: local script opens a PR to update `dbt/seeds/sku_registry.csv` (remove 2 rows for SKU_out, add 2 rows for SKU_in).

## 10) Today’s checklist (D02)
- [ ] Commit `dbt/seeds/sku_registry.csv` from your Top‑30 CSV.
- [ ] Save `ingestion/selectors.yml` and fill **2–3 real selectors** per retailer after devtools inspection.
- [ ] Save `config/retail_coverage.yml` (auto‑filled counts) and commit.
- [ ] Add a **docs page** `docs/tracking-plan.md` (this file) and link it in MkDocs nav.
- [ ] (Optional) Create `docs/candidates.csv` header for the approval queue.

---

**Appendix A — Field definitions (seed)**  
- `sku_id` — stable ID for a product/variant in analytics.  
- `category` — Haircare | Skincare | Makeup.  
- `subcategory` — e.g., Shampoo, Serum, Mascara.  
- `brand` — brand name as displayed.  
- `product_name` — canonical product name without size/shade.  
- `size_value`/`size_unit` — numeric size and unit (ml/g).  
- `variant_id` — shade/option (Makeup) or blank.  
- `retailer` — sephora_fr | carrefour_fr | amazon_fr.  
- `product_url` — PDP URL locked to the intended variant/size.  
- `currency` — EUR.

**Appendix B — Manual quick test**  
Pick 3 rows (one per retailer), run the fetcher, and verify that **price** and **in_stock** parse correctly and that a row lands in `raw_price_checks` with `status='ok'`.
