import type { Metadata } from "next";
import Link from "next/link";
import { headers } from "next/headers";
import { Bike, Database, Heart, LogOut, Search } from "lucide-react";
import { getViewer } from "@/lib/auth";
import "./globals.css";

export const metadata: Metadata = { title: "臺灣機車拍賣情報", description: "可信、可追溯的臺灣政府機車拍賣情報", robots: { index: false, follow: false } };

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const publicSurface = (await headers()).get("x-tm-public-surface") === "1";
  const viewer = publicSurface ? null : await getViewer();
  return <html lang="zh-TW"><body>
    {viewer && <header className="app-header"><div className="container header-inner">
      <Link href="/motorcycles?view=active" className="brand" aria-label="臺灣機車拍賣情報首頁">
        <span className="brand-mark"><Bike size={19} /></span>
        <span className="brand-copy"><small>臺灣官方標售情報</small><strong>機車拍賣情報</strong></span>
      </Link>
      <div className="header-actions">
        <span className="private-status"><i/> 私人情報台</span>
        <nav className="nav" aria-label="主要導覽">
          <Link href="/motorcycles?view=active"><Search size={16}/><span>找車</span></Link>
          <Link href="/motorcycles?view=favorites"><Heart size={16}/><span>收藏</span></Link>
          <Link href="/sources"><Database size={16}/><span>來源狀態</span></Link>
          <Link href="/auth/signout" className="logout-link" title="登出" aria-label="登出"><LogOut size={16}/></Link>
        </nav>
      </div>
    </div></header>}
    {children}
    {viewer && <nav className="mobile-nav" aria-label="手機主要導覽">
      <Link href="/motorcycles?view=active"><Search size={20}/><span>找車</span></Link>
      <Link href="/motorcycles?view=favorites"><Heart size={20}/><span>收藏</span></Link>
      <Link href="/sources"><Database size={20}/><span>來源</span></Link>
    </nav>}
  </body></html>;
}
