-- Production marketplace query support. The read model exposes deterministic
-- sort/filter columns so pagination never has to filter a page in application
-- memory after the database has already applied its limit.

create or replace function taiwan_county_from_text(input_text text)
returns text
language sql
immutable
parallel safe
as $$
  select (regexp_match(
    coalesce(input_text, ''),
    '(臺北市|新北市|桃園市|臺中市|臺南市|高雄市|基隆市|新竹市|嘉義市|新竹縣|苗栗縣|彰化縣|南投縣|雲林縣|嘉義縣|屏東縣|宜蘭縣|花蓮縣|臺東縣|澎湖縣|金門縣|連江縣)'
  ))[1];
$$;

drop view if exists motorcycle_marketplace_listing;

create view motorcycle_marketplace_listing with (security_invoker = true) as
select v.id, v.id as vehicle_id, 'vehicle'::text as listing_entity,
       s.id as source_id, s.name as source_name, s.family as source_family, s.adapter_name as source_adapter,
       sr.id as source_record_id, sr.source_record_id as source_auid,
       sr.official_url, sr.original_title as official_title,
       coalesce(vm.canonical_name, v.original_model, l.title) as model_name,
       coalesce(vb.canonical_name, v.original_brand) as brand_name,
       v.manufacture_year, v.manufacture_month, v.displacement_cc, v.color, v.mileage_km,
       o.canonical_name as organization_name, l.storage_location,
       ac.disposal_origin, ae.status as auction_status, ae.round_number,
       ae.ends_at as auction_at, ae.reserve_price, ae.current_price, ae.sold_price,
       ae.deposit, ae.payment_deadline, ae.pickup_deadline, l.fee_notes,
       l.eligibility, v.registration_status, v.has_key, v.can_start, v.can_test,
       l.lot_size, l.bulk_lot, v.condition_summary, v.completeness,
       v.completeness_groups, p.source_url as primary_image_url,
       plate.normalized_value as plate_number,
       taiwan_county_from_text(concat_ws(' ', l.storage_location, o.canonical_name)) as county,
       coalesce(ae.sold_price, ae.current_price, ae.reserve_price) as display_price,
       (p.storage_path is not null) as has_cached_photo,
       lower(concat_ws(' ', sr.original_title, coalesce(vb.canonical_name, v.original_brand),
         coalesce(vm.canonical_name, v.original_model, l.title), plate.normalized_value,
         o.canonical_name, l.storage_location, sr.source_record_id)) as search_text
from vehicles v
join lots l on l.id = v.lot_id
join auction_events ae on ae.id = l.auction_event_id
join auction_cases ac on ac.id = ae.auction_case_id
join source_records sr on sr.id = ae.source_record_id
join sources s on s.id = sr.source_id
left join organizations o on o.id = ac.organization_id
left join vehicle_brands vb on vb.id = v.brand_id
left join vehicle_models vm on vm.id = v.model_id
left join lateral (
  select source_url, storage_path from photos where vehicle_id = v.id and storage_path is not null order by sort_order limit 1
) p on true
left join lateral (
  select normalized_value from vehicle_identifiers
  where vehicle_id = v.id and identifier_type = 'PLATE' order by id limit 1
) plate on true
union all
select l.id, null::uuid, 'lot'::text,
       s.id, s.name, s.family, s.adapter_name,
       sr.id, sr.source_record_id, sr.official_url, sr.original_title,
       l.title, null::text, null::integer, null::integer, null::integer, null::text, null::integer,
       o.canonical_name, l.storage_location,
       ac.disposal_origin, ae.status, ae.round_number,
       ae.ends_at, ae.reserve_price, ae.current_price, ae.sold_price,
       ae.deposit, ae.payment_deadline, ae.pickup_deadline, l.fee_notes,
       l.eligibility, l.registration_status, l.has_key, l.can_start, l.can_test,
       l.lot_size, l.bulk_lot, l.condition_summary, l.completeness,
       l.completeness_groups, p.source_url, null::text,
       taiwan_county_from_text(concat_ws(' ', l.storage_location, o.canonical_name)),
       coalesce(ae.sold_price, ae.current_price, ae.reserve_price),
       (p.storage_path is not null),
       lower(concat_ws(' ', sr.original_title, l.title, o.canonical_name,
         l.storage_location, sr.source_record_id))
from lots l
join auction_events ae on ae.id = l.auction_event_id
join auction_cases ac on ac.id = ae.auction_case_id
join source_records sr on sr.id = ae.source_record_id
join sources s on s.id = sr.source_id
left join organizations o on o.id = ac.organization_id
left join lateral (
  select source_url, storage_path from photos where lot_id = l.id and storage_path is not null order by sort_order limit 1
) p on true
where not exists (select 1 from vehicles v where v.lot_id = l.id);

grant select on motorcycle_marketplace_listing to authenticated;
comment on view motorcycle_marketplace_listing is
  'Owner-only marketplace read model with normalized county, cached-media, search, and stable sort columns.';

create index if not exists auction_events_marketplace_deadline_idx
  on auction_events (ends_at, id);
create index if not exists auction_events_marketplace_price_idx
  on auction_events ((coalesce(sold_price, current_price, reserve_price)), id);
create index if not exists vehicles_marketplace_completeness_idx
  on vehicles (completeness desc, id);
create index if not exists lots_marketplace_completeness_idx
  on lots (completeness desc, id);
create index if not exists photos_vehicle_storage_sort_idx
  on photos (vehicle_id, sort_order) where storage_path is not null;
create index if not exists photos_lot_storage_sort_idx
  on photos (lot_id, sort_order) where storage_path is not null;
