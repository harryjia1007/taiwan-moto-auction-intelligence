import type { Metadata } from "next";

export const metadata: Metadata = { title: "隱私說明｜臺灣汽機車拍賣情報", robots: { index: true, follow: true } };

export default function PrivacyPage() {
  const contact = process.env.NEXT_PUBLIC_LEGAL_CONTACT_EMAIL ?? "privacy@harryjia.com";
  return <article><p className="eyebrow">隱私保護</p><h1>隱私說明</h1><p className="legal-updated">最後更新：2026 年 9 月 25 日</p>
    <h2>公開作品展示</h2><p>公開 Demo 使用完全合成資料，不對應任何自然人、真實車牌或拍賣案件；公開正式案件頁則只顯示經遮蔽的官方公告摘要，不提供私人原始檔。本專案不在 Demo 中設定分析 Cookie、廣告追蹤或聯絡表單，也不會因瀏覽頁面而即時查詢政府網站。</p>
    <h2>私人情報台</h2><p>正式情報台僅允許 OWNER_EMAIL 登入。收藏、原始附件、證據與圖片存放於受列級安全規則保護的私人資料庫及 Storage，不提供公開 API。</p>
    <h2>保存與權利</h2><p>可能含有識別資料的私人原始檔，依案件截止、取得及後續證據引用的較晚時間設定至少 12 個月的保存期限。目前到期清理需由管理者手動執行及核對，尚未啟用自動刪除排程，因此不保證到期當下立即刪除。執行清理後只刪除私人檔案內容，保留 checksum、來源與刪除稽核紀錄。當事人可請求查詢、更正、停止利用或刪除。</p>
    <h2>聯絡方式</h2><p>請寄信至 <a href={`mailto:${contact}`}>{contact}</a>。原則上 7 天內確認收到，30 天內完成初步決定；資料正確性有爭議時，會先停止相關對外利用。</p>
  </article>;
}
