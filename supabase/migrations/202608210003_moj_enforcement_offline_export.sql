-- The central Administrative Enforcement search form requires CAPTCHA. A
-- direct result GET is not treated as an approved automation path. Keep source
-- 003 human-assisted and document the offline HTML/detail-manifest workflow.

update sources
set name = '行政執行署動產拍賣',
    adapter_name = 'moj_enforcement',
    status = (case
      when status = 'DISABLED' then 'DISABLED'
      when status = 'DEGRADED' then 'DEGRADED'
      else 'PARTIAL'
    end)::adapter_status,
    automation_level = 'CAPTCHA_SAFE_MANUAL',
    official_url = 'https://www.tpkonsale.moj.gov.tw/Chattel',
    updated_at = now()
where id = '20000000-0000-0000-0000-000000000003';

update source_access_policies
set decision = case when decision = 'DISABLED' then 'DISABLED' else 'MANUAL_ONLY' end,
    robots_url = 'https://www.tpkonsale.moj.gov.tw/robots.txt',
    photo_rights = 'LINK_ONLY_NO_FETCH',
    personal_data_risk = 'HIGH',
    checked_on = date '2026-08-21',
    rationale = 'The official search form requires CAPTCHA. Direct result GET behavior is not used; offline human-exported result HTML or validated same-host detail manifests may be processed',
    updated_at = now()
where source_id = '20000000-0000-0000-0000-000000000003';

update source_endpoints
set notes = '人工完成 CAPTCHA 後儲存官方結果 HTML 或匯出案件明細 URL；程式不請求 Query'
where source_id = '20000000-0000-0000-0000-000000000003'
  and endpoint_type = 'DISCOVERY';

update source_endpoints
set notes = '經驗證的官方動產案件明細；PDF 只連官方全文，圖片不擷取'
where source_id = '20000000-0000-0000-0000-000000000003'
  and endpoint_type = 'DETAIL';

-- Prefer the cached document row when an older link-only row has the same
-- official identity. Raw artifact history remains immutable; only duplicate
-- presentation rows are removed before enforcing the canonical key.
with ranked_documents as (
  select id,
         row_number() over (
           partition by source_record_id, official_url
           order by (artifact_id is not null) desc, created_at, id
         ) as duplicate_rank
  from documents
)
delete from documents as document
using ranked_documents as ranked
where document.id = ranked.id
  and ranked.duplicate_rank > 1;

drop index if exists documents_source_link_only_url_uidx;
create unique index if not exists documents_source_url_uidx
  on documents (source_record_id, official_url);

create or replace function public_document_links_are_safe(
  adapter text,
  document_list jsonb
)
returns boolean
language plpgsql
immutable
set search_path = ''
as $$
declare
  document jsonb;
  document_url text;
begin
  if jsonb_typeof(document_list) <> 'array' then
    return false;
  end if;
  for document in select value from jsonb_array_elements(document_list)
  loop
    if jsonb_typeof(document) <> 'object'
       or jsonb_typeof(document -> 'label') <> 'string'
       or jsonb_typeof(document -> 'url') <> 'string' then
      return false;
    end if;
    document_url := document ->> 'url';
    if document_url ~ '[[:cntrl:]]'
       or document_url like '%#%'
       or document_url ~ '^https://[^/]*@' then
      return false;
    end if;
    if adapter = 'judicial' then
      if document_url !~* '^https://aomp109[.]judicial[.]gov[.]tw/judbp/wkw/WHD1A02/DO_VIEWPDF[.]htm[?]filenm=[^&#]+[.]pdf$' then
        return false;
      end if;
    elsif adapter = 'moj_enforcement' then
      if document_url !~* '^https://www[.]tpkonsale[.]moj[.]gov[.]tw/File/Download[?][^#]+$'
         or document_url !~* '[?&]PATH=[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(&|$)'
         or document_url !~* '[?&]NAME=[^&#/]+[.]pdf(&|$)' then
        return false;
      end if;
    elsif adapter = 'customs' then
      if document_url !~* '^https://web[.]customs[.]gov[.]tw/download/[^#]+$' then
        return false;
      end if;
    elsif adapter = 'moj_enforcement_cms' then
      if document_url !~* '^https://www[.](tpy|sly|pcy|tyy|scy|tcy|chy|cyy|tny|ksy|pty|hly|ily)[.]moj[.]gov[.]tw/media/[^?#]*[.]pdf([?][^#]*)?$' then
        return false;
      end if;
    elsif adapter = 'moj_auction' then
      if document_url !~* '^https://(auction[.]moj[.]gov[.]tw|www[.](tcc|qtc|ulc)[.]moj[.]gov[.]tw)/[^?#]*[.]pdf([?][^#]*)?$' then
        return false;
      end if;
    else
      return false;
    end if;
  end loop;
  return true;
end;
$$;

alter table public_live_motorcycle_listings
  drop constraint if exists public_live_document_links_safe_chk;
-- Older publisher versions used a host-only document gate. Quarantine any
-- legacy link that does not meet the new source-and-path validator instead of
-- allowing one stale row to abort the migration. Private artifacts/documents
-- are unaffected.
update public_live_motorcycle_listings
set documents = '[]'::jsonb
where not public_document_links_are_safe(source_adapter, documents);
alter table public_live_motorcycle_listings
  add constraint public_live_document_links_safe_chk
  check (public_document_links_are_safe(source_adapter, documents));

comment on function public_document_links_are_safe(text,jsonb) is
  'Fail-closed source-specific validation for anonymous official document links.';

revoke all on function public_document_links_are_safe(text,jsonb) from public, anon, authenticated;
grant execute on function public_document_links_are_safe(text,jsonb) to service_role;
