import type { Metadata } from "next";

export const metadata: Metadata = { title: "資料使用說明｜臺灣機車拍賣情報", robots: { index: true, follow: true } };

export default function DataUsePage() {
  return <article><p className="eyebrow">DATA USE</p><h1>資料使用與來源治理</h1><p className="legal-updated">本頁說明作品展示與私人研究系統的資料邊界。</p>
    <h2>公開 Demo</h2><p>卡片、價格、日期、機關、地區與車況均為合成情境。示意影像為專案自有視覺，不是政府或拍賣來源照片。Demo 不提供真實案件深層連結。</p>
    <h2>私人來源資料</h2><p>私人系統只處理經審查允許的公開來源，保留來源時間、checksum 與欄位證據。未知資料保持未知，截止不等於成交，來源頁面消失也不會被推論為售出。</p>
    <h2>自動存取政策</h2><ul><li>臺北惜物網及法務部集中拍賣：依已記錄的來源政策進行私人唯讀同步。</li><li>司法院動產拍賣：因目前 robots 規則禁止所有自動路徑，live discovery 已停用。</li><li>政府採購網：等待自動存取與授權方式確認，不進入無人排程。</li><li>行政執行署：由人完成 CAPTCHA 後，才處理已驗證的明細網址。</li></ul>
    <h2>授權與顯名</h2><p>程式碼的 Apache-2.0 授權不涵蓋政府文件、照片或第三方素材。政府資料的使用依個別來源聲明與<a href="https://data.gov.tw/license" target="_blank" rel="noreferrer">政府資料開放授權條款第 1 版</a>處理，且不使用政府標誌暗示官方認可。</p>
  </article>;
}
