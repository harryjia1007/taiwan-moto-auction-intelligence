import {
  DISPLACEMENT_BANDS,
  isEndedAuction,
  isScrapMarketplaceRecord,
  matchesDisplacementBand,
  sortMotorcycles,
  type DisplacementBand,
  type Motorcycle,
  type MotorcycleFilters,
  type SourceSummary,
} from "@tm-ai/shared";
import { fixtureMotorcycles, fixtureSources } from "./fixtures";
import { countyFromLocation } from "./labels";
import { createSupabaseServerClient } from "./supabase-server";
import type { Viewer } from "./auth";

type MarketplaceSort = NonNullable<MotorcycleFilters["sort"]>;
type MarketplaceCursor = { version: 1; sort: MarketplaceSort; value: string | number | null; id: string };
type ListingPhotoRow = { vehicle_id: string | null; lot_id: string | null; storage_path: string | null };
type FavoriteRow = { vehicle_id: string | null; lot_id: string | null };
type FavoriteListingIds = { vehicleIds: Set<string>; lotIds: Set<string> };
type SnapshotRow = { observed_at: string; normalized_payload: Record<string, unknown> | null };
export type DisplacementFacetCounts = Record<DisplacementBand, number>;
type AuctionDocumentRow = {
  id: string;
  title: string;
  document_type: string | null;
  official_url: string;
  raw_artifacts?: { storage_path?: string | null } | null;
};

