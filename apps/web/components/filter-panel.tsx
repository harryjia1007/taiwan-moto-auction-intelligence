import Link from "next/link";
import { CalendarClock, Camera, MapPin, Search, ShieldCheck, SlidersHorizontal, Sparkles, X } from "lucide-react";
import { disposalOriginLabels, eligibilityLabels, motorcycleClassLabels, registrationLabels } from "@/lib/labels";

const counties = ["臺北市","新北市","桃園市","臺中市","臺南市","高雄市","基隆市","新竹市","嘉義市","新竹縣","苗栗縣","彰化縣","南投縣","雲林縣","嘉義縣","屏東縣","宜蘭縣","花蓮縣","臺東縣","澎湖縣","金門縣","連江縣"];

function quickHref(view: string, query = "") {
  return `/motorcycles?view=${view}${query}`;
}

const filterLabels: Record<string, string> = {
  keyword: "關鍵字", county: "地區", source: "來源", origin: "處分性質", brand: "廠牌",
  vehicleClass: "機車級別", eligibility: "投標資格", registration: "領牌狀態", price: "價格",
  hasPhotos: "有官方照片", singleVehicle: "單台標售", within: "截止時間", sort: "排序", cc: "排氣量",
};

const ccLabels: Record<string, string> = {
  "le-50": "50 c.c. 以下", "51-125": "51–125 c.c.", "126-250": "126–250 c.c.",
  "251-550": "251–550 c.c.", "gt-550": "551 c.c. 以上", unknown: "官方未提供",
};

const sourceLabels: Record<string, string> = {
  judicial: "司法院地院法拍", moj_auction: "法務部查扣物拍賣", moj_enforcement: "行政執行署拍賣",
  pcc: "政府採購網變賣", shwoo: "臺北惜物網",
};

const sortLabels: Record<string, string> = {
  auction_asc: "截止最近", auction_desc: "截止最晚", price_asc: "價格低到高",
  price_desc: "價格高到低", completeness_desc: "資料最完整",
};

function filterValue(key: string, value: string) {
  if (key === "source") return sourceLabels[value] ?? value;
  if (key === "origin") return disposalOriginLabels[value as keyof typeof disposalOriginLabels] ?? value;
  if (key === "vehicleClass") return motorcycleClassLabels[value as keyof typeof motorcycleClassLabels] ?? value;
  if (key === "eligibility") return eligibilityLabels[value as keyof typeof eligibilityLabels] ?? value;
  if (key === "registration") return registrationLabels[value as keyof typeof registrationLabels] ?? value;
  if (key === "sort") return sortLabels[value] ?? value;
  if (key === "price") return ({ "0-10000": "一萬元以下", "10000-50000": "一至五萬元", "50000-": "五萬元以上" } as Record<string,string>)[value] ?? value;
  if (key === "within") return `${value} 天內`;
  if (key === "cc") return ccLabels[value] ?? value;
  if (key === "hasPhotos" || key === "singleVehicle") return "是";
  return value;
}

function removeHref(current: URLSearchParams, removeKey: string, removeValue?: string) {
  const query = new URLSearchParams(current);
  query.delete("cursor");
  if (removeKey === "cc" && removeValue) {
    const remaining = query.getAll("cc").filter((value) => value !== removeValue);
    query.delete("cc");
    remaining.forEach((value) => query.append("cc", value));
  } else query.delete(removeKey);
  if (!query.has("view")) query.set("view", "active");
  return `/motorcycles?${query.toString()}`;
}

