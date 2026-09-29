import Link from "next/link";
import { ArrowLeft, ArrowUpRight, Columns3 } from "lucide-react";
import { formatMoney, isEndedAuction, type Motorcycle } from "@tm-ai/shared";
import { requireViewer } from "@/lib/auth";
import { isComparisonEligibleListing, parseComparisonIds } from "@/lib/comparison";
import { getMotorcycle } from "@/lib/data";
import { eligibilityLabels, fourStateLabels, motorcycleClassLabels, registrationLabels } from "@/lib/labels";

const vehicleTypeLabels = { MOTORCYCLE: "機車", CAR: "汽車", MIXED: "汽機車混合批次", UNKNOWN: "車種未確認" } as const;
const carCategoryLabels = { PASSENGER: "小客車／轎車", SUV: "休旅車", VAN: "廂型／客貨車", TRUCK: "貨車", BUS: "大客車／遊覽車", OTHER: "其他汽車", UNKNOWN: "汽車類別未確認" } as const;

function price(motorcycle: Motorcycle) {
  if (motorcycle.soldPrice !== null) return `成交價：${formatMoney(motorcycle.soldPrice)}`;
  if (motorcycle.currentPrice !== null) return `目前出價：${formatMoney(motorcycle.currentPrice)}`;
  if (motorcycle.reservePrice !== null) return `公告底價：${formatMoney(motorcycle.reservePrice)}`;
  return "價格未確認";
}

function auctionTime(motorcycle: Motorcycle) {
  if (!motorcycle.auctionAt) return "拍賣時間未確認";
  const timestamp = new Date(motorcycle.auctionAt);
  if (!Number.isFinite(timestamp.getTime())) return "拍賣時間未確認";
  const options: Intl.DateTimeFormatOptions = motorcycle.auctionDatePrecision === "DATE"
    ? { year: "numeric", month: "numeric", day: "numeric", timeZone: "Asia/Taipei" }
    : { year: "numeric", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Taipei" };
  const formatted = new Intl.DateTimeFormat("zh-TW", options).format(timestamp);
  if (!isEndedAuction(motorcycle)) return `${formatted}（尚未截止）`;
  return motorcycle.auctionStatus === "SOLD" ? `${formatted}（官方標示已成交）` : `${formatted}（已截止，成交結果未確認）`;
}

function classification(motorcycle: Motorcycle) {
  const vehicleType = motorcycle.vehicleType ?? "MOTORCYCLE";
  if (vehicleType === "CAR") return `${vehicleTypeLabels.CAR}・${carCategoryLabels[motorcycle.carCategory ?? "UNKNOWN"]}`;
  if (vehicleType === "MOTORCYCLE") return `${vehicleTypeLabels.MOTORCYCLE}・${motorcycleClassLabels[motorcycle.vehicleClass]}`;
  return vehicleTypeLabels[vehicleType];
}

function manufacture(motorcycle: Motorcycle) {
  if (!motorcycle.manufactureYear) return "出廠年月未確認";
  return motorcycle.manufactureMonth ? `${motorcycle.manufactureYear} 年 ${motorcycle.manufactureMonth} 月` : `${motorcycle.manufactureYear} 年（月份未確認）`;
}

export default async function CompareMotorcyclesPage({ searchParams }: { searchParams: Promise<{ ids?: string | string[] }> }) {
  const viewer = await requireViewer();
  const params = await searchParams;
  const ids = parseComparisonIds(params.ids);
  const records = ids.length ? await Promise.all(ids.map((id) => getMotorcycle(id, viewer))) : [];
  const motorcycles = records.filter((item): item is Motorcycle => item !== null && isComparisonEligibleListing(item));
  const missingCount = records.length - motorcycles.length;

  if (ids.length < 2 || motorcycles.length < 2) {
    return <main className="page comparison-page"><div className="container comparison-container">
      <Link className="comparison-back" href="/motorcycles"><ArrowLeft size={15}/> 返回找車</Link>
      <section className="empty comparison-empty">
        <Columns3 size={28}/><h1>請先選擇 2–3 輛車</h1>
        <p className="muted">比較網址無效、項目已不存在，或目前選擇不足兩台。請回到私人找車頁重新加入候選車輛。</p>
        <Link className="button" href="/motorcycles">回到找車結果</Link>
      </section>
    </div></main>;
  }

  const rows = [
    { label: "價格", render: price },
    { label: "拍賣／截止", render: auctionTime },
    { label: "車種／法定級別", render: classification },
    { label: "排氣量", render: (item: Motorcycle) => item.displacementCc === null ? "排氣量未確認" : `${item.displacementCc.toLocaleString("zh-TW")} c.c.` },
    { label: "出廠年月", render: manufacture },
    { label: "投標資格", render: (item: Motorcycle) => eligibilityLabels[item.bidEligibility] },
    { label: "牌照／領牌", render: (item: Motorcycle) => registrationLabels[item.registrationStatus] },
    { label: "能否發動", render: (item: Motorcycle) => fourStateLabels[item.canStart] },
    { label: "能否測試", render: (item: Motorcycle) => fourStateLabels[item.canTest] },
    { label: "里程", render: (item: Motorcycle) => item.mileageKm === null ? "里程未確認" : `${item.mileageKm.toLocaleString("zh-TW")} km` },
    { label: "地點", render: (item: Motorcycle) => item.location ?? item.county ?? "地點未確認" },
    { label: "情報完整度", render: (item: Motorcycle) => `${item.completeness}%` },
  ];

  return <main className="page comparison-page"><div className="container comparison-container">
    <Link className="comparison-back" href="/motorcycles"><ArrowLeft size={15}/> 返回找車</Link>
    <header className="comparison-header">
      <div><span className="eyebrow">私人候選清單</span><h1>比較候選車輛</h1></div>
      <p>並排檢查價格、截止、資格、領牌與車況。未確認的資料維持未知，不以排氣量推定法定級別。</p>
    </header>
    {missingCount > 0 && <p className="notice" role="status">有 {missingCount} 筆項目已不存在或目前無權讀取；下表只顯示仍可安全取得的候選車輛。</p>}
    <div className="comparison-table-shell" role="region" aria-label="候選車輛比較表" tabIndex={0}>
      <table className="comparison-table">
        <caption className="sr-only">{motorcycles.length} 輛候選車輛的拍賣與車況比較</caption>
        <thead><tr><th scope="col">比較項目</th>{motorcycles.map((item) => <th scope="col" key={item.id}><Link href={`/motorcycles/${item.id}`}>{item.name}</Link><small>{item.organization}</small></th>)}</tr></thead>
        <tbody>
          {rows.map((row) => <tr key={row.label}><th scope="row">{row.label}</th>{motorcycles.map((item) => <td key={item.id}>{row.render(item)}</td>)}</tr>)}
          <tr className="comparison-risk-row"><th scope="row">重要風險</th>{motorcycles.map((item) => <td key={item.id}>{item.riskBadges.length
            ? <ul>{item.riskBadges.map((risk) => <li key={risk}>{risk}</li>)}</ul>
            : <span>未列出額外風險；仍須核對官方公告</span>}</td>)}</tr>
          <tr className="comparison-detail-row"><th scope="row">完整資料</th>{motorcycles.map((item) => <td key={item.id}><Link href={`/motorcycles/${item.id}`}>查看車況、證據與官方全文 <ArrowUpRight size={14}/></Link></td>)}</tr>
        </tbody>
      </table>
    </div>
    <p className="comparison-footnote">比較結果只整理目前已保存的官方資訊，不代表得標、可過戶或可上路；投標前仍須回到發布機關的最新公告逐項確認。</p>
  </div></main>;
}
