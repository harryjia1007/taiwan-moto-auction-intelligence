begin;
create extension if not exists pgtap;
select plan(56);

select has_table('public', 'raw_artifacts', 'raw artifacts exist');
select has_table('public', 'field_evidence', 'field evidence exists');
select has_table('public', 'probable_duplicates', 'probable duplicates exist');
select has_table('public', 'source_access_policies', 'source authorization registry exists');
select has_table('public', 'artifact_tombstones', 'artifact deletion audit exists');
select has_table('public', 'data_subject_requests', 'correction and deletion request ledger exists');
select has_trigger('public', 'artifact_tombstones', 'artifact_tombstones_immutable', 'artifact deletion audit is append-only');
select has_view('public', 'motorcycle_listing', 'motorcycle read model exists');
select has_view('public', 'motorcycle_marketplace_listing', 'multi-source and bulk-lot read model exists');
select has_view('public', 'vehicle_marketplace_listing', 'car-and-motorcycle read model exists');
select has_column('public', 'vehicle_marketplace_listing', 'vehicle_type', 'vehicle marketplace exposes explicit vehicle type');
select has_column('public', 'vehicle_marketplace_listing', 'car_category', 'vehicle marketplace exposes explicit car category');
select has_function('public', 'taiwan_county_from_text', array['text'], 'county normalization is deterministic in the database');
select is(taiwan_county_from_text('臺灣臺中地方法院'), '臺中市', 'county normalization works for court organization names');
select is(taiwan_county_from_text('新竹縣竹北市 臺灣新竹地方法院'), '新竹縣', 'an explicit storage county wins over a court-name fallback');
select is(taiwan_county_from_text('臺灣士林地方法院'), '臺北市', 'special court names map to their administrative area');
select is(taiwan_county_from_text('臺灣橋頭地方法院'), '高雄市', 'cross-named courts map to their administrative area');
select has_column('public', 'motorcycle_marketplace_listing', 'county', 'marketplace exposes normalized county');
select has_column('public', 'motorcycle_marketplace_listing', 'display_price', 'marketplace exposes one deterministic sort price');
select has_column('public', 'motorcycle_marketplace_listing', 'has_cached_photo', 'marketplace distinguishes cached photos from remote URLs');
select has_column('public', 'motorcycle_marketplace_listing', 'search_text', 'marketplace exposes normalized multi-field search text');
select has_column('public', 'motorcycle_marketplace_listing', 'vehicle_category', 'marketplace exposes explicit motorcycle class');
select has_view('public', 'resolved_field_evidence', 'explicit evidence precedence view exists');
select has_index('public', 'source_records', 'source_records_search_vector_idx', 'normalized full-text index exists');
select has_index('public', 'documents', 'documents_source_artifact_uidx', 'official documents are idempotent per source artifact');
select has_index('public', 'auction_events', 'auction_events_marketplace_deadline_idx', 'deadline pagination has a stable database index');
select has_column('public', 'raw_artifacts', 'retention_until', 'private artifact retention deadline is stored');
select col_not_null('public', 'raw_artifacts', 'retention_until', 'every artifact has a retention deadline');
select has_index('public', 'vehicles', 'vehicles_displacement_cc_idx', 'CC band filtering has a B-tree index');
select ok(exists(select 1 from pg_constraint where conname = 'photos_exactly_one_owner_chk'), 'photos belong to exactly one listing entity');
select ok(exists(select 1 from pg_constraint where conname = 'photos_nonnegative_sort_order_chk'), 'photo order cannot be negative');
select col_type_is('public', 'vehicles', 'can_start', 'four_state', 'four-state facts are typed');
select col_type_is('public', 'vehicles', 'registration_status', 'registration_status', 'registration status is typed');
select is((select vehicle_category from vehicles where id = '53000000-0000-0000-0000-000000000001'), 'ORDINARY_HEAVY', 'legacy official class text is normalized without displacement inference');
select is((select count(*) from sources where adapter_name='police' and status <> 'PLANNED'), 0::bigint, 'unimplemented police source never claims active coverage');
select is((select status::text from sources where adapter_name='judicial'), 'PARTIAL', 'Judicial source is honest about human-reviewed manifest coverage');
select is((select status::text from sources where adapter_name='pcc'), 'PARTIAL', 'PCC awaits its first successful official open-data run');
select is((select decision from source_access_policies where source_id='20000000-0000-0000-0000-000000000002'), 'MANUAL_ONLY', 'Judicial access policy requires a human-reviewed official manifest');
select is((select decision from source_access_policies where source_id='20000000-0000-0000-0000-000000000004'), 'ALLOW', 'PCC official machine-readable dataset is approved');
select is((select status::text from sources where adapter_name='customs'), 'PARTIAL', 'Customs awaits its first successful four-office run');
select is((select decision from source_access_policies where source_id='20000000-0000-0000-0000-000000000007'), 'ALLOW', 'Customs HTML access is approved while restricted downloads remain excluded');
select is((select status::text from sources where adapter_name='moj_enforcement_cms'), 'PARTIAL', 'Administrative Enforcement branch CMS awaits an all-branch run');
select is((select decision from source_access_policies where source_id='20000000-0000-0000-0000-000000000008'), 'ALLOW', 'Administrative Enforcement CMS access is limited to reviewed branch hosts');
select ok(not has_table_privilege('anon', 'public.sources', 'select'), 'anonymous role cannot read formal source tables');
select is((select public from storage.buckets where id='raw-artifacts'), false, 'raw artifact storage is private');
select is((select count(*) from sources where adapter_name in ('moj_auction','moj_enforcement','moj_enforcement_cms') and status not in ('PARTIAL','ACTIVE','DEGRADED')), 0::bigint, 'implemented MOJ sources expose only runtime-ready health states');
select is((select count(*) from motorcycle_listing where source_auid = 'SYNTH-SHWOO-01'), 1::bigint, 'seed exposes exactly one synthetic development listing');
select is((select can_start::text from vehicles where id = '53000000-0000-0000-0000-000000000001'), 'NO', 'explicit unable-to-start fact is negative');
select is((select has_key::text from vehicles where id = '53000000-0000-0000-0000-000000000001'), 'UNKNOWN', 'missing key fact remains unknown');
select is((select count(*) from field_evidence where source_record_id = '40000000-0000-0000-0000-000000000001' and parser_version = '1.0.0' and trust = 'OFFICIAL_EXPLICIT'), 3::bigint, 'important seed facts retain evidence');
select is((select count(*) from organizations where organization_type = 'DISTRICT_COURT'), 22::bigint, 'all district courts are seeded');
select is(
  (
    select count(*)
    from public_live_motorcycle_listings
    where plate_number is not null
      and (ends_at is null or ends_at < now() - interval '30 days')
  ),
  0::bigint,
  'unknown or expired public plate projections are cleared without deleting private history'
);
select is(
  (select count(*) from public_live_motorcycle_listings where photo_urls <> '[]'::jsonb),
  0::bigint,
  'anonymous projection has no photos without an explicit public-image right'
);
select is(
  (
    select count(*)
    from public_live_motorcycle_listings as listing
    where concat_ws(
      ' ', listing.source_record_id, listing.source_name, listing.official_url,
      listing.official_title, listing.official_case_number, listing.organization_name,
      listing.brand_name, listing.model_name, listing.color, listing.location,
      listing.description, listing.condition_summary, array_to_string(listing.fee_notes, ' ')
    ) ~* '([A-Z][12][0-9]{8}|[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}|09[0-9]{2}[-－ ]?[0-9]{3}[-－ ]?[0-9]{3})'
  ),
  0::bigint,
  'anonymous public text contains no Taiwan ID, email or mobile number'
);
select is(
  (
    select count(*)
    from public_live_motorcycle_listings as listing
    where concat_ws(
      ' ', listing.source_name, listing.official_title, listing.official_case_number,
      listing.organization_name, listing.brand_name, listing.model_name, listing.color,
      listing.location, listing.description, listing.condition_summary,
      array_to_string(listing.fee_notes, ' ')
    ) ~ '(義務人|債務人|所有人|車主|被告|受刑人|保管人|姓名)[[:space:]]*[:：]?[[:space:]]*(?!已隱去)[一-龥○ＯO·．・]{2,6}'
  ),
  0::bigint,
  'anonymous public text contains no unredacted role-labelled name'
);
select is(
  (
    select count(*)
    from public_live_motorcycle_listings as listing
    cross join lateral jsonb_array_elements(listing.documents) as entry(document)
    where entry.document ->> 'url' ~* '([A-Z][12][0-9]{8}|[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}|09[0-9]{2}[-－ ]?[0-9]{3}[-－ ]?[0-9]{3})'
      or lower(entry.document ->> 'url') ~ '(%e7%be%a9%e5%8b%99%e4%ba%ba|%e5%82%b5%e5%8b%99%e4%ba%ba|%e6%89%80%e6%9c%89%e4%ba%ba|%e8%bb%8a%e4%b8%bb|%e8%a2%ab%e5%91%8a|%e5%8f%97%e5%88%91%e4%ba%ba|%e4%bf%9d%e7%ae%a1%e4%ba%ba|%e5%a7%93%e5%90%8d)'
  ),
  0::bigint,
  'anonymous document links contain no direct or encoded personal data'
);

select * from finish();
rollback;
