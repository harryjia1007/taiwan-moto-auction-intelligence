-- Sanitized run-health projection for the anonymous portfolio marketplace.
-- Detailed warnings, errors, endpoints and operational metadata remain owner-only.

create type public_source_warning as enum (
  'ZERO_DISCOVERY',
  'RUN_FAILED',
  'PARSE_BELOW_90',
  'POLICY_BLOCKED',
  'PARTIAL_COVERAGE'
);

create table public_source_health (
  source_adapter text primary key,
  source_name text not null,
  status adapter_status not null,
  last_run_status text check (
    last_run_status is null or last_run_status in ('RUNNING', 'SUCCEEDED', 'PARTIAL', 'FAILED')
  ),
  last_attempted_at timestamptz,
  last_successful_at timestamptz,
  discovered_count integer not null default 0 check (discovered_count >= 0),
  fetched_count integer not null default 0 check (fetched_count >= 0),
  parsed_count integer not null default 0 check (parsed_count >= 0),
  changed_count integer not null default 0 check (changed_count >= 0),
  failed_count integer not null default 0 check (failed_count >= 0),
  parse_success_rate numeric(5, 2) check (
    parse_success_rate is null or parse_success_rate between 0 and 100
  ),
  warning_codes public_source_warning[] not null default '{}',
  stale_after_hours integer not null default 36 check (stale_after_hours between 1 and 168),
  updated_at timestamptz not null default now()
);

alter table public_source_health enable row level security;

create policy public_read_source_health
  on public_source_health
  for select
  to anon, authenticated
  using (true);

grant select on public_source_health to anon, authenticated;
revoke insert, update, delete, truncate, references, trigger
  on public_source_health from anon, authenticated;

-- The publisher writes this projection through the server-only service key.
-- Supabase's role defaults do not grant DML on newly-created tables reliably,
-- so keep the required privileges explicit and withhold schema-level powers.
grant select, insert, update on public_source_health to service_role;
revoke delete, truncate, references, trigger on public_source_health from service_role;

comment on table public_source_health is
  'Anonymous run-health projection containing derived metrics and closed warning codes only; detailed source errors remain private.';