export function FilterPanel({ queryString, total }: { queryString: string; total: number }) {
  const query = new URLSearchParams(queryString);
  const values = Object.fromEntries(query.entries()) as Record<string, string | undefined>;
  const ccValues = query.getAll("cc");
  const view = values.view ?? "active";
  const refinementKeys = ["county","source","origin","brand","vehicleClass","eligibility","registration","price","hasPhotos","singleVehicle","within"];
  const advancedKeys = ["origin","brand","vehicleClass","cc","eligibility","registration","price","hasPhotos","singleVehicle"];
  const activeCount = refinementKeys.filter((key) => Boolean(values[key])).length + ccValues.length + (values.keyword ? 1 : 0);
  const advancedCount = advancedKeys.filter((key) => Boolean(values[key])).length;
  const refinementOpen = advancedCount > 0 || ccValues.length > 0;
  const activeFilters = ["keyword", ...refinementKeys, ...(values.sort && values.sort !== "auction_asc" ? ["sort"] : [])]
    .filter((key, index, keys) => keys.indexOf(key) === index && Boolean(values[key]));
  const viewLabel = ({ active: "進行中", ended: "已結束", favorites: "我的收藏", scrap: "報廢／回收", all: "全部紀錄" } as Record<string,string>)[view] ?? "進行中";
  const summaryParts = [viewLabel, values.within ? `${values.within} 天內` : null, values.vehicleClass ? motorcycleClassLabels[values.vehicleClass as keyof typeof motorcycleClassLabels] : null, ...ccValues.map((value) => ccLabels[value]), `共 ${total} 筆`].filter(Boolean);
  return <section className="filter-panel" aria-label="拍賣篩選">
    <div className="filter-summary" role="status" aria-label="目前瀏覽條件"><span>目前瀏覽</span><strong>{summaryParts.join("・")}</strong><small>{activeCount ? `已套用 ${activeCount} 個條件` : "尚未套用精準條件"}</small></div>
    <div className="filter-heading">
      <div><span>第一步 · 輸入線索</span><strong>先輸入你知道的線索</strong><small>車款、車牌、案號或機關都可以</small></div>
      {activeCount > 0 && <Link href={quickHref(view)} className="filter-reset"><X size={14}/> 清除 {activeCount} 個條件</Link>}
    </div>
    <form action="/motorcycles" method="get">
      <input type="hidden" name="view" value={view}/>
      <div className="search-row">
        <label className="search-field"><span className="sr-only">想找什麼車？</span><Search size={19}/><input className="input" name="keyword" defaultValue={values.keyword} placeholder="例如：品牌、重型機車、車牌、法院機關" aria-label="關鍵字" /></label>
        <button className="button filter-submit" type="submit"><Search size={17}/> 開始找車</button>
      </div>
      <div className="preset-heading"><span><Sparkles size={14}/> 第二步 · 常用找車方式</span><small>不知道怎麼篩時，先選一個</small></div>
      <div className="decision-presets" aria-label="快速篩選">
        <Link href={quickHref(view, "&eligibility=NATURAL_PERSON_ALLOWED&excludeScrap=true")}><span><ShieldCheck size={18}/></span><div><strong>一般人可投標</strong><small>排除回收商限定案件</small></div></Link>
        <Link href={quickHref(view, "&registration=NORMAL_TRANSFER")}><span><MapPin size={18}/></span><div><strong>可正常過戶</strong><small>道路權利較明確</small></div></Link>
        <Link href={quickHref(view, "&hasPhotos=true&singleVehicle=true")}><span><Camera size={18}/></span><div><strong>有照片的單台車</strong><small>先看得到車況</small></div></Link>
        <Link href={quickHref(view, "&within=7")}><span><CalendarClock size={18}/></span><div><strong>7 天內截止</strong><small>掌握近期機會</small></div></Link>
      </div>
      <div className="core-refinements always-visible">
        <label><span>地區</span><select className="select" name="county" defaultValue={values.county ?? ""} aria-label="地區"><option value="">全臺灣</option>{counties.map((value)=><option key={value}>{value}</option>)}</select></label>
        <label><span>官方來源</span><select className="select" name="source" defaultValue={values.source ?? ""} aria-label="資料來源"><option value="">全部官方來源</option><option value="judicial">司法院地院法拍</option><option value="moj_auction">法務部查扣物拍賣</option><option value="moj_enforcement">行政執行署拍賣</option><option value="pcc">政府採購網變賣</option><option value="shwoo">臺北惜物網</option></select></label>
        <label><span>拍賣時間</span><select className="select" name="within" defaultValue={values.within ?? ""} aria-label="拍賣時間範圍" disabled={view === "ended"}><option value="">不限</option><option value="3">3 天內</option><option value="7">7 天內</option><option value="14">14 天內</option><option value="30">30 天內</option></select></label>
        <label><span>結果排序</span><select className="select" name="sort" defaultValue={values.sort ?? "auction_asc"} aria-label="排序方式"><option value="auction_asc">截止時間：最近優先</option><option value="auction_desc">截止時間：最晚優先</option><option value="price_asc">價格：低到高</option><option value="price_desc">價格：高到低</option><option value="completeness_desc">資料完整度：高到低</option></select></label>
        <button className="button core-submit" type="submit">套用</button>
      </div>
      <details className="filter-refinements" open={refinementOpen}>
        <summary><SlidersHorizontal size={16}/> 更多精準條件 <span>級別、資格、領牌、價格、時間</span>{advancedCount > 0 && <small>{advancedCount}</small>}</summary>
        <div className="refinement-body">
        <div className="advanced-grid">
          <label><span>處分性質</span><select className="select" name="origin" defaultValue={values.origin ?? ""} aria-label="處分性質"><option value="">不限</option><option value="JUDICIAL_EXECUTION">司法強制執行法拍</option><option value="ADMINISTRATIVE_ENFORCEMENT">行政執行拍賣</option><option value="PUBLIC_ASSET_DISPOSAL">公有財產變賣</option><option value="SCRAP_DISPOSAL">公務報廢財物</option><option value="IMPOUNDED_UNCLAIMED">移置保管逾期未領</option><option value="CRIMINAL_SEIZURE_OR_FORFEITURE">刑事扣押／沒收</option><option value="CUSTOMS_FORFEITURE">海關沒入／拍賣</option></select></label>
          <label><span>廠牌</span><select className="select" name="brand" defaultValue={values.brand ?? ""} aria-label="廠牌"><option value="">不限</option>{["SYM","KYMCO","YAMAHA","HONDA","SUZUKI","PGO","GOGORO"].map((value)=><option key={value}>{value}</option>)}</select></label>
          <label><span>機車級別</span><select className="select" name="vehicleClass" defaultValue={values.vehicleClass ?? ""} aria-label="機車級別"><option value="">全部級別</option><option value="ORDINARY_LIGHT">普通輕型</option><option value="ORDINARY_HEAVY">普通重型</option><option value="LARGE_HEAVY">大型重型</option><option value="ELECTRIC_MOTORCYCLE">電動機車</option><option value="HEAVY_UNSPECIFIED">重型（級別未明）</option><option value="UNKNOWN">級別未確認</option></select></label>
          <fieldset className="cc-filter"><legend>排氣量（可複選）</legend>{Object.entries(ccLabels).map(([value,label])=><label key={value}><input type="checkbox" name="cc" value={value} defaultChecked={ccValues.includes(value)}/>{label}</label>)}<small>排氣量只用於篩選，不會推定法定機車級別。</small></fieldset>
          <label><span>投標資格</span><select className="select" name="eligibility" defaultValue={values.eligibility ?? ""} aria-label="投標資格"><option value="">不限</option><option value="NATURAL_PERSON_ALLOWED">一般民眾可投標</option><option value="LICENSED_RECYCLER_ONLY">限合格回收商</option><option value="UNKNOWN">資格未確認</option></select></label>
          <label><span>領牌狀態</span><select className="select" name="registration" defaultValue={values.registration ?? ""} aria-label="牌照狀態"><option value="">不限</option><option value="NORMAL_TRANSFER">可正常過戶</option><option value="RE_REGISTRATION_REQUIRED">需重新領牌</option><option value="INSPECTION_REQUIRED">需檢驗／認證</option><option value="SCRAP_ONLY">僅供報廢</option><option value="UNKNOWN">未確認</option></select></label>
          <label><span>價格</span><select className="select" name="price" defaultValue={values.price ?? ""} aria-label="價格"><option value="">不限</option><option value="0-10000">一萬元以下</option><option value="10000-50000">一至五萬元</option><option value="50000-">五萬元以上</option></select></label>
        </div>
        <div className="check-filters">
          <label><input type="checkbox" name="hasPhotos" value="true" defaultChecked={values.hasPhotos === "true"}/> 有官方照片</label>
          <label><input type="checkbox" name="singleVehicle" value="true" defaultChecked={values.singleVehicle === "true"}/> 只看單台標售</label>
          <span className="muted">報廢與回收商限定案件固定收在獨立專區，不會混入一般找車結果。</span>
        </div>
        <button className="button refinement-submit" type="submit">套用所有條件</button>
        </div>
      </details>
      {(activeFilters.length > 0 || ccValues.length > 0) && <div className="active-filter-row" aria-label="目前套用條件"><span>目前條件</span>{activeFilters.map((key)=><Link key={key} href={removeHref(query,key)}>{filterLabels[key]}：{filterValue(key,values[key]!)} <X size={12}/></Link>)}{ccValues.map((value)=><Link key={`cc-${value}`} href={removeHref(query,"cc",value)}>排氣量：{filterValue("cc",value)} <X size={12}/></Link>)}</div>}
    </form>
  </section>;
}
