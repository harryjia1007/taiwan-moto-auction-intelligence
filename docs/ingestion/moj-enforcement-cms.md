# 行政執行署 13 分署 CMS 車輛公告

## 邊界

這個來源只讀取行政執行署 13 個分署的官方 `*.moj.gov.tw` CMS，不使用、提交、辨識、重用或繞過 `tpkonsale.moj.gov.tw` 的 CAPTCHA。中央查詢仍維持人工匯出明細網址的 `MANUAL_ONLY` 流程；分署 CMS 是另一個獨立、可失敗隔離的發現管道。

涵蓋臺北、士林、新北、桃園、新竹、臺中、彰化、嘉義、臺南、高雄、屏東、花蓮及宜蘭分署。2026-08-18 至 2026-08-19 的逐站檢查顯示，13 站的 `robots.txt` 都是空白 `Disallow`，並各自宣告同站 HTTPS sitemap。每次正式執行仍會重新讀取 robots；規則變更、403、429、跨站導向、無法驗證 sitemap 或清單入口時，該分署立即停止且保留既有資料。

## 有界發現流程

每個分署依序執行：

1. 讀取官方 `robots.txt`，取得其中宣告的同站 HTTPS sitemap。
2. 驗證 sitemap 是有效 XML，且至少包含一個同站 HTTPS 網址。sitemap 只用於來源與邊界驗證，不把過期的 `lastmod` 當成目前公告日期。
3. 從分署首頁既有連結找「動產拍賣公告」、「拍賣品消息」、「電子公布欄」或「最新消息」清單；不猜測節點編號，也不掃描未知路徑。
4. 每站最多讀兩個清單、每個清單最多兩頁、每頁 30 筆，只處理最近 90 天且標題同時含拍賣語意與汽車、機車、重機或車輛語意的公告。
5. 只接受同一分署 HTTPS `/post` 內容頁。取得 HTML 後，可保存同站官方 PDF 附件；不抓 CMS 圖片，也不把頁面中的圖片網址發布成照片。

所有請求共用每秒最多一次的節流、25 MiB 單檔限制、有限重試、官方 host allowlist、MIME 驗證及可聯絡 User-Agent。每個分署各自保存本次 robots 規則，sitemap、清單、內容頁與 PDF 都在連線前逐一檢查；被禁止的內容頁不連線，被禁止的 PDF 只保留同站官方外連而不下載。artifact metadata 只保留 Content-Type、Content-Length、Content-Disposition、Cache-Control、ETag 與 Last-Modified 等安全 response headers；Set-Cookie、Authorization 與任意識別性 header 不入庫。預設單次請求 12 秒、最多 2 次嘗試、每分署 45 秒硬性上限，並可用 `MOJ_ENFORCEMENT_CMS_REQUEST_TIMEOUT_SECONDS`、`MOJ_ENFORCEMENT_CMS_MAX_REQUEST_ATTEMPTS` 與 `MOJ_ENFORCEMENT_CMS_BRANCH_DEADLINE_SECONDS` 調整。因此單一分署失聯只會留下警告，不會讓 13 站工作無限等待。PDF 只作私人證據 artifact，前端應連回官方內容頁；未經另外授權，不對外鏡像附件。

## 正規化原則

- 只有官方文字明確寫出汽車、機車或兩者時才設定車種；只寫「車輛」保留為 `UNKNOWN`，不猜是汽車或機車。
- 只有官方明確寫出普通輕型、普通重型、大型重型或電動機車時才設定法定級別；排氣量不反推級別。
- 日期、底價、車牌、廠牌、型號、鑰匙、可發動、過戶與報廢限制都只從 HTML 明文正規化。PDF 目前先保留，不以未解析附件內容補值。
- 「無法測試」不等於「無法發動」；未知值維持 `UNKNOWN`。
- generic 車輛公告是一個 lot，不建立虛構的單車 vehicle row。

## 已知缺口與目前整合狀態

部分分署只在 PDF、圖片或 CAPTCHA 中列出個別車輛，標題沒有車輛字樣。這個 adapter 會寧可漏收也不擴大掃描或猜測。這些案件仍由中央人工 manifest、取得正式 feed，或日後經核准的 PDF 文字解析補足。

adapter 程式與 fixture tests 位於 `services/ingest/src/ingest/adapters/moj_enforcement_cms.py` 與 `services/ingest/tests/test_moj_enforcement_cms_adapter.py`。來源政策、獨立 source UUID、repository mapping、CLI、同步警告、公開投影與每日兩次排程均已接妥；它不覆寫既有 CAPTCHA 人工來源。個別分署失敗時 run 維持 `PARTIAL`，全部分署都無法安全檢查時整次失敗，既有正式資料不會被當成零案件清除。即使一次正式唯讀同步成功，也只能代表當次可讀的 13 個 CMS 公告清單，不代表中央 CAPTCHA 清單或全國所有車輛拍賣已完整涵蓋。
