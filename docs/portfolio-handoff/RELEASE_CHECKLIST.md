# Portfolio Release Checklist

公開正式案件頁：`PUBLIC_LIVE_MARKETPLACE`

完整私人 ingestion：`CONFIGURATION_REQUIRED`

- [x] 正式網址可載入公開案件資料
- [x] 預設顯示進行中案件，已截止案件不誤列為進行中
- [x] 桌機與手機沒有水平溢位
- [x] 搜尋、狀態、級別、排氣量與照片篩選可用
- [x] 排氣量級距與即時筆數、無照片緊湊卡片、本機收藏及 2–3 台比較可用
- [x] 公開案件詳細頁可用，並可直接返回官方完整公告
- [x] 收藏案件的截止與價格異動可在再次造訪時提示；不宣稱保證送達
- [x] 卡片顯示末二至三碼遮蔽的車牌、官方案號、日期、價格、資格、領牌狀態與官方連結
- [x] 公開頁沒有完整車牌、引擎／車身／VIN 號碼、service-role key、私人 artifacts 或私人 Storage URL
- [x] 法院 PDF 只連回官方來源，不保存公開副本
- [x] 找車頁已移除流程宣言、廣告預留及重複免責文字
- [x] 正式頁部署後無瀏覽器錯誤
- [ ] `SUPABASE_SECRET_KEY`（或舊版 `SUPABASE_SERVICE_ROLE_KEY`）已設定於排程環境
- [ ] Supabase migration、seed 與 pgTAP 已在正式相容環境完整驗證
- [ ] 尚未授權或需要 CAPTCHA 的來源已取得可自動化依據

最後驗證：2026 年 8 月 15 日；正式頁已通過案件載入、本機收藏與公開詳細頁 smoke test；Cloudflare Worker version `915d2627-76c6-4d34-8fb2-8ee6bf5f5dfe`。
