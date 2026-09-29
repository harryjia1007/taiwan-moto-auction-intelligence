"use client";

import Link from "next/link";
import { RotateCcw, TriangleAlert } from "lucide-react";

export default function MotorcyclesError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="page"><div className="container">
    <section className="empty data-load-error" role="alert">
      <TriangleAlert size={30}/>
      <h1>資料目前無法完整載入</h1>
      <p>系統沒有把讀取失敗誤當成「官方未提供」。你可以立即重試；若仍失敗，請到來源狀態確認最近同步情況。</p>
      <div className="error-actions">
        <button type="button" className="button" onClick={reset}><RotateCcw size={16}/> 重新載入</button>
        <Link href="/sources">查看來源狀態</Link>
      </div>
    </section>
  </div></main>;
}
