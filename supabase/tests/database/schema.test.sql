begin;
create extension if not exists pgtap;
select plan(200);

select has_table('public', 'raw_artifacts', 'raw artifacts exist');
select has_table('public', 'field_evidence', 'field evidence exists');
select has_table('public', 'probable_duplicates', 'probable duplicates exist');
select has_table('public', 'source_access_policies', 'source authorization registry exists');
select has_table('public', 'artifact_tombstones', 'artifact deletion audit exists');
select has_table('public', 'data_subject_requests', 'correction and deletion request ledger exists');
select has_table('public', 'public_source_health', 'sanitized public source health projection exists');
select ok(
  exists(
    select 1
    from pg_type as type
    join pg_namespace as namespace on namespace.oid = type.typnamespace
    where namespace.nspname = 'public'
      and type.typname = 'public_source_warning'
  ),
  'public source warning enum exists'
);
select is(
  (
    select array_agg(value.enumlabel order by value.enumsortorder)::text[]
    from pg_type as type
    join pg_namespace as namespace on namespace.oid = type.typnamespace
    join pg_enum as value on value.enumtypid = type.oid
    where namespace.nspname = 'public'
      and type.typname = 'public_source_warning'
  ),
  array[
    'ZERO_DISCOVERY',
    'RUN_FAILED',
    'PARSE_BELOW_90',
    'POLICY_BLOCKED',
    'PARTIAL_COVERAGE'
  ]::text[],
  'anonymous warning vocabulary is a closed reviewed set'
);
select columns_are(
  'public',
  'public_source_health',
  array[
    'source_adapter',
    'source_name',
    'status',
    'last_run_status',
    'last_attempted_at',
    'last_successful_at',
    'discovered_count',
    'fetched_count',
    'parsed_count',
    'changed_count',
    'failed_count',
    'parse_success_rate',
    'warning_codes',
    'stale_after_hours',
    'updated_at'
  ],
  'public health exposes only the reviewed metrics contract'
);
select col_type_is('public', 'public_source_health', 'status', 'adapter_status', 'public health uses the shared adapter status enum');
select col_type_is('public', 'public_source_health', 'warning_codes', 'public_source_warning[]', 'public warnings use the closed enum array');
select col_not_null('public', 'public_source_health', 'warning_codes', 'warning codes cannot be null');
select ok(
  (
    select relation.relrowsecurity
    from pg_class as relation
    join pg_namespace as namespace on namespace.oid = relation.relnamespace
    where namespace.nspname = 'public'
      and relation.relname = 'public_source_health'
  ),
  'row level security is enabled on public source health'
);
select ok(has_table_privilege('anon', 'public.public_source_health', 'select'), 'anonymous clients may read sanitized source health');
select ok(not has_table_privilege('anon', 'public.public_source_health', 'insert'), 'anonymous clients cannot insert source health');
select ok(not has_table_privilege('anon', 'public.public_source_health', 'update'), 'anonymous clients cannot update source health');
select ok(not has_table_privilege('anon', 'public.public_source_health', 'delete'), 'anonymous clients cannot delete source health');
select ok(not has_table_privilege('anon', 'public.public_source_health', 'truncate'), 'anonymous clients cannot truncate source health');
select ok(has_table_privilege('authenticated', 'public.public_source_health', 'select'), 'authenticated clients may read sanitized source health');
select ok(not has_table_privilege('authenticated', 'public.public_source_health', 'insert'), 'authenticated clients cannot insert source health');
select ok(not has_table_privilege('authenticated', 'public.public_source_health', 'update'), 'authenticated clients cannot update source health');
select ok(not has_table_privilege('authenticated', 'public.public_source_health', 'delete'), 'authenticated clients cannot delete source health');
select ok(not has_table_privilege('authenticated', 'public.public_source_health', 'truncate'), 'authenticated clients cannot truncate source health');
select ok(has_table_privilege('service_role', 'public.public_source_health', 'select'), 'service role may read source health for upserts');
select ok(has_table_privilege('service_role', 'public.public_source_health', 'insert'), 'service role may insert source health');
select ok(has_table_privilege('service_role', 'public.public_source_health', 'update'), 'service role may update source health');
select ok(not has_table_privilege('service_role', 'public.public_source_health', 'delete'), 'service role cannot erase source health rows');
select ok(not has_table_privilege('service_role', 'public.public_source_health', 'truncate'), 'service role cannot truncate source health');
select ok(not has_table_privilege('service_role', 'public.public_source_health', 'references'), 'service role cannot create references to source health');
select ok(not has_table_privilege('service_role', 'public.public_source_health', 'trigger'), 'service role cannot create source health triggers');
select ok(has_schema_privilege('service_role', 'public', 'usage'), 'hosted publisher can resolve reviewed public-schema objects');
select ok(not has_schema_privilege('service_role', 'public', 'create'), 'hosted publisher cannot create public-schema objects');
select ok(
  not exists (
    select 1
    from pg_class as relation
    join pg_namespace as namespace on namespace.oid = relation.relnamespace
    where namespace.nspname = 'public'
      and relation.relkind in ('r', 'p')
      and has_table_privilege('service_role', relation.oid, 'delete')
  ),
  'hosted publisher cannot delete from any public table'
);
select ok(
  not exists (
    select 1
    from pg_class as relation
    join pg_namespace as namespace on namespace.oid = relation.relnamespace
    where namespace.nspname = 'public'
      and relation.relkind in ('r', 'p')
      and has_table_privilege('service_role', relation.oid, 'truncate')
  ),
  'hosted publisher cannot truncate any public table'
);
select ok(
  not exists (
    select 1
    from pg_class as relation
    join pg_namespace as namespace on namespace.oid = relation.relnamespace
    where namespace.nspname = 'public'
      and relation.relkind in ('r', 'p')
      and has_table_privilege('service_role', relation.oid, 'references')
  ),
  'hosted publisher cannot create references against any public table'
);
select ok(
  not exists (
    select 1
    from pg_class as relation
    join pg_namespace as namespace on namespace.oid = relation.relnamespace
    where namespace.nspname = 'public'
      and relation.relkind in ('r', 'p')
      and has_table_privilege('service_role', relation.oid, 'trigger')
  ),
  'hosted publisher cannot create triggers on any public table'
);
select ok(
  not exists (
    select 1
    from pg_class as relation
    join pg_namespace as namespace on namespace.oid = relation.relnamespace
    where namespace.nspname = 'public'
      and relation.relkind = 'S'
      and (
        has_sequence_privilege('service_role', relation.oid, 'select')
        or has_sequence_privilege('service_role', relation.oid, 'usage')
        or has_sequence_privilege('service_role', relation.oid, 'update')
      )
  ),
  'hosted publisher has no public-sequence capability'
);
select ok(has_table_privilege('service_role', 'public.sources', 'select'), 'hosted publisher can resolve its source');
select ok(has_table_privilege('service_role', 'public.sources', 'update'), 'hosted publisher can update source health state');
select ok(not has_table_privilege('service_role', 'public.sources', 'insert'), 'hosted publisher cannot invent source registry rows');
select ok(not has_table_privilege('service_role', 'public.sources', 'delete'), 'hosted publisher cannot delete source registry rows');
select ok(has_table_privilege('service_role', 'public.source_access_policies', 'select'), 'hosted publisher can enforce persisted source policy');
select ok(not has_table_privilege('service_role', 'public.source_access_policies', 'update'), 'hosted publisher cannot change its own source policy');
select ok(has_table_privilege('service_role', 'public.sync_runs', 'insert'), 'hosted publisher can create sync runs');
select ok(has_table_privilege('service_role', 'public.sync_runs', 'update'), 'hosted publisher can finish sync runs');
select ok(not has_table_privilege('service_role', 'public.sync_runs', 'delete'), 'hosted publisher cannot erase sync runs');
select ok(has_table_privilege('service_role', 'public.raw_artifacts', 'insert'), 'hosted publisher can register immutable artifacts');
select ok(not has_table_privilege('service_role', 'public.raw_artifacts', 'update'), 'hosted publisher cannot rewrite immutable artifact metadata');
select ok(not has_table_privilege('service_role', 'public.raw_artifacts', 'delete'), 'hosted publisher cannot delete immutable artifact metadata');
select ok(has_table_privilege('service_role', 'public.source_record_artifacts', 'select'), 'hosted publisher can filter artifact links during an idempotent update');
select ok(has_table_privilege('service_role', 'public.documents', 'select'), 'hosted publisher can resolve document conflicts without exposing them publicly');
select ok(has_table_privilege('service_role', 'public.snapshots', 'select'), 'hosted publisher can perform idempotent snapshot inserts');
select ok(has_table_privilege('service_role', 'public.public_live_motorcycle_listings', 'select'), 'hosted publisher can apply filtered safety cleanups');
select ok(has_table_privilege('service_role', 'public.public_live_motorcycle_listings', 'insert'), 'hosted publisher can create sanitized public listings');
select ok(has_table_privilege('service_role', 'public.public_live_motorcycle_listings', 'update'), 'hosted publisher can update and deactivate sanitized listings');
select ok(not has_table_privilege('service_role', 'public.public_live_motorcycle_listings', 'delete'), 'hosted publisher cannot erase public listing history');
select lives_ok(
  $$insert into public_source_health (
      source_adapter, source_name, status, last_run_status,
      discovered_count, fetched_count, parsed_count, changed_count, failed_count,
      parse_success_rate, warning_codes, stale_after_hours
    ) values (
      'pgtap-health', 'pgTAP source health', 'PARTIAL', 'SUCCEEDED',
      0, 0, 0, 0, 0, 0,
      array[
        'ZERO_DISCOVERY', 'RUN_FAILED', 'PARSE_BELOW_90',
        'POLICY_BLOCKED', 'PARTIAL_COVERAGE'
      ]::public_source_warning[],
      1
    )$$,
  'valid boundary metrics and every reviewed warning code are accepted'
);
select throws_ok(
  $$insert into public_source_health (source_adapter, source_name, status, last_run_status)
    values ('health-invalid-run-status', 'invalid', 'PARTIAL', 'UNKNOWN')$$,
  '23514'
);
select throws_ok(
  $$insert into public_source_health (source_adapter, source_name, status, warning_codes)
    values ('health-invalid-warning', 'invalid', 'PARTIAL', array['NOT_REVIEWED']::public_source_warning[])$$,
  '22P02'
);
select throws_ok(
  $$insert into public_source_health (source_adapter, source_name, status, discovered_count)
    values ('health-negative-discovered', 'invalid', 'PARTIAL', -1)$$,
  '23514'
);
select throws_ok(
  $$insert into public_source_health (source_adapter, source_name, status, fetched_count)
    values ('health-negative-fetched', 'invalid', 'PARTIAL', -1)$$,
  '23514'
);
select throws_ok(
  $$insert into public_source_health (source_adapter, source_name, status, parsed_count)
    values ('health-negative-parsed', 'invalid', 'PARTIAL', -1)$$,
  '23514'
);
select throws_ok(
  $$insert into public_source_health (source_adapter, source_name, status, changed_count)
    values ('health-negative-changed', 'invalid', 'PARTIAL', -1)$$,
  '23514'
);
select throws_ok(
  $$insert into public_source_health (source_adapter, source_name, status, failed_count)
    values ('health-negative-failed', 'invalid', 'PARTIAL', -1)$$,
  '23514'
);
select throws_ok(
  $$insert into public_source_health (source_adapter, source_name, status, parse_success_rate)
    values ('health-rate-low', 'invalid', 'PARTIAL', -0.01)$$,
  '23514'
);
select throws_ok(
  $$insert into public_source_health (source_adapter, source_name, status, parse_success_rate)
    values ('health-rate-high', 'invalid', 'PARTIAL', 100.01)$$,
  '23514'
);
select throws_ok(
  $$insert into public_source_health (source_adapter, source_name, status, stale_after_hours)
    values ('health-stale-low', 'invalid', 'PARTIAL', 0)$$,
  '23514'
);
select throws_ok(
  $$insert into public_source_health (source_adapter, source_name, status, stale_after_hours)
    values ('health-stale-high', 'invalid', 'PARTIAL', 169)$$,
  '23514'
);
select throws_ok(
  $$insert into public_source_health (source_adapter, source_name, status)
    values ('pgtap-health', 'duplicate', 'PARTIAL')$$,
  '23505'
);
select has_index('public', 'sources', 'sources_adapter_name_uidx', 'one adapter key resolves to exactly one source');
select has_trigger('public', 'artifact_tombstones', 'artifact_tombstones_immutable', 'artifact deletion audit is append-only');
select has_view('public', 'motorcycle_listing', 'motorcycle read model exists');
select has_view('public', 'motorcycle_marketplace_listing', 'multi-source and bulk-lot read model exists');
select has_view('public', 'vehicle_marketplace_listing', 'car-and-motorcycle read model exists');
select has_column('public', 'vehicle_marketplace_listing', 'vehicle_type', 'vehicle marketplace exposes explicit vehicle type');
select has_column('public', 'vehicle_marketplace_listing', 'car_category', 'vehicle marketplace exposes explicit car category');
select has_column('public', 'vehicles', 'projection_active', 'superseded vehicle interpretations can be retired without deletion');
select has_index('public', 'vehicles', 'vehicles_current_lot_idx', 'current vehicle projection lookup is indexed');
select has_column('public', 'favorites', 'lot_id', 'favorites support official inseparable lots');
select ok(exists(select 1 from pg_constraint where conname='favorites_exactly_one_listing_chk'), 'each favorite targets exactly one listing entity');
select has_index('public', 'favorites', 'favorites_user_vehicle_uidx', 'vehicle favorites remain idempotent');
select has_index('public', 'favorites', 'favorites_user_lot_uidx', 'lot favorites are idempotent');
select has_column('public', 'vehicle_marketplace_listing', 'lot_id', 'current listings expose a stable owning lot');
select has_trigger('public', 'vehicles', 'vehicles_migrate_retired_favorites', 'retired clone favorites move to an inseparable lot at transaction end');
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
select has_index('public', 'documents', 'documents_source_url_uidx', 'all official documents have one canonical source URL identity');
select has_function('public', 'public_document_links_are_safe', array['text','jsonb'], 'public document link validation exists in the database');
select ok(exists(select 1 from pg_constraint where conname='public_live_document_links_safe_chk'), 'anonymous document links are constrained by source');
select ok(exists(select 1 from pg_constraint where conname='public_live_photo_urls_empty_chk'), 'anonymous official-photo redistribution is disabled in the database');
select has_function('public', 'public_text_contains_private_address', array['text'], 'public private-address detector exists at the database boundary');
select ok(exists(select 1 from pg_constraint where conname='public_live_private_address_safe_chk'), 'anonymous private addresses are rejected by a table constraint');
select ok(not has_function_privilege('anon', 'public.public_text_contains_private_address(text)', 'EXECUTE'), 'anonymous clients cannot invoke the private-address detector');
select ok(has_function_privilege('service_role', 'public.public_text_contains_private_address(text)', 'EXECUTE'), 'hosted publisher can satisfy the private-address table guard');
select ok(
  public.public_text_contains_private_address('通訊地址：臺北市大安區安全路 123 號'),
  'an explicitly labelled private address is detected without requiring a person name'
);
select ok(
  not public.public_text_contains_private_address('戶籍地址：已隱去'),
  'the reviewed redaction marker is idempotently accepted'
);
select ok(
  not public.public_text_contains_private_address('官方拍賣地址：臺北市政府倉庫'),
  'an official auction location is not mistaken for a private address'
);
select ok(
  public.public_text_contains_private_address(
    'https://www.gov.tw/notice?field=%E6%88%B6%E7%B1%8D%E5%9C%B0%E5%9D%80'
  ),
  'an encoded private-address label in a public URL is detected case-insensitively'
);
select has_trigger('public', 'public_live_motorcycle_listings', 'public_listing_access_policy_gate', 'every anonymous listing write checks persisted source policy');
select has_trigger('public', 'source_access_policies', 'source_policy_deactivates_public_listings', 'policy changes atomically deactivate public listings');
select has_trigger('public', 'source_access_policies', 'source_policy_delete_deactivates_public_listings', 'removing a policy also deactivates its public listings');
select ok(not has_function_privilege('anon', 'public.public_document_links_are_safe(text,jsonb)', 'EXECUTE'), 'anonymous role cannot invoke the validation RPC');
select ok(not has_function_privilege('authenticated', 'public.public_document_links_are_safe(text,jsonb)', 'EXECUTE'), 'authenticated clients cannot invoke the validation RPC');
select ok(has_function_privilege('service_role', 'public.public_document_links_are_safe(text,jsonb)', 'EXECUTE'), 'service role can enforce document validation during ingestion');
select ok(
  public_document_links_are_safe(
    'customs',
    '[{"label":"官方完整全文","url":"https://web.customs.gov.tw/download/notice.pdf"}]'::jsonb
  ),
  'reviewed exact-host document URL is accepted'
);
select ok(
  public_document_links_are_safe(
    'judicial_notices',
    '[{"label":"官方完整全文","url":"https://www.judicial.gov.tw/tw/dl-12345-01234567-89ab-cdef-0123-456789abcdef.html"}]'::jsonb
  ),
  'Judicial Yuan main-site link-only full text is accepted'
);
select ok(
  not public_document_links_are_safe(
    'judicial_notices',
    '[{"label":"官方完整全文","url":"https://www.judicial.gov.tw/tw/dl-12345-abcdef.html?download=1"}]'::jsonb
  ),
  'Judicial Yuan link-only query strings fail closed'
);
select ok(
  not public_document_links_are_safe(
    'judicial_notices',
    '[{"label":"官方完整全文","url":"https://aomp109.judicial.gov.tw/tw/dl-12345-abcdef.html"}]'::jsonb
  ),
  'Judicial Yuan link-only evidence cannot cross to aomp109'
);
select ok(
  not public_document_links_are_safe(
    'customs',
    '[{"label":"官方完整全文","url":"https://web.customs.gov.tw/download/notice.pdf#unsafe"}]'::jsonb
  ),
  'document URL fragments fail closed'
);
select ok(
  public_document_links_are_safe(
    'customs',
    '[{"label":"官方完整全文","url":"https://web.customs.gov.tw:443/download/notice.pdf"}]'::jsonb
  ),
  'database validator accepts the explicit HTTPS default port accepted by Python'
);
select ok(
  not public_document_links_are_safe(
    'moj_enforcement',
    '[{"label":"官方完整全文","url":"https://www.tpkonsale.moj.gov.tw/File/Download?PATH=11111111-1111-4111-8111-111111111111&NAME=notice.pdf&EXTRA=1"}]'::jsonb
  ),
  'Administrative Enforcement document query keys fail closed'
);
select ok(
  not public_document_links_are_safe(
    'customs',
    '[{"label":"官方完整全文","url":"https://web.customs.gov.tw/download/notice.pdf","storage_path":"private/secret.pdf"}]'::jsonb
  ),
  'anonymous document objects cannot carry private metadata'
);
select ok(
  not public_document_links_are_safe('customs', '[{"label":"官方完整全文"}]'::jsonb),
  'anonymous document objects must contain an official URL'
);
select throws_ok(
  $$insert into public_live_motorcycle_listings
      (id,source_adapter,source_name,source_record_id,official_url,official_title,
       organization_name,documents,content_checksum)
    values
      ('constraint-unsafe-test','customs','海關拍賣','constraint-unsafe-test',
       'https://web.customs.gov.tw/','測試公告','測試機關',
       '[{"label":"官方完整全文","url":"https://web.customs.gov.tw/news/not-a-document"}]'::jsonb,
       'test-checksum')$$,
  '23514'
);
select lives_ok(
  $$insert into public_live_motorcycle_listings
      (id,source_adapter,source_name,source_record_id,official_url,official_title,
       organization_name,location,content_checksum,active)
    values
      ('constraint-address-safe','shwoo','臺北惜物網','constraint-address-safe',
       'https://shwoo.gov.taipei/','機車拍賣公告','臺北市政府',
       '官方看車地點：臺北市政府倉庫','address-safe',false)$$,
  'official viewing and storage locations remain publishable'
);
select throws_ok(
  $$insert into public_live_motorcycle_listings
      (id,source_adapter,source_name,source_record_id,official_url,official_title,
       organization_name,location,content_checksum,active)
    values
      ('constraint-address-unsafe','shwoo','臺北惜物網','constraint-address-unsafe',
       'https://shwoo.gov.taipei/','機車拍賣公告','臺北市政府',
       '債務人戶籍地址：臺北市大安區安全路 123 號','address-unsafe',false)$$,
  '23514'
);
select throws_ok(
  $$insert into public_live_motorcycle_listings
      (id,source_adapter,source_name,source_record_id,official_url,official_title,
       organization_name,photo_urls,content_checksum)
    values
      ('constraint-photo-test','shwoo','臺北惜物網','constraint-photo-test',
       'https://shwoo.gov.taipei/','測試公告','測試機關',
       '["https://shwoo.gov.taipei/private-photo.jpg"]'::jsonb,'test-checksum')$$,
  '23514'
);
select has_function(
  'public',
  'public_text_contains_contact_identifier',
  array['text'],
  'public contact and identity detector exists at the database boundary'
);
select ok(
  exists(
    select 1 from pg_constraint
    where conname = 'public_live_contact_identifiers_safe_chk'
  ),
  'anonymous projection has a contact and Taiwan-ID fail-closed constraint'
);
select throws_ok(
  $$insert into public_live_motorcycle_listings
      (id,source_adapter,source_name,source_record_id,official_url,official_title,
       organization_name,content_checksum)
    values
      ('constraint-twid-test','shwoo','臺北惜物網','constraint-twid-test',
       'https://shwoo.gov.taipei/','車主 A123456789 機車拍賣','臺北市政府',
       'twid-unsafe')$$,
  '23514'
);
select throws_ok(
  $$insert into public_live_motorcycle_listings
      (id,source_adapter,source_name,source_record_id,official_url,official_title,
       organization_name,description,content_checksum)
    values
      ('constraint-email-test','shwoo','臺北惜物網','constraint-email-test',
       'https://shwoo.gov.taipei/','機車拍賣公告','臺北市政府',
       '聯絡 owner@example.com','email-unsafe')$$,
  '23514'
);
select throws_ok(
  $$insert into public_live_motorcycle_listings
      (id,source_adapter,source_name,source_record_id,official_url,official_title,
       organization_name,fee_notes,content_checksum)
    values
      ('constraint-phone-test','shwoo','臺北惜物網','constraint-phone-test',
       'https://shwoo.gov.taipei/','機車拍賣公告','臺北市政府',
       array['承辦人電話 0912-345-678'],'phone-unsafe')$$,
  '23514'
);
select throws_ok(
  $$insert into public_live_motorcycle_listings
      (id,source_adapter,source_name,source_record_id,official_url,official_title,
       organization_name,content_checksum)
    values
      ('constraint-encoded-email-test','shwoo','臺北惜物網',
       'constraint-encoded-email-test',
       'https://shwoo.gov.taipei/?contact=owner%40example.com',
       '機車拍賣公告','臺北市政府','encoded-email-unsafe')$$,
  '23514'
);
select ok(not has_table_privilege('anon', 'public.documents', 'select'), 'anonymous role cannot read the private documents table');
select ok(has_table_privilege('authenticated', 'public.documents', 'select'), 'authenticated role can request owner-protected documents');
insert into documents (id,source_record_id,title,document_type,official_url)
values (
  '59000000-0000-0000-0000-000000000001',
  '40000000-0000-0000-0000-000000000001',
  '官方完整全文',
  'OFFICIAL_LINK_ONLY',
  'https://web.customs.gov.tw/download/idempotency-test.pdf'
);
select throws_ok(
  $$insert into documents (id,source_record_id,title,document_type,official_url)
    values (
      '59000000-0000-0000-0000-000000000002',
      '40000000-0000-0000-0000-000000000001',
      '重複官方完整全文',
      'OFFICIAL_LINK_ONLY',
      'https://web.customs.gov.tw/download/idempotency-test.pdf'
    )$$,
  '23505'
);
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
select is(
  (
    select count(*)
    from source_endpoints
    where source_id = '20000000-0000-0000-0000-000000000002'
      and url like 'https://aomp109.judicial.gov.tw/%'
      and enabled
  ),
  0::bigint,
  'aomp109 endpoints remain disabled for every unattended execution path'
);
select is((select decision from source_access_policies where source_id='20000000-0000-0000-0000-000000000009'), 'ALLOW', 'Judicial main-site supplemental notices use only the reviewed public HTML scope');
select is((select decision from source_access_policies where source_id='20000000-0000-0000-0000-000000000004'), 'ALLOW', 'PCC official machine-readable dataset is approved');
select is((select status::text from sources where adapter_name='customs'), 'PARTIAL', 'Customs awaits its first successful four-office run');
select is((select decision from source_access_policies where source_id='20000000-0000-0000-0000-000000000007'), 'ALLOW', 'Customs HTML access is approved while restricted downloads remain excluded');
select is((select status::text from sources where adapter_name='moj_enforcement_cms'), 'PARTIAL', 'Administrative Enforcement branch CMS awaits an all-branch run');
select is((select decision from source_access_policies where source_id='20000000-0000-0000-0000-000000000008'), 'ALLOW', 'Administrative Enforcement CMS access is limited to reviewed branch hosts');
select is((select decision from source_access_policies where source_id='20000000-0000-0000-0000-000000000003'), 'MANUAL_ONLY', 'Administrative Enforcement central discovery remains human-assisted');
select is((select photo_rights from source_access_policies where source_id='20000000-0000-0000-0000-000000000003'), 'LINK_ONLY_NO_FETCH', 'Administrative Enforcement PDF and image bytes are never mirrored');
select ok(not has_table_privilege('anon', 'public.sources', 'select'), 'anonymous role cannot read formal source tables');
select is((select public from storage.buckets where id='raw-artifacts'), false, 'raw artifact storage is private');
select is((select count(*) from sources where adapter_name in ('moj_auction','moj_enforcement','moj_enforcement_cms') and status not in ('PARTIAL','ACTIVE','DEGRADED')), 0::bigint, 'implemented MOJ sources expose only runtime-ready health states');
select is((select count(*) from motorcycle_listing where source_auid = 'SYNTH-SHWOO-01'), 1::bigint, 'seed exposes exactly one synthetic development listing');
insert into vehicle_identifiers
  (id,vehicle_id,identifier_type,normalized_value,original_value,projection_active)
