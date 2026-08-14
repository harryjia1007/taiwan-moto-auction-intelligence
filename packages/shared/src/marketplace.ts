import type { DisplacementBand } from "./enums";
import type { Motorcycle, MotorcycleFilters } from "./types";

const ENDED_STATUSES = new Set(["SOLD", "UNSOLD", "WITHDRAWN", "CANCELLED", "EXPIRED"]);

export function isEndedAuction(motorcycle: Pick<Motorcycle, "auctionStatus" | "auctionAt">, now = new Date()): boolean {
  if (ENDED_STATUSES.has(motorcycle.auctionStatus)) return true;
  if (!motorcycle.auctionAt) return false;
  const timestamp = new Date(motorcycle.auctionAt).getTime();
  return Number.isFinite(timestamp) && timestamp < now.getTime();
}

export function isScrapMarketplaceRecord(
  motorcycle: Pick<Motorcycle, "disposalOrigin" | "registrationStatus" | "bidEligibility">,
): boolean {
  return motorcycle.disposalOrigin === "SCRAP_DISPOSAL"
    || ["SCRAP_ONLY", "CANNOT_RELICENSE"].includes(motorcycle.registrationStatus)
    || motorcycle.bidEligibility === "LICENSED_RECYCLER_ONLY";
}

export const DISPLACEMENT_QUERY_VALUES: Record<DisplacementBand, string> = {
  LE_50: "le-50",
  CC_51_125: "51-125",
  CC_126_250: "126-250",
  CC_251_550: "251-550",
  GT_550: "gt-550",
  UNKNOWN: "unknown",
};

export function displacementBandFromQuery(value: string): DisplacementBand | null {
  return (Object.entries(DISPLACEMENT_QUERY_VALUES).find(([, query]) => query === value)?.[0] as DisplacementBand | undefined) ?? null;
}

export function matchesDisplacementBand(value: number | null, band: DisplacementBand): boolean {
  if (band === "UNKNOWN") return value === null;
  if (value === null || !Number.isFinite(value) || value <= 0) return false;
  if (band === "LE_50") return value <= 50;
  if (band === "CC_51_125") return value >= 51 && value <= 125;
  if (band === "CC_126_250") return value >= 126 && value <= 250;
  if (band === "CC_251_550") return value >= 251 && value <= 550;
  return value > 550;
}

function priceOf(motorcycle: Motorcycle): number | null {
  return motorcycle.soldPrice ?? motorcycle.currentPrice ?? motorcycle.reservePrice;
}

export function sortMotorcycles(items: Motorcycle[], sort: NonNullable<MotorcycleFilters["sort"]> = "auction_asc"): Motorcycle[] {
  return [...items].sort((left, right) => {
    if (sort === "completeness_desc") return right.completeness - left.completeness || left.id.localeCompare(right.id);
    if (sort === "price_asc" || sort === "price_desc") {
      const leftPrice = priceOf(left);
      const rightPrice = priceOf(right);
      if (leftPrice === null && rightPrice === null) return left.id.localeCompare(right.id);
      if (leftPrice === null) return 1;
      if (rightPrice === null) return -1;
      return (sort === "price_asc" ? leftPrice - rightPrice : rightPrice - leftPrice) || left.id.localeCompare(right.id);
    }
    const leftDate = left.auctionAt ? new Date(left.auctionAt).getTime() : Number.POSITIVE_INFINITY;
    const rightDate = right.auctionAt ? new Date(right.auctionAt).getTime() : Number.POSITIVE_INFINITY;
    return (sort === "auction_desc" ? rightDate - leftDate : leftDate - rightDate) || left.id.localeCompare(right.id);
  });
}
