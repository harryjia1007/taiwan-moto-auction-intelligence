# 臺灣機車拍賣情報 — Portfolio Handoff

正式網址：`https://harryjia.com/projects/taiwan-moto-auction/`

公開頁是精簡的正式案件查詢工具，從 Supabase 唯讀公開 view 取得經整理的案件資料，提供進行中、30 天內、已結束、關鍵字、法定級別、排氣量及照片篩選。每筆案件顯示官方已提供的車牌、案號、價格、日期、機關、地點、資格、領牌狀態、車況及照片，並連回官方公告。

## 公開邊界

- 公開：正規化案件欄位、官方公告連結、允許公開載入的官方照片。
- 不公開：Supabase service-role key、原始 artifacts、私人 Storage、完整證據庫、收藏、來源維運資料及 owner 帳號。
- 不保存或公開複製法院 PDF；網站只連回官方 PDF。
- 未取得的欄位顯示「官方未提供」或「未確認」，不得推測補值。

## 目前介面

主頁只保留頁名、同步時間、案件狀態、搜尋篩選、目前條件、完整案件卡片、來源摘要與必要免責。流程宣言、廣告預留及重複說明不放在找車流程中；完整政策集中於 `legal.html`。

## 上架狀態

- 狀態：`PUBLIC_LIVE_MARKETPLACE`
- 個人網站 repo：`harryjia1007/harry-world`
- Git commit：`96c79cb`
- Cloudflare Worker version：`aa3b6a80-ad3c-4ff2-8596-fc94e159cb84`

公開頁已上線；私人 ingestion 的 service-role 排程、完整資料庫驗證與未授權來源仍須各自通過發布閘門，不得因公開頁上線而視為全部來源已自動化。