values
  ('00000000-0000-0000-0000-000000000001',
   '53000000-0000-0000-0000-000000000001',
   'PLATE','RETIRED-PLATE','RETIRED-PLATE',false);
select is(
  (select plate_number from vehicle_marketplace_listing where id='53000000-0000-0000-0000-000000000001'),
  'TEST-SHWOO-01',
  'current listing never exposes a retired identifier projection'
);
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

insert into sources
  (id,family,name,adapter_name,status,automation_level,official_url)
values
  ('20000000-0000-0000-0000-000000000099','TEST','公開政策閘門測試','policy_gate_test','PARTIAL','TEST','https://www.gov.tw/');
insert into source_access_policies
  (source_id,decision,robots_url,photo_rights,personal_data_risk,checked_on,rationale)
values
  ('20000000-0000-0000-0000-000000000099','ALLOW','https://www.gov.tw/robots.txt','NONE','LOW',current_date,'pgTAP only');
insert into public_live_motorcycle_listings
  (id,source_adapter,source_name,source_record_id,official_url,official_title,
   organization_name,content_checksum,active)
values
  ('policy-gate-allowed','policy_gate_test','測試來源','policy-gate-allowed',
   'https://www.gov.tw/','測試公告','測試機關','allowed',true);
select is(
  (select active from public_live_motorcycle_listings where id='policy-gate-allowed'),
  true,
  'an ALLOW source may atomically publish an active row'
);
update source_access_policies
set decision='DISABLED'
where source_id='20000000-0000-0000-0000-000000000099';
select is(
  (select active from public_live_motorcycle_listings where id='policy-gate-allowed'),
  false,
  'changing policy away from ALLOW atomically deactivates existing rows'
);
insert into public_live_motorcycle_listings
  (id,source_adapter,source_name,source_record_id,official_url,official_title,
   organization_name,content_checksum,active)
