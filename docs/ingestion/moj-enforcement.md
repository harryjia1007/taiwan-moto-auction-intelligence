# 行政執行署動產拍賣

中央 `https://www.tpkonsale.moj.gov.tw/Chattel` 搜尋表單要求 CAPTCHA。本專案不讀取、辨識、提交、重用或繞過 CAPTCHA，也不利用「無 session 仍可能回傳結果」的直接 Query 行為。中央來源維持 `MANUAL_ONLY`，不進 GitHub Actions 排程。

## 安全匯入方式

人工作業完成官方「汽機車」查詢後，可選擇以下任一方式：

1. 將每一頁完整結果另存為 HTML，放入忽略版控的 `.data/moj-enforcement-export/`。如果頁面顯示還有其他分頁，必須逐頁另存；離線解析器會警告其他分頁，不會把單頁結果宣稱為全國完整清單。
2. 將已確認的明細網址寫入 `.data/moj-enforcement-manifest.json`。網址只能是 `https://www.tpkonsale.moj.gov.tw/Detail/Chattel?NO=<official-uuid>`。

離線 HTML 目錄可用：

```bash
docker compose run --rm ingest sync --source moj_enforcement --manifest /data/moj-enforcement-export
```

JSON manifest 仍可使用 `pnpm ingest:moj-enforcement`。manifest 範例：

```json
[
  {
    "official_url": "https://www.tpkonsale.moj.gov.tw/Detail/Chattel?NO=11111111-1111-4111-8111-111111111111",
    "title": "官方頁面的汽機車標題或摘要",
    "organization": "法務部行政執行署○○分署",
    "auction_round": 1
  }
]
```

離線解析不建立 HTTP client，只驗證同 host、HTTPS 443、無帳密資訊的 detail UUID 與 PDF 連結。人工另存的完整索引 HTML 會以 checksum-addressed 私有 raw artifact 保存；索引欄位只在該 artifact 同次送入保存時建立 evidence，並以 SHA-256 精確連結。明細文字的 evidence 則連到正式抓取的 detail HTML；detail 永遠是 snapshot 的 primary artifact。多筆案件來自同一份索引時只保留一份不可變 bytes，`raw_artifacts.source_record_id` 僅表示第一筆保存 owner，不表示索引只屬該案件。

正式 detail 匯入每次先讀官方 robots；只使用 GET、每秒最多一個請求、限制回應大小、不跟隨 redirect，且不請求 JPG/GIF 或任何圖片。PDF 不下載、不鏡像；官方全文 URL 僅作為實際包含該 href 的 index 或 detail HTML 證據。回應標頭不保存 `Set-Cookie`。

在資料庫能完整重建「一份人工匯出索引對應多筆案件」的關聯前，`reprocess --source moj_enforcement` 會 fail closed。需要新版 parser 時應重新匯入原始另存 HTML，以免在缺少索引 metadata 與 artifact 時靜默丟失日期、分署、拍次或證據。

「種類：汽機車」只代表官方搜尋分類桶，不代表一批標的同時含汽車與機車。明細沒有明示車種時保留 `UNKNOWN`；多車牌但規格無法逐車配對時保留一個 bulk lot，不複製首台規格或創造車輛列。既有資料與快照不因頁面消失而變成已拍定。
