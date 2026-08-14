import type { Metadata } from "next";

export const metadata: Metadata = { title: "免責與更正｜臺灣機車拍賣情報", robots: { index: true, follow: true } };

export default function DisclaimerPage() {
  const contact = process.env.NEXT_PUBLIC_LEGAL_CONTACT_EMAIL ?? "privacy@harryjia.com";
  return <article><p className="eyebrow">DISCLAIMER & CORRECTION</p><h1>免責、正確性與更正</h1>
    <h2>非政府官方服務</h2><p>本專案是 Harry Jia 的個人作品與私人研究工具，不代表司法院、法務部、臺北市政府、政府電子採購網或任何拍賣機關，也不構成其推薦、認可或合作。</p>
    <h2>不構成投標或法律建議</h2><p>公開 Demo 全部為合成資料，不可作為投標、估價、領牌或道路使用決策。私人情報也必須在投標當下回到官方公告核對資格、時間、價金、點交與車籍條件。</p>
    <h2>狀態語意</h2><p>「已截止」不等於「已成交」；只有官方明確結果才能標示成交。缺值不等於否定，「不能測試」也不等於「不能發動」。</p>
    <h2>更正與停止利用</h2><p>若你認為資料涉及本人、內容不正確或不應繼續利用，請寄信至 <a href={`mailto:${contact}`}>{contact}</a>，附上頁面、資料範圍與請求類型。收到爭議後會先標記並停止相關公開利用，再依個案確認。</p>
  </article>;
}
