-- Keep superseded parser interpretations for evidence/history without letting
-- them remain visible as current vehicles. This is required when a newer
-- parser correctly changes cloned multi-plate rows into one inseparable lot.

alter table vehicles
  add column if not exists projection_active boolean not null default true,
  add column if not exists projection_retired_at timestamptz,
  add column if not exists projection_retired_reason text;

alter table vehicle_identifiers
  add column if not exists projection_active boolean not null default true;

create unique index if not exists sources_adapter_name_uidx
  on sources (adapter_name);

create index if not exists vehicles_current_lot_idx
  on vehicles (lot_id, id)
  where projection_active;

create index if not exists vehicle_identifiers_current_vehicle_idx
  on vehicle_identifiers (vehicle_id,identifier_type,id)
  where projection_active;

comment on column vehicles.projection_active is
  'Current marketplace interpretation. False retains history while excluding a superseded vehicle projection.';

create or replace view vehicle_marketplace_listing with (security_invoker = true) as
select v.id, v.id as vehicle_id, 'vehicle'::text as listing_entity,
       s.id as source_id, s.name as source_name, s.family as source_family, s.adapter_name as source_adapter,
       sr.id as source_record_id, sr.source_record_id as source_auid,
       sr.official_url, sr.original_title as official_title,
       coalesce(vm.canonical_name, v.original_model, l.title) as model_name,
       coalesce(vb.canonical_name, v.original_brand) as brand_name,
       v.manufacture_year, v.manufacture_month, v.displacement_cc, v.vehicle_type,
       v.vehicle_category, v.car_category, v.color, v.mileage_km,
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
         o.canonical_name, l.storage_location, sr.source_record_id, v.vehicle_type,
         v.vehicle_category, v.car_category)) as search_text
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
  where vehicle_id = v.id and identifier_type = 'PLATE' and projection_active
  order by id limit 1
) plate on true
where v.projection_active
union all
select l.id, null::uuid, 'lot'::text,
       s.id, s.name, s.family, s.adapter_name,
       sr.id, sr.source_record_id, sr.official_url, sr.original_title,
       l.title, null::text, null::integer, null::integer, null::integer,
       l.vehicle_type, l.vehicle_category, l.car_category, null::text, null::integer,
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
         l.storage_location, sr.source_record_id, l.vehicle_type,
         l.vehicle_category, l.car_category))
from lots l
join auction_events ae on ae.id = l.auction_event_id
join auction_cases ac on ac.id = ae.auction_case_id
join source_records sr on sr.id = ae.source_record_id
join sources s on s.id = sr.source_id
left join organizations o on o.id = ac.organization_id
left join lateral (
  select source_url, storage_path from photos where lot_id = l.id and storage_path is not null order by sort_order limit 1
) p on true
where not exists (
  select 1 from vehicles v where v.lot_id = l.id and v.projection_active
);

grant select on vehicle_marketplace_listing to authenticated;
comment on view vehicle_marketplace_listing is
  'Owner-only current car-and-motorcycle marketplace; superseded vehicle interpretations remain in history but are not presented as current facts.';

create or replace view motorcycle_listing with (security_invoker = true) as
select v.id, sr.id as source_record_id, sr.source_record_id as source_auid,
       sr.official_url, sr.original_title as official_title,
       coalesce(vm.canonical_name, v.original_model, l.title) as model_name,
       coalesce(vb.canonical_name, v.original_brand) as brand_name,
       v.manufacture_year, v.displacement_cc, v.color, v.mileage_km,
       o.canonical_name as organization_name, l.storage_location,
       ac.disposal_origin, ae.status as auction_status, ae.round_number,
       ae.ends_at as auction_at, ae.reserve_price, ae.current_price, ae.sold_price,
       ae.deposit, ae.payment_deadline, ae.pickup_deadline, l.fee_notes,
       l.eligibility, v.registration_status, v.has_key, v.can_start, v.can_test,
       l.lot_size, l.bulk_lot, v.condition_summary, v.completeness,
       v.completeness_groups,
       p.source_url as primary_image_url,
       coalesce((
         select normalized_value from vehicle_identifiers vi
         where vi.vehicle_id=v.id and vi.identifier_type='PLATE' and vi.projection_active
         order by vi.id limit 1
       ), null) as plate_number
from vehicles v
join lots l on l.id = v.lot_id
join auction_events ae on ae.id = l.auction_event_id
join auction_cases ac on ac.id = ae.auction_case_id
join source_records sr on sr.id = ae.source_record_id
left join organizations o on o.id = ac.organization_id
left join vehicle_brands vb on vb.id = v.brand_id
left join vehicle_models vm on vm.id = v.model_id
left join lateral (
  select source_url from photos where vehicle_id=v.id order by sort_order limit 1
) p on true
where v.projection_active;

grant select on motorcycle_listing to authenticated;
comment on view motorcycle_listing is
  'Legacy owner-only motorcycle read model restricted to the current vehicle and identifier projection.';
