{{ config(materialized='view') }}
-- latest price per (retailer, product_url)
with ranked as (
  select
    retailer,
    product_url,
    http_status,
    price,
    list_price,
    discount_pct,
    in_stock,
    observed_at_utc,
    row_number() over (
      partition by retailer, product_url
      order by observed_at_utc desc
    ) as rn
  from {{ ref('stg_obs_latest') }}
)
select
  retailer,
  product_url,
  http_status,
  price,
  list_price,
  discount_pct,
  in_stock,
  observed_at_utc as last_seen_at_utc
from ranked
where rn = 1;
