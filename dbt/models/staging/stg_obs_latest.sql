-- stg_obs_latest.sql
-- Normalize types and column names coming from the obs_latest seed.

with src as (
  select
    retailer,
    product_url,
    safe_cast(status as int64)                     as http_status,
    safe_cast(price  as numeric)                   as price,
    safe_cast(`list` as numeric)                   as list_price,   -- backticks: list is a reserved word
    safe_cast(disc   as numeric)                   as discount,     -- source column is 'disc'
    safe_cast(in_stock as bool)                    as in_stock,
    -- ISO8601 string -> TIMESTAMP (UTC)
    safe.parse_timestamp('%Y-%m-%dT%H:%M:%S%z', observed_at_utc) as observed_at_utc
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
  observed_at_utc
from src
