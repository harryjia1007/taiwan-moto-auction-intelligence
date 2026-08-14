-- Narrow, publication-safe projection for the public portfolio page.
-- Operational tables, raw evidence and private artifacts remain owner-only.

create table public_live_motorcycle_listings (
  id text primary key,
  source_adapter text not null,
  source_name text not null,
  source_record_id text not null,
  official_url text not null check (official_url ~ '^https://'),
  official_title text not null,
  official_case_number text,
  organization_name text not null,
  disposal_origin disposal_origin not null default 'UNKNOWN',
  auction_status auction_status not null default 'UNKNOWN',
  auction_round integer check (auction_round is null or auction_round > 0),
  starts_at timestamptz,
  ends_at timestamptz,
  reserve_price numeric(14,2),
  current_price numeric(14,2),
  sold_price numeric(14,2),
  deposit numeric(14,2),
  eligibility bid_eligibility not null default 'UNKNOWN',
  registration_status registration_status not null default 'UNKNOWN',
  vehicle_category text not null default 'UNKNOWN',
  brand_name text,
  model_name text,
  manufacture_year integer,
  manufacture_month integer check (manufacture_month between 1 and 12),
  displacement_cc integer check (displacement_cc is null or displacement_cc > 0),
  color text,
  mileage_km integer check (mileage_km is null or mileage_km >= 0),
  plate_number text,
  has_key four_state not null default 'UNKNOWN',
  can_start four_state not null default 'UNKNOWN',
  can_test four_state not null default 'UNKNOWN',
  location text,
  description text,
  condition_summary text,
  fee_notes text[] not null default '{}',
  lot_size integer not null default 1 check (lot_size > 0),
  bulk_lot boolean not null default false,
  photo_urls jsonb not null default '[]'::jsonb check (jsonb_typeof(photo_urls) = 'array'),
  documents jsonb not null default '[]'::jsonb check (jsonb_typeof(documents) = 'array'),
  completeness smallint not null default 0 check (completeness between 0 and 100),
  completeness_groups jsonb not null default '{}'::jsonb,
  official_updated_at timestamptz,
  first_published_at timestamptz not null default now(),
  last_synced_at timestamptz not null default now(),
  content_checksum text not null,
  active boolean not null default true,
  search_text text generated always as (
    lower(official_title || ' ' || coalesce(official_case_number, '') || ' ' || organization_name || ' ' ||
      coalesce(brand_name, '') || ' ' || coalesce(model_name, '') || ' ' || coalesce(plate_number, '') || ' ' ||
      coalesce(location, '') || ' ' || coalesce(description, ''))
  ) stored,
  unique (source_adapter, source_record_id)
);

create index public_live_motorcycle_ends_idx on public_live_motorcycle_listings (ends_at);
create index public_live_motorcycle_status_idx on public_live_motorcycle_listings (auction_status, active);
create index public_live_motorcycle_cc_idx on public_live_motorcycle_listings (displacement_cc);
create index public_live_motorcycle_search_idx on public_live_motorcycle_listings using gin (search_text extensions.gin_trgm_ops);

alter table public_live_motorcycle_listings enable row level security;

create policy public_read_live_motorcycle_listings
  on public_live_motorcycle_listings
  for select
  to anon, authenticated
  using (active);

grant select on public_live_motorcycle_listings to anon, authenticated;
revoke insert, update, delete, truncate, references, trigger on public_live_motorcycle_listings from anon, authenticated;

comment on table public_live_motorcycle_listings is
  'Public least-privilege projection of official motorcycle listings. It excludes people, engine/frame/VIN identifiers, private artifacts and evidence text.';
comment on column public_live_motorcycle_listings.plate_number is
  'Official plate text may be published through 30 days after the official auction end time; the publisher must clear it after that window.';
comment on column public_live_motorcycle_listings.photo_urls is
  'Official source URLs only. No private Storage URL or cached artifact path may be published.';
