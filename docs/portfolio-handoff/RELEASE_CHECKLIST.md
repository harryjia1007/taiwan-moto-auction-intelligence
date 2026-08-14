# Portfolio Release Checklist

公開合成 Demo：`PUBLIC_DEMO_PUBLISHED`  
私人真實資料系統：`NO_GO`

- [x] `/demo` 桌機與手機截圖已人工檢查，沒有真實案件或政府標誌
- [x] `pnpm test`、`pnpm lint`、`pnpm build`、`pnpm test:e2e` 全部成功
- [x] Python fixture tests 全部成功
- [ ] Supabase migration、seed 與 pgTAP 全部成功
- [x] `pnpm audit:public` 為零發現
- [x] Judicial 無人排程已停用，離線 reprocess 仍可用
- [x] PCC 為 `REVIEW_REQUIRED`，未進入無人排程
- [x] Shwoo 與 MOJ robots／條款清冊已由人工複查日期確認
- [x] 公開頁無分析 Cookie、廣告、聯絡表單、私人 API 或 Supabase 請求
- [x] 所有影像與字型都有自有或可再利用證明
- [x] 隱私、資料使用、免責、更正／下架說明與聯絡信箱已確認
- [x] `harryjia.com` 的 Cloudflare Web Analytics 與 Worker 彙總統計已更新隱私告知
- [ ] 熟悉臺灣個資與政府資料授權的律師已複核預定公開內容

公開合成 Demo 已由專案負責人於 2026 年 8 月 15 日明確授權發布，網址為 `https://harryjia.com/projects/taiwan-moto-auction`。未完成項目仍阻擋私人系統上線、真實資料公開與任何公開爬蟲；不得據此把私人系統標示為 production ready。
