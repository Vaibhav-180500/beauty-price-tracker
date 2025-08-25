{{ config(
  materialized='incremental',
  unique_key=['retailer','product_url','observed_at_utc']
) }}

SELECT
  retailer,
  product_url,
  http_status,
  price,
  list_price,
  discount_pct,
  in_stock,
  observed_at_utc
FROM {{ ref('stg_obs_latest') }}

{% if is_incremental() %}
-- only new rows since last run
WHERE observed_at_utc > (
  SELECT IFNULL(MAX(observed_at_utc), TIMESTAMP('1970-01-01'))
  FROM {{ this }}
)
{% endif %}
