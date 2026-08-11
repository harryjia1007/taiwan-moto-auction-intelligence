import Link from "next/link";
import { Search, SlidersHorizontal, Sparkles, X } from "lucide-react";

const counties = ["臺北市","新北市","桃園市","臺中市","臺南市","高雄市","基隆市","新竹市","嘉義市","新竹縣","苗栗縣","彰化縣","南投縣","雲林縣","嘉義縣","屏東縣","宜蘭縣","花蓮縣","臺東縣","澎湖縣","金門縣","連江縣"];

function quickHref(view: string, query = "") {
  return `/motorcycles?view=${view}${query}`;
}

export function FilterPanel({ values }: { values: Record<string, string | undefined> }) {
  const view = values.view ?? "active";
  const refinementKeys = ["county","source","origin","brand","eligibility","registration","price","hasPhotos","singleVehicle","excludeScrap","within"];
  const activeCount = refinementKeys.filter((key) => Boolean(values[key])).length + (values.keyword ? 1 : 0);
  const refinementOpen = activeCount > (values.keyword ? 1 : 0) || Boolean(values.sort && values.sort !== "auction_asc");
  return <section className="filter-panel" aria-label="拍賣篩選">
    <div className="filter-heading">
      <div><span>SEARCH WORKSPACE</span><strong>用你的購車條件篩選</strong></div>
      {activeCount > 0 && <Link href={quickHref(view)} className="filter-reset"><X size={14}/> 清除 {activeCount} 個條件</Link>}
    </div>
    <form action="/motorcycles" method="get">
      <input type="hidden" name="view" value={view}/>
      <div className="search-row">
        <label className="search-field"><span className="sr-only">想找什麼車？</span><Search size={19}/><input className="input" name="keyword" defaultValue={values.keyword} placeholder="輸入車款、車牌、案號或機關" aria-label="關鍵字" /></label>
        <button className="button filter-submit" type="submit"><Search size={17}/> 搜尋車輛</button>
      </div>
      <div className="quick-filters" aria-label="快速篩選">
        <span><Sparkles size={14}/> 一鍵找車</span>
        <Link href={quickHref(view, "&eligibility=NATURAL_PERSON_ALLOWED&excludeScrap=true")}>一般人可買、可上路優先</Link>
        <Link href={quickHref(view, "&hasPhotos=true&singleVehicle=true")}>有照片的單台車</Link>
        <Link href={quickHref(view, "&within=7")}>7 天內截止</Link>
        <Link href={quickHref(view, "&origin=JUDICIAL_EXECUTION")}>法院法拍</Link>
        <Link href={quickHref(view, "&source=shwoo")}>臺北惜物網</Link>
      </div>
      <details className="filter-refinements" open={refinementOpen}>
        <summary><SlidersHorizontal size={16}/> 地區、來源與進階條件 {activeCount > 0 && <small>{activeCount}</small>}</summary>
        <div className="refinement-body">
          <div className="core-refinements">
            <label><span>地區</span><select className="select" name="county" defaultValue={values.county ?? ""} aria-label="地區"><option value="">全臺灣</option>{counties.map((value)=><option key={value}>{value}</option>)}</select></label>
            <label><span>來源</span><select className="select" name="source" defaultValue={values.source ?? ""} aria-label="資料來源"><option value="">全部官方來源</option><option value="judicial">司法院地院法拍</option><option value="pcc">政府採購網變賣</option><option value="shwoo">臺北惜物網</option></select></label>
            <label><span>排序</span><select className="select" name="sort" defaultValue={values.sort ?? "auction_asc"} aria-label="排序方式"><option value="auction_asc">截止時間：最近優先</option><option value="auction_desc">截止時間：最晚優先</option><option value="price_asc">價格：低到高</option><option value="price_desc">價格：高到低</option><option value="completeness_desc">資料完整度：高到低</option></select></label>
          </div>
        <div className="advanced-grid">
          <label><span>處分性質</span><select className="select" name="origin" defaultValue={values.origin ?? ""} aria-label="處分性質"><option value="">不限</option><option value="JUDICIAL_EXECUTION">司法強制執行法拍</option><option value="ADMINISTRATIVE_ENFORCEMENT">行政執行拍賣</option><option value="PUBLIC_ASSET_DISPOSAL">公有財產變賣</option><option value="SCRAP_DISPOSAL">公務報廢財物</option><option value="IMPOUNDED_UNCLAIMED">移置保管逾期未領</option><option value="CRIMINAL_SEIZURE_OR_FORFEITURE">刑事扣押／沒收</option><option value="CUSTOMS_FORFEITURE">海關沒入／拍賣</option></select></label>
          <label><span>廠牌</span><select className="select" name="brand" defaultValue={values.brand ?? ""} aria-label="廠牌"><option value="">不限</option>{["SYM","KYMCO","YAMAHA","HONDA","SUZUKI","PGO","GOGORO"].map((value)=><option key={value}>{value}</option>)}</select></label>
          <label><span>投標資格</span><select className="select" name="eligibility" defaultValue={values.eligibility ?? ""} aria-label="投標資格"><option value="">不限</option><option value="NATURAL_PERSON_ALLOWED">一般民眾可投標</option><option value="LICENSED_RECYCLER_ONLY">限合格回收商</option><option value="UNKNOWN">資格未確認</option></select></label>
          <label><span>領牌狀態</span><select className="select" name="registration" defaultValue={values.registration ?? ""} aria-label="牌照狀態"><option value="">不限</option><option value="NORMAL_TRANSFER">可正常過戶</option><option value="RE_REGISTRATION_REQUIRED">需重新領牌</option><option value="INSPECTION_REQUIRED">需檢驗／認證</option><option value="SCRAP_ONLY">僅供報廢</option><option value="UNKNOWN">未確認</option></select></label>
          <label><span>價格</span><select className="select" name="price" defaultValue={values.price ?? ""} aria-label="價格"><option value="">不限</option><option value="0-10000">一萬元以下</option><option value="10000-50000">一至五萬元</option><option value="50000-">五萬元以上</option></select></label>
          <label><span>拍賣時間</span><select className="select" name="within" defaultValue={values.within ?? ""} aria-label="拍賣時間範圍"><option value="">不限</option><option value="3">3 天內</option><option value="7">7 天內</option><option value="14">14 天內</option><option value="30">30 天內</option></select></label>
        </div>
        <div className="check-filters">
          <label><input type="checkbox" name="hasPhotos" value="true" defaultChecked={values.hasPhotos === "true"}/> 有官方照片</label>
          <label><input type="checkbox" name="singleVehicle" value="true" defaultChecked={values.singleVehicle === "true"}/> 只看單台標售</label>
          <label><input type="checkbox" name="excludeScrap" value="true" defaultChecked={values.excludeScrap === "true"}/> 排除不得領牌／報廢車</label>
        </div>
        <button className="button refinement-submit" type="submit">套用所有條件</button>
        </div>
      </details>
    </form>
  </section>;
}
