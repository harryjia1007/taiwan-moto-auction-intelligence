import Link from "next/link";
import { Archive, ArrowLeft, ArrowRight, CalendarRange, Heart, Search, ShieldCheck, TimerReset } from "lucide-react";
import { requireViewer } from "@/lib/auth";
import { decodeMarketplaceCursor, listMotorcycles } from "@/lib/data";
import { FilterPanel } from "@/components/filter-panel";
import { MotorcycleCard } from "@/components/motorcycle-card";
import { ComparisonProvider } from "@/components/comparison-provider";
import { marketplaceViewHref, pageParamsToSearchParams, parseMarketplaceQuery, sanitizedMarketplaceQuery, type PageSearchParams } from "@/lib/marketplace-query";

function paginationHref(filters: URLSearchParams, cursor: string | null, limit: number) {
  const query = new URLSearchParams(filters);
  if (limit !== 24) query.set("limit", String(limit));
  if (cursor) query.set("cursor", cursor); else query.delete("cursor");
  return `/motorcycles?${query.toString()}`;
}

const viewCopy = {
  active: { label: "進行中", title: "目前仍可參與的拍賣", empty: "目前沒有符合條件且仍可參與的案件。" },
  ended: { label: "已結束紀錄", title: "已截止與歷史拍賣", empty: "目前沒有符合條件的歷史案件。" },
  favorites: { label: "我的收藏", title: "你收藏的車輛", empty: "還沒有收藏符合條件的車輛。" },
  scrap: { label: "報廢／回收專區", title: "報廢與回收商限定標售", empty: "目前沒有符合條件的報廢或回收商限定案件。" },
  all: { label: "全部紀錄", title: "全部拍賣紀錄", empty: "沒有符合條件的案件。" },
} as const;

const sortCopy = {
  auction_asc: "截止最近優先",
  auction_desc: "截止最晚優先",
  price_asc: "價格低到高",
  price_desc: "價格高到低",
  completeness_desc: "資料最完整優先",
} as const;

export default async function MotorcyclesPage({ searchParams }: { searchParams: Promise<PageSearchParams> }) {
  const viewer = await requireViewer();
  const params = await searchParams;
  const rawQuery = pageParamsToSearchParams(params);
  const { filters, limit, cursor } = parseMarketplaceQuery(rawQuery);
  const decodedCursor = decodeMarketplaceCursor(cursor);
  const currentCursor = decodedCursor?.sort === (filters.sort ?? "auction_asc") ? cursor : null;
  const { items, total, nextCursor, displacementFacetCounts } = await listMotorcycles(filters, viewer, limit, currentCursor);
  const cleanQuery = sanitizedMarketplaceQuery(rawQuery);
  const view = filters.marketView ?? "active";
  const copy = viewCopy[view];
  return <main className="page marketplace-page"><div className="container">{viewer.fixture && <aside className="fixture-banner" role="status"><strong>私人開發展示資料</strong><span>目前筆數不代表全臺完整即時覆蓋；報廢與回收商限定案件已固定移到獨立專區。</span></aside>}
    <section className="market-launch">
      <div className="launch-copy"><div className="eyebrow">私人汽機車拍賣情報</div><h1>今天想找什麼車？</h1><p>先選汽車或機車，再確認誰能買、能不能上路，並比較價格與截止時間。所有判斷都能回到官方證據。</p></div>
      <div className="launch-summary" aria-label="目前瀏覽摘要">
        <div><strong>{total}</strong><span>{copy.label}案件</span></div>
        <ul><li><ShieldCheck size={15}/> 資格與領牌先看</li><li><TimerReset size={15}/> {sortCopy[filters.sort ?? "auction_asc"]}</li></ul>
      </div>
    </section>
    <nav className="market-tabs" aria-label="拍賣案件狀態">
      <Link className={view === "active" && filters.auctionWithinDays !== 30 ? "active" : ""} href={marketplaceViewHref(rawQuery,"active")}><Search size={17}/><span><strong>找進行中</strong><small>仍可參與</small></span></Link>
      <Link className={view === "active" && filters.auctionWithinDays === 30 ? "active" : ""} href={marketplaceViewHref(rawQuery,"active",30)}><CalendarRange size={17}/><span><strong>30 天內</strong><small>近期拍賣</small></span></Link>
      <Link className={view === "ended" ? "active" : ""} href={marketplaceViewHref(rawQuery,"ended")}><Archive size={17}/><span><strong>看歷史</strong><small>截止不等於成交</small></span></Link>
      <Link className={view === "favorites" ? "active" : ""} href={marketplaceViewHref(rawQuery,"favorites")}><Heart size={17}/><span><strong>我的收藏</strong><small>候選車輛</small></span></Link>
      <Link className={`scrap-tab ${view === "scrap" ? "active" : ""}`} href={marketplaceViewHref(rawQuery,"scrap")}><Archive size={17}/><span><strong>報廢／回收</strong><small>與一般找車分開</small></span></Link>
    </nav>
    <FilterPanel queryString={cleanQuery.toString()} total={total} displacementFacetCounts={displacementFacetCounts} />
    <div className="result-bar"><div><span className="result-kicker">搜尋結果</span><strong>{copy.title}</strong><span>{total} 筆符合條件</span></div><span className="result-note">{sortCopy[filters.sort ?? "auction_asc"]} · 截止不等於成交</span></div>
    <ComparisonProvider>
      {items.length ? <section className="grid" aria-label="汽機車拍賣結果">{items.map((item)=><MotorcycleCard key={item.id} motorcycle={item} />)}</section> : <section className="empty"><h2>{copy.empty}</h2><p className="muted">可以清除部分篩選條件，或查看其他案件狀態。新的官方資料會在後續同步後出現。</p><Link className="button" href={`/motorcycles?view=${view}`}>清除篩選</Link></section>}
    </ComparisonProvider>
    {(currentCursor || nextCursor) && <nav className="cursor-pagination" aria-label="搜尋結果分頁">
      <div><strong>本頁顯示 {items.length} 筆</strong><span>完整條件共有 {total} 筆；分頁網址可收藏或返回。</span></div>
      <div>
        {currentCursor && <Link href={paginationHref(cleanQuery, null, limit)}><ArrowLeft size={15}/> 回第一頁</Link>}
        {nextCursor
          ? <Link className="button" href={paginationHref(cleanQuery, nextCursor, limit)}>下一批結果 <ArrowRight size={15}/></Link>
          : <span>已到最後一頁</span>}
      </div>
    </nav>}
    {items.length > 0 && <div className="market-end"><span>所有資料都應以投標當下的官方公告為準</span><Link href="/sources">查看來源健康狀態 <ArrowRight size={15}/></Link></div>}
  </div></main>;
}
