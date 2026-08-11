import type { BidEligibility, DisposalOrigin, FourState, RegistrationStatus } from "@tm-ai/shared";

export const eligibilityLabels: Record<BidEligibility, string> = {
  PUBLIC: "公開投標", NATURAL_PERSON_ALLOWED: "一般民眾可投標", BUSINESS_ONLY: "限公司／商號",
  LICENSED_RECYCLER_ONLY: "限合格回收商", SPECIAL_QUALIFICATION: "需特殊資格", BULK_PURCHASE_ONLY: "限整批投標", UNKNOWN: "資格未確認",
};
export const registrationLabels: Record<RegistrationStatus, string> = {
  NORMAL_TRANSFER: "可正常過戶", RE_REGISTRATION_REQUIRED: "需重新領牌", INSPECTION_REQUIRED: "需檢驗／認證",
  REGISTRABILITY_UNKNOWN: "可否領牌未確認", DEREGISTERED: "已繳銷", CANNOT_RELICENSE: "不得重新領牌",
  SCRAP_ONLY: "僅供報廢", EXPORT_ONLY: "僅供出口", UNKNOWN: "牌照狀態未確認",
};
export const fourStateLabels: Record<FourState, string> = { YES: "有／可", NO: "無／不可", UNKNOWN: "未確認", CONFLICTING: "官方資料衝突" };
export const disposalOriginLabels: Record<DisposalOrigin, string> = {
  JUDICIAL_EXECUTION: "司法強制執行法拍",
  ADMINISTRATIVE_ENFORCEMENT: "行政執行拍賣",
  CRIMINAL_SEIZURE_OR_FORFEITURE: "刑事扣押／沒收",
  IMPOUNDED_UNCLAIMED: "移置保管逾期未領",
  PUBLIC_ASSET_DISPOSAL: "公有財產變賣",
  CUSTOMS_FORFEITURE: "海關沒入／拍賣",
  SCRAP_DISPOSAL: "公務報廢財物",
  OTHER: "其他",
  UNKNOWN: "處分性質未確認",
};

export function countyFromLocation(location: string | null) {
  return location?.match(/^(臺北市|新北市|桃園市|臺中市|臺南市|高雄市|基隆市|新竹市|嘉義市|[^市縣]{2,3}[縣市])/)?.[1] ?? null;
}
