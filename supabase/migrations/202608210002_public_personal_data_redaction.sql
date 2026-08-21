-- Remove personal data and unlicensed media from the anonymous projection.
--
-- This migration is intentionally limited to public_live_motorcycle_listings.
-- Private normalized records, snapshots, evidence, photos and raw artifacts are
-- not changed. Every transformation is idempotent so interrupted deployments
-- can safely retry the migration.

create function public.__redact_public_personal_data(value text)
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
    '(義務人|債務人|所有人|車主|被告|受刑人|保管人|姓名)[[:space:]]*[:：]?[[:space:]]*([一-龥○ＯO·．・]{2,6}?)(?=$|[[:space:]，,。；;、/()（）.\-_?&#]|應|係|之|於|住址|電話|身分|證號)',
    '\1：已隱去',
    'g'
  );
  redacted := regexp_replace(
    redacted,
    '(?<![0-9])(09[0-9]{2}([-－ ]?[0-9]{3}){2}|0[0-9]{1,2}[-－ ]?[0-9]{6,8})([[:space:]]*(#|分機)[[:space:]]*[0-9]+)?(?![0-9])',
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

create function public.__public_url_contains_personal_data(value text)
returns boolean
language plpgsql
immutable
strict
set search_path = ''
as $$
declare
  normalized text := lower(value);
  ascii_code integer;
begin
  -- Decode percent-encoded printable ASCII so encoded IDs, email addresses and
  -- phone numbers cannot evade the checks. Encoded Chinese role labels are
  -- matched separately below without attempting a lossy UTF-8 rewrite.
  for ascii_code in 32..126 loop
    normalized := replace(
      normalized,
      '%' || lpad(to_hex(ascii_code), 2, '0'),
      chr(ascii_code)
    );
  end loop;

  if public.__redact_public_personal_data(normalized) <> normalized then
    return true;
  end if;

  return normalized ~ (
    '(%e7%be%a9%e5%8b%99%e4%ba%ba|' || -- 義務人
    '%e5%82%b5%e5%8b%99%e4%ba%ba|' ||  -- 債務人
    '%e6%89%80%e6%9c%89%e4%ba%ba|' ||  -- 所有人
    '%e8%bb%8a%e4%b8%bb|' ||            -- 車主
    '%e8%a2%ab%e5%91%8a|' ||            -- 被告
    '%e5%8f%97%e5%88%91%e4%ba%ba|' ||  -- 受刑人
    '%e4%bf%9d%e7%ae%a1%e4%ba%ba|' ||  -- 保管人
    '%e5%a7%93%e5%90%8d)'               -- 姓名
  );
end;
$$;

with prepared as (
  select
    listing.id as old_id,
    case
      when public.__redact_public_personal_data(listing.source_record_id) <> listing.source_record_id
        then 'redacted-' || substr(md5(listing.source_adapter || ':' || listing.source_record_id), 1, 20)
      else listing.source_record_id
    end as safe_source_record_id
  from public.public_live_motorcycle_listings as listing
)
update public.public_live_motorcycle_listings as listing
set id = listing.source_adapter || '-' || prepared.safe_source_record_id,
    source_record_id = prepared.safe_source_record_id,
    source_name = public.__redact_public_personal_data(listing.source_name),
    official_url = case
      when public.__public_url_contains_personal_data(listing.official_url)
        then coalesce(substring(listing.official_url from '^https://[^/]+'), 'https://www.gov.tw/') || '/'
      else listing.official_url
    end,
    official_title = public.__redact_public_personal_data(listing.official_title),
    official_case_number = public.__redact_public_personal_data(listing.official_case_number),
    organization_name = public.__redact_public_personal_data(listing.organization_name),
    brand_name = public.__redact_public_personal_data(listing.brand_name),
    model_name = public.__redact_public_personal_data(listing.model_name),
    color = public.__redact_public_personal_data(listing.color),
    location = public.__redact_public_personal_data(listing.location),
    description = public.__redact_public_personal_data(listing.description),
    condition_summary = public.__redact_public_personal_data(listing.condition_summary),
    fee_notes = (
      select coalesce(
        array_agg(public.__redact_public_personal_data(note) order by position),
        '{}'::text[]
      )
      from unnest(listing.fee_notes) with ordinality as notes(note, position)
    ),
    plate_number = case
      when listing.ends_at is null or listing.ends_at < now() - interval '30 days' then null
      else listing.plate_number
    end,
    photo_urls = '[]'::jsonb,
    documents = (
      select coalesce(
        jsonb_agg(
          jsonb_build_object(
            'label', public.__redact_public_personal_data(coalesce(document ->> 'label', '官方附件')),
            'url', document ->> 'url'
          )
          order by position
        ),
        '[]'::jsonb
      )
      from jsonb_array_elements(listing.documents) with ordinality as entries(document, position)
      where jsonb_typeof(document) = 'object'
        and document ->> 'url' ~ '^https://'
        and not public.__public_url_contains_personal_data(document ->> 'url')
    )
from prepared
where listing.id = prepared.old_id;

-- risk_notes is not part of the current public contract. If an already-hosted
-- environment added it ahead of this migration, sanitize supported text forms
-- instead of silently leaving a legacy field behind.
do $$
declare
  column_udt text;
begin
  select udt_name into column_udt
  from information_schema.columns
  where table_schema = 'public'
    and table_name = 'public_live_motorcycle_listings'
    and column_name = 'risk_notes';

  if column_udt = 'text' then
    execute 'update public.public_live_motorcycle_listings '
      || 'set risk_notes = public.__redact_public_personal_data(risk_notes)';
  elsif column_udt = '_text' then
    execute $statement$
      update public.public_live_motorcycle_listings as listing
      set risk_notes = (
        select coalesce(
          array_agg(public.__redact_public_personal_data(note) order by position),
          '{}'::text[]
        )
        from unnest(listing.risk_notes) with ordinality as notes(note, position)
      )
    $statement$;
  elsif column_udt = 'jsonb' then
    execute $statement$
      update public.public_live_motorcycle_listings as listing
      set risk_notes = case
        when jsonb_typeof(listing.risk_notes) = 'array' then (
          select coalesce(
            jsonb_agg(
              to_jsonb(public.__redact_public_personal_data(note #>> '{}')) order by position
            ),
            '[]'::jsonb
          )
          from jsonb_array_elements(listing.risk_notes) with ordinality as notes(note, position)
          where jsonb_typeof(note) = 'string'
        )
        when jsonb_typeof(listing.risk_notes) = 'string' then
          to_jsonb(public.__redact_public_personal_data(listing.risk_notes #>> '{}'))
        else '[]'::jsonb
      end
    $statement$;
  end if;
end;
$$;

-- Recompute the projection checksum only after every redaction above is final.
update public.public_live_motorcycle_listings as listing
set content_checksum = md5(concat_ws(
  '|',
  listing.source_adapter,
  listing.source_record_id,
  listing.official_url,
  listing.official_title,
  listing.official_case_number,
  listing.organization_name,
  listing.plate_number,
  listing.location,
  listing.fee_notes::text,
  listing.photo_urls::text,
  listing.documents::text,
  listing.last_synced_at::text
));

comment on column public.public_live_motorcycle_listings.plate_number is
  'Partially masked official plate text. It is never published without a verified auction end time and is cleared 30 days after that time.';
comment on column public.public_live_motorcycle_listings.photo_urls is
  'Anonymous photo URLs are empty until a source has an explicit public-image right and an exact-host HTTPS allowlist. Private owner media is unchanged.';

drop function public.__public_url_contains_personal_data(text);
drop function public.__redact_public_personal_data(text);
