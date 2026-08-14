-- The public portfolio demo is static. The hosted operational database is
-- owner-only, so the anonymous Data API role needs no database object grants.

revoke all privileges on all tables in schema public from anon;
revoke all privileges on all sequences in schema public from anon;
revoke execute on all functions in schema public from anon;

alter default privileges in schema public revoke all privileges on tables from anon;
alter default privileges in schema public revoke all privileges on sequences from anon;
alter default privileges in schema public revoke execute on functions from anon;
