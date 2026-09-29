-- Make favorites work for both individually identified vehicles and official
-- inseparable lots, and enforce anonymous-publication policy in the database.

alter table favorites
  add column if not exists id uuid default gen_random_uuid(),
  add column if not exists lot_id uuid references lots(id) on delete cascade;

alter table favorites drop constraint if exists favorites_pkey;
alter table favorites alter column id set not null;
alter table favorites add constraint favorites_pkey primary key (id);
alter table favorites alter column vehicle_id drop not null;

-- Preserve the owner's intent when a newer parser retires invented vehicle
-- clones and exposes the official inseparable lot instead.
update favorites as favorite
set lot_id = vehicle.lot_id,
    vehicle_id = null
from vehicles as vehicle
where favorite.vehicle_id = vehicle.id
  and not vehicle.projection_active
  and not exists (
    select 1
    from vehicles as current_vehicle
    where current_vehicle.lot_id = vehicle.lot_id
      and current_vehicle.projection_active
  );

delete from favorites as duplicate
using favorites as canonical
where duplicate.id > canonical.id
  and duplicate.user_id = canonical.user_id
  and duplicate.lot_id is not null
  and duplicate.lot_id = canonical.lot_id;

alter table favorites
  add constraint favorites_exactly_one_listing_chk
  check (num_nonnulls(vehicle_id, lot_id) = 1);

create unique index favorites_user_vehicle_uidx
  on favorites (user_id, vehicle_id)
  where vehicle_id is not null;
create unique index favorites_user_lot_uidx
  on favorites (user_id, lot_id)
  where lot_id is not null;
create index favorites_lot_id_idx on favorites (lot_id) where lot_id is not null;

-- The trigger is deferred so an ingestion transaction can first retire every
-- old projection and then reactivate the exact current vehicles. Only a lot
-- that has no current vehicle at transaction end inherits retired favorites.
create or replace function migrate_retired_vehicle_favorite_to_lot()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.projection_active or old.projection_active = new.projection_active then
    return new;
  end if;
  if exists (
    select 1 from public.vehicles as current_vehicle
    where current_vehicle.lot_id = new.lot_id
      and current_vehicle.projection_active
  ) then
    return new;
  end if;
  insert into public.favorites (user_id, lot_id, created_at)
  select favorite.user_id, new.lot_id, favorite.created_at
  from public.favorites as favorite
  where favorite.vehicle_id = new.id
    and not exists (
      select 1 from public.favorites as existing
      where existing.user_id = favorite.user_id
        and existing.lot_id = new.lot_id
    );
  delete from public.favorites where vehicle_id = new.id;
  return new;
end;
$$;

revoke all on function migrate_retired_vehicle_favorite_to_lot() from public, anon, authenticated;

drop trigger if exists vehicles_migrate_retired_favorites on vehicles;
create constraint trigger vehicles_migrate_retired_favorites
after update of projection_active on vehicles
deferrable initially deferred
for each row
when (old.projection_active and not new.projection_active)
execute function migrate_retired_vehicle_favorite_to_lot();

