import Link from "next/link";
import { Badge, Card } from "@tm-ai/ui";
import { ArrowUpRight, CalendarDays, Camera, Gauge, KeyRound, MapPin, Power, ShieldCheck } from "lucide-react";
import { formatMoney, isEndedAuction, type Motorcycle } from "@tm-ai/shared";
import { disposalOriginLabels, eligibilityLabels, fourStateLabels, registrationLabels } from "@/lib/labels";
import { FavoriteButton } from "./favorite-button";
import { PhotoGallery } from "./photo-gallery";

function date(value: string | null, precision: "DATE" | "DATETIME" = "DATETIME") {
  if (!value) return "日期未確認";
  const options: Intl.DateTimeFormatOptions = precision === "DATE"
    ? { year: "numeric", month: "numeric", day: "numeric", timeZone: "Asia/Taipei" }
    : { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Taipei" };
  return new Intl.DateTimeFormat("zh-TW", options).format(new Date(value));
}

function timeline(motorcycle: Motorcycle) {
  if (isEndedAuction(motorcycle)) return { label: motorcycle.auctionStatus === "SOLD" ? "已成交" : "已截止／結果待確認", urgency: "ended" };
  if (!motorcycle.auctionAt) return { label: "截止時間未確認", urgency: "unknown" };
  const days = Math.ceil((new Date(motorcycle.auctionAt).getTime() - Date.now()) / 86_400_000);
  if (days <= 0) return { label: "今天截止", urgency: "critical" };
  if (days === 1) return { label: "明天截止", urgency: "critical" };
  if (days <= 7) return { label: `${days} 天後截止`, urgency: "soon" };
  return { label: `${days} 天後截止`, urgency: "normal" };
}

function price(motorcycle: Motorcycle) {
  if (motorcycle.soldPrice !== null) return { label: "成交價", value: motorcycle.soldPrice };
  if (motorcycle.currentPrice !== null) return { label: "目前出價", value: motorcycle.currentPrice };
  return { label: "公告底價", value: motorcycle.reservePrice };
}

export function MotorcycleCard({ motorcycle }: { motorcycle: Motorcycle }) {
  const cachedImages = [...new Set([
    ...(motorcycle.imageUrls ?? []),
    ...(motorcycle.imageUrl ? [motorcycle.imageUrl] : []),
  ].filter((url) => !url.includes("shwoo.gov.taipei")))];
  const photoCount = cachedImages.length;
  const displayPrice = price(motorcycle);
  const manufacture = motorcycle.manufactureYear ? `${motorcycle.manufactureYear}${motorcycle.manufactureMonth ? ` / ${motorcycle.manufactureMonth}` : ""}` : "未確認";
  const href = `/motorcycles/${motorcycle.id}`;
  const deadline = timeline(motorcycle);
  const eligibilityTone = motorcycle.bidEligibility === "LICENSED_RECYCLER_ONLY" ? "danger" : motorcycle.bidEligibility === "UNKNOWN" ? "warn" : "good";
  const registrationTone = ["SCRAP_ONLY", "CANNOT_RELICENSE"].includes(motorcycle.registrationStatus) ? "danger" : motorcycle.registrationStatus === "NORMAL_TRANSFER" ? "good" : "warn";

  return <Card className="moto-card">
    <div className="card-image">
      <PhotoGallery
        images={cachedImages}
        name={motorcycle.name}
        source={motorcycle.source}
        organization={motorcycle.organization}
        plateNumber={motorcycle.plateNumber}
        sourceAuid={motorcycle.sourceAuid}
        mediaNote={motorcycle.mediaNote}
        href={href}
        variant="card"
      />
      <span className={`auction-state ${deadline.urgency}`}>{deadline.label}</span>
      {photoCount > 0 && <span className="photo-count"><Camera size={14}/>{photoCount} 張官方照片</span>}
      {motorcycle.favoriteSupported && <FavoriteButton id={motorcycle.id} initial={motorcycle.favorite} />}
    </div>
    <div className="card-body">
      <div className="source-line"><span><ShieldCheck size={13}/> {motorcycle.sourceName}</span><span>{motorcycle.county ?? "地區未確認"}</span></div>
      <h2 className="card-title"><Link href={href}>{motorcycle.name}</Link></h2>
      <p className="agency">{motorcycle.organization}</p>

      <div className="decision-badges" aria-label="投標與領牌判斷">
        <Badge tone={eligibilityTone}>{eligibilityLabels[motorcycle.bidEligibility]}</Badge>
        <Badge tone={registrationTone}>{registrationLabels[motorcycle.registrationStatus]}</Badge>
        {motorcycle.bulkLot && <Badge tone="warn">{motorcycle.lotSize > 1 ? `${motorcycle.lotSize} 臺整批` : "整批標售"}</Badge>}
      </div>

      <div className="bid-snapshot">
        <div><span>{displayPrice.label}</span><strong>{formatMoney(displayPrice.value)}</strong><small>{motorcycle.auctionRound ? `第 ${motorcycle.auctionRound} 拍` : "拍次未確認"}</small></div>
        <div><span><CalendarDays size={14}/> 拍賣時間</span><strong>{date(motorcycle.auctionAt, motorcycle.auctionDatePrecision)}</strong><small className={`deadline-copy ${deadline.urgency}`}>{deadline.label}</small></div>
      </div>

      <dl className="vehicle-specs">
        <div><dt>出廠年月</dt><dd>{manufacture}</dd></div>
        <div><dt>排氣量</dt><dd>{motorcycle.displacementCc ? `${motorcycle.displacementCc} c.c.` : "未確認"}</dd></div>
        <div><dt>車牌</dt><dd>{motorcycle.plateNumber ?? "未確認"}</dd></div>
        <div><dt>標售方式</dt><dd>{motorcycle.bulkLot ? motorcycle.lotSize > 1 ? `${motorcycle.lotSize} 臺整批` : "整批" : "單台"}</dd></div>
      </dl>

      <div className="condition-row" aria-label="車況摘要">
        <span><KeyRound size={14}/>鑰匙 {fourStateLabels[motorcycle.hasKey]}</span>
        <span><Power size={14}/>發動 {fourStateLabels[motorcycle.canStart]}</span>
        <span><Gauge size={14}/>里程 {motorcycle.mileageKm === null ? "未確認" : `${motorcycle.mileageKm.toLocaleString("zh-TW")} km`}</span>
      </div>
      <div className="card-context">
        <span>{disposalOriginLabels[motorcycle.disposalOrigin]}</span>
        {motorcycle.location && <span><MapPin size={14}/>{motorcycle.location}</span>}
      </div>
      <div className="badges risk-list">{motorcycle.riskBadges.slice(0,3).map((risk)=><Badge key={risk} tone="warn">{risk}</Badge>)}</div>
      <div className="card-footer">
        <div className="completeness"><span>情報完整度 <strong>{motorcycle.completeness}%</strong></span><span className="meter" aria-hidden="true"><i style={{width:`${motorcycle.completeness}%`}} /></span></div>
        <Link className="card-cta" href={href}>查看決策資料 <ArrowUpRight size={15}/></Link>
      </div>
    </div>
  </Card>;
}
