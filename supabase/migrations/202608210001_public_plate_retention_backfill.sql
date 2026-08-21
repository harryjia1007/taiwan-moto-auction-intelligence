-- Enforce the public plate retention window for rows published before the
-- hosted publisher began running the same cleanup after every sync.
--
-- Private normalized records, snapshots, evidence and artifacts are not
-- changed. Re-running this migration is safe because only non-null public
-- projection values outside the retention window are selected.

update public.public_live_motorcycle_listings
set plate_number = null
where plate_number is not null
  and ends_at < now() - interval '30 days';
