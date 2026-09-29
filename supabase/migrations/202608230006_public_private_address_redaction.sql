-- Redact explicitly labelled private residential/contact addresses from the
-- anonymous projection while preserving official vehicle viewing/storage
-- locations. Future writes are guarded by a CHECK constraint as defense in
-- depth; the Python publisher performs the same transformation before upsert.

create or replace function public.__redact_public_private_address(value text)
returns text
language sql
immutable
strict
set search_path = ''
as $$
  select regexp_replace(
    value,
    '((義務人|債務人|所有人|車主|被告|受刑人|保管人|姓名)[^，,。；;\n]{0,20})?(戶籍地址|通訊地址|聯絡地址|送達地址|住址|住所|居所)[[:space:]]*[:：]?[[:space:]]*[^，,。；;\n]{4,100}',
    '\3：已隱去',
    'g'
  )
$$;

create or replace function public.public_text_contains_private_address(value text)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select coalesce(
    regexp_replace(
      value,
      '(戶籍地址|通訊地址|聯絡地址|送達地址|住址|住所|居所)[[:space:]]*[:：]?[[:space:]]*已隱去',
      '',
      'g'
    ) ~ '((義務人|債務人|所有人|車主|被告|受刑人|保管人|姓名)[^，,。；;\n]{0,20})?(戶籍地址|通訊地址|聯絡地址|送達地址|住址|住所|居所)[[:space:]]*[:：]?[[:space:]]*[^，,。；;\n]{4,100}'
    or lower(value) ~ '(%e6%88%b6%e7%b1%8d%e5%9c%b0%e5%9d%80|%e9%80%9a%e8%a8%8a%e5%9c%b0%e5%9d%80|%e8%81%af%e7%b5%a1%e5%9c%b0%e5%9d%80|%e9%80%81%e9%81%94%e5%9c%b0%e5%9d%80|%e4%bd%8f%e5%9d%80|%e4%bd%8f%e6%89%80|%e5%b1%85%e6%89%80)',
    false
  )
$$;

with prepared as (
  select
    listing.id as old_id,
    case
      when public.public_text_contains_private_address(listing.source_record_id)
        then 'redacted-' || substr(md5(listing.source_adapter || ':' || listing.source_record_id), 1, 20)
      else listing.source_record_id
    end as safe_source_record_id
  from public.public_live_motorcycle_listings as listing
)
update public.public_live_motorcycle_listings as listing
set id = listing.source_adapter || '-' || prepared.safe_source_record_id,
    source_record_id = prepared.safe_source_record_id,
    source_name = public.__redact_public_private_address(listing.source_name),
    official_url = case
      when public.public_text_contains_private_address(listing.official_url)
        then coalesce(substring(listing.official_url from '^https://[^/]+'), 'https://www.gov.tw/') || '/'
      else listing.official_url
    end,
    official_title = public.__redact_public_private_address(listing.official_title),
    official_case_number = public.__redact_public_private_address(listing.official_case_number),
    organization_name = public.__redact_public_private_address(listing.organization_name),
    brand_name = public.__redact_public_private_address(listing.brand_name),
    model_name = public.__redact_public_private_address(listing.model_name),
    color = public.__redact_public_private_address(listing.color),
    location = public.__redact_public_private_address(listing.location),
    description = public.__redact_public_private_address(listing.description),
    condition_summary = public.__redact_public_private_address(listing.condition_summary),
    fee_notes = (
      select coalesce(
        array_agg(public.__redact_public_private_address(note) order by position),
        '{}'::text[]
      )
      from unnest(listing.fee_notes) with ordinality as notes(note, position)
    ),
    documents = (
      select coalesce(
        jsonb_agg(
          jsonb_build_object(
            'label', public.__redact_public_private_address(coalesce(document ->> 'label', '官方附件')),
            'url', document ->> 'url'
          )
          order by position
        ),
        '[]'::jsonb
      )
      from jsonb_array_elements(listing.documents) with ordinality as entries(document, position)
      where jsonb_typeof(document) = 'object'
        and not public.public_text_contains_private_address(coalesce(document ->> 'url', ''))
    )
from prepared
where listing.id = prepared.old_id;

update public.public_live_motorcycle_listings as listing
set content_checksum = md5(concat_ws(
  '|', listing.source_adapter, listing.source_record_id, listing.official_url,
  listing.official_title, listing.official_case_number, listing.organization_name,
  listing.plate_number, listing.location, listing.fee_notes::text,
  listing.photo_urls::text, listing.documents::text, listing.last_synced_at::text
));

alter table public.public_live_motorcycle_listings
  drop constraint if exists public_live_private_address_safe_chk;
alter table public.public_live_motorcycle_listings
  add constraint public_live_private_address_safe_chk
  check (
    not public.public_text_contains_private_address(
      concat_ws(
        ' ', source_record_id, source_name, official_url, official_title,
        official_case_number, organization_name, brand_name, model_name, color,
        location, description, condition_summary, array_to_string(fee_notes, ' '),
        documents::text
      )
    )
  );

revoke all on function public.public_text_contains_private_address(text)
  from public, anon, authenticated;
grant execute on function public.public_text_contains_private_address(text)
  to service_role;

drop function if exists public.__redact_public_private_address(text);