values
  ('policy-gate-blocked','policy_gate_test','測試來源','policy-gate-blocked',
   'https://www.gov.tw/','測試公告','測試機關','blocked',true);
select is(
  (select active from public_live_motorcycle_listings where id='policy-gate-blocked'),
  false,
  'a non-ALLOW source cannot reactivate itself through an upsert'
);

-- Restore only the known-safe row before exercising the anonymous read policy.
-- Changing a policy back to ALLOW must not reactivate every historical row, so
-- the allowed row is explicitly reviewed and re-enabled while the blocked row
-- remains inactive.
update source_access_policies
set decision='ALLOW'
where source_id='20000000-0000-0000-0000-000000000099';
update public_live_motorcycle_listings
set active=true
where id='policy-gate-allowed';

-- Exercise the policies as the API roles instead of checking catalog flags
-- alone. The observation table exists only inside this rolled-back test
-- transaction and lets pgTAP assert results after RESET ROLE.
create table public._pgtap_rls_observations (
  label text primary key,
  observed bigint not null
);
grant insert on public._pgtap_rls_observations to anon, authenticated;

set local request.jwt.claims = '{"role":"anon"}';
set local role anon;
insert into public._pgtap_rls_observations (label, observed) values
  ('anon-active-listing',
   (select count(*) from public.public_live_motorcycle_listings where id='policy-gate-allowed')),
  ('anon-inactive-listing',
   (select count(*) from public.public_live_motorcycle_listings where id='policy-gate-blocked')),
  ('anon-source-health',
   (select count(*) from public.public_source_health where source_adapter='pgtap-health'));
