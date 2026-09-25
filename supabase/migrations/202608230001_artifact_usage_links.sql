-- A checksum-addressed artifact may be reused by several records and snapshots.
-- Model every use explicitly so retention and offline reprocessing do not
-- mistake the first source_record_id owner for the only evidence consumer.

create table source_record_artifacts (
  id uuid primary key default gen_random_uuid(),
  source_record_id uuid not null references source_records(id) on delete cascade,
  artifact_id uuid not null references raw_artifacts(id),
  first_sync_run_id uuid references sync_runs(id),
  last_sync_run_id uuid references sync_runs(id),
  artifact_role text not null check (artifact_role in ('PRIMARY','SUPPORTING')),
  sort_order integer not null default 0 check (sort_order >= 0),
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  unique (source_record_id,artifact_id)
);

with historical_usage as (
  select ra.source_record_id,ra.id as artifact_id,ra.sync_run_id,
         'SUPPORTING'::text as artifact_role,0 as sort_order,
         ra.fetched_at as observed_at
  from raw_artifacts ra
  union all
  select snapshot.source_record_id,snapshot.artifact_id,null::uuid,
         'PRIMARY',0,snapshot.observed_at
  from snapshots snapshot where snapshot.artifact_id is not null
  union all
  select document.source_record_id,document.artifact_id,null::uuid,
         'SUPPORTING',1,document.created_at
  from documents document where document.artifact_id is not null
  union all
  select photo.source_record_id,photo.artifact_id,null::uuid,
         'SUPPORTING',1,greatest(photo.first_seen_at,photo.last_seen_at)
  from photos photo where photo.artifact_id is not null
  union all
  select evidence.source_record_id,evidence.artifact_id,null::uuid,
         'SUPPORTING',1,evidence.created_at
  from field_evidence evidence
), aggregated_usage as (
  select source_record_id,artifact_id,
         case when bool_or(artifact_role='PRIMARY') then 'PRIMARY' else 'SUPPORTING' end as artifact_role,
         min(sort_order) as sort_order,
         min(observed_at) as first_seen_at,
         max(observed_at) as last_seen_at
  from historical_usage
  group by source_record_id,artifact_id
)
insert into source_record_artifacts
  (source_record_id,artifact_id,first_sync_run_id,last_sync_run_id,
   artifact_role,sort_order,first_seen_at,last_seen_at)
select usage.source_record_id,usage.artifact_id,artifact.sync_run_id,artifact.sync_run_id,
       usage.artifact_role,usage.sort_order,usage.first_seen_at,usage.last_seen_at
from aggregated_usage usage
join raw_artifacts artifact on artifact.id=usage.artifact_id
on conflict (source_record_id,artifact_id) do nothing;

create index source_record_artifacts_artifact_idx
  on source_record_artifacts (artifact_id,source_record_id,last_seen_at);
create index source_record_artifacts_source_idx
  on source_record_artifacts (source_record_id,artifact_role,sort_order);

alter table source_record_artifacts enable row level security;
create policy owner_read_source_record_artifacts
  on source_record_artifacts for select to authenticated using ((select private.is_owner()));
grant select on source_record_artifacts to authenticated;

comment on table source_record_artifacts is
  'Explicit many-to-many artifact usage for retention, evidence audit and exact offline reprocessing.';
