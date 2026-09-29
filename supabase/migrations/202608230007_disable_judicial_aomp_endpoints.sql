-- The Judicial movable-auction application disallows unattended access. Keep
-- its official URLs only as provenance for human-reviewed manifest imports;
-- neither endpoint is eligible for scheduler discovery or document fetching.

update public.source_endpoints
set enabled = false,
    notes = case endpoint_type
      when 'DISCOVERY' then
        '人工參考：中央查詢禁止程式連線；只能匯入人工核對的官方清單'
      else
        '人工參考：只驗證人工清單中的官方 PDF 網址；程式不下載或鏡像 PDF'
    end
where source_id = '20000000-0000-0000-0000-000000000002'
  and url like 'https://aomp109.judicial.gov.tw/%';