const VALID_SORTS = new Set<MarketplaceSort>(["auction_asc", "auction_desc", "price_asc", "price_desc", "completeness_desc"]);
const SAFE_CURSOR_ID = /^(?:fixture-[a-z0-9-]+|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$/i;

function cursorValueMatchesSort(sort: MarketplaceSort, value: unknown): value is MarketplaceCursor["value"] {
  if (value === null) return true;
  if (sort === "auction_asc" || sort === "auction_desc") {
    return typeof value === "string"
      && value.length <= 64
      && /^[0-9T:+.Z-]+$/i.test(value)
      && Number.isFinite(Date.parse(value));
  }
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return false;
  return sort !== "completeness_desc" || value <= 100;
}

export function encodeMarketplaceCursor(cursor: Omit<MarketplaceCursor, "version">): string {
  return Buffer.from(JSON.stringify({ version: 1, ...cursor }), "utf8").toString("base64url");
}

export function decodeMarketplaceCursor(value?: string | null): MarketplaceCursor | null {
  if (!value || value.length > 512) return null;
  try {
    const cursor = JSON.parse(Buffer.from(value, "base64url").toString("utf8")) as Partial<MarketplaceCursor>;
    if (cursor.version !== 1 || !VALID_SORTS.has(cursor.sort as MarketplaceSort) || typeof cursor.id !== "string" || !SAFE_CURSOR_ID.test(cursor.id)) return null;
    if (!cursorValueMatchesSort(cursor.sort as MarketplaceSort, cursor.value)) return null;
    return cursor as MarketplaceCursor;
  } catch {
    return null;
  }
}

export function groupSignedPhotoUrls(photoRows: ListingPhotoRow[], signedByPath: Map<string, string>): Map<string, string[]> {
  const imagesByListing = new Map<string, string[]>();
  for (const row of photoRows) {
    const listingId = row.vehicle_id ?? row.lot_id;
    const signedUrl = row.storage_path ? signedByPath.get(row.storage_path) : null;
    if (!listingId || !signedUrl) continue;
    const images = imagesByListing.get(listingId) ?? [];
    if (!images.includes(signedUrl)) images.push(signedUrl);
    imagesByListing.set(listingId, images);
  }
  return imagesByListing;
}

export function collectFavoriteListingIds(rows: FavoriteRow[]): FavoriteListingIds {
  return {
    vehicleIds: new Set(rows.flatMap((row) => row.vehicle_id ? [row.vehicle_id] : [])),
    lotIds: new Set(rows.flatMap((row) => row.lot_id ? [row.lot_id] : [])),
  };
}

export function isDatabaseListingFavorite(
  row: { id: unknown; lot_id?: unknown },
  favorites: FavoriteListingIds,
): boolean {
  const id = String(row.id);
  const lotId = typeof row.lot_id === "string" ? row.lot_id : null;
  return favorites.vehicleIds.has(id) || Boolean(lotId && favorites.lotIds.has(lotId));
}

export function mapSnapshotHistory(rows: SnapshotRow[]): Motorcycle["history"] {
  return rows.map((entry) => {
    const payload = entry.normalized_payload ?? {};
    return {
      observedAt: entry.observed_at,
      round: typeof payload.auction_round === "number" ? payload.auction_round : null,
      reservePrice: typeof payload.reserve_price === "number" ? payload.reserve_price : null,
      currentPrice: typeof payload.current_price === "number" ? payload.current_price : null,
      soldPrice: typeof payload.sold_price === "number" ? payload.sold_price : null,
      status: typeof payload.status === "string" ? payload.status as Motorcycle["auctionStatus"] : "UNKNOWN",
    };
  });
}

/**
 * Public document actions must always return to the publisher's copy.
 * A private checksum copy may exist for evidence/reprocessing, but it must not
 * silently replace the official notice with a temporary Storage URL.
 */
export function mapOfficialDocument(entry: AuctionDocumentRow): NonNullable<Motorcycle["documents"]>[number] {
  return {
    id: entry.id,
    title: entry.title,
    documentType: entry.document_type,
    url: entry.official_url,
    cached: Boolean(entry.raw_artifacts?.storage_path),
  };
}

function cursorValue(item: Motorcycle, sort: MarketplaceSort): string | number | null {
  if (sort === "price_asc" || sort === "price_desc") return item.soldPrice ?? item.currentPrice ?? item.reservePrice;
  if (sort === "completeness_desc") return item.completeness;
  return item.auctionAt;
}

function safeSearchTerm(value: string): string {
  return value.trim().slice(0, 120).replace(/[,%()]/g, " ").replace(/\s+/g, " ");
}

export function deriveRiskBadges(motorcycle: Pick<Motorcycle, "bidEligibility" | "registrationStatus" | "canStart" | "bulkLot" | "lotSize">): string[] {
  const risks: string[] = [];
  if (motorcycle.bidEligibility === "LICENSED_RECYCLER_ONLY") risks.push("限合格回收商");
  if (motorcycle.bidEligibility === "UNKNOWN") risks.push("投標資格未確認");
  if (["SCRAP_ONLY", "CANNOT_RELICENSE"].includes(motorcycle.registrationStatus)) risks.push("不得領牌上路");
  if (["UNKNOWN", "REGISTRABILITY_UNKNOWN"].includes(motorcycle.registrationStatus)) risks.push("牌照狀態未確認");
  if (motorcycle.canStart === "NO") risks.push("目前無法發動");
  if (motorcycle.canStart === "CONFLICTING") risks.push("發動資訊衝突");
  if (motorcycle.bulkLot) risks.push(`整批 ${motorcycle.lotSize} 臺`);
  return risks;
}

export function matchesFilters(motorcycle: Motorcycle, filters: MotorcycleFilters): boolean {
  const scrapRecord = isScrapMarketplaceRecord(motorcycle);
  if (filters.marketView === "scrap" && !scrapRecord) return false;
  if (filters.marketView !== "scrap" && filters.marketView !== "favorites" && scrapRecord) return false;
  const keyword = filters.keyword?.trim().toLocaleLowerCase("zh-TW");
  if (keyword) {
    const haystack = [motorcycle.name, motorcycle.brand, motorcycle.model, motorcycle.plateNumber, motorcycle.officialTitle, motorcycle.organization, motorcycle.location]
      .filter(Boolean).join(" ").toLocaleLowerCase("zh-TW").replace(/\s/g, "");
    if (!haystack.includes(keyword.replace(/\s/g, ""))) return false;
  }
  if (filters.source && motorcycle.source !== filters.source) return false;
  if (filters.disposalOrigin && motorcycle.disposalOrigin !== filters.disposalOrigin) return false;
  if (filters.county && motorcycle.county !== filters.county) return false;
  if (filters.brand && motorcycle.brand !== filters.brand) return false;
  if (filters.eligibility && motorcycle.bidEligibility !== filters.eligibility) return false;
  if (filters.registration && motorcycle.registrationStatus !== filters.registration) return false;
  const vehicleType = motorcycle.vehicleType
    ?? (motorcycle.vehicleClass !== "UNKNOWN" ? "MOTORCYCLE" : "UNKNOWN");
  if (filters.vehicleType && vehicleType !== filters.vehicleType) return false;
  if (filters.vehicleClass && motorcycle.vehicleClass !== filters.vehicleClass) return false;
  if (filters.carCategory && motorcycle.carCategory !== filters.carCategory) return false;
  if (filters.displacementBands?.length && !filters.displacementBands.some((band) => matchesDisplacementBand(motorcycle.displacementCc, band))) return false;
  if (filters.hasPhotos === true && !(motorcycle.imageUrls?.length || motorcycle.imageUrl)) return false;
  if (filters.singleVehicle === true && motorcycle.bulkLot) return false;
  if (filters.excludeScrap === true && ["SCRAP_ONLY", "CANNOT_RELICENSE"].includes(motorcycle.registrationStatus)) return false;
  if (filters.marketView === "active" && isEndedAuction(motorcycle)) return false;
  if (filters.marketView === "ended" && !isEndedAuction(motorcycle)) return false;
  if (filters.marketView === "favorites" && !motorcycle.favorite) return false;
  const price = motorcycle.soldPrice ?? motorcycle.currentPrice ?? motorcycle.reservePrice;
  if (filters.minPrice !== undefined && (price === null || price < filters.minPrice)) return false;
  if (filters.maxPrice !== undefined && (price === null || price > filters.maxPrice)) return false;
  if (filters.auctionWithinDays) {
    if (!motorcycle.auctionAt) return false;
    const delta = new Date(motorcycle.auctionAt).getTime() - Date.now();
    if (delta < 0 || delta > filters.auctionWithinDays * 86_400_000) return false;
  }
  return true;
}

export function emptyDisplacementFacetCounts(): DisplacementFacetCounts {
  return Object.fromEntries(DISPLACEMENT_BANDS.map((band) => [band, 0])) as DisplacementFacetCounts;
}

/**
 * Facets deliberately ignore the current CC selection while honoring every
 * other marketplace filter. This makes adding a second CC band predictable.
 */
export function displacementFacetCountsForItems(
  items: Motorcycle[],
  filters: MotorcycleFilters,
): DisplacementFacetCounts {
  const filtersWithoutDisplacement = {
    ...filters,
    displacementBands: undefined,
    vehicleType: "MOTORCYCLE" as const,
    carCategory: undefined,
  };
  const eligibleItems = items.filter((item) => matchesFilters(item, filtersWithoutDisplacement));
  return Object.fromEntries(DISPLACEMENT_BANDS.map((band) => [
    band,
    eligibleItems.filter((item) => matchesDisplacementBand(item.displacementCc, band)).length,
  ])) as DisplacementFacetCounts;
}

function mapRow(row: Record<string, unknown>, favorite = false): Motorcycle {
  const location = row.storage_location as string | null;
  const item: Motorcycle = {
    id: String(row.id), source: String(row.source_adapter ?? "unknown"), sourceName: String(row.source_name ?? "未辨識來源"),
    sourceFamily: String(row.source_family ?? "UNKNOWN"), favoriteSupported: row.listing_entity === "vehicle" || row.listing_entity === "lot",
    sourceRecordId: String(row.source_record_id), sourceAuid: String(row.source_auid), officialUrl: String(row.official_url),
    officialTitle: String(row.official_title ?? "未命名標售"), name: [row.brand_name, row.model_name].filter(Boolean).join(" ") || String(row.official_title),
    brand: row.brand_name as string | null, model: row.model_name as string | null, manufactureYear: row.manufacture_year as number | null,
    manufactureMonth: row.manufacture_month as number | null,
    vehicleType: (row.vehicle_type ?? (row.vehicle_category && row.vehicle_category !== "UNKNOWN" ? "MOTORCYCLE" : "UNKNOWN")) as Motorcycle["vehicleType"],
    vehicleClass: (row.vehicle_category ?? "UNKNOWN") as Motorcycle["vehicleClass"],
    carCategory: (row.car_category ?? "UNKNOWN") as Motorcycle["carCategory"],
    displacementCc: row.displacement_cc as number | null, plateNumber: row.plate_number as string | null, color: row.color as string | null,
    organization: String(row.organization_name ?? "未辨識機關"), location, county: (row.county as string | null) ?? countyFromLocation(location),
    disposalOrigin: row.disposal_origin as Motorcycle["disposalOrigin"], auctionStatus: row.auction_status as Motorcycle["auctionStatus"],
    auctionRound: row.round_number as number | null, auctionAt: row.auction_at as string | null,
    auctionDatePrecision: row.source_adapter === "judicial" ? "DATE" : "DATETIME",
    reservePrice: row.reserve_price === null ? null : Number(row.reserve_price), currentPrice: row.current_price === null ? null : Number(row.current_price),
    soldPrice: row.sold_price === null ? null : Number(row.sold_price), bidEligibility: row.eligibility as Motorcycle["bidEligibility"],
    deposit: row.deposit === null ? null : Number(row.deposit), paymentDeadline: row.payment_deadline as string | null,
    pickupDeadline: row.pickup_deadline as string | null, feeNotes: (row.fee_notes ?? []) as string[],
    registrationStatus: row.registration_status as Motorcycle["registrationStatus"], hasKey: row.has_key as Motorcycle["hasKey"],
    canStart: row.can_start as Motorcycle["canStart"], canTest: row.can_test as Motorcycle["canTest"], mileageKm: row.mileage_km as number | null,
    lotSize: Number(row.lot_size ?? 1), bulkLot: Boolean(row.bulk_lot), conditionSummary: row.condition_summary as string | null,
    riskBadges: [], imageUrl: null, imageUrls: [],
    mediaState: row.has_cached_photo ? "UNAVAILABLE" : "NOT_PROVIDED",
    mediaNote: row.has_cached_photo ? "官方照片記錄存在，但目前尚未取得可讀取的簽名連結。" : undefined,
    dataWarnings: [], completeness: Number(row.completeness ?? 0),
    completenessGroups: (row.completeness_groups ?? {}) as Record<string, number>, favorite, evidence: [], history: [], duplicateCandidates: [], documents: [],
  };
  item.riskBadges = deriveRiskBadges(item);
  return item;
}

export function displacementBandDatabaseClause(band: DisplacementBand): string {
  if (band === "UNKNOWN") return "displacement_cc.is.null";
  if (band === "LE_125") return "and(displacement_cc.gt.0,displacement_cc.lte.125)";
  if (band === "CC_126_150") return "and(displacement_cc.gte.126,displacement_cc.lte.150)";
  if (band === "CC_151_250") return "and(displacement_cc.gte.151,displacement_cc.lte.250)";
  if (band === "CC_251_550") return "and(displacement_cc.gte.251,displacement_cc.lte.550)";
  return "displacement_cc.gt.550";
}

function applyDatabaseFilters(query: any, filters: MotorcycleFilters, favorites: FavoriteListingIds, now: Date) {
  const nowIso = now.toISOString();
  if (filters.marketView === "scrap") {
    query = query.or("disposal_origin.eq.SCRAP_DISPOSAL,registration_status.in.(SCRAP_ONLY,CANNOT_RELICENSE),eligibility.eq.LICENSED_RECYCLER_ONLY");
  } else if (filters.marketView !== "favorites") {
    query = query.not("disposal_origin", "eq", "SCRAP_DISPOSAL")
      .not("registration_status", "in", "(SCRAP_ONLY,CANNOT_RELICENSE)")
      .not("eligibility", "eq", "LICENSED_RECYCLER_ONLY");
  }
  if (filters.marketView === "active") query = query.not("auction_status", "in", "(SOLD,UNSOLD,WITHDRAWN,CANCELLED,EXPIRED)").or(`auction_at.is.null,auction_at.gte.${nowIso}`);
  if (filters.marketView === "ended") query = query.or(`auction_status.in.(SOLD,UNSOLD,WITHDRAWN,CANCELLED,EXPIRED),auction_at.lt.${nowIso}`);
  if (filters.marketView === "favorites") {
    const clauses = [
      favorites.vehicleIds.size ? `id.in.(${[...favorites.vehicleIds].join(",")})` : null,
      favorites.lotIds.size ? `lot_id.in.(${[...favorites.lotIds].join(",")})` : null,
    ].filter((clause): clause is string => Boolean(clause));
    query = query.or(clauses.join(","));
  }
  const keyword = filters.keyword ? safeSearchTerm(filters.keyword) : "";
  if (keyword) query = query.ilike("search_text", `%${keyword}%`);
  if (filters.source) query = query.eq("source_adapter", filters.source);
  if (filters.disposalOrigin) query = query.eq("disposal_origin", filters.disposalOrigin);
  if (filters.county) query = query.eq("county", filters.county);
  if (filters.brand) query = query.eq("brand_name", filters.brand);
  if (filters.eligibility) query = query.eq("eligibility", filters.eligibility);
  if (filters.registration) query = query.eq("registration_status", filters.registration);
  if (filters.vehicleType) query = query.eq("vehicle_type", filters.vehicleType);
  if (filters.vehicleClass) query = query.eq("vehicle_category", filters.vehicleClass);
  if (filters.carCategory) query = query.eq("car_category", filters.carCategory);
  if (filters.displacementBands?.length) {
    const clauses = filters.displacementBands.map(displacementBandDatabaseClause);
    query = query.or(clauses.join(","));
  }
  if (filters.singleVehicle) query = query.eq("bulk_lot", false);
  if (filters.hasPhotos) query = query.eq("has_cached_photo", true);
  if (filters.excludeScrap) query = query.not("registration_status", "in", "(SCRAP_ONLY,CANNOT_RELICENSE)");
  if (filters.minPrice !== undefined) query = query.gte("display_price", filters.minPrice);
  if (filters.maxPrice !== undefined) query = query.lte("display_price", filters.maxPrice);
  if (filters.auctionWithinDays) {
    query = query.gte("auction_at", nowIso).lte("auction_at", new Date(now.getTime() + filters.auctionWithinDays * 86_400_000).toISOString());
  }
  return query;
}

export async function listMotorcycles(filters: MotorcycleFilters, viewer: Viewer, limit = 24, cursor?: string | null) {
  const sort = filters.sort ?? "auction_asc";
  const decodedCursor = decodeMarketplaceCursor(cursor);
  if (viewer.fixture) {
    const withFavorites = fixtureMotorcycles.map((item) => ({ ...item, favorite: viewer.favoriteIds.includes(item.id) }));
    const displacementFacetCounts = displacementFacetCountsForItems(withFavorites, filters);
    const filtered = sortMotorcycles(withFavorites.filter((item) => matchesFilters(item, filters)), sort);
    const start = decodedCursor?.sort === sort ? Math.max(0, filtered.findIndex((item) => item.id === decodedCursor.id) + 1) : 0;
    const items = filtered.slice(start, start + limit);
    const last = items.at(-1);
    const nextCursor = last && start + items.length < filtered.length
      ? encodeMarketplaceCursor({ sort, value: cursorValue(last, sort), id: last.id })
      : null;
    return { items, nextCursor, total: filtered.length, displacementFacetCounts };
  }

  const supabase = await createSupabaseServerClient();
  const { data: favoriteRows, error: favoriteRowsError } = await supabase.from("favorites").select("vehicle_id,lot_id").eq("user_id", viewer.id);
  if (favoriteRowsError) throw new Error(`讀取收藏狀態失敗：${favoriteRowsError.message}`);
  const favoriteIds = collectFavoriteListingIds((favoriteRows ?? []) as FavoriteRow[]);
  if (filters.marketView === "favorites" && favoriteIds.vehicleIds.size === 0 && favoriteIds.lotIds.size === 0) {
    return { items: [], nextCursor: null, total: 0, displacementFacetCounts: emptyDisplacementFacetCounts() };
  }

  const now = new Date();
  let countQuery = supabase.from("vehicle_marketplace_listing").select("id", { count: "exact", head: true });
  countQuery = applyDatabaseFilters(countQuery, filters, favoriteIds, now);

  const facetFilters = {
    ...filters,
    displacementBands: undefined,
    vehicleType: "MOTORCYCLE" as const,
    carCategory: undefined,
  };
  const facetQueries = DISPLACEMENT_BANDS.map((band) => {
    let facetQuery = supabase.from("vehicle_marketplace_listing").select("id", { count: "exact", head: true });
    facetQuery = applyDatabaseFilters(facetQuery, facetFilters, favoriteIds, now);
    return facetQuery.or(displacementBandDatabaseClause(band));
  });

  let query = supabase.from("vehicle_marketplace_listing").select("*");
  query = applyDatabaseFilters(query, filters, favoriteIds, now);
  const sortColumn = sort === "price_asc" || sort === "price_desc" ? "display_price" : sort === "completeness_desc" ? "completeness" : "auction_at";
  const ascending = sort === "auction_asc" || sort === "price_asc";
  query = query.order(sortColumn, { ascending, nullsFirst: false }).order("id", { ascending: true });

  if (decodedCursor?.sort === sort && /^[0-9a-f-]{36}$/i.test(decodedCursor.id)) {
    if (decodedCursor.value === null) query = query.is(sortColumn, null).gt("id", decodedCursor.id);
    else {
      const operator = ascending ? "gt" : "lt";
      query = query.or(`${sortColumn}.${operator}.${decodedCursor.value},and(${sortColumn}.eq.${decodedCursor.value},id.gt.${decodedCursor.id}),${sortColumn}.is.null`);
    }
  }
  query = query.limit(limit + 1);

  const [facetResults, { count, error: countError }, { data, error }] = await Promise.all([
    Promise.all(facetQueries),
    countQuery,
    query,
  ]);
  const facetError = facetResults.find((result) => result.error)?.error;
  if (facetError) throw new Error(`計算排氣量級距筆數失敗：${facetError.message}`);
  if (countError) throw new Error(`計算汽機車筆數失敗：${countError.message}`);
  if (error) throw new Error(`讀取汽機車資料失敗：${error.message}`);
  const displacementFacetCounts = Object.fromEntries(DISPLACEMENT_BANDS.map((band, index) => [
    band,
    facetResults[index]?.count ?? 0,
  ])) as DisplacementFacetCounts;
  const rows = data ?? [];
  const pageRows = rows.slice(0, limit);
  const vehicleIds = pageRows.filter((row) => row.listing_entity === "vehicle").map((row) => row.id);
  const lotIds = pageRows.filter((row) => row.listing_entity === "lot").map((row) => row.id);
  const emptyPhotoResult = { data: [] as ListingPhotoRow[], error: null };
  const [vehiclePhotoResult, lotPhotoResult] = await Promise.all([
    vehicleIds.length ? supabase.from("photos").select("vehicle_id,lot_id,storage_path").in("vehicle_id", vehicleIds).not("storage_path", "is", null).order("sort_order") : Promise.resolve(emptyPhotoResult),
    lotIds.length ? supabase.from("photos").select("vehicle_id,lot_id,storage_path").in("lot_id", lotIds).not("storage_path", "is", null).order("sort_order") : Promise.resolve(emptyPhotoResult),
  ]);
  const vehiclePhotos = vehiclePhotoResult.data ?? [];
  const lotPhotos = lotPhotoResult.data ?? [];
  const photoRows = [...(vehiclePhotos ?? []), ...(lotPhotos ?? [])];
  const paths = photoRows.map((row) => row.storage_path).filter((path): path is string => Boolean(path));
  const signedResult = paths.length
    ? await supabase.storage.from("raw-artifacts").createSignedUrls(paths, 3600)
    : { data: [], error: null };
  const signedRows = signedResult.data ?? [];
  const signedByPath = new Map<string, string>((signedRows ?? []).flatMap((row) =>
    row.path && row.signedUrl ? [[row.path, row.signedUrl] as [string, string]] : []
  ));
  const imagesByListing = groupSignedPhotoUrls(photoRows, signedByPath);
  const items = pageRows.map((row) => {
    const item = mapRow(row as Record<string, unknown>, isDatabaseListingFavorite(row, favoriteIds));
    const imageUrls = imagesByListing.get(item.id) ?? [];
    const mediaState = imageUrls.length ? "AVAILABLE" as const : item.mediaState;
    const photoQueryFailed = row.listing_entity === "vehicle" ? Boolean(vehiclePhotoResult.error) : Boolean(lotPhotoResult.error);
    const mediaNote = mediaState === "UNAVAILABLE"
      ? photoQueryFailed
        ? "官方照片記錄存在，但照片清單目前無法載入。"
        : signedResult.error
          ? "官方照片已私下保存，但簽名連結目前無法建立。"
          : item.mediaNote
      : undefined;
    return { ...item, imageUrl: imageUrls[0] ?? null, imageUrls, mediaState, mediaNote };
  });
  const last = pageRows.at(-1);
  const nextCursor = rows.length > limit && last
    ? encodeMarketplaceCursor({ sort, value: (last as any)[sortColumn] as string | number | null, id: String(last.id) })
    : null;
  return { items, nextCursor, total: count ?? 0, displacementFacetCounts };
}

export async function getMotorcycle(id: string, viewer: Viewer): Promise<Motorcycle | null> {
  if (viewer.fixture) {
    const motorcycle = fixtureMotorcycles.find((item) => item.id === id);
    return motorcycle ? { ...motorcycle, favorite: viewer.favoriteIds.includes(motorcycle.id) } : null;
  }
  if (!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id)) return null;
  const supabase = await createSupabaseServerClient();
  const { data: row, error } = await supabase.from("vehicle_marketplace_listing").select("*").eq("id", id).maybeSingle();
  if (error) throw new Error(`讀取汽機車詳細資料失敗：${error.message}`);
  if (!row) return null;
  const listingEntity = row.listing_entity === "lot" ? "lot" : "vehicle";
  const photoKey = listingEntity === "lot" ? "lot_id" : "vehicle_id";
  const sharedLotId = listingEntity === "vehicle" && typeof row.lot_id === "string" ? row.lot_id : null;
  const favoriteClauses = [`vehicle_id.eq.${id}`];
  if (typeof row.lot_id === "string") favoriteClauses.push(`lot_id.eq.${row.lot_id}`);
  const favoriteMatch = favoriteClauses.join(",");
  const evidenceSelection = "id,field_name,source_text,trust,confidence,source_records!inner(official_url)";
  const [evidenceResult, snapshotResult, favoriteResult, photoResult, duplicateResult, documentResult, sharedEvidenceResult, sharedPhotoResult] = await Promise.all([
    supabase.from("field_evidence").select(evidenceSelection).eq("entity_type", listingEntity).eq("entity_id", id),
    supabase.from("snapshots").select("observed_at,normalized_payload").eq("source_record_id", row.source_record_id).order("observed_at"),
    supabase.from("favorites").select("id").eq("user_id", viewer.id).or(favoriteMatch).limit(1).maybeSingle(),
    supabase.from("photos").select("storage_path").eq(photoKey, id).order("sort_order"),
    supabase.from("probable_duplicates").select("id,left_vehicle_id,right_vehicle_id,score,matching_signals,review_status").or(`left_vehicle_id.eq.${id},right_vehicle_id.eq.${id}`),
    supabase.from("documents").select("id,title,document_type,official_url,raw_artifacts(storage_path)").eq("source_record_id", row.source_record_id),
    sharedLotId
      ? supabase.from("field_evidence").select(evidenceSelection).eq("entity_type", "lot").eq("entity_id", sharedLotId)
      : Promise.resolve({ data: [], error: null }),
    sharedLotId
      ? supabase.from("photos").select("storage_path").eq("lot_id", sharedLotId).is("vehicle_id", null).order("sort_order")
      : Promise.resolve({ data: [], error: null }),
  ]);
  const warnings: string[] = [];
  if (evidenceResult.error) warnings.push("欄位證據目前無法載入，請直接核對官方公告。");
  if (snapshotResult.error) warnings.push("拍賣快照歷史目前無法載入。");
  if (favoriteResult.error) warnings.push("收藏狀態目前無法確認，已暫停收藏操作。");
  if (duplicateResult.error) warnings.push("可能重複標的目前無法載入。");
  if (documentResult.error) warnings.push("官方全文連結目前無法載入，請使用主要官方公告按鈕。");
  if (photoResult.error) warnings.push("本標的照片清單目前無法載入。");
  if (sharedEvidenceResult.error) warnings.push("整批共用證據目前無法載入，請直接核對官方公告。");
  if (sharedPhotoResult.error) warnings.push("整批共用照片清單目前無法載入。");

  const motorcycle = mapRow(row as Record<string, unknown>, Boolean(favoriteResult.data));
  if (favoriteResult.error) motorcycle.favoriteSupported = false;
  const ownPhotoRows = (photoResult.data ?? []).map((photo) => ({
    vehicle_id: listingEntity === "vehicle" ? id : null,
    lot_id: listingEntity === "lot" ? id : null,
    storage_path: photo.storage_path,
  }));
  const sharedPhotoRows = (sharedPhotoResult.data ?? []).map((photo) => ({
    vehicle_id: null,
    lot_id: sharedLotId,
    storage_path: photo.storage_path,
  }));
  const photoRows = [...ownPhotoRows, ...sharedPhotoRows];
  const photoPaths = [...new Set(photoRows.map((photo) => photo.storage_path).filter((value): value is string => Boolean(value)))];
  let signedError = false;
  let signedByPath = new Map<string, string>();
  if (photoPaths.length) {
    const signedResult = await supabase.storage.from("raw-artifacts").createSignedUrls(photoPaths, 3600);
    signedError = Boolean(signedResult.error);
    signedByPath = new Map((signedResult.data ?? []).flatMap((entry) =>
      entry.path && entry.signedUrl ? [[entry.path, entry.signedUrl] as [string, string]] : []
    ));
  }
  const imagesByOwner = groupSignedPhotoUrls(photoRows, signedByPath);
  const ownImages = imagesByOwner.get(id) ?? [];
  const sharedImages = sharedLotId ? imagesByOwner.get(sharedLotId) ?? [] : [];
  motorcycle.imageUrls = ownImages;
  motorcycle.imageUrl = ownImages[0] ?? null;
  motorcycle.sharedLotImageUrls = sharedImages;
  const imageCount = ownImages.length + sharedImages.length;
  const photoRecordExists = photoRows.length > 0 || Boolean(row.has_cached_photo);
  motorcycle.mediaState = imageCount ? "AVAILABLE" : photoRecordExists || photoResult.error || sharedPhotoResult.error ? "UNAVAILABLE" : "NOT_PROVIDED";
  motorcycle.mediaNote = motorcycle.mediaState === "UNAVAILABLE"
    ? photoResult.error || sharedPhotoResult.error
      ? "官方照片記錄存在，但照片清單目前無法載入。"
      : "官方照片記錄存在，但目前沒有可讀取的簽名連結。"
    : undefined;
  if (signedError || (photoPaths.length > 0 && signedByPath.size < photoPaths.length)) {
    warnings.push(imageCount ? "部分官方照片目前無法載入，已顯示其餘可用照片。" : "官方照片目前無法載入；這不代表發布機關沒有提供照片。");
  } else if (motorcycle.mediaState === "UNAVAILABLE" && !photoResult.error && !sharedPhotoResult.error) {
    warnings.push("官方照片目前無法載入；這不代表發布機關沒有提供照片。");
  }
  motorcycle.evidence = (evidenceResult.data ?? []).map((entry: any) => ({
    id: entry.id, fieldName: entry.field_name, sourceText: entry.source_text,
    officialUrl: entry.source_records.official_url, trust: entry.trust, confidence: Number(entry.confidence),
  }));
  motorcycle.sharedLotEvidence = (sharedEvidenceResult.data ?? []).map((entry: any) => ({
    id: entry.id, fieldName: entry.field_name, sourceText: entry.source_text,
    officialUrl: entry.source_records.official_url, trust: entry.trust, confidence: Number(entry.confidence),
  }));
  motorcycle.history = mapSnapshotHistory((snapshotResult.data ?? []) as SnapshotRow[]);
  motorcycle.duplicateCandidates = (duplicateResult.data ?? []).map((entry: any) => ({
    id: entry.id,
    counterpartVehicleId: entry.left_vehicle_id === id ? entry.right_vehicle_id : entry.left_vehicle_id,
    score: Number(entry.score),
    reviewStatus: entry.review_status,
    matchingSignals: entry.matching_signals ?? {},
  }));
  motorcycle.documents = (documentResult.data ?? []).map((entry: any) => mapOfficialDocument(entry));
  motorcycle.dataWarnings = warnings;
  return motorcycle;
}

export async function getSources(viewer: Viewer): Promise<SourceSummary[]> {
  if (viewer.fixture) return fixtureSources;
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.from("source_health").select("*").order("name");
  if (error) throw new Error(`讀取來源健康狀態失敗：${error.message}`);
  return (data ?? []).map((row: any) => {
    const stale = row.last_successful_at && Date.now() - new Date(row.last_successful_at).getTime() > 36 * 3_600_000;
    return {
      id: row.id, name: row.name, adapter: row.adapter_name, status: row.status, automationLevel: row.automation_level,
      lastAttemptedAt: row.last_attempted_at, lastSuccessfulAt: row.last_successful_at, discoveredCount: row.discovered_count,
      changedCount: row.changed_count, parseSuccessRate: row.parse_success_rate === null ? null : Number(row.parse_success_rate),
      warnings: [...(row.warnings ?? []), ...(row.last_run_status === "FAILED" ? ["最近一次同步失敗"] : []), ...(stale ? ["距離上次成功同步已超過 36 小時"] : [])],
    };
  });
}
