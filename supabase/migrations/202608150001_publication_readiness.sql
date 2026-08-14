-- Publication-readiness controls: source access policy, retention audit, and CC filtering.

alter table raw_artifacts add column if not exists retention_until timestamptz;
update raw_artifacts ra
set retention_until = coalesce(
  (select max(ae.ends_at) + interval '12 months' from auction_events ae where ae.source_record_id=ra.source_record_id),
  ra.fetched_at + interval '12 months'
)
where retention_until is null;
alter table raw_artifacts alter column retention_until set not null;

create table source_access_policies (
  source_id uuid primary key references sources(id) on delete cascade,
  decision text not null check (decision in ('ALLOW','MANUAL_ONLY','REVIEW_REQUIRED','DISABLED')),
  robots_url text not null,
  terms_url text,
  photo_rights text not null,
  personal_data_risk text not null,
  checked_on date not null,
  rationale text not null,
  permission_reference text,
  updated_at timestamptz not null default now()
);

create table artifact_tombstones (
  id uuid primary key default gen_random_uuid(),
  artifact_id uuid not null unique references raw_artifacts(id),
  storage_path text not null,
  checksum_sha256 text not null,
  reason text not null,
  deleted_at timestamptz not null default now()
);

create table data_subject_requests (
  id uuid primary key default gen_random_uuid(),
  request_type text not null check (request_type in ('ACCESS','CORRECTION','STOP_USE','DELETE')),
  requester_email text not null,
  request_scope text not null,
  status text not null default 'RECEIVED' check (status in ('RECEIVED','ACKNOWLEDGED','IN_REVIEW','COMPLETED','REJECTED')),
  received_at timestamptz not null default now(),
  acknowledged_at timestamptz,
  decided_at timestamptz,
  decision_notes text
);

update sources
set status='PARTIAL',
    automation_level='HUMAN_OFFICIAL_MANIFEST',
    parser_version='1.3.0'
where adapter_name='judicial';
update sources set status='DEGRADED', automation_level='LEGAL_REVIEW_REQUIRED' where adapter_name='pcc';

create index if not exists vehicles_displacement_cc_idx on vehicles (displacement_cc);
create index if not exists raw_artifacts_retention_idx on raw_artifacts (retention_until);

alter table source_access_policies enable row level security;
alter table artifact_tombstones enable row level security;
alter table data_subject_requests enable row level security;
create trigger artifact_tombstones_immutable before update or delete on artifact_tombstones for each row execute function reject_immutable_mutation();
create policy owner_read_source_access_policies on source_access_policies for select to authenticated using (is_owner());
create policy owner_read_artifact_tombstones on artifact_tombstones for select to authenticated using (is_owner());
create policy owner_read_data_subject_requests on data_subject_requests for select to authenticated using (is_owner());
grant select on source_access_policies, artifact_tombstones, data_subject_requests to authenticated;

comment on table artifact_tombstones is 'Append-only audit records for deleted private artifact bytes; immutable artifact metadata and checksums remain.';
comment on column raw_artifacts.retention_until is 'Default private-byte retention deadline; deletion is recorded in artifact_tombstones.';
