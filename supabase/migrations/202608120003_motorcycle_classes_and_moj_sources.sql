-- Explicit motorcycle classes and product-level scrap separation. Classification
-- is based on official wording; displacement alone never changes UNKNOWN.

alter table lots add column if not exists vehicle_category text not null default 'UNKNOWN';

update vehicles
set vehicle_category = case
  when vehicle_category in ('普通輕型機車','ORDINARY_LIGHT') then 'ORDINARY_LIGHT'
  when vehicle_category in ('普通重型機車','ORDINARY_HEAVY') then 'ORDINARY_HEAVY'
  when vehicle_category in ('大型重型機車','LARGE_HEAVY') then 'LARGE_HEAVY'
  when vehicle_category in ('電動機車','普通重型電動機車','ELECTRIC_MOTORCYCLE') then 'ELECTRIC_MOTORCYCLE'
  when vehicle_category in ('重型機車','HEAVY_UNSPECIFIED') then 'HEAVY_UNSPECIFIED'
  else 'UNKNOWN'
end;

alter table vehicles alter column vehicle_category set default 'UNKNOWN';
alter table vehicles alter column vehicle_category set not null;
alter table vehicles add constraint vehicles_motorcycle_class_chk check (
  vehicle_category in ('ORDINARY_LIGHT','ORDINARY_HEAVY','LARGE_HEAVY','ELECTRIC_MOTORCYCLE','HEAVY_UNSPECIFIED','UNKNOWN')
);
alter table lots add constraint lots_motorcycle_class_chk check (
  vehicle_category in ('ORDINARY_LIGHT','ORDINARY_HEAVY','LARGE_HEAVY','ELECTRIC_MOTORCYCLE','HEAVY_UNSPECIFIED','UNKNOWN')
);

update sources set name='法務部查扣物集中拍賣', adapter_name='moj_auction', status='PARTIAL',
  automation_level='PUBLIC_READ_ONLY', official_url='https://auction.moj.gov.tw/1724/1726/searchList', parser_version='1.3.0'
where id='20000000-0000-0000-0000-000000000005';
update sources set name='行政執行署動產拍賣', adapter_name='moj_enforcement', status='PARTIAL',
  automation_level='CAPTCHA_SAFE_MANUAL', official_url='https://www.tpkonsale.moj.gov.tw/Chattel', parser_version='1.3.0'
where id='20000000-0000-0000-0000-000000000003';

insert into source_endpoints (source_id,endpoint_type,url,notes)
select values_to_insert.source_id::uuid, values_to_insert.endpoint_type, values_to_insert.url, values_to_insert.notes
from (values
  ('20000000-0000-0000-0000-000000000005','DISCOVERY','https://auction.moj.gov.tw/1724/1726/searchList','法務部查扣物汽機車類公開清單'),
  ('20000000-0000-0000-0000-000000000005','DETAIL','https://auction.moj.gov.tw/1724/1726/','法務部查扣物公告與附件'),
  ('20000000-0000-0000-0000-000000000003','DISCOVERY','https://www.tpkonsale.moj.gov.tw/Chattel','需由人完成官方 CAPTCHA；系統不自動送出搜尋'),
  ('20000000-0000-0000-0000-000000000003','DETAIL','https://www.tpkonsale.moj.gov.tw/Detail/Chattel','人工匯出官方明細 URL 後的唯讀擷取')
) as values_to_insert(source_id, endpoint_type, url, notes)
join sources on sources.id = values_to_insert.source_id::uuid
on conflict do nothing;

drop view if exists motorcycle_marketplace_listing;

create view motorcycle_marketplace_listing with (security_invoker = true) as
select v.id, v.id as vehicle_id, 'vehicle'::text as listing_entity,
       s.id as source_id, s.name as source_name, s.family as source_family, s.adapter_name as source_adapter,
       sr.id as source_record_id, sr.source_record_id as source_auid,
       sr.official_url, sr.original_title as official_title,
       coalesce(vm.canonical_name, v.original_model, l.title) as model_name,
       coalesce(vb.canonical_name, v.original_brand) as brand_name,
       v.manufacture_year, v.manufacture_month, v.displacement_cc, v.vehicle_category, v.color, v.mileage_km,
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
         o.canonical_name, l.storage_location, sr.source_record_id, v.vehicle_category)) as search_text
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
       l.title, null::text, null::integer, null::integer, null::integer, l.vehicle_category, null::text, null::integer,
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
         l.storage_location, sr.source_record_id, l.vehicle_category))
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
  'Owner-only marketplace read model with explicit motorcycle class and product-level scrap separation support.';

create index if not exists vehicles_motorcycle_class_idx on vehicles (vehicle_category);
create index if not exists lots_motorcycle_class_idx on lots (vehicle_category);
