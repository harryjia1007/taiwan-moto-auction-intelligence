export const COMPARISON_STORAGE_KEY = "tm_private_vehicle_comparison_v1";
export const MAX_COMPARISON_ITEMS = 3;

export interface ComparisonItem {
  id: string;
  name: string;
}

export interface ComparisonUpdate {
  items: ComparisonItem[];
  rejected: boolean;
}

const FIXTURE_ID = /^fixture-[a-z0-9-]+$/i;
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;

export function isSafeComparisonId(value: unknown): value is string {
  return typeof value === "string"
    && value.length <= 128
    && (FIXTURE_ID.test(value) || UUID.test(value));
}

export function isComparisonEligibleListing(
  listing: Pick<Motorcycle, "favoriteSupported" | "bulkLot" | "lotSize" | "vehicleType">,
): boolean {
  return listing.favoriteSupported
    && !listing.bulkLot
    && listing.lotSize === 1
    && listing.vehicleType !== "MIXED";
}

function safeName(value: unknown): string {
  if (typeof value !== "string") return "未命名車輛";
  return value.trim().replace(/\s+/g, " ").slice(0, 100) || "未命名車輛";
}

export function restoreComparisonItems(raw: string | null): ComparisonItem[] {
  if (!raw || raw.length > 8_192) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    const items: ComparisonItem[] = [];
    for (const candidate of parsed) {
      if (!candidate || typeof candidate !== "object") continue;
      const id = (candidate as { id?: unknown }).id;
      if (!isSafeComparisonId(id) || items.some((item) => item.id === id)) continue;
      items.push({ id, name: safeName((candidate as { name?: unknown }).name) });
      if (items.length === MAX_COMPARISON_ITEMS) break;
    }
    return items;
  } catch {
    return [];
  }
}

export function toggleComparisonItem(current: ComparisonItem[], candidate: ComparisonItem): ComparisonUpdate {
  const normalized = { id: candidate.id, name: safeName(candidate.name) };
  if (!isSafeComparisonId(normalized.id)) return { items: current, rejected: true };
  if (current.some((item) => item.id === normalized.id)) {
    return { items: current.filter((item) => item.id !== normalized.id), rejected: false };
  }
  if (current.length >= MAX_COMPARISON_ITEMS) return { items: current, rejected: true };
  return { items: [...current, normalized], rejected: false };
}

export function parseComparisonIds(value: string | string[] | undefined): string[] {
  if (typeof value !== "string" || value.length > 512) return [];
  const ids = value.split(",");
  if (ids.length < 2 || ids.length > MAX_COMPARISON_ITEMS) return [];
  if (ids.some((id) => !isSafeComparisonId(id))) return [];
  if (new Set(ids).size !== ids.length) return [];
  return ids;
}

export function comparisonHref(items: ComparisonItem[]): string | null {
  if (items.length < 2 || items.length > MAX_COMPARISON_ITEMS) return null;
  const params = new URLSearchParams({ ids: items.map((item) => item.id).join(",") });
  return `/motorcycles/compare?${params.toString()}`;
}
import type { Motorcycle } from "@tm-ai/shared";
