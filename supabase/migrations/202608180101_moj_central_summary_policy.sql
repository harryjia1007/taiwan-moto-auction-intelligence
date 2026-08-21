update source_access_policies
set checked_on = date '2026-08-18',
    rationale = 'ALLOW is limited to auction.moj.gov.tw. Unreviewed prosecutor-office redirect targets are not contacted; exact central list-row evidence is retained as a partial record',
    updated_at = now()
where source_id = '20000000-0000-0000-0000-000000000005';

update sources
set parser_version = '1.4.0'
where id = '20000000-0000-0000-0000-000000000005';