reset role;

set local request.jwt.claims =
  '{"role":"authenticated","sub":"60000000-0000-0000-0000-000000000010","email":"owner@example.com"}';
set local role authenticated;
insert into public._pgtap_rls_observations (label, observed) values
  ('owner-sources', (select count(*) from public.sources)),
  ('owner-source-policies', (select count(*) from public.source_access_policies));
reset role;

set local request.jwt.claims =
  '{"role":"authenticated","sub":"60000000-0000-0000-0000-000000000011","email":"not-owner@example.test"}';
set local role authenticated;
insert into public._pgtap_rls_observations (label, observed) values
  ('non-owner-sources', (select count(*) from public.sources));
reset role;

select is(
  (select observed from public._pgtap_rls_observations where label='anon-active-listing'),
  1::bigint,
  'anonymous API role can read an active sanitized listing'
);
select is(
  (select observed from public._pgtap_rls_observations where label='anon-inactive-listing'),
  0::bigint,
  'anonymous API role cannot read an inactive sanitized listing'
);
select is(
  (select observed from public._pgtap_rls_observations where label='anon-source-health'),
  1::bigint,
  'anonymous API role can read sanitized source health'
);
select ok(
  (select observed > 0 from public._pgtap_rls_observations where label='owner-sources'),
  'owner JWT can read the operational source registry through RLS'
);
select ok(
  (select observed > 0 from public._pgtap_rls_observations where label='owner-source-policies'),
  'owner JWT can read private source authorization policy through RLS'
);
select is(
  (select observed from public._pgtap_rls_observations where label='non-owner-sources'),
  0::bigint,
  'authenticated non-owner JWT cannot read operational sources'
);

