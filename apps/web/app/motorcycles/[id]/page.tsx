import Link from "next/link";
import { notFound } from "next/navigation";
import { Badge } from "@tm-ai/ui";
import { ArrowLeft, CalendarClock, CheckCircle2, CircleHelp, ExternalLink, FileSearch, Gavel, ShieldAlert, ShieldCheck } from "lucide-react";
import { formatMoney, isEndedAuction, quickSummary } from "@tm-ai/shared";
import { requireViewer } from "@/lib/auth";
import { getMotorcycle } from "@/lib/data";
import { disposalOriginLabels, eligibilityLabels, fourStateLabels, registrationLabels } from "@/lib/labels";
import { FavoriteButton } from "@/components/favorite-button";
import { PhotoGallery } from "@/components/photo-gallery";

const displayDate = (value: string | null) => value ? new Intl.DateTimeFormat("zh-TW", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Taipei" }).format(new Date(value)) : "未確認";
const displayAuctionDate = (value: string | null, precision: "DATE" | "DATETIME" = "DATETIME") => value ? new Intl.DateTimeFormat("zh-TW", precision === "DATE" ? { dateStyle: "medium", timeZone: "Asia/Taipei" } : { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Taipei" }).format(new Date(value)) : "未確認";
const evidenceLabels: Record<string, string> = {
  registration_status: "牌照／領牌狀態", can_start: "能否發動", can_test: "能否測試", has_key: "有無鑰匙",
  reserve_price: "底價", current_price: "目前價", sold_price: "成交價", eligibility: "投標資格",
  identity: "車輛身分", official_case_number: "官方案號", ends_at: "拍賣截止", tax_arrears: "欠稅狀態",
};
const completenessLabels: Record<string, string> = { identity: "車輛身分", auction: "拍賣條件", condition: "車況", registration: "監理／領牌", fees: "費用", media: "照片文件" };

function deadlineLabel(value: string | null, ended: boolean) {
  if (ended) return "已截止／結果以官方公告為準";
  if (!value) return "截止時間未確認";
  const days = Math.ceil((new Date(value).getTime() - Date.now()) / 86_400_000);
  if (days <= 0) return "今天截止";
  if (days === 1) return "明天截止";
  return `${days} 天後截止`;
}

export default async function MotorcycleDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const viewer = await requireViewer();
  const { id } = await params;
  const moto = await getMotorcycle(id, viewer);
  if (!moto) notFound();
  const maxHistory = Math.max(...moto.history.map((point) => point.currentPrice ?? point.reservePrice ?? 0), 1);
  const cachedImages = (moto.imageUrls?.length ? moto.imageUrls : moto.imageUrl ? [moto.imageUrl] : [])
    .filter((url) => !url.includes("shwoo.gov.taipei"));
  const manufactureDate = moto.manufactureYear
    ? `${moto.manufactureYear} 年${moto.manufactureMonth ? ` ${moto.manufactureMonth} 月` : "（月份未確認）"}`
    : "未確認";
  const ended = isEndedAuction(moto);
  const displayPrice = moto.soldPrice ?? moto.currentPrice ?? moto.reservePrice;
  const displayPriceLabel = moto.soldPrice !== null ? "官方成交價" : moto.currentPrice !== null ? "目前出價" : "公告底價";
  const officialActionLabel = moto.source === "judicial"
    ? "查看這台機車的法院公告 PDF"
    : ended ? "查看這筆機車的官方歷史公告" : "查看這筆機車的官方公告";
  const missingFacts = [
    !moto.brand && "廠牌", !moto.model && "型號", !moto.manufactureYear && "出廠年月", moto.mileageKm === null && "里程",
    moto.hasKey === "UNKNOWN" && "鑰匙", moto.canStart === "UNKNOWN" && "能否發動", moto.canTest === "UNKNOWN" && "能否測試",
    ["UNKNOWN","REGISTRABILITY_UNKNOWN"].includes(moto.registrationStatus) && "可否領牌", moto.bidEligibility === "UNKNOWN" && "投標資格",
  ].filter((value): value is string => Boolean(value));
  return <main className="page detail-page"><div className="container">
    <div className="detail-breadcrumb"><Link href="/motorcycles?view=active"><ArrowLeft size={15}/> 返回找車結果</Link><span>{moto.sourceName} · #{moto.sourceAuid}</span></div>
    <section className="detail-hero">
      <div className="detail-media">
        <div className="card-image detail-photo"><PhotoGallery
          images={cachedImages}
          name={moto.name}
          source={moto.source}
          organization={moto.organization}
          plateNumber={moto.plateNumber}
          sourceAuid={moto.sourceAuid}
          mediaNote={moto.mediaNote}
          variant="detail"
        /></div>
      </div>
      <div className="detail-panel">
        <div className="detail-source"><ShieldCheck size={15}/><span>官方來源</span><strong>{moto.organization}</strong></div>
        <h1>{moto.name}</h1><p className="detail-official-title">{moto.officialTitle}</p>
        <div className="badges detail-badges"><Badge tone={ended ? "neutral" : "good"}>{ended ? "歷史紀錄" : "仍可參與"}</Badge><Badge tone="info">{disposalOriginLabels[moto.disposalOrigin]}</Badge><Badge tone={moto.bidEligibility === "LICENSED_RECYCLER_ONLY" ? "danger" : moto.bidEligibility === "UNKNOWN" ? "warn" : "good"}>{eligibilityLabels[moto.bidEligibility]}</Badge><Badge tone={moto.registrationStatus === "SCRAP_ONLY" ? "danger" : moto.registrationStatus === "NORMAL_TRANSFER" ? "good" : "warn"}>{registrationLabels[moto.registrationStatus]}</Badge>{moto.bulkLot && <Badge tone="warn">{moto.lotSize > 1 ? `整批 ${moto.lotSize} 臺` : "整批數量未確認"}</Badge>}</div>
        <div className="detail-bid-grid">
          <div><span>{displayPriceLabel}</span><strong>{formatMoney(displayPrice)}</strong><small>{moto.auctionRound ? `第 ${moto.auctionRound} 拍` : "拍次未確認"}</small></div>
          <div><span><CalendarClock size={15}/> {moto.auctionDatePrecision === "DATE" ? "拍賣日期" : "拍賣時間"}</span><strong>{displayAuctionDate(moto.auctionAt, moto.auctionDatePrecision)}</strong><small>{deadlineLabel(moto.auctionAt, ended)}</small></div>
        </div>
        <div className="summary-strip"><strong>30 秒決策摘要</strong><span>{quickSummary(moto)}</span></div>
        <div className="detail-actions">{moto.favoriteSupported && <FavoriteButton id={moto.id} initial={moto.favorite} variant="inline"/>}<a className="button official-action" href={moto.officialUrl} target="_blank" rel="noreferrer"><Gavel size={16}/>{officialActionLabel} <ExternalLink size={14}/></a></div>
      </div>
    </section>
    <div className="detail-grid"><div className="sections">
      <section className="section decision-section"><div className="section-heading"><span>BUYER DECISION</span><h2>先判斷這台適不適合你</h2></div><div className="decision-grid">
        <article><span>你能不能投標</span><strong>{eligibilityLabels[moto.bidEligibility]}</strong><small>{moto.bidEligibility === "UNKNOWN" ? "官方尚未明示，投標前務必確認" : "以官方投標須知的資格條款為準"}</small></article>
        <article><span>得標後能否上路</span><strong>{registrationLabels[moto.registrationStatus]}</strong><small>法拍得標不代表一定能領牌或過戶</small></article>
        <article><span>目前已知車況</span><strong>發動：{fourStateLabels[moto.canStart]}</strong><small>測試：{fourStateLabels[moto.canTest]} · 鑰匙：{fourStateLabels[moto.hasKey]}</small></article>
        <article><span>資料可判斷程度</span><strong>{moto.completeness}%</strong><small>{missingFacts.length ? `仍缺 ${missingFacts.slice(0,4).join("、")}${missingFacts.length > 4 ? "等" : ""}` : "核心欄位已有資料"}</small></article>
      </div>{missingFacts.length > 0 && <div className="missing-facts"><CircleHelp size={18}/><p><strong>投標前仍需查清楚：</strong>{missingFacts.join("、")}。未知不等於沒有；請勿把空白欄位當成良好車況。</p></div>}</section>
      <section className="section"><h2>拍賣資訊</h2><dl className="definition-grid">
        <div><dt>{moto.auctionDatePrecision === "DATE" ? "拍賣日期" : "拍賣時間"}</dt><dd>{displayAuctionDate(moto.auctionAt, moto.auctionDatePrecision)}</dd></div><div><dt>拍次</dt><dd>{moto.auctionRound ? `第 ${moto.auctionRound} 拍` : "未確認"}</dd></div>
        <div><dt>底價</dt><dd>{formatMoney(moto.reservePrice)}</dd></div><div><dt>目前／得標價</dt><dd>{formatMoney(moto.soldPrice ?? moto.currentPrice)}</dd></div>
        <div><dt>放置地點</dt><dd>{moto.location ?? "未確認"}</dd></div><div><dt>標售方式</dt><dd>{moto.bulkLot ? moto.lotSize > 1 ? `${moto.lotSize} 臺整批` : "整批（數量未確認）" : "單台標售"}</dd></div>
      </dl></section>
      <section className="section"><h2>費用與期限</h2><dl className="definition-grid">
        <div><dt>押標金</dt><dd>{moto.deposit === null ? "未確認" : formatMoney(moto.deposit)}</dd></div>
        <div><dt>付款期限</dt><dd>{displayDate(moto.paymentDeadline)}</dd></div>
        <div><dt>領取期限</dt><dd>{displayDate(moto.pickupDeadline)}</dd></div>
        <div><dt>其他費用</dt><dd>{moto.feeNotes.length ? moto.feeNotes.join("；") : "未確認"}</dd></div>
      </dl></section>
      <section className="section"><h2>資格與道路使用</h2><dl className="definition-grid">
        <div><dt>投標資格</dt><dd>{eligibilityLabels[moto.bidEligibility]}</dd></div><div><dt>牌照／領牌</dt><dd>{registrationLabels[moto.registrationStatus]}</dd></div>
        <div><dt>有無鑰匙</dt><dd>{fourStateLabels[moto.hasKey]}</dd></div><div><dt>能否發動</dt><dd>{fourStateLabels[moto.canStart]}</dd></div><div><dt>能否測試</dt><dd>{fourStateLabels[moto.canTest]}</dd></div>
      </dl></section>
      <section className="section"><h2>車輛與車況</h2><dl className="definition-grid">
        <div><dt>廠牌／型號</dt><dd>{[moto.brand,moto.model].filter(Boolean).join(" ") || "未確認"}</dd></div><div><dt>出廠年月</dt><dd>{manufactureDate}</dd></div>
        <div><dt>排氣量</dt><dd>{moto.displacementCc ? `${moto.displacementCc} c.c.` : "未確認"}</dd></div><div><dt>車牌</dt><dd>{moto.plateNumber ?? "未確認"}</dd></div>
        <div><dt>里程</dt><dd>{moto.mileageKm === null ? "未確認" : `${moto.mileageKm.toLocaleString("zh-TW")} km`}</dd></div><div><dt>顏色</dt><dd>{moto.color ?? "未確認"}</dd></div>
      </dl>{moto.conditionSummary && <p>{moto.conditionSummary}</p>}</section>
      <section className="section"><h2>監理資料補強</h2>
        <p>可到公路監理資料有償利用服務網，以車牌等識別資料逐筆查詢。官方目前標示即時查詢每筆新臺幣 2 元；本系統不會在未取得你的逐筆授權前自動登入或扣款。</p>
        <dl className="definition-grid">
          <div><dt>可帶入的車牌</dt><dd>{moto.plateNumber ?? "官方公告未提供"}</dd></div>
          <div><dt>機車里程</dt><dd>該服務明示不提供機車的里程欄位</dd></div>
          <div><dt>出廠年月判定</dt><dd>只採官方公告或監理查詢結果</dd></div>
          <div><dt>車牌英文字母</dt><dd>不推算月份；一般牌號不是出廠月份碼</dd></div>
        </dl>
        <p className="muted">付費結果可用來補強車籍基本資料與牌照狀態，實際欄位以查詢當下回傳為準。查無資料通常仍會計費。</p>
        <a className="button" href="https://mvdvan.mvdis.gov.tw/mvdvan/" target="_blank" rel="noreferrer">前往官方每筆 2 元查詢 <ExternalLink size={15} style={{display:"inline",verticalAlign:"-2px"}}/></a>
      </section>
      <section className="section"><h2>拍賣歷史</h2>{moto.history.length ? <div className="history">{moto.history.map((point,index)=>{const price=point.soldPrice??point.currentPrice??point.reservePrice??0;return <div className="history-row" key={`${point.observedAt}-${index}`}><span>{displayDate(point.observedAt)}</span><span className="history-bar"><i style={{width:`${Math.max(3,(price/maxHistory)*100)}%`}}/></span><strong>{formatMoney(price)}</strong></div>})}</div> : <p className="muted">目前只有首次觀測。後續同步會追加快照，不覆寫歷史價格。</p>}</section>
      <section className="section" id="evidence"><div className="section-heading"><span>TRACEABLE FACTS</span><h2>官方證據</h2></div>{moto.evidence.length ? moto.evidence.map((evidence)=><article className="evidence" key={evidence.id}><Badge tone="info">{evidenceLabels[evidence.fieldName] ?? evidence.fieldName}</Badge><blockquote>「{evidence.sourceText}」</blockquote><small>{evidence.trust} · 信心 {(evidence.confidence*100).toFixed(0)}% · <a className="official-link" href={evidence.officialUrl} target="_blank" rel="noreferrer">核對官方來源</a></small></article>) : <p className="muted">這筆開發資料尚未載入欄位級證據；請查看官方原始頁面。</p>}</section>
      <section className="section"><h2>文件與來源歷史</h2><p><FileSearch size={17} style={{display:"inline",verticalAlign:"-3px"}}/> {moto.sourceName} · 來源記錄 {moto.sourceAuid}</p>{moto.documents?.length ? <div className="evidence">{moto.documents.map((document)=><p key={document.id}><a className="official-link" href={document.url} target="_blank" rel="noreferrer">{document.title}</a> <small>· {document.cached ? "私有快取簽名連結（1 小時）" : "官方連結"}</small></p>)}</div> : <p className="muted">正式同步後，官方公告 PDF 或附件會在此提供私有簽名連結。</p>}<p className="muted">原始 HTML、JSON、PDF、圖片與後續解析版本會以 checksum 保存；目前頁面不因來源消失而自動標記為已售出。</p></section>
      <section className="section"><h2>可能重複標的</h2>{moto.duplicateCandidates.length ? moto.duplicateCandidates.map((candidate)=><article className="evidence" key={candidate.id}><Badge tone="warn">相似度 {(candidate.score*100).toFixed(0)}%</Badge><p>候選車輛 {candidate.counterpartVehicleId}</p><small>{candidate.reviewStatus} · {Object.keys(candidate.matchingSignals).join("、") || "未提供比對訊號"}</small></article>) : <p className="muted">目前沒有待人工審核的重複候選。系統只提示候選，不會自動合併模糊比對結果。</p>}</section>
    </div><aside className="sticky"><section className="section risk-panel"><h2><ShieldAlert size={20}/>重要風險</h2><div className="badges">{moto.riskBadges.length ? moto.riskBadges.map((risk)=><Badge tone="warn" key={risk}>{risk}</Badge>) : <Badge>尚無明確風險標記</Badge>}</div></section>
      <section className="section checklist stacked-section"><h2><CheckCircle2 size={20}/>投標前檢查</h2><ol><li>確認一般民眾是否有投標資格</li><li>確認可否過戶、重新領牌與道路使用</li><li>預約現場看車，核對車身／引擎號碼</li><li>估算修復、補稅、拖運與領牌成本</li><li>回到官方公告確認截止時間與付款條件</li></ol></section>
      <section className="section stacked-section"><h2>資料完整度 {moto.completeness}%</h2>{Object.entries(moto.completenessGroups).map(([name,value])=><div className="completeness-row" key={name}><span>{completenessLabels[name] ?? name}</span><span className="completeness"><span>{value}%</span><span className="meter"><i style={{width:`${value}%`}}/></span></span></div>)}<p className="muted completeness-note">完整度表示欄位是否存在，不代表資訊一定正確；可信度由官方證據另行判定。</p></section>
    </aside></div>
    <div className="mobile-detail-action"><a className="button" href={moto.officialUrl} target="_blank" rel="noreferrer"><Gavel size={16}/> {officialActionLabel} <ExternalLink size={14}/></a></div>
  </div></main>;
}
