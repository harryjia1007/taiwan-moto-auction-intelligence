-- The hosted scheduler uses the Supabase service role through PostgREST rather
-- than a direct database password. Supabase's default table ACLs can leave that
-- role with destructive privileges but without the read/write permissions the
-- publisher actually needs. Replace those defaults with an explicit, minimal
-- capability set for the reviewed ingestion path.

-- The publisher needs to resolve reviewed objects, but it must never be able
-- to create replacement tables, functions, or other objects in the public
-- schema even if an upstream default ACL changes.
revoke create on schema public from service_role;
grant usage on schema public to service_role;

-- Start from no data-plane capability anywhere in the application schema.
-- This closes destructive privileges inherited from Supabase's historical
-- defaults on tables the hosted publisher does not use as well as those it
-- does. New migration-owned tables and sequences inherit the same posture.
revoke all privileges on all tables in schema public from service_role;
revoke all privileges on all sequences in schema public from service_role;
alter default privileges in schema public
  revoke all privileges on tables from service_role;
alter default privileges in schema public
  revoke all privileges on sequences from service_role;

grant select, update on sources to service_role;
grant select on source_access_policies, artifact_tombstones to service_role;
grant select, insert, update on sync_runs, source_records to service_role;
grant select, insert on raw_artifacts to service_role;
-- PostgREST upserts and filtered PATCH operations also require SELECT even
-- when the response preference is return=minimal.
grant select, insert, update on source_record_artifacts, documents to service_role;
grant select, insert on snapshots to service_role;
grant select, insert, update on public_live_motorcycle_listings to service_role;
grant select, insert, update on public_source_health to service_role;
