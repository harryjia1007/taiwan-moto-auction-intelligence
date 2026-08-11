import type { FourState, Motorcycle } from "./index";

const fourStateLabel: Record<FourState, string> = {
  YES: "是", NO: "否", UNKNOWN: "未確認", CONFLICTING: "資料衝突",
};

export function formatMoney(value: number | null): string {
  return value === null ? "價格未公開" : `NT$ ${new Intl.NumberFormat("zh-TW").format(value)}`;
}

export function quickSummary(motorcycle: Motorcycle): string {
  const eligibility = motorcycle.bidEligibility === "LICENSED_RECYCLER_ONLY"
    ? "限合格回收商"
    : motorcycle.bidEligibility === "NATURAL_PERSON_ALLOWED" || motorcycle.bidEligibility === "PUBLIC"
      ? "一般民眾可投標"
      : "投標資格未確認";
  const round = motorcycle.auctionRound ? `第${motorcycle.auctionRound}拍` : "拍次未確認";
  const price = formatMoney(motorcycle.currentPrice ?? motorcycle.reservePrice);
  const place = motorcycle.county ?? motorcycle.location ?? "地點未確認";
  return [
    eligibility,
    round,
    price,
    place,
    `有鑰匙：${fourStateLabel[motorcycle.hasKey]}`,
    `可發動：${fourStateLabel[motorcycle.canStart]}`,
    `可測試：${fourStateLabel[motorcycle.canTest]}`,
  ].join("｜");
}
