-- Defense in depth for the anonymous projection. Publisher-side redaction is
-- still required, but an active row containing a Taiwan national ID, phone
-- number or email address must also fail at the database boundary.

create or replace function public.public_text_contains_contact_identifier(value text)
returns boolean
language plpgsql
immutable
set search_path = ''
as $$
declare
  normalized text := lower(coalesce(value, ''));
  ascii_code integer;
begin
  -- Decode printable percent-encoded ASCII. Iterating in ascending order also
  -- catches common double-encoding such as %2540 for an email @ character.
  for ascii_code in 32..126 loop
    normalized := replace(
      normalized,
      '%' || lpad(to_hex(ascii_code), 2, '0'),
      chr(ascii_code)
    );
  end loop;

  return normalized ~ '(?<![a-z0-9])[a-z][12][0-9]{8}(?![a-z0-9])'
    or normalized ~ '[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}'
    or normalized ~ '(?<![0-9])09[0-9]{2}[-－ .]?[0-9]{3}[-－ .]?[0-9]{3}(?![0-9])'
    or normalized ~ '(?<![0-9])0[0-9]{1,2}[-－ ]?[0-9]{6,8}([[:space:]]*(#|分機)[[:space:]]*[0-9]+)?(?![0-9])';
end;
$$;

create function public.__redact_public_contact_identifier(value text)
returns text
language plpgsql
immutable
strict
set search_path = ''
as $$
declare
  redacted text := value;
begin
  redacted := regexp_replace(
    redacted,
    '(?<![A-Za-z0-9])[A-Z][12][0-9]{8}(?![A-Za-z0-9])',
    '身分證字號已隱去',
    'gi'
  );
  redacted := regexp_replace(
    redacted,
    '(?<![0-9])(09[0-9]{2}([-－ .]?[0-9]{3}){2}|0[0-9]{1,2}[-－ ]?[0-9]{6,8})([[:space:]]*(#|分機)[[:space:]]*[0-9]+)?(?![0-9])',
    '聯絡電話已隱藏',
    'gi'
  );
  redacted := regexp_replace(
    redacted,
    '[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}',
    '聯絡信箱已隱藏',
    'gi'
  );
  return redacted;
end;
$$;

-- Keep the migration deployable even if a legacy publisher wrote unsafe
-- values. Such rows are sanitized and deactivated for operator review rather
-- than causing the release migration to stop halfway through.
with unsafe as (
  select
    listing.id as old_id,
    'redacted-' || substr(
      md5(listing.source_adapter || ':' || listing.source_record_id),
      1,
      20
    ) as safe_source_record_id
  from public.public_live_motorcycle_listings as listing
  where public.public_text_contains_contact_identifier(
    concat_ws(
      ' ', listing.id, listing.source_adapter, listing.source_record_id,
      listing.source_name, listing.official_url, listing.official_title,
      listing.official_case_number, listing.organization_name,
      listing.vehicle_category, listing.car_category, listing.brand_name,
      listing.model_name, listing.color, listing.plate_number, listing.location,
      listing.description, listing.condition_summary,
      array_to_string(listing.fee_notes, ' '), listing.documents::text,
      listing.completeness_groups::text
    )
  )
)
update public.public_live_motorcycle_listings as listing
set id = listing.source_adapter || '-' || unsafe.safe_source_record_id,
    source_record_id = unsafe.safe_source_record_id,
    source_name = public.__redact_public_contact_identifier(listing.source_name),
    official_url = case
      when public.public_text_contains_contact_identifier(listing.official_url)
        then coalesce(
          substring(listing.official_url from '^https://[^/]+'),
          'https://www.gov.tw'
        ) || '/'
      else listing.official_url
    end,
    official_title = public.__redact_public_contact_identifier(listing.official_title),
    official_case_number = public.__redact_public_contact_identifier(listing.official_case_number),
    organization_name = public.__redact_public_contact_identifier(listing.organization_name),
    brand_name = public.__redact_public_contact_identifier(listing.brand_name),
    model_name = public.__redact_public_contact_identifier(listing.model_name),
    color = public.__redact_public_contact_identifier(listing.color),
    plate_number = case
      when public.public_text_contains_contact_identifier(listing.plate_number) then null
      else listing.plate_number
    end,
    location = public.__redact_public_contact_identifier(listing.location),
    description = public.__redact_public_contact_identifier(listing.description),
    condition_summary = public.__redact_public_contact_identifier(listing.condition_summary),
    fee_notes = (
      select coalesce(
        array_agg(
          public.__redact_public_contact_identifier(note) order by position
        ),
        '{}'::text[]
      )
      from unnest(listing.fee_notes) with ordinality as notes(note, position)
    ),
    documents = (
      select coalesce(jsonb_agg(document order by position), '[]'::jsonb)
      from jsonb_array_elements(listing.documents)
        with ordinality as entries(document, position)
      where not public.public_text_contains_contact_identifier(document::text)
    ),
    completeness_groups = case
      when public.public_text_contains_contact_identifier(listing.completeness_groups::text)
        then '{}'::jsonb
      else listing.completeness_groups
    end,
    active = false,
    content_checksum = md5(
      listing.content_checksum || ':contact-identifier-redacted:' || unsafe.safe_source_record_id
    )
from unsafe
where listing.id = unsafe.old_id;

alter table public.public_live_motorcycle_listings
  drop constraint if exists public_live_contact_identifiers_safe_chk;
alter table public.public_live_motorcycle_listings
  add constraint public_live_contact_identifiers_safe_chk
  check (
    not public.public_text_contains_contact_identifier(
      concat_ws(
        ' ', id, source_adapter, source_record_id, source_name, official_url,
        official_title, official_case_number, organization_name,
        vehicle_category, car_category, brand_name, model_name, color,
        plate_number, location, description, condition_summary,
        array_to_string(fee_notes, ' '), documents::text,
        completeness_groups::text
      )
    )
  );

revoke all on function public.public_text_contains_contact_identifier(text)
  from public, anon, authenticated;
grant execute on function public.public_text_contains_contact_identifier(text)
  to service_role;

drop function public.__redact_public_contact_identifier(text);

comment on constraint public_live_contact_identifiers_safe_chk
  on public.public_live_motorcycle_listings is
  'Fail-closed anonymous boundary for direct or percent-encoded Taiwan IDs, phone numbers and email addresses.';
