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
  ('20000000-0000-0000-0000-000000000002',null,'JUDICIAL','司法院 22 地院動產法拍','judicial','PARTIAL','PUBLIC_READ_ONLY','https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02.htm','1.2.0'),
  ('20000000-0000-0000-0000-000000000003',null,'ADMINISTRATIVE_ENFORCEMENT','行政執行署拍賣','moj_enforcement','PLANNED','CAPTCHA_SAFE_PARTIAL','https://www.tpk.moj.gov.tw/',''),
  ('20000000-0000-0000-0000-000000000004',null,'PROCUREMENT','政府電子採購網財物變賣','pcc','PARTIAL','PUBLIC_READ_ONLY','https://web.pcc.gov.tw/opas/aspam/public/indexAspam','1.2.0'),
  ('20000000-0000-0000-0000-000000000005',null,'PROSECUTORS','地方檢察署公告','moj_cms','PLANNED','PLANNED','https://www.moj.gov.tw/',''),
  ('20000000-0000-0000-0000-000000000006',null,'POLICE_TRAFFIC','警政與交通機關','police','PLANNED','PLANNED','https://www.npa.gov.tw/',''),
  ('20000000-0000-0000-0000-000000000007',null,'CUSTOMS','海關拍賣','customs','PLANNED','PLANNED','https://web.customs.gov.tw/','')
on conflict (name) do nothing;

insert into source_endpoints (source_id, endpoint_type, url, notes) values
('20000000-0000-0000-0000-000000000001','DISCOVERY','https://shwoo.gov.taipei/shwoo/browse/browse00/','公開搜尋表單'),
('20000000-0000-0000-0000-000000000001','RESULTS','https://shwoo.gov.taipei/shwoo/newproduct/newproduct00/bidresult','公開近期待決標/決標查詢'),
('20000000-0000-0000-0000-000000000002','DISCOVERY','https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02/V2.htm','22 個地院中央動產拍賣公開查詢'),
('20000000-0000-0000-0000-000000000002','DETAIL','https://aomp109.judicial.gov.tw/judbp/wkw/WHD1A02/DO_VIEWPDF.htm','法院拍賣公告 PDF'),
('20000000-0000-0000-0000-000000000004','DISCOVERY','https://web.pcc.gov.tw/opas/aspam/public/readAspam','全國財物變賣公開關鍵字查詢'),
('20000000-0000-0000-0000-000000000004','DETAIL','https://web.pcc.gov.tw/opas/aspam/public/readOneAspamDetailOld','公開財物變賣明細')
on conflict do nothing;

insert into vehicle_brands (id, canonical_name, aliases) values
('30000000-0000-0000-0000-000000000001','SYM',array['SYM','三陽','三陽牌','三陽工業','SANYANG']),
('30000000-0000-0000-0000-000000000002','YAMAHA',array['YAMAHA','Yamaha','山葉','台灣山葉']),
('30000000-0000-0000-0000-000000000003','KYMCO',array['KYMCO','光陽'])
on conflict (canonical_name) do nothing;

insert into vehicle_models (id, brand_id, canonical_name, model_code)
values ('31000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001','HM12VB','HM12VB')
on conflict do nothing;

-- Sanitized development record captured from public Shwoo AUID 939528 on 2026-08-09.
insert into organizations (id, canonical_name, organization_type, jurisdiction, official_domain)
values ('10000000-0000-0000-0000-000000000002','台灣電力股份有限公司台南區營業處','PUBLIC_ENTERPRISE','臺南市','taipower.com.tw')
on conflict do nothing;

insert into source_records (id, source_id, source_record_id, official_url, original_title, first_seen_at, last_seen_at, last_content_checksum)
values ('40000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','939528','https://shwoo.gov.taipei/shwoo/newproduct/newproduct00/product?AUID=939528','【115Y431240018】機器腳踏車1台','2026-08-09T00:00:00Z','2026-08-09T00:00:00Z','fixture-939528')
on conflict do nothing;

insert into auction_cases (id, source_id, organization_id, official_case_number, title, disposal_origin)
values ('50000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000002','115Y431240018','機器腳踏車1台','PUBLIC_ASSET_DISPOSAL')
on conflict do nothing;

insert into auction_events (id, auction_case_id, source_record_id, round_number, status, starts_at, ends_at, reserve_price, current_price)
values ('51000000-0000-0000-0000-000000000001','50000000-0000-0000-0000-000000000001','40000000-0000-0000-0000-000000000001',1,'SCHEDULED','2026-08-05T00:00:00+08:00','2026-08-12T12:00:00+08:00',2000,4300)
on conflict do nothing;

insert into lots (id, auction_event_id, lot_number, title, lot_size, bulk_lot, eligibility, storage_location, original_description)
values ('52000000-0000-0000-0000-000000000001','51000000-0000-0000-0000-000000000001','1','機器腳踏車1台',1,false,'NATURAL_PERSON_ALLOWED','臺南市永康區','已繳銷，可再領牌；目前無法發動。')
on conflict do nothing;

insert into vehicles (id, lot_id, brand_id, model_id, original_brand, original_model, model_code, vehicle_category, manufacture_year, manufacture_month, displacement_cc, color, has_key, can_start, can_test, registration_status, condition_summary, visible_damage, tax_arrears, fine_arrears, completeness, completeness_groups)
values ('53000000-0000-0000-0000-000000000001','52000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001','31000000-0000-0000-0000-000000000001','三陽牌','HM12VB','HM12VB','普通重型機車',2011,5,125,'黃色','UNKNOWN','NO','YES','RE_REGISTRATION_REQUIRED','目前車子發不動；僅提供靜態功能測試。','排氣管有生鏽痕跡','NO','NO',84,'{"identity":100,"auction":100,"condition":80,"registration":100,"fees":67,"media":100}')
on conflict do nothing;

insert into vehicle_identifiers (vehicle_id, identifier_type, normalized_value, original_value) values
('53000000-0000-0000-0000-000000000001','PLATE','367-JSJ','367－JSJ'),
('53000000-0000-0000-0000-000000000001','ENGINE','FD328707','FD328707'),
('53000000-0000-0000-0000-000000000001','FRAME','RFGHM12VRBS017215','RFGHM12VRBS017215')
on conflict do nothing;

insert into photos (vehicle_id, source_record_id, source_url, sort_order)
values ('53000000-0000-0000-0000-000000000001','40000000-0000-0000-0000-000000000001','https://shwoo.gov.taipei/shwoo/image?piccode=20260728504721&width=960&height=720&attach=20260728160842.PNG',0)
on conflict do nothing;

insert into field_evidence (entity_type, entity_id, field_name, normalized_value, source_record_id, source_text, parser_name, parser_version, extraction_method, trust, confidence) values
('vehicle','53000000-0000-0000-0000-000000000001','registration_status','"RE_REGISTRATION_REQUIRED"','40000000-0000-0000-0000-000000000001','已繳銷(可再領牌)','shwoo','1.0.0','HTML','OFFICIAL_EXPLICIT',1),
('vehicle','53000000-0000-0000-0000-000000000001','can_start','"NO"','40000000-0000-0000-0000-000000000001','目前車子發不動，不確定是否有那一部位機件故障，或電池沒電。','shwoo','1.0.0','HTML','OFFICIAL_EXPLICIT',1),
('vehicle','53000000-0000-0000-0000-000000000001','can_test','"YES"','40000000-0000-0000-0000-000000000001','僅提供靜態功能測試，無法提供道路行駛測試。','shwoo','1.0.0','HTML','OFFICIAL_EXPLICIT',1)
on conflict do nothing;
