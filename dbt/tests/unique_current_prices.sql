-- Fail if any (retailer, product_url) appears more than once
WITH t AS (
  SELECT retailer, product_url, COUNT(*) c
  FROM {{ ref('current_prices') }}
  GROUP BY 1,2
)
SELECT * FROM t WHERE c > 1
