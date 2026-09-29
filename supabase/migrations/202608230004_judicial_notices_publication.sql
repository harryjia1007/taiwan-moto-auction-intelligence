-- Extend the anonymous outbound-document guard for the Judicial Yuan main-site
-- supplemental notice source. Only the reviewed link-only /tw/dl shape is
-- accepted; no attachment bytes are downloaded or mirrored by the adapter.

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
  query_string text;
  query_pair text;
  query_key text;
  query_value text;
  seen_keys text[];
  path_value text;
  name_value text;
  download_value text;
begin
  if jsonb_typeof(document_list) <> 'array' then
    return false;
  end if;
  for document in select value from jsonb_array_elements(document_list)
  loop
    if jsonb_typeof(document) <> 'object' then
      return false;
    end if;
    if not (document ? 'label')
       or not (document ? 'url')
       or (document - 'label' - 'url') <> '{}'::jsonb
       or jsonb_typeof(document -> 'label') <> 'string'
       or btrim(document ->> 'label') = ''
       or jsonb_typeof(document -> 'url') <> 'string' then
      return false;
    end if;
    document_url := document ->> 'url';
    if document_url ~ '[[:cntrl:]]'
       or document_url like '%#%'
       or document_url !~ '^https://'
       or document_url ~ '^https://[^/]*@'
       or split_part(document_url, '?', 1) like '%;%' then
      return false;
    end if;

    if adapter = 'judicial' then
      if document_url !~* '^https://aomp109[.]judicial[.]gov[.]tw(:443)?/judbp/wkw/WHD1A02/DO_VIEWPDF[.]htm[?]filenm=[^&#]+[.]pdf$' then
        return false;
      end if;
    elsif adapter = 'judicial_notices' then
      if document_url !~ '^https://www[.]judicial[.]gov[.]tw(:443)?/tw/dl-[0-9]+-[A-Za-z0-9-]+[.]html$' then
        return false;
      end if;
    elsif adapter = 'moj_enforcement' then
      if document_url !~ '^https://www[.]tpkonsale[.]moj[.]gov[.]tw(:443)?/File/Download[?][^#]+$' then
        return false;
      end if;
      query_string := split_part(document_url, '?', 2);
      seen_keys := '{}';
      path_value := null;
      name_value := null;
      download_value := null;
      foreach query_pair in array string_to_array(query_string, '&')
      loop
        if query_pair = '' or strpos(query_pair, '=') = 0 then
          return false;
        end if;
        query_key := split_part(query_pair, '=', 1);
        query_value := substr(query_pair, strpos(query_pair, '=') + 1);
        if query_key not in ('PATH', 'NAME', 'DOWNLOAD')
           or query_key = any(seen_keys) then
          return false;
        end if;
        seen_keys := array_append(seen_keys, query_key);
        if query_key = 'PATH' then path_value := query_value;
        elsif query_key = 'NAME' then name_value := query_value;
        else download_value := query_value;
        end if;
      end loop;
      if path_value is null
         or path_value !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
         or name_value is null
         or name_value !~* '[.]pdf$'
         or name_value ~* '(/|\\|%2f|%5c)'
         or (download_value is not null and download_value !~* '[.]pdf$') then
        return false;
      end if;
    elsif adapter = 'customs' then
      if document_url !~* '^https://web[.]customs[.]gov[.]tw(:443)?/download/[^#]+$' then
        return false;
      end if;
    elsif adapter = 'moj_enforcement_cms' then
      if document_url !~* '^https://www[.](tpy|sly|pcy|tyy|scy|tcy|chy|cyy|tny|ksy|pty|hly|ily)[.]moj[.]gov[.]tw(:443)?/media/[^?#]*[.]pdf([?][^#]*)?$' then
        return false;
      end if;
    elsif adapter = 'moj_auction' then
      if document_url !~* '^https://(auction[.]moj[.]gov[.]tw|www[.](tcc|qtc|ulc)[.]moj[.]gov[.]tw)(:443)?/[^?#]*[.]pdf([?][^#]*)?$' then
        return false;
      end if;
    else
      return false;
    end if;
  end loop;
  return true;
end;
$$;

revoke all on function public_document_links_are_safe(text,jsonb) from public, anon, authenticated;
grant execute on function public_document_links_are_safe(text,jsonb) to service_role;
