import type { Motorcycle, MotorcycleFilters } from "./types";

const ENDED_STATUSES = new Set(["SOLD", "UNSOLD", "WITHDRAWN", "CANCELLED", "EXPIRED"]);

export function isEndedAuction(motorcycle: Pick<Motorcycle, "auctionStatus" | "auctionAt">, now = new Date()): boolean {
  if (ENDED_STATUSES.has(motorcycle.auctionStatus)) return true;
  if (!motorcycle.auctionAt) return false;
  const timestamp = new Date(motorcycle.auctionAt).getTime();
  return Number.isFinite(timestamp) && timestamp < now.getTime();
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
