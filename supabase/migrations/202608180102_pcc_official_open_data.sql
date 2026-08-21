update sources
set status = 'PARTIAL',
    automation_level = 'OFFICIAL_OPEN_DATA',
    official_url = 'https://web.pcc.gov.tw/opas/aspam/public/downloadOpenData',
    parser_version = '1.4.0'
where id = '20000000-0000-0000-0000-000000000004';

update source_access_policies
set decision = 'ALLOW',
    terms_url = 'https://data.gov.tw/license',
    checked_on = date '2026-08-18',
    rationale = 'ALLOW is based on official machine-readable dataset 7263 under OGDL 1.0, not an ambiguous robots response; detail matching stays on web.pcc.gov.tw HTTPS',
    updated_at = now()
where source_id = '20000000-0000-0000-0000-000000000004';

update source_endpoints
set url = 'https://web.pcc.gov.tw/opas/aspam/public/downloadOpenData',
    notes = '資料集 7263 財物變賣公告 XML；上班日每日更新'
where source_id = '20000000-0000-0000-0000-000000000004'
  and endpoint_type = 'DISCOVERY';
