-- Register the four Customs HTML channels after public identifier redaction.
insert into sources
  (id, organization_id, family, name, adapter_name, status, automation_level, official_url, parser_version)
values
  ('20000000-0000-0000-0000-000000000007', null, 'CUSTOMS', '財政部關務署四關標售',
   'customs', 'PARTIAL', 'PUBLIC_HTML_LINK_ONLY',
   'https://web.customs.gov.tw/singlehtml/1207?cntId=cus1_93228_1207', '1.4.0')
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
  ('20000000-0000-0000-0000-000000000007', 'ALLOW',
   'https://web.customs.gov.tw/robots.txt', 'https://web.customs.gov.tw/singlehtml/694',
   'LINK_ONLY_NO_FETCH', 'MEDIUM', date '2026-08-19',
   'Four Customs HTML announcement channels are allowed; /download/ attachments remain official outbound links and are never fetched or mirrored')
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
  ('20000000-0000-0000-0000-000000000007', 'DISCOVERY', 'https://web.customs.gov.tw/singlehtml/1207?cntId=cus1_93228_1207', '財政部關務署四關標售官方總覽'),
  ('20000000-0000-0000-0000-000000000007', 'DISCOVERY', 'https://web.customs.gov.tw/keelung/multiplehtml/572', '基隆關標售公告 HTML'),
  ('20000000-0000-0000-0000-000000000007', 'DISCOVERY', 'https://web.customs.gov.tw/taipei/multiplehtml/120', '臺北關標售公告 HTML'),
  ('20000000-0000-0000-0000-000000000007', 'DISCOVERY', 'https://web.customs.gov.tw/taichung/multiplehtml/396', '臺中關標售公告 HTML'),
  ('20000000-0000-0000-0000-000000000007', 'DISCOVERY', 'https://web.customs.gov.tw/kaohsiung/multiplehtml/541', '高雄關標售公告 HTML')
on conflict do nothing;
