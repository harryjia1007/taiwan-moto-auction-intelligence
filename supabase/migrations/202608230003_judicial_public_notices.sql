-- Supplemental vehicle-auction discovery on the Judicial Yuan main website.
-- This source is independent from the aomp109 movable-auction application and
-- is deliberately limited to the main site's other-judicial-notices list.

insert into sources
  (id, organization_id, family, name, adapter_name, status, automation_level, official_url, parser_version)
values
  (
    '20000000-0000-0000-0000-000000000009',
    null,
    'JUDICIAL_PUBLIC_NOTICES',
    '司法院其他司法公告（車輛拍賣補充）',
    'judicial_notices',
    'PARTIAL',
    'PUBLIC_HTML_BOUNDED_LINK_ONLY',
    'https://www.judicial.gov.tw/tw/lp-1913-1.html',
    '1.5.0'
  )
on conflict (id) do update set
  name = excluded.name,
  adapter_name = excluded.adapter_name,
  status = case when sources.status = 'ACTIVE' then sources.status else excluded.status end,
  automation_level = excluded.automation_level,
  official_url = excluded.official_url,
  parser_version = excluded.parser_version,
  updated_at = now();

insert into source_access_policies
  (source_id, decision, robots_url, terms_url, photo_rights, personal_data_risk,
   checked_on, rationale, permission_reference)
values
  (
    '20000000-0000-0000-0000-000000000009',
    'ALLOW',
    'https://www.judicial.gov.tw/robots.txt',
    'https://www.judicial.gov.tw/tw/cp-1327-84674-d8e05-1.html',
    'OFFICIAL_LINK_ONLY_NO_ATTACHMENT_OR_IMAGE_FETCH',
    'HIGH',
    date '2026-08-23',
    'ALLOW is limited to www.judicial.gov.tw /tw/lp-1913 and /tw/cp-1913 HTML after a fresh robots check, a 180-day bounded search, and exact vehicle-plus-auction detail validation. It never extends to aomp109, and /tw/dl attachment URLs are linked as evidence without downloading or mirroring their bytes.',
    'https://www.judicial.gov.tw/tw/cp-1327-84674-d8e05-1.html'
  )
on conflict (source_id) do update set
  decision = excluded.decision,
  robots_url = excluded.robots_url,
  terms_url = excluded.terms_url,
  photo_rights = excluded.photo_rights,
  personal_data_risk = excluded.personal_data_risk,
  checked_on = excluded.checked_on,
  rationale = excluded.rationale,
  permission_reference = excluded.permission_reference,
  updated_at = now();

insert into source_endpoints (source_id, endpoint_type, url, notes) values
  (
    '20000000-0000-0000-0000-000000000009',
    'DISCOVERY',
    'https://www.judicial.gov.tw/tw/lp-1913-1.html',
    '其他司法公告搜尋 POST；每次先複查 robots，限定 180 天與固定車種關鍵詞'
  ),
  (
    '20000000-0000-0000-0000-000000000009',
    'DETAIL_PATTERN',
    'https://www.judicial.gov.tw/tw/',
    '只允許 /tw/cp-1913-...html 詳細頁；/tw/dl-...html 僅作官方連結，不抓檔'
  )
on conflict (source_id, endpoint_type, url) do update set
  enabled = true,
  notes = excluded.notes;
