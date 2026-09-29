# Claude 整合 Prompt

你要維護已整合到 `harryjia.com/projects/taiwan-moto-auction` 的「臺灣汽機車拍賣情報」公開查詢頁。

公開頁可唯讀連線 Supabase 的 `public_live_motorcycle_listings` 匿名投影，但不可連線任何私人表、私人 API、Storage 或 ingestion 服務。只可使用 publishable／anon key；不得帶入 `.env`、OWNER_EMAIL、service-role／secret key、完整車牌、引擎／車身／VIN 號碼、人名、私人地址、原始 artifact 或快取照片。法院與機關文件只使用通過來源別 URL 驗證的官方外連，不建立公開鏡像。

視覺方向是安靜、可信、編輯感強的資料產品：米白底、深墨綠、少量銅色，優先呈現投標資格、領牌條件、拍賣日期、法定級別與排氣量。手機版必須先看見目前篩選摘要，支援「進行中、30 天內、已結束、我的收藏」、法定級別與 125 以下、126–150、151–250、251–550、551 以上及未提供的 CC 級距。排氣量不可推定法定級別，已截止不可寫成已成交；無照片案件不可放大型佔位圖。

此作品已整合至 `harryjia1007/harry-world`，正式路徑為 `/projects/taiwan-moto-auction`。本 repository 的共享資料契約與 Supabase migration 是案件欄位的唯一規格；Cloud 只改公開呈現層，不另建爬蟲、不重命名資料欄位、不寫入正式資料。後續改版先拉取兩個 repository 的最新提交，在獨立分支完成公開資料掃描、無障礙檢查、桌機與手機測試，再執行 Cloudflare production deploy，避免覆蓋 ingestion 或資料庫變更。
