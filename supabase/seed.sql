insert into app_settings (id, owner_email) values (true, 'owner@example.com')
on conflict (id) do update set owner_email = excluded.owner_email;

insert into organizations (id, canonical_name, organization_type, jurisdiction, official_domain)
values ('10000000-0000-0000-0000-000000000001', '臺北市動產質借處', 'GOVERNMENT_AGENCY', '臺灣', 'shwoo.gov.taipei')
on conflict do nothing;

do $$
declare name text;
begin
  foreach name in array array[
    '臺灣臺北地方法院','臺灣士林地方法院','臺灣新北地方法院','臺灣桃園地方法院','臺灣新竹地方法院',
    '臺灣苗栗地方法院','臺灣臺中地方法院','臺灣南投地方法院','臺灣彰化地方法院','臺灣雲林地方法院',
    '臺灣嘉義地方法院','臺灣臺南地方法院','臺灣高雄地方法院','臺灣橋頭地方法院','臺灣屏東地方法院',
    '臺灣臺東地方法院','臺灣花蓮地方法院','臺灣宜蘭地方法院','臺灣基隆地方法院','臺灣澎湖地方法院',
    '福建金門地方法院','福建連江地方法院'
  ] loop
    insert into organizations (canonical_name, organization_type, jurisdiction, official_domain)
    values (name, 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw') on conflict do nothing;
  end loop;

  foreach name in array array[
    '法務部行政執行署臺北分署','法務部行政執行署士林分署','法務部行政執行署新北分署','法務部行政執行署桃園分署',
    '法務部行政執行署新竹分署','法務部行政執行署臺中分署','法務部行政執行署彰化分署','法務部行政執行署嘉義分署',
    '法務部行政執行署臺南分署','法務部行政執行署高雄分署','法務部行政執行署屏東分署','法務部行政執行署花蓮分署',
    '法務部行政執行署宜蘭分署'
  ] loop
    insert into organizations (canonical_name, organization_type, jurisdiction, official_domain)
    values (name, 'ADMINISTRATIVE_ENFORCEMENT_BRANCH', '臺灣', 'tpk.moj.gov.tw') on conflict do nothing;
  end loop;

  foreach name in array array[
    '臺灣臺北地方檢察署','臺灣士林地方檢察署','臺灣新北地方檢察署','臺灣桃園地方檢察署','臺灣新竹地方檢察署',
    '臺灣苗栗地方檢察署','臺灣臺中地方檢察署','臺灣南投地方檢察署','臺灣彰化地方檢察署','臺灣雲林地方檢察署',
    '臺灣嘉義地方檢察署','臺灣臺南地方檢察署','臺灣橋頭地方檢察署','臺灣高雄地方檢察署','臺灣屏東地方檢察署',
    '臺灣臺東地方檢察署','臺灣花蓮地方檢察署','臺灣宜蘭地方檢察署','臺灣基隆地方檢察署','臺灣澎湖地方檢察署',
    '福建金門地方檢察署','福建連江地方檢察署'
  ] loop
    insert into organizations (canonical_name, organization_type, jurisdiction, official_domain)
    values (name, 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw') on conflict do nothing;
  end loop;

  foreach name in array array['基隆關','臺北關','臺中關','高雄關'] loop
    insert into organizations (canonical_name, organization_type, jurisdiction, official_domain)
    values (name, 'CUSTOMS', '臺灣', 'customs.gov.tw') on conflict do nothing;
  end loop;
end $$;

insert into sources (id, organization_id, family, name, adapter_name, status, automation_level, official_url, parser_version)
values
  ('20000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','SHWOO','臺北惜物網','shwoo','PARTIAL','PUBLIC_READ_ONLY','https://shwoo.gov.taipei/shwoo/browse/browse00/','1.1.0'),
  ('20000000-0000-0000-0000-000000000002',null,'JUDICIAL','司法院 22 地院動產法拍','judicial','PARTIAL','HUMAN_OFFICIAL_MANIFEST','https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02.htm','1.3.0'),
  ('20000000-0000-0000-0000-000000000003',null,'ADMINISTRATIVE_ENFORCEMENT','行政執行署動產拍賣','moj_enforcement','PARTIAL','CAPTCHA_SAFE_MANUAL','https://www.tpkonsale.moj.gov.tw/Chattel','1.3.0'),
  ('20000000-0000-0000-0000-000000000004',null,'PROCUREMENT','政府電子採購網財物變賣','pcc','PARTIAL','OFFICIAL_OPEN_DATA','https://web.pcc.gov.tw/opas/aspam/public/downloadOpenData','1.4.0'),
  ('20000000-0000-0000-0000-000000000005',null,'PROSECUTORS','法務部查扣物集中拍賣','moj_auction','PARTIAL','PUBLIC_READ_ONLY','https://auction.moj.gov.tw/1724/1726/searchList','1.4.0'),
  ('20000000-0000-0000-0000-000000000006',null,'POLICE_TRAFFIC','警政與交通機關','police','PLANNED','PLANNED','https://www.npa.gov.tw/',''),
  ('20000000-0000-0000-0000-000000000007',null,'CUSTOMS','財政部關務署四關標售','customs','PARTIAL','PUBLIC_HTML_LINK_ONLY','https://web.customs.gov.tw/singlehtml/1207?cntId=cus1_93228_1207','1.4.0'),
  ('20000000-0000-0000-0000-000000000008',null,'ADMINISTRATIVE_ENFORCEMENT','行政執行署各分署公告','moj_enforcement_cms','PARTIAL','BRANCH_CMS_READ_ONLY','https://www.tpk.moj.gov.tw/9539/9685/1458230/1461437/','1.4.0')
on conflict (name) do nothing;

insert into source_access_policies
  (source_id,decision,robots_url,terms_url,photo_rights,personal_data_risk,checked_on,rationale)
values
  ('20000000-0000-0000-0000-000000000001','ALLOW','https://shwoo.gov.taipei/robots.txt','https://shwoo.gov.taipei/shwoo/newhome/newhome00/index','PRIVATE_CACHE_ONLY','MEDIUM','2026-08-15','/shwoo/ application path is allowed; public redistribution is not enabled'),
  ('20000000-0000-0000-0000-000000000002','MANUAL_ONLY','https://aomp109.judicial.gov.tw/robots.txt','https://www.judicial.gov.tw/tw/cp-1327-84674-d8e05-1.html','OGL_V1_WITH_EXCEPTIONS','HIGH','2026-08-15','Central query automation is disallowed. Human-reviewed official PDF manifests may be imported without querying or mirroring the blocked site; former dataset 49107 was permanently withdrawn and unattended discovery awaits a replacement official feed'),
  ('20000000-0000-0000-0000-000000000003','MANUAL_ONLY','https://www.tpkonsale.moj.gov.tw/','https://www.moj.gov.tw/umbraco/surface/Ini/CountAndRedirectUrl?nodeId=70586','PRIVATE_CACHE_ONLY','HIGH','2026-08-15','Human CAPTCHA discovery only; validated detail manifests may be processed'),
  ('20000000-0000-0000-0000-000000000004','ALLOW','https://web.pcc.gov.tw/robots.txt','https://data.gov.tw/license','PRIVATE_CACHE_ONLY','MEDIUM','2026-08-18','ALLOW is based on official machine-readable dataset 7263 under OGDL 1.0, not an ambiguous robots response; detail matching stays on web.pcc.gov.tw HTTPS'),
  ('20000000-0000-0000-0000-000000000005','ALLOW','https://auction.moj.gov.tw/robots.txt','https://www.moj.gov.tw/umbraco/surface/Ini/CountAndRedirectUrl?nodeId=70586','PRIVATE_CACHE_ONLY','HIGH','2026-08-18','ALLOW is limited to auction.moj.gov.tw. Unreviewed prosecutor-office redirect targets are not contacted; exact central list-row evidence is retained as a partial record'),
  ('20000000-0000-0000-0000-000000000007','ALLOW','https://web.customs.gov.tw/robots.txt','https://web.customs.gov.tw/singlehtml/694','LINK_ONLY_NO_FETCH','MEDIUM','2026-08-19','Four Customs HTML announcement channels are allowed; /download/ attachments remain official outbound links and are never fetched or mirrored'),
  ('20000000-0000-0000-0000-000000000008','ALLOW','https://www.tpy.moj.gov.tw/robots.txt','https://www.moj.gov.tw/umbraco/surface/Ini/CountAndRedirectUrl?nodeId=70586','PRIVATE_ARTIFACT_OFFICIAL_LINK','HIGH','2026-08-20','ALLOW is limited to 13 explicitly registered branch CMS hosts; every branch robots and declared sitemap are rechecked each run, and the CAPTCHA-gated central search remains excluded')
on conflict (source_id) do update set
  decision=excluded.decision,robots_url=excluded.robots_url,terms_url=excluded.terms_url,
  photo_rights=excluded.photo_rights,personal_data_risk=excluded.personal_data_risk,
  checked_on=excluded.checked_on,rationale=excluded.rationale,updated_at=now();

insert into source_endpoints (source_id, endpoint_type, url, notes) values
('20000000-0000-0000-0000-000000000001','DISCOVERY','https://shwoo.gov.taipei/shwoo/browse/browse00/','公開搜尋表單'),
('20000000-0000-0000-0000-000000000001','RESULTS','https://shwoo.gov.taipei/shwoo/newproduct/newproduct00/bidresult','公開近期待決標/決標查詢'),
('20000000-0000-0000-0000-000000000002','DISCOVERY','https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02/V2.htm','22 個地院中央動產拍賣公開查詢'),
('20000000-0000-0000-0000-000000000002','DETAIL','https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02/DO_VIEWPDF.htm','法院拍賣公告 PDF'),
('20000000-0000-0000-0000-000000000003','DISCOVERY','https://www.tpkonsale.moj.gov.tw/Chattel','人工完成 CAPTCHA 後匯出官方案件明細 URL'),
('20000000-0000-0000-0000-000000000003','DETAIL','https://www.tpkonsale.moj.gov.tw/Detail/Chattel','官方動產案件明細、公告與照片'),
('20000000-0000-0000-0000-000000000004','DISCOVERY','https://web.pcc.gov.tw/opas/aspam/public/downloadOpenData','資料集 7263 財物變賣公告 XML；上班日每日更新'),
('20000000-0000-0000-0000-000000000004','DETAIL','https://web.pcc.gov.tw/opas/aspam/public/readOneAspamDetailOld','公開財物變賣明細'),
('20000000-0000-0000-0000-000000000005','DISCOVERY','https://auction.moj.gov.tw/1724/1726/searchList','法務部查扣物汽機車類公開清單'),
('20000000-0000-0000-0000-000000000005','DETAIL','https://auction.moj.gov.tw/1724/1726/','法務部查扣物公告與附件'),
('20000000-0000-0000-0000-000000000007','DISCOVERY','https://web.customs.gov.tw/singlehtml/1207?cntId=cus1_93228_1207','財政部關務署四關標售官方總覽'),
('20000000-0000-0000-0000-000000000007','DISCOVERY','https://web.customs.gov.tw/keelung/multiplehtml/572','基隆關標售公告 HTML'),
('20000000-0000-0000-0000-000000000007','DISCOVERY','https://web.customs.gov.tw/taipei/multiplehtml/120','臺北關標售公告 HTML'),
('20000000-0000-0000-0000-000000000007','DISCOVERY','https://web.customs.gov.tw/taichung/multiplehtml/396','臺中關標售公告 HTML'),
('20000000-0000-0000-0000-000000000007','DISCOVERY','https://web.customs.gov.tw/kaohsiung/multiplehtml/541','高雄關標售公告 HTML'),
('20000000-0000-0000-0000-000000000008','DISCOVERY','https://www.tpy.moj.gov.tw/','臺北分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
('20000000-0000-0000-0000-000000000008','DISCOVERY','https://www.sly.moj.gov.tw/','士林分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
('20000000-0000-0000-0000-000000000008','DISCOVERY','https://www.pcy.moj.gov.tw/','新北分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
('20000000-0000-0000-0000-000000000008','DISCOVERY','https://www.tyy.moj.gov.tw/','桃園分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
('20000000-0000-0000-0000-000000000008','DISCOVERY','https://www.scy.moj.gov.tw/','新竹分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
('20000000-0000-0000-0000-000000000008','DISCOVERY','https://www.tcy.moj.gov.tw/','臺中分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
('20000000-0000-0000-0000-000000000008','DISCOVERY','https://www.chy.moj.gov.tw/','彰化分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
('20000000-0000-0000-0000-000000000008','DISCOVERY','https://www.cyy.moj.gov.tw/','嘉義分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
('20000000-0000-0000-0000-000000000008','DISCOVERY','https://www.tny.moj.gov.tw/','臺南分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
('20000000-0000-0000-0000-000000000008','DISCOVERY','https://www.ksy.moj.gov.tw/','高雄分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
('20000000-0000-0000-0000-000000000008','DISCOVERY','https://www.pty.moj.gov.tw/','屏東分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
('20000000-0000-0000-0000-000000000008','DISCOVERY','https://www.hly.moj.gov.tw/','花蓮分署官方 CMS；每次由 robots 與 sitemap 驗證入口'),
('20000000-0000-0000-0000-000000000008','DISCOVERY','https://www.ily.moj.gov.tw/','宜蘭分署官方 CMS；每次由 robots 與 sitemap 驗證入口')
on conflict do nothing;

insert into vehicle_brands (id, canonical_name, aliases) values
('30000000-0000-0000-0000-000000000001','SYM',array['SYM','三陽','三陽牌','三陽工業','SANYANG']),
('30000000-0000-0000-0000-000000000002','YAMAHA',array['YAMAHA','Yamaha','山葉','台灣山葉']),
('30000000-0000-0000-0000-000000000003','KYMCO',array['KYMCO','光陽'])
on conflict (canonical_name) do nothing;

insert into vehicle_models (id, brand_id, canonical_name, model_code)
values ('31000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001','HM12VB','HM12VB')
on conflict do nothing;

-- Fully synthetic development record. It is not a real Shwoo case.
insert into organizations (id, canonical_name, organization_type, jurisdiction, official_domain)
values ('10000000-0000-0000-0000-000000000002','合成公營事業機關','PUBLIC_ENTERPRISE','臺南市',null)
on conflict do nothing;

insert into source_records (id, source_id, source_record_id, official_url, original_title, first_seen_at, last_seen_at, last_content_checksum)
values ('40000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','SYNTH-SHWOO-01','https://shwoo.gov.taipei/shwoo/browse/browse00/','【合成測試案件 A】機器腳踏車 1 台','2026-08-09T00:00:00Z','2026-08-09T00:00:00Z','fixture-synthetic-01')
on conflict do nothing;

insert into auction_cases (id, source_id, organization_id, official_case_number, title, disposal_origin)
values ('50000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000002','SYNTH-CASE-01','合成機器腳踏車 1 台','PUBLIC_ASSET_DISPOSAL')
on conflict do nothing;

insert into auction_events (id, auction_case_id, source_record_id, round_number, status, starts_at, ends_at, reserve_price, current_price)
values ('51000000-0000-0000-0000-000000000001','50000000-0000-0000-0000-000000000001','40000000-0000-0000-0000-000000000001',1,'SCHEDULED','2026-08-05T00:00:00+08:00','2026-08-12T12:00:00+08:00',2000,4300)
on conflict do nothing;

insert into lots (id, auction_event_id, lot_number, title, lot_size, bulk_lot, eligibility, storage_location, original_description)
values ('52000000-0000-0000-0000-000000000001','51000000-0000-0000-0000-000000000001','1','合成機器腳踏車 1 台',1,false,'NATURAL_PERSON_ALLOWED','臺南市（測試地點）','合成測試：牌照狀態與發動狀態待確認。')
on conflict do nothing;

insert into vehicles (id, lot_id, brand_id, model_id, original_brand, original_model, model_code, vehicle_category, manufacture_year, manufacture_month, displacement_cc, color, has_key, can_start, can_test, registration_status, condition_summary, visible_damage, tax_arrears, fine_arrears, completeness, completeness_groups)
values ('53000000-0000-0000-0000-000000000001','52000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001','31000000-0000-0000-0000-000000000001','三陽牌','HM12VB','HM12VB','ORDINARY_HEAVY',2011,5,125,'黃色','UNKNOWN','NO','YES','RE_REGISTRATION_REQUIRED','目前車子發不動；僅提供靜態功能測試。','排氣管有生鏽痕跡','NO','NO',84,'{"identity":100,"auction":100,"condition":80,"registration":100,"fees":67,"media":100}')
on conflict do nothing;

insert into vehicle_identifiers (vehicle_id, identifier_type, normalized_value, original_value) values
('53000000-0000-0000-0000-000000000001','PLATE','TEST-SHWOO-01','TEST-SHWOO-01'),
('53000000-0000-0000-0000-000000000001','ENGINE','SYNTH-ENGINE-01','SYNTH-ENGINE-01'),
('53000000-0000-0000-0000-000000000001','FRAME','SYNTH-FRAME-01','SYNTH-FRAME-01')
on conflict do nothing;

insert into photos (vehicle_id, source_record_id, source_url, sort_order)
values ('53000000-0000-0000-0000-000000000001','40000000-0000-0000-0000-000000000001','https://shwoo.gov.taipei/shwoo/browse/browse00/',0)
on conflict do nothing;

insert into field_evidence (entity_type, entity_id, field_name, normalized_value, source_record_id, source_text, parser_name, parser_version, extraction_method, trust, confidence) values
('vehicle','53000000-0000-0000-0000-000000000001','registration_status','"RE_REGISTRATION_REQUIRED"','40000000-0000-0000-0000-000000000001','合成測試：牌照已繳銷，領牌條件待確認。','shwoo','1.0.0','HTML','OFFICIAL_EXPLICIT',1),
('vehicle','53000000-0000-0000-0000-000000000001','can_start','"NO"','40000000-0000-0000-0000-000000000001','合成測試：目前無法發動，原因未確認。','shwoo','1.0.0','HTML','OFFICIAL_EXPLICIT',1),
('vehicle','53000000-0000-0000-0000-000000000001','can_test','"YES"','40000000-0000-0000-0000-000000000001','合成測試：只允許靜態檢查。','shwoo','1.0.0','HTML','OFFICIAL_EXPLICIT',1)
on conflict do nothing;