-- Add the stable owning lot to the read model. A lot favorite can therefore
-- remain meaningful if a later parser exposes separable current vehicles.
create or replace view vehicle_marketplace_listing with (security_invoker = true) as
select v.id, v.id as vehicle_id, 'vehicle'::text as listing_entity,
       s.id as source_id, s.name as source_name, s.family as source_family, s.adapter_name as source_adapter,
       sr.id as source_record_id, sr.source_record_id as source_auid,
       sr.official_url, sr.original_title as official_title,
       coalesce(vm.canonical_name, v.original_model, l.title) as model_name,
       coalesce(vb.canonical_name, v.original_brand) as brand_name,
       v.manufacture_year, v.manufacture_month, v.displacement_cc, v.vehicle_type,
       v.vehicle_category, v.car_category, v.color, v.mileage_km,
       o.canonical_name as organization_name, l.storage_location,
       ac.disposal_origin, ae.status as auction_status, ae.round_number,
       ae.ends_at as auction_at, ae.reserve_price, ae.current_price, ae.sold_price,
       ae.deposit, ae.payment_deadline, ae.pickup_deadline, l.fee_notes,
       l.eligibility, v.registration_status, v.has_key, v.can_start, v.can_test,
       l.lot_size, l.bulk_lot, v.condition_summary, v.completeness,
       v.completeness_groups, p.source_url as primary_image_url,
       plate.normalized_value as plate_number,
       taiwan_county_from_text(concat_ws(' ', l.storage_location, o.canonical_name)) as county,
       coalesce(ae.sold_price, ae.current_price, ae.reserve_price) as display_price,
       (p.storage_path is not null) as has_cached_photo,
       lower(concat_ws(' ', sr.original_title, coalesce(vb.canonical_name, v.original_brand),
         coalesce(vm.canonical_name, v.original_model, l.title), plate.normalized_value,
         o.canonical_name, l.storage_location, sr.source_record_id, v.vehicle_type,
         v.vehicle_category, v.car_category)) as search_text,
       l.id as lot_id
from vehicles v
join lots l on l.id = v.lot_id
join auction_events ae on ae.id = l.auction_event_id
join auction_cases ac on ac.id = ae.auction_case_id
join source_records sr on sr.id = ae.source_record_id
join sources s on s.id = sr.source_id
left join organizations o on o.id = ac.organization_id
left join vehicle_brands vb on vb.id = v.brand_id
left join vehicle_models vm on vm.id = v.model_id
left join lateral (
  select source_url, storage_path from photos where vehicle_id = v.id and storage_path is not null order by sort_order limit 1
) p on true
left join lateral (
  select normalized_value from vehicle_identifiers
  where vehicle_id = v.id and identifier_type = 'PLATE' and projection_active
  order by id limit 1
) plate on true
where v.projection_active
union all
select l.id, null::uuid, 'lot'::text,
       s.id, s.name, s.family, s.adapter_name,
       sr.id, sr.source_record_id, sr.official_url, sr.original_title,
       l.title, null::text, null::integer, null::integer, null::integer,
       l.vehicle_type, l.vehicle_category, l.car_category, null::text, null::integer,
       o.canonical_name, l.storage_location,
       ac.disposal_origin, ae.status, ae.round_number,
       ae.ends_at, ae.reserve_price, ae.current_price, ae.sold_price,
       ae.deposit, ae.payment_deadline, ae.pickup_deadline, l.fee_notes,
       l.eligibility, l.registration_status, l.has_key, l.can_start, l.can_test,
       l.lot_size, l.bulk_lot, l.condition_summary, l.completeness,
       l.completeness_groups, p.source_url, null::text,
       taiwan_county_from_text(concat_ws(' ', l.storage_location, o.canonical_name)),
       coalesce(ae.sold_price, ae.current_price, ae.reserve_price),
       (p.storage_path is not null),
       lower(concat_ws(' ', sr.original_title, l.title, o.canonical_name,
         l.storage_location, sr.source_record_id, l.vehicle_type,
         l.vehicle_category, l.car_category)),
       l.id
from lots l
join auction_events ae on ae.id = l.auction_event_id
join auction_cases ac on ac.id = ae.auction_case_id
join source_records sr on sr.id = ae.source_record_id
join sources s on s.id = sr.source_id
left join organizations o on o.id = ac.organization_id
left join lateral (
  select source_url, storage_path from photos where lot_id = l.id and storage_path is not null order by sort_order limit 1
) p on true
where not exists (
  select 1 from vehicles v where v.lot_id = l.id and v.projection_active
);

grant select on vehicle_marketplace_listing to authenticated;

