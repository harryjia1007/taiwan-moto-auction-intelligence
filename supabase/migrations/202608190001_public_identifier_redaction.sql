-- Redact direct vehicle identifiers from the anonymous marketplace projection.
-- Private normalized records, evidence and raw artifacts remain unchanged.

create function public.__mask_public_plate(value text)
returns text
language plpgsql
immutable
strict
set search_path = ''
as $$
declare
  masked text := btrim(value);
  suffix text;
  total_count integer;
  target_count integer;
  masked_count integer := 0;
  character_index integer;
  character_value text;
begin
  total_count := char_length(regexp_replace(masked, '[^A-Za-z0-9]', '', 'g'));
  if total_count < 2 then
    return null;
  end if;

  suffix := substring(masked from '([A-Za-z0-9]+)$');
  if suffix is not null and char_length(suffix) >= 2 then
    target_count := least(3, char_length(suffix));
  else
    target_count := least(2, total_count);
  end if;

  for character_index in reverse char_length(masked)..1 loop
    character_value := substring(masked from character_index for 1);
    if character_value ~ '[A-Za-z0-9]' then
      masked := overlay(masked placing '*' from character_index for 1);
      masked_count := masked_count + 1;
      exit when masked_count = target_count;
    end if;
  end loop;
  return masked;
end;
$$;

create function public.__redact_public_identifiers(value text, plate_values text)
returns text
language plpgsql
immutable
set search_path = ''
as $$
declare
  redacted text := value;
  plate_value text;
  masked_plate text;
begin
  if redacted is null then
    return null;
  end if;

  if plate_values is not null then
    foreach plate_value in array string_to_array(plate_values, '、') loop
      masked_plate := public.__mask_public_plate(plate_value);
      if masked_plate is not null then
        redacted := replace(redacted, plate_value, masked_plate);
      end if;
    end loop;
  end if;

  redacted := regexp_replace(
    redacted,
    '((引擎|車身|車架|VIN)(號碼|號|碼)?[[:space:]]*[:：]?[[:space:]]*)[A-Za-z0-9-]{5,}',
    '\1已隱藏',
    'gi'
  );
  redacted := regexp_replace(
    redacted,
    '(^|[^A-Za-z0-9])([A-HJ-NPR-Z0-9]{17})([^A-Za-z0-9]|$)',
    '\1車身識別碼已隱藏\3',
    'gi'
  );
  return redacted;
end;
$$;

with masked as (
  select id, plate_number as original_plate,
         (
           select string_agg(public.__mask_public_plate(segment), '、' order by position)
           from unnest(string_to_array(plate_number, '、')) with ordinality as parts(segment, position)
         ) as masked_plate
  from public.public_live_motorcycle_listings
)
update public.public_live_motorcycle_listings as listing
set plate_number = masked.masked_plate,
    official_title = public.__redact_public_identifiers(listing.official_title, masked.original_plate),
    official_case_number = public.__redact_public_identifiers(listing.official_case_number, masked.original_plate),
    organization_name = public.__redact_public_identifiers(listing.organization_name, masked.original_plate),
    brand_name = public.__redact_public_identifiers(listing.brand_name, masked.original_plate),
    model_name = public.__redact_public_identifiers(listing.model_name, masked.original_plate),
    color = public.__redact_public_identifiers(listing.color, masked.original_plate),
    location = public.__redact_public_identifiers(listing.location, masked.original_plate),
    description = public.__redact_public_identifiers(listing.description, masked.original_plate),
    condition_summary = public.__redact_public_identifiers(listing.condition_summary, masked.original_plate),
    fee_notes = (
      select coalesce(
        array_agg(public.__redact_public_identifiers(note, masked.original_plate) order by position),
        '{}'::text[]
      )
      from unnest(listing.fee_notes) with ordinality as notes(note, position)
    ),
    official_url = case
      when listing.official_url <> public.__redact_public_identifiers(listing.official_url, masked.original_plate)
        then substring(listing.official_url from '^https://[^/]+') || '/'
      else listing.official_url
    end,
    photo_urls = (
      select coalesce(jsonb_agg(image_url order by position), '[]'::jsonb)
      from jsonb_array_elements(listing.photo_urls) with ordinality as images(image_url, position)
      where image_url #>> '{}' = public.__redact_public_identifiers(image_url #>> '{}', masked.original_plate)
    )
from masked
where listing.id = masked.id;

alter table public.public_live_motorcycle_listings
  drop constraint if exists public_live_plate_masked_chk;
alter table public.public_live_motorcycle_listings
  add constraint public_live_plate_masked_chk
  check (
    plate_number is null
    or (
      plate_number ~ '\*{2,}'
      and plate_number !~ '[A-Za-z0-9]{1,4}[-－][A-Za-z0-9]{2,4}'
    )
  );

comment on column public.public_live_motorcycle_listings.plate_number is
  'Partially masked official plate text (final 2-3 characters hidden), retained only through 30 days after the official auction end time.';

drop function public.__redact_public_identifiers(text, text);
drop function public.__mask_public_plate(text);
