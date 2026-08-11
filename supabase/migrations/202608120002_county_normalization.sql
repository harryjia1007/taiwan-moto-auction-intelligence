-- Prefer an explicit administrative area in an address, then fall back to the
-- standard location of district courts and enforcement branches whose names
-- omit the 市/縣 suffix.

create or replace function public.taiwan_county_from_text(input_text text)
returns text
language sql
immutable
parallel safe
as $$
  with normalized as (
    select replace(coalesce(input_text, ''), '台', '臺') as value
  )
  select coalesce(
    substring(value from '(臺北市|新北市|桃園市|臺中市|臺南市|高雄市|基隆市|新竹市|嘉義市|新竹縣|苗栗縣|彰化縣|南投縣|雲林縣|嘉義縣|屏東縣|宜蘭縣|花蓮縣|臺東縣|澎湖縣|金門縣|連江縣)'),
    case
      when value like '%士林%' then '臺北市'
      when value like '%橋頭%' then '高雄市'
      when value like '%臺北%' then '臺北市'
      when value like '%新北%' then '新北市'
      when value like '%桃園%' then '桃園市'
      when value like '%新竹%' then '新竹市'
      when value like '%苗栗%' then '苗栗縣'
      when value like '%臺中%' then '臺中市'
      when value like '%南投%' then '南投縣'
      when value like '%彰化%' then '彰化縣'
      when value like '%雲林%' then '雲林縣'
      when value like '%嘉義%' then '嘉義市'
      when value like '%臺南%' then '臺南市'
      when value like '%高雄%' then '高雄市'
      when value like '%屏東%' then '屏東縣'
      when value like '%臺東%' then '臺東縣'
      when value like '%花蓮%' then '花蓮縣'
      when value like '%宜蘭%' then '宜蘭縣'
      when value like '%基隆%' then '基隆市'
      when value like '%澎湖%' then '澎湖縣'
      when value like '%金門%' then '金門縣'
      when value like '%連江%' then '連江縣'
      else null
    end
  )
  from normalized;
$$;
