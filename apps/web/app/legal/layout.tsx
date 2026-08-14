import Link from "next/link";

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return <main className="legal-page"><div className="legal-shell"><header><Link href="/demo">← 返回作品展示</Link><span>臺灣機車拍賣情報</span></header>{children}<footer><Link href="/legal/privacy">隱私</Link><Link href="/legal/data-use">資料使用</Link><Link href="/legal/disclaimer">免責與更正</Link></footer></div></main>;
}
