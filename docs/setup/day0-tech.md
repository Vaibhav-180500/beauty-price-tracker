# Day 0 — Pre‑Start Setup Log (Technical)

This is the **engineer’s log**: exact commands, file paths, and root‑cause notes for future reproducibility.

## Environment
- OS: Windows 11 (Git Bash), Python 3.12 (venv)
- Warehouse: BigQuery **Sandbox**, dataset `bpt_dbt` in **EU**
- Tooling: dbt‑core 1.10 + dbt‑bigquery, requests/bs4/pandas/pydantic/pytest

---

## Repo & skeleton
```bash
git clone https://github.com/<me>/beauty-price-tracker.git
cd beauty-price-tracker
mkdir -p dbt/models/staging dbt/seeds dbt/macros dbt/snapshots analyses ingestion dashboards docs contracts synthetic .github/workflows
```

## venv + libs
```bash
python -m venv .venv
source .venv/Scripts/activate
python -V
pip install --upgrade pip
pip install "dbt-bigquery>=1.7,<2.0" requests beautifulsoup4 pandas pydantic pytest python-dotenv
```

## dbt profile (`~/.dbt/profiles.yml`)
```yaml
beauty_price_tracker:
  target: dev
  outputs:
    dev:
      type: bigquery
      method: oauth
      project: <MY_GCP_PROJECT_ID>
      dataset: bpt_dbt
      location: EU
      threads: 4
      priority: interactive
```

Auth / ADC:
```bash
gcloud auth login
gcloud config set project <MY_GCP_PROJECT_ID>
gcloud services enable bigquery.googleapis.com
gcloud auth application-default login
```

## dbt project file (repo root)
```yaml
# dbt_project.yml
name: 'beauty_price_tracker'
version: '1.0.0'
config-version: 2
profile: 'beauty_price_tracker'
model-paths: ['dbt/models']
analysis-paths: ['analyses']
seed-paths: ['dbt/seeds']
macro-paths: ['dbt/macros']
snapshot-paths: ['dbt/snapshots']
models:
  beauty_price_tracker:
    +materialized: view
```

## Smoke model
```bash
cat > dbt/models/staging/hello.sql <<'SQL'
select 1 as ok
SQL
dbt debug
dbt run --select hello
```

## Config files
```
# .env (untracked)
ENV=dev
BPT_DEFAULT_CURRENCY=EUR

# docs/sku_list.csv (header; ~30 rows target)
sku_id,brand,product_name,retailer,product_url,currency

# docs/legal-notes.md
- Respect robots.txt / ToS
- ≤ 1 request / 10–15s per retailer
- No PII; cache HTML while prototyping
```

## First commit
```bash
git add -A
git commit -m "chore: day0 setup — dbt hello model, env files, sku list, legal notes"
git push -u origin main
```

---

## Errors & fixes

### 1) `dbt_project.yml file [ERROR not found]`
- **Cause:** project file missing or not at repo root.
- **Fix:** create at root (above) or run `dbt debug --project-dir dbt`.

### 2) `bash: dbt: command not found`
- **Cause:** venv not activated in Git Bash or dbt not installed in venv.
- **Fix:** `source .venv/Scripts/activate && pip install dbt-bigquery`; fallback `python -m dbt --version`.

### 3) BigQuery auth error (`NoneType ... close`)
- **Cause:** no ADC/token yet.
- **Fix:** `gcloud auth application-default login` (after `gcloud auth login` and setting project).

### 4) Tried to execute a CSV (`command not found`)
- **Cause:** ran `docs/sku_list.csv` as a command.
- **Fix:** open/edit with `notepad`/`code`/`nano`.

### 5) Git identity unknown
- **Fix:** `git config --global user.name "Vaibhav Kumar"` and `git config --global user.email "<email>"`.

---

## DoD (Definition of Done)
- `dbt debug` passes; `hello` built in `bpt_dbt`
- `.env` present; SKU list + legal notes added
- Initial commit pushed to `main`

