create extension if not exists pgcrypto;
create extension if not exists pg_trgm;

create type adapter_status as enum ('PLANNED','PARTIAL','ACTIVE','DEGRADED','DISABLED');
create type auction_status as enum ('DISCOVERED','ANNOUNCED','SCHEDULED','SOLD','UNSOLD','WITHDRAWN','CANCELLED','EXPIRED','UNKNOWN');
create type disposal_origin as enum ('JUDICIAL_EXECUTION','ADMINISTRATIVE_ENFORCEMENT','CRIMINAL_SEIZURE_OR_FORFEITURE','IMPOUNDED_UNCLAIMED','PUBLIC_ASSET_DISPOSAL','CUSTOMS_FORFEITURE','SCRAP_DISPOSAL','OTHER','UNKNOWN');
create type bid_eligibility as enum ('PUBLIC','NATURAL_PERSON_ALLOWED','BUSINESS_ONLY','LICENSED_RECYCLER_ONLY','SPECIAL_QUALIFICATION','BULK_PURCHASE_ONLY','UNKNOWN');
create type registration_status as enum ('NORMAL_TRANSFER','RE_REGISTRATION_REQUIRED','INSPECTION_REQUIRED','REGISTRABILITY_UNKNOWN','DEREGISTERED','CANNOT_RELICENSE','SCRAP_ONLY','EXPORT_ONLY','UNKNOWN');
create type four_state as enum ('YES','NO','UNKNOWN','CONFLICTING');
create type source_trust as enum ('OFFICIAL_EXPLICIT','OFFICIAL_INFERRED','CROSS_SOURCE_CONFIRMED','SYSTEM_CALCULATED','LLM_EXTRACTED','THIRD_PARTY_REFERENCE','UNKNOWN');
create type extraction_method as enum ('STRUCTURED','HTML','DOCUMENT_RULE','OCR','LLM');

create table app_settings (
  id boolean primary key default true check (id),
  owner_email text not null check (owner_email = lower(owner_email)),
  updated_at timestamptz not null default now()
);

create table organizations (
  id uuid primary key default gen_random_uuid(),
  canonical_name text not null,
  organization_type text not null,
  jurisdiction text,
  official_domain text,
  created_at timestamptz not null default now(),
  unique (canonical_name, jurisdiction)
);

