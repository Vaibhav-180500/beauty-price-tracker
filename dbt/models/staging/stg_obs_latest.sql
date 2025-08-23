{{ config(materialized="view") }}

with src as (
  select * from {{ ref('obs_latest') }}
)

select
  -- timestamps (works if the seed wrote ISO8601; SAFE keeps nulls if not parsable)
  safe.timestamp(observed_at)           as observed_at,

  -- ids / descriptors
  cast(retailer as string)              as retailer,
  cast(sku_id as string)                as sku_id,
  cast(brand as string)                 as brand,
  cast(product_name as string)          as product_name,
  cast(category as string)              as category,
  cast(subcategory as string)           as subcategory,
  cast(variant_id as string)            as variant_id,
  cast(currency as string)              as currency,
  cast(product_url as string)           as product_url,

  -- sizing
  safe_cast(size_value as float64)      as size_value,
  cast(size_unit as string)             as size_unit,

  -- pricing
  safe_cast(price as numeric)           as price,
  safe_cast(list_price as numeric)      as list_price,
  safe_cast(discount as numeric)        as discount,

  -- stock: accept “true/false/1/0/yes/no”
  case
    when lower(cast(in_stock as string)) in ("true","1","yes") then true
    when lower(cast(in_stock as string)) in ("false","0","no") then false
    else null
  end                                    as in_stock
from src