insert into auth.users
  (id,aud,role,email,encrypted_password,email_confirmed_at,raw_app_meta_data,raw_user_meta_data,created_at,updated_at)
values
  ('60000000-0000-0000-0000-000000000001','authenticated','authenticated','favorite-one@example.test','',now(),'{}','{}',now(),now()),
  ('60000000-0000-0000-0000-000000000002','authenticated','authenticated','favorite-two@example.test','',now(),'{}','{}',now(),now());
insert into favorites (user_id,lot_id)
values ('60000000-0000-0000-0000-000000000001','52000000-0000-0000-0000-000000000001');
select is(
  (select count(*) from favorites where user_id='60000000-0000-0000-0000-000000000001' and lot_id='52000000-0000-0000-0000-000000000001'),
  1::bigint,
  'an owner favorite may target an official lot'
);
select throws_ok(
  $$insert into favorites (user_id,vehicle_id,lot_id)
    values ('60000000-0000-0000-0000-000000000002',
      '53000000-0000-0000-0000-000000000001',
      '52000000-0000-0000-0000-000000000001')$$,
  '23514'
);
insert into favorites (user_id,vehicle_id)
values ('60000000-0000-0000-0000-000000000002','53000000-0000-0000-0000-000000000001');

update vehicles
set projection_active = false,
    projection_retired_at = now(),
    projection_retired_reason = 'pgTAP projection transition'