-- Match the reviewed Python outbound-link contract at the database boundary.
-- The document object itself is also closed: anonymous JSON may contain only a
-- fixed label and one official URL, never private metadata or Storage paths.
create or replace function public_document_links_are_safe(
  adapter text,
  document_list jsonb
)
returns boolean
language plpgsql
immutable
set search_path = ''
as $$
declare
  document jsonb;
  document_url text;
  query_string text;
  query_pair text;
  query_key text;
  query_value text;
  seen_keys text[];
  path_value text;
  name_value text;
  download_value text;
begin
  if jsonb_typeof(document_list) <> 'array' then
    return false;
  end if;
  for document in select value from jsonb_array_elements(document_list)
  loop
    if jsonb_typeof(document) <> 'object' then
      return false;
    end if;
    if not (document ? 'label')
       or not (document ? 'url')
       or (document - 'label' - 'url') <> '{}'::jsonb
       or jsonb_typeof(document -> 'label') <> 'string'
       or btrim(document ->> 'label') = ''
       or jsonb_typeof(document -> 'url') <> 'string' then
      return false;
    end if;
    document_url := document ->> 'url';
    if document_url ~ '[[:cntrl:]]'
       or document_url like '%#%'
       or document_url !~ '^https://'
       or document_url ~ '^https://[^/]*@'
       or split_part(document_url, '?', 1) like '%;%' then
      return false;
    end if;

    if adapter = 'judicial' then
      if document_url !~* '^https://aomp109[.]judicial[.]gov[.]tw(:443)?/judbp/wkw/WHD1A02/DO_VIEWPDF[.]htm[?]filenm=[^&#]+[.]pdf$' then
        return false;
      end if;
    elsif adapter = 'moj_enforcement' then
      if document_url !~ '^https://www[.]tpkonsale[.]moj[.]gov[.]tw(:443)?/File/Download[?][^#]+$' then
        return false;
      end if;
      query_string := split_part(document_url, '?', 2);
      seen_keys := '{}';
      path_value := null;
      name_value := null;
      download_value := null;
      foreach query_pair in array string_to_array(query_string, '&')
      loop
        if query_pair = '' or strpos(query_pair, '=') = 0 then
          return false;
        end if;
        query_key := split_part(query_pair, '=', 1);
        query_value := substr(query_pair, strpos(query_pair, '=') + 1);
        if query_key not in ('PATH', 'NAME', 'DOWNLOAD')
           or query_key = any(seen_keys) then
          return false;
        end if;
        seen_keys := array_append(seen_keys, query_key);
        if query_key = 'PATH' then path_value := query_value;
        elsif query_key = 'NAME' then name_value := query_value;
        else download_value := query_value;
        end if;
      end loop;
      if path_value is null
         or path_value !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
         or name_value is null
         or name_value !~* '[.]pdf$'
         or name_value ~* '(/|\\|%2f|%5c)'
         or (download_value is not null and download_value !~* '[.]pdf$') then
        return false;
      end if;
    elsif adapter = 'customs' then
      if document_url !~* '^https://web[.]customs[.]gov[.]tw(:443)?/download/[^#]+$' then
        return false;
      end if;
    elsif adapter = 'moj_enforcement_cms' then
      if document_url !~* '^https://www[.](tpy|sly|pcy|tyy|scy|tcy|chy|cyy|tny|ksy|pty|hly|ily)[.]moj[.]gov[.]tw(:443)?/media/[^?#]*[.]pdf([?][^#]*)?$' then
        return false;
      end if;
    elsif adapter = 'moj_auction' then
      if document_url !~* '^https://(auction[.]moj[.]gov[.]tw|www[.](tcc|qtc|ulc)[.]moj[.]gov[.]tw)(:443)?/[^?#]*[.]pdf([?][^#]*)?$' then
        return false;
      end if;
    else
      return false;
    end if;
  end loop;
  return true;
end;
$$;

