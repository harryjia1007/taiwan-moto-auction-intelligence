import Link from "next/link";
import { Archive, ArrowRight, Heart, Search } from "lucide-react";
import type { BidEligibility, DisposalOrigin, MotorcycleFilters, RegistrationStatus } from "@tm-ai/shared";
import { requireViewer } from "@/lib/auth";
import { listMotorcycles } from "@/lib/data";
import { FilterPanel } from "@/components/filter-panel";
import { MotorcycleCard } from "@/components/motorcycle-card";

type Params = Record<string, string | string[] | undefined>;
const one = (value: string | string[] | undefined) => Array.isArray(value) ? value[0] : value;

function filtersFrom(params: Params): MotorcycleFilters {
  const price = one(params.price)?.split("-");
  const marketView = (["active", "ended", "favorites", "all"].includes(one(params.view) ?? "") ? one(params.view) : "active") as MotorcycleFilters["marketView"];
  const sort = (["auction_asc", "auction_desc", "price_asc", "price_desc", "completeness_desc"].includes(one(params.sort) ?? "") ? one(params.sort) : "auction_asc") as MotorcycleFilters["sort"];
  return {
    keyword: one(params.keyword), source: one(params.source), county: one(params.county), brand: one(params.brand), marketView, sort,
    disposalOrigin: one(params.origin) as DisposalOrigin | undefined,
    eligibility: one(params.eligibility) as BidEligibility | undefined,
    registration: one(params.registration) as RegistrationStatus | undefined,
    hasPhotos: one(params.hasPhotos) === "true", singleVehicle: one(params.singleVehicle) === "true", excludeScrap: one(params.excludeScrap) === "true",
    auctionWithinDays: Number(one(params.within)) || undefined,
    minPrice: price?.[0] ? Number(price[0]) : undefined, maxPrice: price?.[1] ? Number(price[1]) : undefined,
  };
}

function tabHref(params: Params, view: NonNullable<MotorcycleFilters["marketView"]>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (one(value) && key !== "cursor") query.set(key, one(value)!);
  query.set("view", view);
  return `/motorcycles?${query.toString()}`;
}

const viewCopy = {
  active: { label: "進行中", title: "目前仍可參與的拍賣", empty: "目前沒有符合條件且仍可參與的案件。" },
  ended: { label: "已結束紀錄", title: "已截止與歷史拍賣", empty: "目前沒有符合條件的歷史案件。" },
  favorites: { label: "我的收藏", title: "你收藏的機車", empty: "還沒有收藏符合條件的車輛。" },
  all: { label: "全部紀錄", title: "全部拍賣紀錄", empty: "沒有符合條件的案件。" },
} as const;

export default async function MotorcyclesPage({ searchParams }: { searchParams: Promise<Params> }) {
  const viewer = await requireViewer();
  const params = await searchParams;
  const filters = filtersFrom(params);
  const { items, total } = await listMotorcycles(filters, viewer);
  const values = Object.fromEntries(Object.entries(params).map(([key,value]) => [key,one(value)]));
  values.view = filters.marketView;
  values.sort = filters.sort;
  const view = filters.marketView ?? "active";
  const copy = viewCopy[view];
  return <main className="page"><div className="container">
    <section className="market-hero">
      <div className="market-intro"><div className="eyebrow">全臺官方標售情報 · OWNER WORKSPACE</div><h1>找到下一台值得出手的機車</h1><p>把法院法拍、公務機關變賣與臺北惜物網放在同一個決策畫面。先排除不能買、不能上路的案件，再比較價格、車況與官方證據。</p></div>
      <ol className="market-method" aria-label="找車方法">
        <li><span>01</span><div><strong>先看資格</strong><small>一般人能否投標</small></div></li>
        <li><span>02</span><div><strong>再看道路權利</strong><small>能否過戶或重新領牌</small></div></li>
        <li><span>03</span><div><strong>最後核對證據</strong><small>回到官方公告再出價</small></div></li>
      </ol>
    </section>
    <nav className="market-tabs" aria-label="拍賣案件狀態">
      <Link className={view === "active" ? "active" : ""} href={tabHref(params,"active")}><Search size={17}/> 進行中</Link>
      <Link className={view === "ended" ? "active" : ""} href={tabHref(params,"ended")}><Archive size={17}/> 已結束紀錄</Link>
      <Link className={view === "favorites" ? "active" : ""} href={tabHref(params,"favorites")}><Heart size={17}/> 我的收藏</Link>
    </nav>
    <FilterPanel values={values} />
    <div className="result-bar"><div><span className="result-kicker">MATCHED LOTS</span><strong>{copy.title}</strong><span>{total} 筆符合條件</span></div><span className="result-note">依你選擇的排序呈現 · 截止不等於成交</span></div>
    {items.length ? <section className="grid" aria-label="機車拍賣結果">{items.map((item)=><MotorcycleCard key={item.id} motorcycle={item} />)}</section> : <section className="empty"><h2>{copy.empty}</h2><p className="muted">可以清除部分篩選條件，或查看其他案件狀態。新的官方資料會在後續同步後出現。</p><Link className="button" href={`/motorcycles?view=${view}`}>清除篩選</Link></section>}
    {items.length > 0 && <div className="market-end"><span>所有資料都應以投標當下的官方公告為準</span><Link href="/sources">查看來源健康狀態 <ArrowRight size={15}/></Link></div>}
  </div></main>;
}
