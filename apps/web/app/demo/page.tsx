import type { Metadata } from "next";
import Link from "next/link";
import { CalendarDays, ChevronRight, Database, ExternalLink, Filter, LockKeyhole, ShieldCheck } from "lucide-react";
import { displacementBandFromQuery, type MotorcycleClass } from "@tm-ai/shared";
import { filterDemoMotorcycles, syntheticDemoMotorcycles } from "@/lib/demo-data";
import { motorcycleClassLabels } from "@/lib/labels";

export const metadata: Metadata = {
  title: "臺灣機車拍賣情報｜互動作品展示",
  description: "使用完全合成資料展示機車拍賣情報的篩選、風險判斷與證據導向設計。",
  robots: { index: true, follow: true },
};

type Params = Record<string, string | string[] | undefined>;
const first = (value: string | string[] | undefined) => Array.isArray(value) ? value[0] : value;
const all = (value: string | string[] | undefined) => Array.isArray(value) ? value : value ? [value] : [];
const classValues = new Set<MotorcycleClass>(["ORDINARY_LIGHT","ORDINARY_HEAVY","LARGE_HEAVY","ELECTRIC_MOTORCYCLE","HEAVY_UNSPECIFIED","UNKNOWN"]);
const ccLabels: Record<string,string> = { "le-125": "125 以下", "126-150": "126–150", "151-250": "151–250", "251-550": "251–550", "gt-550": "551 以上", unknown: "未提供" };

function demoHref(params: Params, view: "active" | "ended", within?: number) {
  const query = new URLSearchParams();
  const vehicleClass = first(params.vehicleClass);
  if (vehicleClass) query.set("vehicleClass", vehicleClass);
  all(params.cc).forEach((value) => query.append("cc", value));
  query.set("view", view);
  if (view === "active" && within) query.set("within", String(within));
  return `/demo?${query.toString()}`;
}

