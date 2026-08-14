-- Harden owner authorization helpers and add indexes reported by the hosted
-- database advisors. Keep the authorization helper outside the exposed API
-- schema so it cannot become a public RPC endpoint.

create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated;

create or replace function private.is_owner()
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public
as $$
  select exists (
    select 1
    from public.app_settings
    where lower(coalesce(auth.jwt() ->> 'email', '')) = owner_email
  );
$$;

revoke all on function private.is_owner() from public, anon;
grant execute on function private.is_owner() to authenticated;

do $$
declare table_name text;
begin
  foreach table_name in array array[
    'organizations','sources','source_endpoints','sync_runs','source_records','raw_artifacts','snapshots',
    'auction_cases','auction_events','lots','vehicle_brands','vehicle_models','vehicle_model_aliases','vehicles',
    'vehicle_identifiers','vehicle_observations','photos','documents','field_evidence','cross_source_links',
    'probable_duplicates','favorites','saved_searches','app_settings'
  ] loop
    execute format(
      'alter policy owner_read on public.%I using ((select private.is_owner()))',
      table_name
    );
  end loop;
end $$;

alter policy owner_insert_favorites on public.favorites
  with check ((select private.is_owner()) and user_id = (select auth.uid()));
alter policy owner_delete_favorites on public.favorites
  using ((select private.is_owner()) and user_id = (select auth.uid()));
alter policy owner_manage_saved_searches on public.saved_searches
  using ((select private.is_owner()) and user_id = (select auth.uid()))
  with check ((select private.is_owner()) and user_id = (select auth.uid()));

drop policy owner_read on public.saved_searches;

alter policy owner_read_source_access_policies on public.source_access_policies
  using ((select private.is_owner()));
alter policy owner_read_artifact_tombstones on public.artifact_tombstones
  using ((select private.is_owner()));
alter policy owner_read_data_subject_requests on public.data_subject_requests
  using ((select private.is_owner()));
alter policy owner_read_raw_artifacts on storage.objects
  using (bucket_id = 'raw-artifacts' and (select private.is_owner()));

drop function public.is_owner();

alter function public.touch_updated_at() set search_path = pg_catalog, public;
alter function public.reject_immutable_mutation() set search_path = pg_catalog, public;
alter function public.taiwan_county_from_text(text) set search_path = pg_catalog, public;

create schema if not exists extensions;
alter extension pg_trgm set schema extensions;

create index if not exists auction_cases_organization_id_idx on public.auction_cases (organization_id);
create index if not exists auction_events_auction_case_id_idx on public.auction_events (auction_case_id);
create index if not exists cross_source_links_right_record_idx on public.cross_source_links (right_source_record_id);
create index if not exists documents_artifact_id_idx on public.documents (artifact_id);
create index if not exists favorites_vehicle_id_idx on public.favorites (vehicle_id);
create index if not exists field_evidence_artifact_id_idx on public.field_evidence (artifact_id);
create index if not exists field_evidence_source_record_id_idx on public.field_evidence (source_record_id);
create index if not exists photos_artifact_id_idx on public.photos (artifact_id);
create index if not exists probable_duplicates_right_vehicle_id_idx on public.probable_duplicates (right_vehicle_id);
create index if not exists raw_artifacts_source_record_id_idx on public.raw_artifacts (source_record_id);
create index if not exists raw_artifacts_sync_run_id_idx on public.raw_artifacts (sync_run_id);
create index if not exists saved_searches_user_id_idx on public.saved_searches (user_id);
create index if not exists snapshots_artifact_id_idx on public.snapshots (artifact_id);
create index if not exists sources_organization_id_idx on public.sources (organization_id);
create index if not exists sync_runs_source_id_idx on public.sync_runs (source_id);
create index if not exists vehicle_observations_snapshot_id_idx on public.vehicle_observations (snapshot_id);
create index if not exists vehicles_brand_id_idx on public.vehicles (brand_id);
create index if not exists vehicles_model_id_idx on public.vehicles (model_id);
