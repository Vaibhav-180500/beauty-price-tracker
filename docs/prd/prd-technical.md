# Day 1 — Product Requirements Document (Technical)
*Version:* v1.0  •  *Date:* 2025-08-11

## 1) Context & goal
Build a governed, low‑cost pipeline to observe public PDPs, capture **price/availability**, derive **events** (price_up/down, oos/restock), and expose a small **mart** for BI—within **BigQuery Sandbox** constraints.

## 2) Retail coverage (final)
- **SKUs:** **Top‑30** across **3 categories** (10 Haircare, 10 Skincare, 10 Makeup).  
- **Retailers:** **Amazon FR, Carrefour FR, Sephora FR** → **90 priority pages**.  
- **Total pages:** target **≈300** (priority + daily basket).

**Cadence**
- **Priority (90 pages):** every **6h** at **00:30/06:30/12:30/18:30 CET/CEST**, **±20% jitter**.  
- **Rest (~210):** **daily** at **03:00**, **±20% jitter**.

**Politeness**
- Per domain: **single thread**, **1 req / 12–20s**, **timeout 10s**, **retries: 2 (2s→4s)**, clear **User‑Agent** (`BeautyPriceTracker/0.1 (contact: <email>)`), respect robots/ToS, back off on 403/429.  
- Dev: local HTML cache to avoid refetch loops.

**Load & runtime**
- **Requests/day:** `4×90 + 1×(300−90) = 570` total (~**190/domain/day**).  
- With 15s spacing: **priority run ≈ 22.5 min** (≈7.5 min/domain), **daily run ≈ 52.5 min** (≈17.5 min/domain).  
- **Total/day:** ~**2h 23m** of scraping across 5 runs (domains can run in parallel, one worker each).

## 3) Data model (v0.1)

**Raw (append‑only)** — `raw_price_checks`  
- `ts_utc TIMESTAMP`, `sku_id STRING`, `retailer STRING`, `url STRING`,  
  `price NUMERIC`, `currency STRING`, `in_stock BOOL`,  
  `parse_version STRING`, `status STRING` (`ok|parse_error|http_error`).

**Dimensions**  
- `dim_product`: `sku_id`, `brand`, `product_name`, `category` {Haircare|Skincare|Makeup}, `subcategory`, `size_value NUMERIC`, `size_unit STRING`, `variant_id STRING`, `standard_pack BOOL`.  
- `dim_retailer`: `retailer`, `domain`, `country`.  
- `dim_product_page`: `sku_id`, `retailer`, `url`, `selector_notes`.

**Facts / Marts**  
- `fact_price_sampled`: normalized snapshot of price & availability (from raw).  
- `fact_availability_sampled`: boolean series for OOS duration aggregates.  
- `price_events` (mart): `event_ts`, `sku_id`, `retailer`, `prev_price`, `new_price`, `pct_delta`, `change_type` (`price_up|price_down|oos|restock`).  
- `oos_hours_by_sku_daily` (mart).

**Category normalization**  
- Haircare/Skincare: maintain `size_value/size_unit` (ml/g), compute `unit_price_eur_per_100`.  
- Makeup: lock a specific variant (`variant_id`), unit price often N/A.

## 4) Sandbox‑compliant ingestion
- **No streaming/DML** → **batch load jobs** per run (CSV/Parquet append).  
- Partition raw by **date**; rely on **60‑day auto‑expiry**.  
- Keep raw HTML out of BQ (local/dev cache only).  
- Optional safety: set `maximum_bytes_billed: 1GB` in dbt profile.

**Per‑run steps**  
1) Fetch & parse with `requests + BeautifulSoup`; rate‑limit per domain.  
2) Write `raw_price_checks_YYYYMMDD_HH.csv`.  
3) BigQuery **load job** (append to that date’s partition).  
4) `dbt run + dbt test`; update marts.

## 5) Event logic & thresholds
- **Price events:** emit if `abs(new−prev)/prev ≥ 0.01` (1% threshold) per `(sku_id, retailer)`.  
- **Availability events:** transitions in `in_stock` (true↔false).  
- **Debounce:** if multiple fetches in the same hour, keep last per `(sku_id, retailer, hour)`.

## 6) Tests & monitoring

**dbt tests**  
- `not_null`: keys and critical fields.  
- `unique`: `(sku_id, retailer, ts_hour)` post‑dedupe.  
- `relationships`: raw → dims.  
- **Freshness** on marts (Top‑30 ≤ 6h; others ≤ 24h).

**Monitors**  
- Block rate (403/429/5xx) — **target < 2%** per domain.  
- Freshness per page — SLOs above.  
- Unit‑price completeness (Haircare/Skincare).  
- Row volumes per run vs baseline.

## 7) Success metrics (targets)
- Coverage: **≈300 pages/day**; Top‑30 refreshed **4×/day**.  
- Freshness: **Top‑30 ≤ 6h**, rest **≤ 24h** (≥95%).  
- Accuracy: **≥ 98%** parse correctness (price & availability).  
- Reliability: **≥ 90%** scheduled runs succeed.  
- Cost: remain within **Sandbox** (no billing).

## 8) Risks & mitigations
- **Blocking (Amazon):** low RPS, jitter, single‑thread/domain; if 403/429 >2% → lower cadence for that domain and/or trim priority list there.  
- **HTML drift:** selector registry, `parse_version`, weekly smoke tests.  
- **Size/variant drift:** recompute unit price when `size_value` changes; lock variants in URLs for makeup.  
- **Sandbox limits:** batch loads, partitioning, auto‑expiry; keep HTML out of BQ.

## 9) Milestones
- **W1:** PRD v1; Top‑30 list; parser spike; synthetic rows; stub dims.  
- **W2:** dbt staging/dims/facts/marts; schema tests; first events.  
- **W3:** Dashboard v1 (KPIs, changes table, OOS hours); monitoring queries.  
- **W4:** SLO review; runbook; demo.

## 10) Acceptance criteria
- **Given** a Top‑30 SKU with price ↑ **≥1%**, **when** the next 6‑hour run completes, **then** `price_events` has a `price_up` row with `pct_delta` and correct prev/new values.  
- **Given** a SKU flips to OOS, **then** an `oos` event is produced within its cadence window (≤6h Top‑30; ≤24h others) and contributes to `oos_hours_by_sku_daily`.  
- **Given** a fetch/parse failure, **then** a raw row with `status∈{http_error,parse_error}` is logged and the run still succeeds.