create table sources (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references organizations(id),
  family text not null,
  name text not null unique,
  adapter_name text not null,
  status adapter_status not null default 'PLANNED',
  automation_level text not null,
  official_url text not null,
  parser_version text,
  last_attempted_at timestamptz,
  last_successful_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table source_endpoints (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references sources(id) on delete cascade,
  endpoint_type text not null,
  url text not null,
  enabled boolean not null default true,
  notes text,
  unique (source_id, endpoint_type, url)
);

create table sync_runs (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references sources(id),
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  status text not null check (status in ('RUNNING','SUCCEEDED','PARTIAL','FAILED')),
  discovered_count integer not null default 0 check (discovered_count >= 0),
  fetched_count integer not null default 0 check (fetched_count >= 0),
  changed_count integer not null default 0 check (changed_count >= 0),
  parsed_count integer not null default 0 check (parsed_count >= 0),
  failed_count integer not null default 0 check (failed_count >= 0),
  warnings jsonb not null default '[]'::jsonb,
  errors jsonb not null default '[]'::jsonb,
  parser_version text not null
);

create table source_records (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references sources(id),
  source_record_id text not null,
  official_url text not null,
  original_title text,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  last_content_checksum text,
  search_vector tsvector generated always as (to_tsvector('simple', lower(coalesce(original_title, '')))) stored,
  active boolean not null default true,
  unique (source_id, source_record_id)
);

create table raw_artifacts (
  id uuid primary key default gen_random_uuid(),
  source_record_id uuid references source_records(id),
  sync_run_id uuid references sync_runs(id),
  official_url text not null,
  fetched_at timestamptz not null,
  http_status integer,
  http_headers jsonb not null default '{}'::jsonb,
  mime_type text not null,
  filename text,
  checksum_sha256 text not null,
  content_length bigint not null check (content_length >= 0),
  storage_path text not null,
  extraction_status text not null default 'PENDING',
  parser_version text,
  created_at timestamptz not null default now(),
  unique (checksum_sha256, storage_path)
);

create table snapshots (
  id uuid primary key default gen_random_uuid(),
  source_record_id uuid not null references source_records(id),
  artifact_id uuid references raw_artifacts(id),
  observed_at timestamptz not null default now(),
  normalized_payload jsonb not null,
  payload_checksum text not null,
  parser_version text not null,
  unique (source_record_id, payload_checksum, parser_version)
);

create table auction_cases (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references sources(id),
  organization_id uuid references organizations(id),
  official_case_number text,
  title text not null,
  disposal_origin disposal_origin not null default 'UNKNOWN',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique nulls not distinct (source_id, official_case_number)
);

create table auction_events (
  id uuid primary key default gen_random_uuid(),
  auction_case_id uuid not null references auction_cases(id) on delete cascade,
  source_record_id uuid not null references source_records(id),
  round_number integer check (round_number is null or round_number > 0),
  status auction_status not null default 'UNKNOWN',
  starts_at timestamptz,
  ends_at timestamptz,
  reserve_price numeric(14,2),
  current_price numeric(14,2),
  sold_price numeric(14,2),
  deposit numeric(14,2),
  auction_method text,
  payment_deadline timestamptz,
  pickup_deadline timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique nulls not distinct (source_record_id, round_number)
);

create table lots (
  id uuid primary key default gen_random_uuid(),
  auction_event_id uuid not null references auction_events(id) on delete cascade,
  lot_number text,
  title text not null,
  lot_size integer not null default 1 check (lot_size > 0),
  bulk_lot boolean not null default false,
  eligibility bid_eligibility not null default 'UNKNOWN',
  storage_location text,
  viewing_time text,
  original_description text,
  fee_notes text[] not null default '{}',
  search_vector tsvector generated always as (to_tsvector('simple', lower(coalesce(title, '') || ' ' || coalesce(storage_location, '') || ' ' || coalesce(original_description, '')))) stored,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index lots_event_number_uidx on lots (auction_event_id, coalesce(lot_number, ''));

create table vehicle_brands (
  id uuid primary key default gen_random_uuid(),
  canonical_name text not null unique,
  aliases text[] not null default '{}'
);

create table vehicle_models (
  id uuid primary key default gen_random_uuid(),
  brand_id uuid not null references vehicle_brands(id),
  canonical_name text not null,
  model_code text,
  unique (brand_id, canonical_name)
);

create table vehicle_model_aliases (
  id uuid primary key default gen_random_uuid(),
  model_id uuid not null references vehicle_models(id) on delete cascade,
  alias text not null,
  unique (model_id, alias)
);

create table vehicles (
  id uuid primary key default gen_random_uuid(),
  lot_id uuid not null references lots(id) on delete cascade,
  source_vehicle_key text not null default 'primary',
  brand_id uuid references vehicle_brands(id),
  model_id uuid references vehicle_models(id),
  original_brand text,
  original_model text,
  model_code text,
  vehicle_category text,
  manufacture_year integer,
  manufacture_month integer check (manufacture_month between 1 and 12),
  displacement_cc integer,
  color text,
  mileage_km integer check (mileage_km is null or mileage_km >= 0),
  has_key four_state not null default 'UNKNOWN',
  can_start four_state not null default 'UNKNOWN',
  can_test four_state not null default 'UNKNOWN',
  registration_status registration_status not null default 'UNKNOWN',
  plate_status text,
  condition_summary text,
  visible_damage text,
  tax_arrears four_state not null default 'UNKNOWN',
  fine_arrears four_state not null default 'UNKNOWN',
  fuel_fee_arrears four_state not null default 'UNKNOWN',
  encumbrance_status four_state not null default 'UNKNOWN',
  completeness smallint not null default 0 check (completeness between 0 and 100),
  completeness_groups jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index vehicles_lot_source_key_uidx on vehicles (lot_id, source_vehicle_key);

create table vehicle_identifiers (
  id uuid primary key default gen_random_uuid(),
  vehicle_id uuid not null references vehicles(id) on delete cascade,
  identifier_type text not null check (identifier_type in ('PLATE','ENGINE','FRAME','VIN','OTHER')),
  normalized_value text not null,
  original_value text not null,
  is_masked boolean not null default false,
  unique (vehicle_id, identifier_type, normalized_value)
);

create index vehicle_identifiers_lookup_idx on vehicle_identifiers (identifier_type, normalized_value);

create table vehicle_observations (
  id uuid primary key default gen_random_uuid(),
  vehicle_id uuid not null references vehicles(id) on delete cascade,
  snapshot_id uuid not null references snapshots(id),
  observed_at timestamptz not null,
  payload jsonb not null,
  created_at timestamptz not null default now(),
  unique (vehicle_id, snapshot_id)
);

create table photos (
  id uuid primary key default gen_random_uuid(),
  vehicle_id uuid references vehicles(id) on delete cascade,
  lot_id uuid references lots(id) on delete cascade,
  source_record_id uuid not null references source_records(id),
  artifact_id uuid references raw_artifacts(id),
  source_url text not null,
  storage_path text,
  checksum_sha256 text,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  availability_status text not null default 'AVAILABLE',
  sort_order integer not null default 0,
  width integer,
  height integer,
  check (vehicle_id is not null or lot_id is not null)
);
create unique index photos_source_url_uidx on photos (source_record_id, source_url);

create table documents (
  id uuid primary key default gen_random_uuid(),
  source_record_id uuid not null references source_records(id),
  artifact_id uuid references raw_artifacts(id),
  title text not null,
  document_type text,
  official_url text not null,
  created_at timestamptz not null default now()
);

create table field_evidence (
  id uuid primary key default gen_random_uuid(),
  entity_type text not null,
  entity_id uuid not null,
  field_name text not null,
  normalized_value jsonb,
  source_record_id uuid not null references source_records(id),
  artifact_id uuid references raw_artifacts(id),
  source_text text not null,
  page_number integer,
  table_row text,
  parser_name text not null,
  parser_version text not null,
  extraction_method extraction_method not null,
  trust source_trust not null,
  confidence numeric(4,3) not null check (confidence between 0 and 1),
  created_at timestamptz not null default now()
);
create unique index field_evidence_artifact_uidx on field_evidence (entity_type, entity_id, field_name, artifact_id, md5(source_text));

create index field_evidence_entity_idx on field_evidence (entity_type, entity_id, field_name);

create table cross_source_links (
  id uuid primary key default gen_random_uuid(),
  left_source_record_id uuid not null references source_records(id),
  right_source_record_id uuid not null references source_records(id),
  relationship text not null,
  matching_signals jsonb not null,
  confidence numeric(4,3) not null check (confidence between 0 and 1),
  algorithm_version text not null,
  created_at timestamptz not null default now(),
  check (left_source_record_id <> right_source_record_id),
  unique (left_source_record_id, right_source_record_id, relationship)
);

create table probable_duplicates (
  id uuid primary key default gen_random_uuid(),
  left_vehicle_id uuid not null references vehicles(id),
  right_vehicle_id uuid not null references vehicles(id),
  score numeric(5,4) not null check (score between 0 and 1),
  matching_signals jsonb not null,
  algorithm_version text not null,
  review_status text not null default 'PENDING' check (review_status in ('PENDING','CONFIRMED','REJECTED')),
  created_at timestamptz not null default now(),
  check (left_vehicle_id <> right_vehicle_id),
  unique (left_vehicle_id, right_vehicle_id)
);

create table favorites (
  user_id uuid not null references auth.users(id) on delete cascade,
  vehicle_id uuid not null references vehicles(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, vehicle_id)
);

create table saved_searches (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  filters jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index source_records_title_trgm_idx on source_records using gin (original_title gin_trgm_ops);
create index source_records_search_vector_idx on source_records using gin (search_vector);
create index auction_cases_title_trgm_idx on auction_cases using gin (title gin_trgm_ops);
create index lots_title_trgm_idx on lots using gin (title gin_trgm_ops);
create index lots_location_trgm_idx on lots using gin (storage_location gin_trgm_ops);
create index lots_search_vector_idx on lots using gin (search_vector);

create or replace function is_owner() returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from app_settings
    where lower(auth.jwt() ->> 'email') = owner_email
  );
$$;

revoke all on function is_owner() from public;
grant execute on function is_owner() to authenticated;

create or replace function touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;

create trigger sources_touch before update on sources for each row execute function touch_updated_at();
create trigger cases_touch before update on auction_cases for each row execute function touch_updated_at();
create trigger events_touch before update on auction_events for each row execute function touch_updated_at();
create trigger lots_touch before update on lots for each row execute function touch_updated_at();
create trigger vehicles_touch before update on vehicles for each row execute function touch_updated_at();
create trigger saved_searches_touch before update on saved_searches for each row execute function touch_updated_at();

create or replace function reject_immutable_mutation() returns trigger language plpgsql as $$
begin raise exception '% is append-only', tg_table_name; end;
$$;

create trigger raw_artifacts_immutable before update or delete on raw_artifacts for each row execute function reject_immutable_mutation();
create trigger snapshots_immutable before update or delete on snapshots for each row execute function reject_immutable_mutation();

create view source_health with (security_invoker = true) as
select s.id, s.name, s.adapter_name, s.status, s.automation_level,
       s.last_attempted_at, s.last_successful_at,
       coalesce(r.discovered_count, 0) as discovered_count,
       coalesce(r.changed_count, 0) as changed_count,
       case when coalesce(r.fetched_count, 0) = 0 then null
            else round((r.parsed_count::numeric / r.fetched_count::numeric) * 100, 1) end as parse_success_rate,
       coalesce(r.warnings, '[]'::jsonb) as warnings,
       r.status as last_run_status
from sources s
left join lateral (
  select * from sync_runs where source_id = s.id order by started_at desc limit 1
) r on true;

create view motorcycle_listing with (security_invoker = true) as
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
       coalesce((select normalized_value from vehicle_identifiers vi where vi.vehicle_id=v.id and vi.identifier_type='PLATE' limit 1), null) as plate_number
from vehicles v
join lots l on l.id = v.lot_id
join auction_events ae on ae.id = l.auction_event_id
join auction_cases ac on ac.id = ae.auction_case_id
join source_records sr on sr.id = ae.source_record_id
left join organizations o on o.id = ac.organization_id
left join vehicle_brands vb on vb.id = v.brand_id
left join vehicle_models vm on vm.id = v.model_id
left join lateral (select source_url from photos where vehicle_id=v.id order by sort_order limit 1) p on true;

create view resolved_field_evidence with (security_invoker = true) as
select distinct on (entity_type, entity_id, field_name)
       id, entity_type, entity_id, field_name, normalized_value, source_record_id,
       artifact_id, source_text, page_number, table_row, parser_name, parser_version,
       extraction_method, trust, confidence, created_at
from field_evidence
order by entity_type, entity_id, field_name,
  case trust
    when 'OFFICIAL_EXPLICIT' then 1
    when 'CROSS_SOURCE_CONFIRMED' then 2
    when 'OFFICIAL_INFERRED' then 3
    when 'SYSTEM_CALCULATED' then 4
    when 'LLM_EXTRACTED' then 5
    when 'THIRD_PARTY_REFERENCE' then 6
    else 7
  end,
  confidence desc,
  created_at desc;

do $$
declare t text;
begin
  foreach t in array array[
    'organizations','sources','source_endpoints','sync_runs','source_records','raw_artifacts','snapshots',
    'auction_cases','auction_events','lots','vehicle_brands','vehicle_models','vehicle_model_aliases','vehicles',
    'vehicle_identifiers','vehicle_observations','photos','documents','field_evidence','cross_source_links',
    'probable_duplicates','favorites','saved_searches','app_settings'
  ] loop
    execute format('alter table %I enable row level security', t);
    execute format('create policy owner_read on %I for select to authenticated using (is_owner())', t);
  end loop;
end $$;

create policy owner_insert_favorites on favorites for insert to authenticated with check (is_owner() and user_id = auth.uid());
create policy owner_delete_favorites on favorites for delete to authenticated using (is_owner() and user_id = auth.uid());
create policy owner_manage_saved_searches on saved_searches for all to authenticated using (is_owner() and user_id = auth.uid()) with check (is_owner() and user_id = auth.uid());

insert into storage.buckets (id, name, public, file_size_limit)
values ('raw-artifacts', 'raw-artifacts', false, 26214400)
on conflict (id) do update set public = excluded.public, file_size_limit = excluded.file_size_limit;

create policy owner_read_raw_artifacts on storage.objects for select to authenticated using (bucket_id = 'raw-artifacts' and public.is_owner());

grant usage on schema public to authenticated;
grant select on all tables in schema public to authenticated;
grant insert, delete on favorites to authenticated;
grant insert, update, delete on saved_searches to authenticated;
grant usage, select on all sequences in schema public to authenticated;

comment on view motorcycle_listing is 'Authenticated read model; official and normalized values remain available through base tables and field_evidence.';