export default async function DemoPage({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const view = first(params.view) === "ended" ? "ended" : "active";
  const withinRaw = Number(first(params.within));
  const within = view === "active" && [3,7,14,30].includes(withinRaw) ? withinRaw : undefined;
  const rawClass = first(params.vehicleClass) as MotorcycleClass | undefined;
  const vehicleClass = rawClass && classValues.has(rawClass) ? rawClass : undefined;
  const cc = all(params.cc).map(displacementBandFromQuery).filter((value): value is NonNullable<typeof value> => Boolean(value));
  const now = new Date();
  const items = filterDemoMotorcycles(syntheticDemoMotorcycles(now), { view, within, vehicleClass, cc }, now);
  const summary = [view === "ended" ? "已結束" : "進行中", within ? `${within} 天內` : null, vehicleClass ? motorcycleClassLabels[vehicleClass] : null, ...all(params.cc).map((value) => `${ccLabels[value]} c.c.`), `共 ${items.length} 筆`].filter(Boolean).join("・");
  return <main className="demo-page">
    <header className="demo-header"><div className="container demo-header-inner"><Link href="/demo" className="demo-brand">HARRY JIA <span>PROJECT</span></Link><nav><Link href="#architecture">專案架構</Link><Link href="/legal/data-use">資料使用</Link><Link href="/login"><LockKeyhole size={15}/> 私人情報台</Link></nav></div></header>
    <div className="container">
      <aside className="demo-disclosure" role="note"><ShieldCheck size={19}/><div><strong>互動作品展示・全部為合成資料</strong><span>本頁不對應任何真實案件、車牌或自然人，也不會連線至政府拍賣網站。</span></div></aside>
      <section className="demo-hero"><div><p className="eyebrow">TAIWAN MOTO AUCTION INTELLIGENCE</p><h1>先看能不能買，<br/>再決定值不值得追。</h1><p>把分散的機車拍賣條件整理成可搜尋、可比較、可追溯的決策介面。正式情報與原始證據維持私人存取。</p><div className="demo-hero-actions"><a href="#market" className="button">體驗找車流程 <ChevronRight size={16}/></a><Link href="/legal/disclaimer">閱讀使用限制</Link></div></div><div className="demo-architecture-card"><Database size={24}/><strong>Evidence-first pipeline</strong><span>官方來源 → 私有保存 → 保守正規化 → 欄位證據 → 私人儀表板</span><small>公開作品層只使用獨立合成資料</small></div></section>
      <section className="demo-market" id="market"><div className="demo-section-heading"><div><span>INTERACTIVE DEMO</span><h2>用真正找車的方式操作</h2></div><p>先選案件狀態，再用法定級別與排氣量縮小範圍。</p></div>
        <nav className="demo-tabs" aria-label="展示案件狀態"><Link className={view === "active" && within !== 30 ? "active" : ""} href={demoHref(params,"active")}>進行中</Link><Link className={view === "active" && within === 30 ? "active" : ""} href={demoHref(params,"active",30)}>30 天內</Link><Link className={view === "ended" ? "active" : ""} href={demoHref(params,"ended")}>已結束</Link><span title="正式站登入後可使用">收藏（私人）</span></nav>
        <form className="demo-filters" action="/demo" method="get"><input type="hidden" name="view" value={view}/><label><span>拍賣時間</span><select name="within" defaultValue={within ?? ""} disabled={view === "ended"}><option value="">不限</option><option value="3">3 天內</option><option value="7">7 天內</option><option value="14">14 天內</option><option value="30">30 天內</option></select></label><label><span>法定級別</span><select name="vehicleClass" defaultValue={vehicleClass ?? ""}><option value="">全部級別</option>{Object.entries(motorcycleClassLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><fieldset><legend>排氣量（可複選）</legend>{Object.entries(ccLabels).map(([value,label])=><label key={value}><input type="checkbox" name="cc" value={value} defaultChecked={all(params.cc).includes(value)}/>{label}</label>)}</fieldset><button className="button" type="submit"><Filter size={15}/> 套用</button></form>
        <div className="demo-current"><span>目前瀏覽</span><strong>{summary}</strong><Link href={`/demo?view=${view}`}>清除條件</Link></div>
        <div className="demo-grid">{items.map((item)=><article className="demo-card" key={item.id}><div className={`demo-image ${item.imageTone}`}><span>合成示意影像</span><small>非官方照片</small></div><div className="demo-card-body"><div className="demo-source"><ShieldCheck size={13}/>{item.sourceLabel}<span>{item.county}</span></div><h3>{item.title}</h3><div className="demo-gates"><div><span>誰能投標</span><strong>{item.eligibility}</strong></div><div><span>能否上路</span><strong>{item.registration}</strong></div></div><dl><div><dt>級別</dt><dd>{motorcycleClassLabels[item.vehicleClass]}</dd></div><div><dt>排氣量</dt><dd>{item.displacementCc ? `${item.displacementCc} c.c.` : "官方未提供"}</dd></div><div><dt>示意價格</dt><dd>{item.price === null ? "未公開" : `NT$ ${item.price.toLocaleString("zh-TW")}`}</dd></div><div><dt>拍賣時間</dt><dd><CalendarDays size={13}/>{new Intl.DateTimeFormat("zh-TW",{month:"numeric",day:"numeric",timeZone:"Asia/Taipei"}).format(new Date(item.auctionAt))}</dd></div></dl><p>{item.condition}</p><span className="demo-card-note">此卡片僅展示資訊架構，不可用於投標</span></div></article>)}</div>
        {!items.length && <div className="empty"><h3>沒有符合條件的合成案例</h3><p>請清除部分排氣量或級別條件。</p></div>}
      </section>
      <section className="demo-explainer" id="architecture"><div><span>01</span><h2>資料不亂猜</h2><p>未知、否定、衝突與無法測試分開保存；排氣量不會被拿來冒充法定級別。</p></div><div><span>02</span><h2>證據可回查</h2><p>私人正式站保留原始快照、checksum 與欄位證據，但公開作品層不散布附件。</p></div><div><span>03</span><h2>來源會停手</h2><p>遇到 robots、CAPTCHA、登入或授權不明時 fail closed，不以涵蓋率犧牲合規。</p></div></section>
      <footer className="demo-footer"><div><strong>臺灣機車拍賣情報</strong><span>Harry Jia 個人作品・非政府官方服務</span></div><nav><Link href="/legal/privacy">隱私</Link><Link href="/legal/data-use">資料使用</Link><Link href="/legal/disclaimer">免責與更正</Link><a href="https://data.gov.tw/license" target="_blank" rel="noreferrer">政府資料開放授權 <ExternalLink size={12}/></a></nav></footer>
    </div>
  </main>;
}