where id = '53000000-0000-0000-0000-000000000001';
set constraints vehicles_migrate_retired_favorites immediate;
select is(
  (select count(*) from favorites where user_id='60000000-0000-0000-0000-000000000002' and vehicle_id is null and lot_id='52000000-0000-0000-0000-000000000001'),
  1::bigint,
  'a retired clone favorite follows the official inseparable lot'
);
select is(
  (
    select listing_entity
    from vehicle_marketplace_listing
    where id = '52000000-0000-0000-0000-000000000001'
  ),
  'lot',
  'retiring a superseded vehicle exposes the official lot without deleting history'
);

-- Reapply the exact migration bootstrap after operator restrictions are set.
-- Release metadata must not silently reactivate a source, policy or endpoint.
select lives_ok(
  $$insert into public.organizations
      (canonical_name, organization_type, jurisdiction, official_domain)
    values ('臺灣臺北地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw')
    on conflict (canonical_name, jurisdiction) do update set
      organization_type = excluded.organization_type,
      official_domain = excluded.official_domain$$,
  'production organization bootstrap uses the actual composite unique key'
);
select is(
  (select count(*) from public.organizations where canonical_name = '臺灣臺北地方法院' and jurisdiction = '臺灣'),
  1::bigint,
  'replaying an official organization does not create a duplicate'
);
select ok(
  not has_function_privilege('anon', 'private.bootstrap_judicial_public_notices()', 'execute'),
  'anonymous users cannot invoke the private source bootstrap'
);
select ok(
  not has_function_privilege('service_role', 'private.bootstrap_judicial_public_notices()', 'execute'),
  'hosted publisher cannot invoke the private source bootstrap'
);
update public.sources
set status = 'DISABLED'
where id = '20000000-0000-0000-0000-000000000009';
update public.source_access_policies
set decision = 'MANUAL_ONLY'
where source_id = '20000000-0000-0000-0000-000000000009';
update public.source_endpoints
set enabled = false
where source_id = '20000000-0000-0000-0000-000000000009'
  and endpoint_type = 'DISCOVERY';
