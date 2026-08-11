-- Multi-source marketplace read model. Bulk lots remain lots when the official
-- notice does not provide separable vehicle identities; no vehicle is invented.
alter table lots add column if not exists registration_status registration_status not null default 'UNKNOWN';
alter table lots add column if not exists has_key four_state not null default 'UNKNOWN';
alter table lots add column if not exists can_start four_state not null default 'UNKNOWN';
alter table lots add column if not exists can_test four_state not null default 'UNKNOWN';
alter table lots add column if not exists condition_summary text;
alter table lots add column if not exists completeness smallint not null default 0 check (completeness between 0 and 100);
alter table lots add column if not exists completeness_groups jsonb not null default '{}'::jsonb;

create or replace view motorcycle_marketplace_listing with (security_invoker = true) as
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
       (select normalized_value from vehicle_identifiers vi where vi.vehicle_id=v.id and vi.identifier_type='PLATE' limit 1) as plate_number
from vehicles v
join lots l on l.id = v.lot_id
join auction_events ae on ae.id = l.auction_event_id
join auction_cases ac on ac.id = ae.auction_case_id
join source_records sr on sr.id = ae.source_record_id
join sources s on s.id = sr.source_id
left join organizations o on o.id = ac.organization_id
left join vehicle_brands vb on vb.id = v.brand_id
left join vehicle_models vm on vm.id = v.model_id
left join lateral (select source_url from photos where vehicle_id=v.id order by sort_order limit 1) p on true
union all
select l.id, null::uuid as vehicle_id, 'lot'::text as listing_entity,
       s.id, s.name, s.family, s.adapter_name,
       sr.id, sr.source_record_id, sr.official_url, sr.original_title,
       l.title, null::text, null::integer, null::integer, null::integer, null::text, null::integer,
       o.canonical_name, l.storage_location,
       ac.disposal_origin, ae.status, ae.round_number,
       ae.ends_at, ae.reserve_price, ae.current_price, ae.sold_price,
       ae.deposit, ae.payment_deadline, ae.pickup_deadline, l.fee_notes,
       l.eligibility, l.registration_status, l.has_key, l.can_start, l.can_test,
       l.lot_size, l.bulk_lot, l.condition_summary, l.completeness,
       l.completeness_groups, p.source_url, null::text
from lots l
join auction_events ae on ae.id = l.auction_event_id
join auction_cases ac on ac.id = ae.auction_case_id
join source_records sr on sr.id = ae.source_record_id
join sources s on s.id = sr.source_id
left join organizations o on o.id = ac.organization_id
left join lateral (select source_url from photos where lot_id=l.id order by sort_order limit 1) p on true
where not exists (select 1 from vehicles v where v.lot_id = l.id);

grant select on motorcycle_marketplace_listing to authenticated;
comment on view motorcycle_marketplace_listing is 'Owner-only vehicle and inseparable motorcycle-lot marketplace read model with source coverage metadata.';

create unique index if not exists documents_source_artifact_uidx on documents (source_record_id, artifact_id);
