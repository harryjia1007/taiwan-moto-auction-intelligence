insert into sources
  (id, organization_id, family, name, adapter_name, status, automation_level, official_url, parser_version)
values
  ('20000000-0000-0000-0000-000000000008', null, 'ADMINISTRATIVE_ENFORCEMENT',
   '行政執行署各分署公告', 'moj_enforcement_cms', 'PARTIAL', 'BRANCH_CMS_READ_ONLY',
   'https://www.tpk.moj.gov.tw/9539/9685/1458230/1461437/', '1.4.0')
on conflict (id) do update set
  name = excluded.name,
  adapter_name = excluded.adapter_name,
  status = case when sources.status = 'ACTIVE' then sources.status else excluded.status end,
  automation_level = excluded.automation_level,
  official_url = excluded.official_url,
  parser_version = excluded.parser_version,
  updated_at = now();

insert into source_access_policies
  (source_id, decision, robots_url, terms_url, photo_rights, personal_data_risk, checked_on, rationale)
values
  ('20000000-0000-0000-0000-000000000008', 'ALLOW',
   'https://www.tpy.moj.gov.tw/robots.txt',
   'https://www.moj.gov.tw/umbraco/surface/Ini/CountAndRedirectUrl?nodeId=70586',
   'PRIVATE_ARTIFACT_OFFICIAL_LINK', 'HIGH', date '2026-08-20',
   'ALLOW is limited to 13 explicitly registered branch CMS hosts; every branch robots and declared sitemap are rechecked each run, and the CAPTCHA-gated central search remains excluded')
on conflict (source_id) do update set
  decision = excluded.decision,
  robots_url = excluded.robots_url,
  terms_url = excluded.terms_url,
  photo_rights = excluded.photo_rights,
  personal_data_risk = excluded.personal_data_risk,
  checked_on = excluded.checked_on,
  rationale = excluded.rationale,
  updated_at = now();

insert into source_endpoints (source_id, endpoint_type, url, notes) values
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.tpy.moj.gov.tw/', '臺北分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.sly.moj.gov.tw/', '士林分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.pcy.moj.gov.tw/', '新北分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.tyy.moj.gov.tw/', '桃園分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.scy.moj.gov.tw/', '新竹分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.tcy.moj.gov.tw/', '臺中分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.chy.moj.gov.tw/', '彰化分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.cyy.moj.gov.tw/', '嘉義分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.tny.moj.gov.tw/', '臺南分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.ksy.moj.gov.tw/', '高雄分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.pty.moj.gov.tw/', '屏東分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.hly.moj.gov.tw/', '花蓮分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.ily.moj.gov.tw/', '宜蘭分署官方 CMS；每次由 robots 與 sitemap 驗證入口')
on conflict do nothing;
