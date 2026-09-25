-- Production-safe source registry bootstrap.
--
-- This migration contains only operational source metadata. It deliberately
-- excludes the local owner placeholder, synthetic cases, fixtures and aliases
-- from supabase/seed.sql so a linked `supabase db push` is safe by default.

insert into public.organizations
  (id, canonical_name, organization_type, jurisdiction, official_domain)
values
  ('10000000-0000-0000-0000-000000000001', '臺北市動產質借處',
   'GOVERNMENT_AGENCY', '臺灣', 'shwoo.gov.taipei')
on conflict (id) do update set
  canonical_name = excluded.canonical_name,
  organization_type = excluded.organization_type,
  jurisdiction = excluded.jurisdiction,
  official_domain = excluded.official_domain;

-- Canonical public organizations are operational registry data, not fixtures.
-- Keep them in the migration so a fresh hosted project normalizes agencies in
-- exactly the same way as local ingestion without running the development seed.
insert into public.organizations
  (canonical_name, organization_type, jurisdiction, official_domain)
values
  ('臺灣臺北地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣士林地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣新北地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣桃園地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣新竹地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣苗栗地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣臺中地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣南投地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣彰化地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣雲林地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣嘉義地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣臺南地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣高雄地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣橋頭地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣屏東地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣臺東地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣花蓮地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣宜蘭地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣基隆地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('臺灣澎湖地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('福建金門地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('福建連江地方法院', 'DISTRICT_COURT', '臺灣', 'judicial.gov.tw'),
  ('法務部行政執行署臺北分署', 'ADMINISTRATIVE_ENFORCEMENT_BRANCH', '臺灣', 'tpy.moj.gov.tw'),
  ('法務部行政執行署士林分署', 'ADMINISTRATIVE_ENFORCEMENT_BRANCH', '臺灣', 'sly.moj.gov.tw'),
  ('法務部行政執行署新北分署', 'ADMINISTRATIVE_ENFORCEMENT_BRANCH', '臺灣', 'pcy.moj.gov.tw'),
  ('法務部行政執行署桃園分署', 'ADMINISTRATIVE_ENFORCEMENT_BRANCH', '臺灣', 'tyy.moj.gov.tw'),
  ('法務部行政執行署新竹分署', 'ADMINISTRATIVE_ENFORCEMENT_BRANCH', '臺灣', 'scy.moj.gov.tw'),
  ('法務部行政執行署臺中分署', 'ADMINISTRATIVE_ENFORCEMENT_BRANCH', '臺灣', 'tcy.moj.gov.tw'),
  ('法務部行政執行署彰化分署', 'ADMINISTRATIVE_ENFORCEMENT_BRANCH', '臺灣', 'chy.moj.gov.tw'),
  ('法務部行政執行署嘉義分署', 'ADMINISTRATIVE_ENFORCEMENT_BRANCH', '臺灣', 'cyy.moj.gov.tw'),
  ('法務部行政執行署臺南分署', 'ADMINISTRATIVE_ENFORCEMENT_BRANCH', '臺灣', 'tny.moj.gov.tw'),
  ('法務部行政執行署高雄分署', 'ADMINISTRATIVE_ENFORCEMENT_BRANCH', '臺灣', 'ksy.moj.gov.tw'),
  ('法務部行政執行署屏東分署', 'ADMINISTRATIVE_ENFORCEMENT_BRANCH', '臺灣', 'pty.moj.gov.tw'),
  ('法務部行政執行署花蓮分署', 'ADMINISTRATIVE_ENFORCEMENT_BRANCH', '臺灣', 'hly.moj.gov.tw'),
  ('法務部行政執行署宜蘭分署', 'ADMINISTRATIVE_ENFORCEMENT_BRANCH', '臺灣', 'ily.moj.gov.tw'),
  ('臺灣臺北地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣士林地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣新北地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣桃園地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣新竹地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣苗栗地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣臺中地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣南投地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣彰化地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣雲林地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣嘉義地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣臺南地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣橋頭地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣高雄地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣屏東地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣臺東地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣花蓮地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣宜蘭地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣基隆地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('臺灣澎湖地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('福建金門地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('福建連江地方檢察署', 'LOCAL_PROSECUTORS_OFFICE', '臺灣', 'moj.gov.tw'),
  ('基隆關', 'CUSTOMS', '臺灣', 'customs.gov.tw'),
  ('臺北關', 'CUSTOMS', '臺灣', 'customs.gov.tw'),
  ('臺中關', 'CUSTOMS', '臺灣', 'customs.gov.tw'),
  ('高雄關', 'CUSTOMS', '臺灣', 'customs.gov.tw')
on conflict (canonical_name) do update set
  organization_type = excluded.organization_type,
  jurisdiction = excluded.jurisdiction,
  official_domain = excluded.official_domain;

insert into public.vehicle_brands (id, canonical_name, aliases)
values
  ('30000000-0000-0000-0000-000000000001', 'SYM', array['SYM','三陽','三陽牌','三陽工業','SANYANG']),
  ('30000000-0000-0000-0000-000000000002', 'YAMAHA', array['YAMAHA','Yamaha','山葉','台灣山葉']),
  ('30000000-0000-0000-0000-000000000003', 'KYMCO', array['KYMCO','光陽'])
on conflict (canonical_name) do update set aliases = excluded.aliases;

insert into public.vehicle_models
  (id, brand_id, canonical_name, model_code)
values
  ('31000000-0000-0000-0000-000000000001',
   '30000000-0000-0000-0000-000000000001', 'HM12VB', 'HM12VB')
on conflict (id) do update set
  brand_id = excluded.brand_id,
  canonical_name = excluded.canonical_name,
  model_code = excluded.model_code;

insert into public.sources
  (id, organization_id, family, name, adapter_name, status,
   automation_level, official_url, parser_version)
values
  ('20000000-0000-0000-0000-000000000001',
   '10000000-0000-0000-0000-000000000001', 'SHWOO', '臺北惜物網',
   'shwoo', 'PARTIAL', 'PUBLIC_READ_ONLY',
   'https://shwoo.gov.taipei/shwoo/browse/browse00/', '1.1.0'),
  ('20000000-0000-0000-0000-000000000002', null, 'JUDICIAL',
   '司法院 22 地院動產法拍', 'judicial', 'PARTIAL',
   'HUMAN_OFFICIAL_MANIFEST',
   'https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02.htm', '1.3.0'),
  ('20000000-0000-0000-0000-000000000003', null,
   'ADMINISTRATIVE_ENFORCEMENT', '行政執行署動產拍賣',
   'moj_enforcement', 'PARTIAL', 'CAPTCHA_SAFE_MANUAL',
   'https://www.tpkonsale.moj.gov.tw/Chattel', '1.3.0'),
  ('20000000-0000-0000-0000-000000000004', null, 'PROCUREMENT',
   '政府電子採購網財物變賣', 'pcc', 'PARTIAL', 'OFFICIAL_OPEN_DATA',
   'https://web.pcc.gov.tw/opas/aspam/public/downloadOpenData', '1.4.0'),
  ('20000000-0000-0000-0000-000000000005', null, 'PROSECUTORS',
   '法務部查扣物集中拍賣', 'moj_auction', 'PARTIAL', 'PUBLIC_READ_ONLY',
   'https://auction.moj.gov.tw/1724/1726/searchList', '1.4.0'),
  ('20000000-0000-0000-0000-000000000006', null, 'POLICE_TRAFFIC',
   '警政與交通機關', 'police', 'PLANNED', 'PLANNED',
   'https://www.npa.gov.tw/', null),
  ('20000000-0000-0000-0000-000000000007', null, 'CUSTOMS',
   '財政部關務署四關標售', 'customs', 'PARTIAL',
   'PUBLIC_HTML_LINK_ONLY',
   'https://web.customs.gov.tw/singlehtml/1207?cntId=cus1_93228_1207', '1.4.0'),
  ('20000000-0000-0000-0000-000000000008', null,
   'ADMINISTRATIVE_ENFORCEMENT', '行政執行署各分署公告',
   'moj_enforcement_cms', 'PARTIAL', 'BRANCH_CMS_READ_ONLY',
   'https://www.tpk.moj.gov.tw/9539/9685/1458230/1461437/', '1.4.0'),
  ('20000000-0000-0000-0000-000000000009', null,
   'JUDICIAL_PUBLIC_NOTICES', '司法院其他司法公告（車輛拍賣補充）',
   'judicial_notices', 'PARTIAL', 'PUBLIC_HTML_BOUNDED_LINK_ONLY',
   'https://www.judicial.gov.tw/tw/lp-1913-1.html', '1.5.0')
on conflict (id) do update set
  organization_id = excluded.organization_id,
  family = excluded.family,
  name = excluded.name,
  adapter_name = excluded.adapter_name,
  automation_level = excluded.automation_level,
  official_url = excluded.official_url,
  parser_version = excluded.parser_version;

-- Existing operator decisions are never broadened by this bootstrap. These
-- defaults are inserted only when the hosted registry has no policy row.
insert into public.source_access_policies
  (source_id, decision, robots_url, terms_url, photo_rights,
   personal_data_risk, checked_on, rationale, permission_reference)
values
  ('20000000-0000-0000-0000-000000000001', 'ALLOW',
   'https://shwoo.gov.taipei/robots.txt',
   'https://shwoo.gov.taipei/shwoo/newhome/newhome00/index',
   'PRIVATE_CACHE_ONLY', 'MEDIUM', date '2026-08-15',
   '/shwoo/ application path is allowed; public photo redistribution is not enabled', null),
  ('20000000-0000-0000-0000-000000000002', 'MANUAL_ONLY',
   'https://aomp109.judicial.gov.tw/robots.txt',
   'https://www.judicial.gov.tw/tw/cp-1327-84674-d8e05-1.html',
   'OGL_V1_WITH_EXCEPTIONS', 'HIGH', date '2026-08-15',
   'Central query automation is disallowed. Only a human-reviewed official-link manifest may be imported; the adapter makes no aomp109 request.',
   'https://www.judicial.gov.tw/tw/cp-1327-84674-d8e05-1.html'),
  ('20000000-0000-0000-0000-000000000003', 'MANUAL_ONLY',
   'https://www.tpkonsale.moj.gov.tw/robots.txt',
   'https://www.moj.gov.tw/umbraco/surface/Ini/CountAndRedirectUrl?nodeId=70586',
   'LINK_ONLY_NO_FETCH', 'HIGH', date '2026-08-21',
   'The official search form requires CAPTCHA. Code may process only human-saved result HTML or a validated same-host detail manifest.', null),
  ('20000000-0000-0000-0000-000000000004', 'ALLOW',
   'https://web.pcc.gov.tw/robots.txt', 'https://data.gov.tw/license',
   'PRIVATE_CACHE_ONLY', 'MEDIUM', date '2026-08-18',
   'ALLOW is based on official machine-readable dataset 7263 under OGDL 1.0; detail matching remains on web.pcc.gov.tw HTTPS.',
   'https://data.gov.tw/dataset/7263'),
  ('20000000-0000-0000-0000-000000000005', 'ALLOW',
   'https://auction.moj.gov.tw/robots.txt',
   'https://www.moj.gov.tw/umbraco/surface/Ini/CountAndRedirectUrl?nodeId=70586',
   'PRIVATE_CACHE_ONLY', 'HIGH', date '2026-08-18',
   'ALLOW is limited to auction.moj.gov.tw; unreviewed prosecutor-office redirect targets are not contacted.', null),
  ('20000000-0000-0000-0000-000000000006', 'DISABLED',
   'https://www.npa.gov.tw/robots.txt', 'https://www.npa.gov.tw/',
   'NONE', 'HIGH', date '2026-08-23',
   'Registry placeholder only. No reviewed adapter or unattended collection policy exists.', null),
  ('20000000-0000-0000-0000-000000000007', 'ALLOW',
   'https://web.customs.gov.tw/robots.txt',
   'https://web.customs.gov.tw/singlehtml/694',
   'LINK_ONLY_NO_FETCH', 'MEDIUM', date '2026-08-19',
   'Four Customs HTML announcement channels are allowed; /download/ attachments remain outbound links and are not fetched or mirrored.', null),
  ('20000000-0000-0000-0000-000000000008', 'ALLOW',
   'https://www.tpy.moj.gov.tw/robots.txt',
   'https://www.moj.gov.tw/umbraco/surface/Ini/CountAndRedirectUrl?nodeId=70586',
   'PRIVATE_ARTIFACT_OFFICIAL_LINK', 'HIGH', date '2026-08-20',
   'ALLOW is limited to 13 explicitly registered branch CMS hosts; every branch robots and declared sitemap are rechecked each run.', null),
  ('20000000-0000-0000-0000-000000000009', 'ALLOW',
   'https://www.judicial.gov.tw/robots.txt',
   'https://www.judicial.gov.tw/tw/cp-1327-84674-d8e05-1.html',
   'OFFICIAL_LINK_ONLY_NO_ATTACHMENT_OR_IMAGE_FETCH', 'HIGH', date '2026-08-23',
   'ALLOW is limited to the bounded Judicial Yuan main-site other-notices HTML search and never extends to aomp109 or attachment bytes.',
   'https://www.judicial.gov.tw/tw/cp-1327-84674-d8e05-1.html')
on conflict (source_id) do nothing;

insert into public.source_endpoints
  (source_id, endpoint_type, url, enabled, notes)
values
  ('20000000-0000-0000-0000-000000000001', 'DISCOVERY',
   'https://shwoo.gov.taipei/shwoo/browse/browse00/', true, '公開搜尋表單'),
  ('20000000-0000-0000-0000-000000000001', 'RESULTS',
   'https://shwoo.gov.taipei/shwoo/newproduct/newproduct00/bidresult', true, '公開近期待決標／決標查詢'),
  ('20000000-0000-0000-0000-000000000002', 'DISCOVERY',
   'https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02/V2.htm', false,
   '人工參考：中央查詢禁止程式連線；只能匯入人工核對的官方清單'),
  ('20000000-0000-0000-0000-000000000002', 'DETAIL',
   'https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02/DO_VIEWPDF.htm', false,
   '人工參考：只驗證人工清單中的官方 PDF 網址；程式不下載或鏡像 PDF'),
  ('20000000-0000-0000-0000-000000000003', 'DISCOVERY',
   'https://www.tpkonsale.moj.gov.tw/Chattel', true,
   '人工完成 CAPTCHA 後儲存官方結果 HTML；程式不請求 Query'),
  ('20000000-0000-0000-0000-000000000003', 'DETAIL',
   'https://www.tpkonsale.moj.gov.tw/Detail/Chattel', true,
   '經驗證的官方動產案件明細；PDF 只連官方全文，圖片不擷取'),
  ('20000000-0000-0000-0000-000000000004', 'DISCOVERY',
   'https://web.pcc.gov.tw/opas/aspam/public/downloadOpenData', true,
   '資料集 7263 財物變賣公告 XML'),
  ('20000000-0000-0000-0000-000000000004', 'DETAIL',
   'https://web.pcc.gov.tw/opas/aspam/public/readOneAspamDetailOld', true,
   '公開財物變賣明細'),
  ('20000000-0000-0000-0000-000000000005', 'DISCOVERY',
   'https://auction.moj.gov.tw/1724/1726/searchList', true,
   '法務部查扣物汽機車類公開清單'),
  ('20000000-0000-0000-0000-000000000005', 'DETAIL',
   'https://auction.moj.gov.tw/1724/1726/', true, '法務部查扣物公告與附件'),
  ('20000000-0000-0000-0000-000000000006', 'DISCOVERY',
   'https://www.npa.gov.tw/', false, '未實作；僅保留官方來源首頁'),
  ('20000000-0000-0000-0000-000000000007', 'DISCOVERY',
   'https://web.customs.gov.tw/singlehtml/1207?cntId=cus1_93228_1207', true,
   '財政部關務署四關標售官方總覽'),
  ('20000000-0000-0000-0000-000000000007', 'DISCOVERY',
   'https://web.customs.gov.tw/keelung/multiplehtml/572', true, '基隆關標售公告 HTML'),
  ('20000000-0000-0000-0000-000000000007', 'DISCOVERY',
   'https://web.customs.gov.tw/taipei/multiplehtml/120', true, '臺北關標售公告 HTML'),
  ('20000000-0000-0000-0000-000000000007', 'DISCOVERY',
   'https://web.customs.gov.tw/taichung/multiplehtml/396', true, '臺中關標售公告 HTML'),
  ('20000000-0000-0000-0000-000000000007', 'DISCOVERY',
   'https://web.customs.gov.tw/kaohsiung/multiplehtml/541', true, '高雄關標售公告 HTML'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.tpy.moj.gov.tw/', true, '臺北分署官方 CMS'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.sly.moj.gov.tw/', true, '士林分署官方 CMS'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.pcy.moj.gov.tw/', true, '新北分署官方 CMS'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.tyy.moj.gov.tw/', true, '桃園分署官方 CMS'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.scy.moj.gov.tw/', true, '新竹分署官方 CMS'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.tcy.moj.gov.tw/', true, '臺中分署官方 CMS'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.chy.moj.gov.tw/', true, '彰化分署官方 CMS'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.cyy.moj.gov.tw/', true, '嘉義分署官方 CMS'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.tny.moj.gov.tw/', true, '臺南分署官方 CMS'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.ksy.moj.gov.tw/', true, '高雄分署官方 CMS'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.pty.moj.gov.tw/', true, '屏東分署官方 CMS'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.hly.moj.gov.tw/', true, '花蓮分署官方 CMS'),
  ('20000000-0000-0000-0000-000000000008', 'DISCOVERY', 'https://www.ily.moj.gov.tw/', true, '宜蘭分署官方 CMS'),
  ('20000000-0000-0000-0000-000000000009', 'DISCOVERY',
   'https://www.judicial.gov.tw/tw/lp-1913-1.html', true,
   '其他司法公告搜尋 POST；每次先複查 robots，限定 180 天與固定車種關鍵詞'),
  ('20000000-0000-0000-0000-000000000009', 'DETAIL_PATTERN',
   'https://www.judicial.gov.tw/tw/', true,
   '只允許 /tw/cp-1913 詳細頁；/tw/dl 附件僅作官方連結，不抓檔')
on conflict (source_id, endpoint_type, url) do update set
  enabled = excluded.enabled,
  notes = excluded.notes;
