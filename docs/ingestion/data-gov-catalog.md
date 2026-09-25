# 政府資料開放平臺目錄監看

## 用途與非用途

這個元件只監看政府資料開放平臺的官方「全部資料集詮釋資料」每日匯出，目的是及早發現可能新增的行政執行、司法或政府汽機車拍賣開放資料集。官方目錄來源是 [資料集 6564](https://data.gov.tw/dataset/6564) 所提供的 `https://data.gov.tw/api/front/dataset/export?format=json`；平臺標示每日凌晨 1 時更新，適用政府資料開放授權條款第 1 版。

目錄中的一筆 metadata **不是拍賣案件**。監看器不建立 `source`、`source_record`、公開案件、車輛、照片、附件或收藏資料，也不呼叫候選資料集的下載網址。候選必須先由人員檢查授權、內容、更新頻率、robots、個資與附件權利，再以獨立變更加入來源清冊及 adapter。

2026-08-22 臺灣時間的初始目錄快照共有 53,094 筆；其中找不到行政執行署提供且同時具有汽車、機車、車輛或非不動產動產語意的資料集。現有行政執行拍賣開放資料系列是歷史「已拍定不動產」，不能代替進行中汽機車案件來源。

## 有界網路規則

- 只允許 HTTPS `data.gov.tw:443` 的固定 export path 與唯一 `format=json` 參數。
- 最多接受兩次仍落在同一固定 endpoint 的安全導向；跨 host、帳密 URL、額外參數或其他 path 立即失敗。
- 使用可聯絡 User-Agent，單一連線、連線 10 秒／讀取 120 秒 timeout，解壓後最多 128 MiB、最多 100,000 筆 metadata。
- 一般接受 `application/json`；平臺目前把 JSON attachment 標為 `text/html`，因此只有同時帶 `.json` filename 的官方 attachment 才接受這個窄例外，內容仍必須是 UTF-8 JSON array。
- 不保存或輸出 `Set-Cookie`、聯絡人姓名、電話、電子郵件、資料集描述或其他任意 catalog 欄位。輸出候選只含資料集 ID、上架日、候選類別與 `https://data.gov.tw/dataset/{id}` 官方 metadata 連結。

## 候選判定

每筆候選必須同時具備：

1. 可辨識的政府提供機關語意；
2. 拍賣、法拍、標售、變賣、拍定、公開競價等拍賣語意；
3. 汽車、機車、重機、車輛、公務車或具體車種語意；
4. 上架日在預設 14 日視窗內。

純土地、房屋、建物或不動產資料不會因「不動產」包含「動產」二字而入選。混合資料集只有在 metadata 明確出現車輛語意時才成為人工審核候選。若語意符合但沒有可解析上架日，監看器 fail closed，不把它宣稱為「新資料集」，只增加 `undated_matching_entries` 計數且不產生 GitHub candidate warning。候選數大於安全上限、catalog 結構異常、MIME 不符、過小／過大、網路失敗或跨站導向都視為 validation failure。

## 執行與狀態

```sh
python -m ingest watch-data-catalog --lookback-days 14
```

沒有候選時輸出 `success`；有候選時輸出 `warning` 並在 GitHub Actions 建立只含資料集 ID 與官方 metadata URL 的 warning，兩者皆回傳 exit code 0。只有網路或驗證失敗回傳非 0。這個工作安排在正式來源同步 jobs 完成後執行，不需要 Supabase secrets，也不影響前一次案件資料或來源健康狀態。
