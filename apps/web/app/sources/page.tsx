import { Badge } from "@tm-ai/ui";
import { requireViewer } from "@/lib/auth";
import { getSources } from "@/lib/data";

const date = (value: string | null) => value ? new Intl.DateTimeFormat("zh-TW", { dateStyle:"medium", timeStyle:"short", timeZone:"Asia/Taipei" }).format(new Date(value)) : "尚無";
const statusCopy = {
  ACTIVE: { label: "正式同步", tone: "good" as const, detail: "已通過真實資料庫同步" },
  PARTIAL: { label: "試運轉", tone: "warn" as const, detail: "已有介接，但尚未通過正式驗收" },
  PLANNED: { label: "未實作", tone: "neutral" as const, detail: "只在來源藍圖中，尚無介接" },
  DEGRADED: { label: "需注意", tone: "danger" as const, detail: "同步異常或來源授權仍待複核" },
  DISABLED: { label: "已停用", tone: "neutral" as const, detail: "目前不執行同步" },
};

export default async function SourcesPage() {
  const viewer = await requireViewer();
  const sources = await getSources(viewer);
  const activeCount = sources.filter((source)=>source.status==="ACTIVE").length;
  const monitoredCount = sources.filter((source)=>["ACTIVE","PARTIAL","DEGRADED"].includes(source.status)).length;
  const warningCount = sources.reduce((total, source)=>total + source.warnings.length, 0);
  return <main className="page"><div className="container">{viewer.fixture && <aside className="fixture-banner" role="status"><strong>開發展示資料</strong><span>目前數量不代表全臺即時或完整覆蓋；只有「正式同步」才通過真實資料庫驗收。</span></aside>}<section className="hero"><div><div className="eyebrow">Source observability</div><h1>資料來源健康狀態</h1><p>把「介接進度」和「最近同步狀態」分開看。未實作只代表列入藍圖，試運轉也不等於已正式上線。</p></div><div className="hero-stat"><strong>{activeCount}</strong><span className="muted">個已通過真實資料庫同步的正式來源</span></div></section>
    <section className="source-metrics" aria-label="來源概況"><article><span>正式同步</span><strong>{activeCount}</strong><small>已通過正式同步</small></article><article><span>已有介接</span><strong>{monitoredCount}</strong><small>正式或試運轉中</small></article><article><span>需要注意</span><strong>{warningCount}</strong><small>警告與人工步驟</small></article></section>
    <div className="source-table-shell"><table className="source-table"><thead><tr><th>來源</th><th>介接進度</th><th>存取／覆蓋方式</th><th>最近成功</th><th>發現／變更</th><th>解析率</th><th>警告</th></tr></thead><tbody>{sources.map((source)=>{const copy=statusCopy[source.status];return <tr key={source.id}><td data-label="來源"><strong>{source.name}</strong><br/><span className="muted">{source.adapter}</span></td><td data-label="介接進度"><Badge tone={copy.tone}>{copy.label}</Badge><br/><small className="muted">{copy.detail}</small></td><td data-label="存取／覆蓋方式">{source.automationLevel}</td><td data-label="最近成功">{date(source.lastSuccessfulAt)}</td><td data-label="發現／變更">{source.discoveredCount}／{source.changedCount}</td><td data-label="解析率">{source.parseSuccessRate===null?"—":`${source.parseSuccessRate}%`}</td><td data-label="警告" className={source.warnings.length ? "source-warning" : ""}>{source.warnings.length?source.warnings.join("；"):"無"}</td></tr>})}</tbody></table></div>
  </div></main>;
}