select lives_ok(
  $$select private.bootstrap_judicial_public_notices()$$,
  'source registry bootstrap may safely repeat after manual-only restriction'
);
select is(
  (select status::text from public.sources where id = '20000000-0000-0000-0000-000000000009'),
  'DISABLED',
  'source bootstrap preserves an operator-disabled source'
);
select is(
  (select decision from public.source_access_policies where source_id = '20000000-0000-0000-0000-000000000009'),
  'MANUAL_ONLY',
  'source bootstrap does not promote manual-only access to ALLOW'
);
select is(
  (select enabled from public.source_endpoints where source_id = '20000000-0000-0000-0000-000000000009' and endpoint_type = 'DISCOVERY'),
  false,
  'source bootstrap preserves an operator-disabled endpoint'
);
update public.source_access_policies
set decision = 'REVIEW_REQUIRED'
where source_id = '20000000-0000-0000-0000-000000000009';
select lives_ok(
  $$select private.bootstrap_judicial_public_notices()$$,
  'source registry bootstrap may safely repeat during policy review'
);
select is(
  (select decision from public.source_access_policies where source_id = '20000000-0000-0000-0000-000000000009'),
  'REVIEW_REQUIRED',
  'source bootstrap preserves policy review gate'
);
update public.source_access_policies
set decision = 'DISABLED'
where source_id = '20000000-0000-0000-0000-000000000009';
select lives_ok(
  $$select private.bootstrap_judicial_public_notices()$$,
  'source registry bootstrap may safely repeat after policy disablement'
);
select is(
  (select decision from public.source_access_policies where source_id = '20000000-0000-0000-0000-000000000009'),
  'DISABLED',
  'source bootstrap preserves disabled policy'
);
select is(
  (select enabled from public.source_endpoints where source_id = '20000000-0000-0000-0000-000000000009' and endpoint_type = 'DISCOVERY'),
  false,
  'source bootstrap never re-enables the discovery endpoint'
);

select * from finish();
rollback;
