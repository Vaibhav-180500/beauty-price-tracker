-- dbt/models/staging/stg_obs_latest.sql
with src as (
  select * from {{ ref('obs_latest') }}
),

typed as (
  select
    -- seed has UTC as text; cast to TIMESTAMP
    safe_cast(observed_at_utc as timestamp) as observed_at_utc,

    cast(retailer as string)     as retailer,
    cast(sku_id as string)       as sku_id,
    cast(product_url as string)  as product_url,

    safe_cast(price as float64)      as price,
    safe_cast(list_price as float64) as list_price,
    safe_cast(discount as float64)   as discount,

    -- handle “true/false/True/False/1/0”
    case
      when lower(cast(in_stock as string)) in ('true','t','1','yes','y')  then true
      when lower(cast(in_stock as string)) in ('false','f','0','no','n') then false
      else null
    end as in_stock,

    cast(currency as string) as currency
  from src
)

select * from typed
