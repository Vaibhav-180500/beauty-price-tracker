-- stg_obs_latest.sql
-- Normalize types and column names coming from the obs_latest seed.

with src as (
  select
    retailer,
    product_url,
    safe_cast(http_status as int64)                     as http_status,
    safe_cast(price  as numeric)                   as price,
    safe_cast(list_price as numeric)                   as list_price,   -- backticks: list is a reserved word
    safe_cast(discount_pct   as numeric)                   as discount_pct,     -- source column is 'disc'
    safe_cast(in_stock as bool)                    as in_stock,
    safe_cast(sku_id as string)               as sku_id,
    -- ISO8601 string -> TIMESTAMP (UTC)
    cast(observed_at_utc as timestamp)   as observed_at_utc
  from {{ ref('obs_latest') }}
)

select
  retailer,
  product_url,
  http_status,
  price,
  list_price,
  discount_pct,
  in_stock,
  sku_id,
  observed_at_utc
from src
