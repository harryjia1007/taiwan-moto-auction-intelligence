import { Badge } from "@tm-ai/ui";
import { requireViewer } from "@/lib/auth";
import { getSources } from "@/lib/data";

const date = (value: string | null) => value ? new Intl.DateTimeFormat("zh-TW", { dateStyle:"medium", timeStyle:"short", timeZone:"Asia/Taipei" }).format(new Date(value)) : "尚無";

export default async function SourcesPage() {
  const viewer = await requireViewer();
  const sources = await getSources(viewer);
  const activeCount = sources.filter((source)=>source.status==="ACTIVE").length;
  const monitoredCount = sources.filter((source)=>["ACTIVE","PARTIAL","DEGRADED"].includes(source.status)).length;
  const warningCount = sources.reduce((total, source)=>total + source.warnings.length, 0);
  return <main className="page"><div className="container"><section className="hero"><div><div className="eyebrow">Source observability</div><h1>資料來源健康狀態</h1><p>來源是否正常、上次何時同步、解析成功率與可疑變化都在這裡。尚未實作的來源會明確標示為「規劃中」。</p></div><div className="hero-stat"><strong>{activeCount}</strong><span className="muted">個已通過即時同步的 ACTIVE 來源</span></div></section>
    <section className="source-metrics" aria-label="來源概況"><article><span>ACTIVE</span><strong>{activeCount}</strong><small>已通過正式同步</small></article><article><span>MONITORED</span><strong>{monitoredCount}</strong><small>已有程式或監測</small></article><article><span>WARNINGS</span><strong>{warningCount}</strong><small>需要人工注意</small></article></section>
    <div className="source-table-shell"><table className="source-table"><thead><tr><th>來源</th><th>狀態</th><th>自動化</th><th>最近成功</th><th>發現／變更</th><th>解析率</th><th>警告</th></tr></thead><tbody>{sources.map((source)=><tr key={source.id}><td data-label="來源"><strong>{source.name}</strong><br/><span className="muted">{source.adapter}</span></td><td data-label="狀態"><Badge tone={source.status==="ACTIVE"?"good":source.status==="DEGRADED"?"danger":source.status==="PARTIAL"?"warn":"neutral"}>{source.status}</Badge></td><td data-label="自動化">{source.automationLevel}</td><td data-label="最近成功">{date(source.lastSuccessfulAt)}</td><td data-label="發現／變更">{source.discoveredCount}／{source.changedCount}</td><td data-label="解析率">{source.parseSuccessRate===null?"—":`${source.parseSuccessRate}%`}</td><td data-label="警告" className={source.warnings.length ? "source-warning" : ""}>{source.warnings.length?source.warnings.join("；"):"無"}</td></tr>)}</tbody></table></div>
  </div></main>;
}
