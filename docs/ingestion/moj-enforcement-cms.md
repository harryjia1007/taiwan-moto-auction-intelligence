# 行政執行署 13 分署 CMS 車輛公告

## 邊界

這個來源只讀取行政執行署 13 個分署的官方 `*.moj.gov.tw` CMS，不使用、提交、辨識、重用或繞過 `tpkonsale.moj.gov.tw` 的 CAPTCHA。中央查詢仍維持人工儲存結果 HTML（離線解析）或匯出明細網址的 `MANUAL_ONLY` 流程；分署 CMS 是另一個獨立、可失敗隔離的發現管道。

涵蓋臺北、士林、新北、桃園、新竹、臺中、彰化、嘉義、臺南、高雄、屏東、花蓮及宜蘭分署。2026-09-25 實測臺北、臺中與士林站的 `/robots.txt` 會以 302 導向同站 `/robots`，後者回傳 `text/plain`、空白 `Disallow` 與同站 HTTPS sitemap。adapter 僅在讀取 robots 政策期間允許這兩個精確路徑之間的有界同站 HTTPS 導向；其他導向仍須先通過已載入的 robots 規則。每次正式執行都重新讀取 robots；規則變更、403、429、跨站導向、無法驗證 sitemap 或清單入口時，該分署立即停止且保留既有資料。

## 有界發現流程

每個分署依序執行：

1. 讀取官方 `robots.txt`，若官方回應同站 HTTPS `/robots` 導向，僅在這個 robots preflight 特例追蹤並取得其中宣告的同站 HTTPS sitemap；其他導向目標仍須先受已驗證的 robots 規則允許。
2. 驗證 sitemap 是有效 XML，且至少包含一個同站 HTTPS 網址。sitemap 只用於來源與邊界驗證，不把過期的 `lastmod` 當成目前公告日期。
3. 從分署首頁既有連結找「動產拍賣公告」、「拍賣品消息」、「電子公布欄」或「最新消息」清單；`Normalnodelist` 導覽頁不占用清單名額，分署若將動產公告連回中央網站也不自動跟進。不猜測節點編號，也不掃描未知路徑。清單分頁只加 `Page`／`PageSize`，不自行加入會漏掉公告的 `type=01` 篩選。
4. 每站最多讀兩個清單、每個清單最多兩頁、每頁 30 筆，只處理最近 90 天的公告。標題明確含拍賣及車輛語意者納入；泛稱「動產拍賣」者每分署最多檢查 12 個同站官方明細，只有明細在拍賣標的脈絡明確提及車輛才納入，單獨提到汽車燃料費或牌照稅不算。純不動產標題不列入泛稱候選。超過上限、下一頁未檢查、只有跳轉連結而無日期公告列或無法辨識的新版清單都回報涵蓋缺口，不當成零筆；run 標為 `PARTIAL`。
5. 只接受同一分署 HTTPS `/post` 內容頁。泛稱公告在發現時取得的 HTML 會在 8 MiB 全次快取預算內供後續解析使用；超出快取預算時於正式 fetch 重新讀取，並先保存官方 artifact 再解析。可保存同站官方 PDF 附件；不抓 CMS 圖片，也不把頁面中的圖片網址發布成照片。

