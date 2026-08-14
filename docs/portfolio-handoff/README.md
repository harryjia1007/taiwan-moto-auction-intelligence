# 臺灣機車拍賣情報 — Portfolio Handoff

建議整合路徑：`harryjia.com/projects/taiwan-moto-auction`

這個交付包只描述公開的合成資料互動展示。正式案件、登入、收藏、來源健康、官方文件、照片、證據及資料庫全部留在私人系統，不是作品集部署範圍。

## 可移植範圍

- `apps/web/app/demo/page.tsx`：公開作品頁與篩選介面
- `apps/web/lib/demo-data.ts`：完全合成資料與純函式篩選
- `apps/web/app/legal/*`：隱私、資料使用、免責與更正頁
- `apps/web/app/globals.css` 中 `.demo-*` 與 `.legal-*` 樣式
- `design-tokens.json`：顏色、字體、圓角與間距

公開頁不得匯入 `apps/web/lib/fixtures.ts`、Supabase client、私人 API 或任何官方附件。若整合環境沒有本專案的 shared package，需把 MotorcycleClass 與 DisplacementBand 型別及排氣量比對函式一併複製成局部純函式。

## 專案故事

臺灣機車拍賣資訊散落在多個政府入口、公告與附件中。此專案的重點不是做另一個列表，而是把「誰能投標、能否領牌、車況是否真的有證據、期限是否仍有效」放在使用者決策之前。資料管線採證據優先、未知不等於否定、來源不允許自動存取就停止的設計。

## 技術架構

公開層是無資料庫、無 Cookie、無追蹤碼的 Next.js 合成 Demo。私人層使用 owner-only Supabase Auth、PostgreSQL RLS、私有 Storage、checksum 原始檔、歷史 snapshots 與非同步 Python adapters。公開與私人層沒有資料依賴。

## 上架狀態

公開合成資料作品頁已於 2026 年 8 月 15 日由專案負責人明確授權發布：

- 正式網址：`https://harryjia.com/projects/taiwan-moto-auction`
- 個人網站 repo：`harryjia1007/harry-world`
- Git commit：`4fe3afd`
- Cloudflare Worker version：`f5622619-41b3-4db8-8769-b29e9a5183c6`

狀態為 `PUBLIC_DEMO_PUBLISHED`。私人真實資料系統仍是 `NO_GO`，因 Supabase migration／seed／pgTAP 尚未在可用的容器環境完成，且公開真實案件仍明確排除。未來改版須繼續遵守本資料夾的公開資料邊界。
