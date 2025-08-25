{{ config(materialized='view') }}

WITH ordered AS (
  SELECT
    retailer,
    product_url,
    observed_at_utc,
    price,
    list_price,
    LAG(price)      OVER (PARTITION BY retailer, product_url ORDER BY observed_at_utc) AS prev_price,
    LAG(list_price) OVER (PARTITION BY retailer, product_url ORDER BY observed_at_utc) AS prev_list_price
  FROM {{ ref('price_history') }}
),
deltas AS (
  SELECT
    retailer,
    product_url,
    observed_at_utc,
    price,
    prev_price,
    SAFE_DIVIDE(price - prev_price, NULLIF(prev_price,0)) AS price_change_pct,
    CASE 
      WHEN prev_price IS NULL THEN NULL
      WHEN price > prev_price   THEN 'up'
      WHEN price < prev_price   THEN 'down'
      ELSE 'flat'
    END AS price_direction
  FROM ordered
)
SELECT * FROM deltas
WHERE prev_price IS NOT NULL
ORDER BY observed_at_utc DESC