所有請求共用每秒最多一次的節流、PDF 25 MiB、HTML 1 MiB、robots 256 KiB 與 sitemap 8 MiB 的回應上限、有限重試、官方 host allowlist、MIME 驗證及可聯絡 User-Agent。請求宣告 `Accept-Encoding: identity`，以避開部分 CMS 不正常的壓縮回應；若站方仍回傳壓縮內容，實際解碼後逐塊檢查上限，且不對已解碼內容重複解碼。每個分署各自保存本次 robots 規則，sitemap、清單、內容頁與 PDF 都在連線前逐一檢查；除上方精確的 robots 文件導向外，同站 redirect 的每一個 target 也會在下一次 GET 前重新執行 `robots.can_fetch`。被禁止的內容頁不連線，被禁止的 PDF 只保留同站官方外連而不下載。artifact metadata 只保留 Content-Type、Content-Length、Content-Disposition、Cache-Control、ETag 與 Last-Modified 等安全 response headers；Set-Cookie、Authorization 與任意識別性 header 不入庫。預設單次請求 12 秒、最多 2 次嘗試、每分署 45 秒硬性上限，並可用 `MOJ_ENFORCEMENT_CMS_REQUEST_TIMEOUT_SECONDS`、`MOJ_ENFORCEMENT_CMS_MAX_REQUEST_ATTEMPTS` 與 `MOJ_ENFORCEMENT_CMS_BRANCH_DEADLINE_SECONDS` 調整。若連續三個分署的 preflight 發生同一種連線或請求逾時，系統會開啟斷路器並把剩餘分署明確標成「未檢查」；先前已有成功分署時 run 為 `PARTIAL`，一個都沒有成功時整次失敗，兩者都保留舊資料。PDF bytes 只作私人證據 artifact；公開面只可顯示通過同一套來源、host、`/media/` 路徑與個資檢查的官方全文外連，未經另外授權不對外鏡像附件。

## 正規化原則

- 只有官方文字明確寫出汽車、機車或兩者時才設定車種；只寫「車輛」保留為 `UNKNOWN`，不猜是汽車或機車。
- 只有官方明確寫出普通輕型、普通重型、大型重型或電動機車時才設定法定級別；排氣量不反推級別。
- 日期、底價、車牌、廠牌、型號、鑰匙、可發動、過戶與報廢限制都只從 HTML 明文正規化。PDF 目前先保留，不以未解析附件內容補值。
- 「無法測試」不等於「無法發動」；未知值維持 `UNKNOWN`。
- generic 車輛公告是一個 lot，不建立虛構的單車 vehicle row。只列多個車牌但沒有逐車規格配對時也維持 bulk lot，不把一段共享品牌、年份或排氣量複製到多台車。

## 已知缺口與目前整合狀態

泛標題但 HTML 正文在拍賣標的脈絡明確寫出車輛的案件會在上述有界檢查後納入；只在 PDF、圖片或 CAPTCHA 中列出個別車輛，或只有 CMS 轉址連結而無日期列的案件仍不會猜測。這些涵蓋缺口會顯示警告，可另由中央人工 manifest、正式 feed，或日後經核准的 PDF 文字解析補足；不能把本來源的零筆誤稱全站沒有拍賣。

adapter 程式與 fixture tests 位於 `services/ingest/src/ingest/adapters/moj_enforcement_cms.py` 與 `services/ingest/tests/test_moj_enforcement_cms_adapter.py`。來源政策、獨立 source UUID、repository mapping、CLI、同步警告、公開投影與每日兩次排程已設定；它不覆寫既有 CAPTCHA 人工來源。2026-09-25 的本機唯讀驗證顯示 13/13 分署預檢成功；一次有界 discovery 找到 5 筆車輛候選（臺中 3、屏東 2），並產生 21 個涵蓋警告，其中多個「動產拍賣公告」入口實際是連外或無日期列的導覽頁，不能當成已完整檢查的案件清單。臺中其中一筆可保存官方 HTML 並完成解析；這些只是本機讀取結果，正式 GitHub 排程仍須以修正後的新 run 驗證。個別分署失敗時 run 維持 `PARTIAL`，全部分署都無法安全檢查時整次失敗，既有正式資料不會被當成零案件清除。即使一次正式唯讀同步成功，也只能代表當次可讀的 CMS 公告清單，不代表中央 CAPTCHA 清單或全國所有車輛拍賣已完整涵蓋。

2026-09-25 的 GitHub-hosted 正式同步在 13 站都留下空白的 branch-discovery 例外訊息，無法從舊紀錄判定失敗類別；臺灣本機的單站健康檢查可通過，但這不等於 GitHub 排程已修復。後續分署層級的失敗診斷只記錄固定階段（`robots`、`sitemap`、`homepage`、`list_discovery`、`announcement_list`、`generic_detail`）與例外類別，不記錄原始例外文字、案件內容或來源網址。這項變更僅改善定位能力，不放寬 robots、CAPTCHA、網域、重試、速率或失敗時保留既有資料的邊界；確認 GitHub runner 的實際失敗原因後才決定下一步。