revoke all on function public_document_links_are_safe(text,jsonb) from public, anon, authenticated;
grant execute on function public_document_links_are_safe(text,jsonb) to service_role;

alter table public_live_motorcycle_listings
  drop constraint if exists public_live_document_links_safe_chk;
update public_live_motorcycle_listings
set documents = '[]'::jsonb
where not public_document_links_are_safe(source_adapter, documents);
alter table public_live_motorcycle_listings
  add constraint public_live_document_links_safe_chk
  check (public_document_links_are_safe(source_adapter, documents));

-- No integrated source currently has reviewed anonymous photo redistribution
-- rights. Enforce that decision in PostgreSQL as well as in the publisher.
update public_live_motorcycle_listings set photo_urls = '[]'::jsonb
where photo_urls <> '[]'::jsonb;
alter table public_live_motorcycle_listings
  drop constraint if exists public_live_photo_urls_empty_chk;
alter table public_live_motorcycle_listings
  add constraint public_live_photo_urls_empty_chk
  check (photo_urls = '[]'::jsonb);

-- Every public row is checked atomically against the persisted source policy.
-- Unknown adapters and any decision other than ALLOW are stored inactive.
create or replace function enforce_public_listing_access_policy()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  publication_allowed boolean;
begin
  if not new.active then
    return new;
  end if;
  select exists (
    select 1
    from public.sources as source
    join public.source_access_policies as policy on policy.source_id = source.id
    where source.adapter_name = new.source_adapter
      and policy.decision = 'ALLOW'
  ) into publication_allowed;
  new.active := publication_allowed;
  return new;
end;
$$;

revoke all on function enforce_public_listing_access_policy() from public, anon, authenticated;

drop trigger if exists public_listing_access_policy_gate on public_live_motorcycle_listings;
create trigger public_listing_access_policy_gate
before insert or update on public_live_motorcycle_listings
for each row execute function enforce_public_listing_access_policy();

create or replace function deactivate_public_listings_for_policy()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  affected_source_id uuid;
  affected_decision text;
  affected_adapter text;
begin
  affected_source_id := case when tg_op = 'DELETE' then old.source_id else new.source_id end;
  affected_decision := case when tg_op = 'DELETE' then 'DISABLED' else new.decision end;
  if affected_decision = 'ALLOW' then
    if tg_op = 'DELETE' then return old; else return new; end if;
  end if;
  select adapter_name into affected_adapter
  from public.sources where id = affected_source_id;
  if affected_adapter is not null then
    update public.public_live_motorcycle_listings
    set active = false
    where source_adapter = affected_adapter
      and active;
  end if;
  if tg_op = 'DELETE' then return old; else return new; end if;
end;
$$;

revoke all on function deactivate_public_listings_for_policy() from public, anon, authenticated;

drop trigger if exists source_policy_deactivates_public_listings on source_access_policies;
create trigger source_policy_deactivates_public_listings
after insert or update of decision on source_access_policies
for each row execute function deactivate_public_listings_for_policy();

drop trigger if exists source_policy_delete_deactivates_public_listings on source_access_policies;
create trigger source_policy_delete_deactivates_public_listings
before delete on source_access_policies
for each row execute function deactivate_public_listings_for_policy();

-- Correct any legacy row that predates the atomic trigger.
update public_live_motorcycle_listings as listing
set active = false
where listing.active
  and not exists (
    select 1
    from sources as source
    join source_access_policies as policy on policy.source_id = source.id
    where source.adapter_name = listing.source_adapter
      and policy.decision = 'ALLOW'
  );

comment on table favorites is
  'Owner-only favorites for either an identified vehicle or an official inseparable lot.';
comment on column vehicle_marketplace_listing.lot_id is
  'Stable owning lot used to preserve favorites across conservative projection changes.';
comment on constraint public_live_photo_urls_empty_chk on public_live_motorcycle_listings is
  'Anonymous photo redistribution remains disabled until a reviewed rights migration changes this gate.';
