import { isEndedAuction, isScrapMarketplaceRecord, matchesDisplacementBand, sortMotorcycles, type Motorcycle, type MotorcycleFilters, type SourceSummary } from "@tm-ai/shared";
import { fixtureMotorcycles, fixtureSources } from "./fixtures";
import { countyFromLocation } from "./labels";
import { createSupabaseServerClient } from "./supabase-server";
import type { Viewer } from "./auth";

type MarketplaceSort = NonNullable<MotorcycleFilters["sort"]>;
type MarketplaceCursor = { version: 1; sort: MarketplaceSort; value: string | number | null; id: string };
type ListingPhotoRow = { vehicle_id: string | null; lot_id: string | null; storage_path: string | null };
type AuctionDocumentRow = {
  id: string;
  title: string;
  document_type: string | null;
  official_url: string;
  raw_artifacts?: { storage_path?: string | null } | null;
};

const VALID_SORTS = new Set<MarketplaceSort>(["auction_asc", "auction_desc", "price_asc", "price_desc", "completeness_desc"]);

export function encodeMarketplaceCursor(cursor: Omit<MarketplaceCursor, "version">): string {
  return Buffer.from(JSON.stringify({ version: 1, ...cursor }), "utf8").toString("base64url");
}

export function decodeMarketplaceCursor(value?: string | null): MarketplaceCursor | null {
  if (!value || value.length > 512) return null;
  try {
    const cursor = JSON.parse(Buffer.from(value, "base64url").toString("utf8")) as Partial<MarketplaceCursor>;
    if (cursor.version !== 1 || !VALID_SORTS.has(cursor.sort as MarketplaceSort) || typeof cursor.id !== "string") return null;
    if (cursor.value !== null && typeof cursor.value !== "string" && typeof cursor.value !== "number") return null;
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
  if (filters.marketView === "scrap" ? !scrapRecord : scrapRecord) return false;
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
  if (filters.vehicleClass && motorcycle.vehicleClass !== filters.vehicleClass) return false;
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

function mapRow(row: Record<string, unknown>, favorite = false): Motorcycle {
  const location = row.storage_location as string | null;
  const item: Motorcycle = {
    id: String(row.id), source: String(row.source_adapter ?? "unknown"), sourceName: String(row.source_name ?? "未辨識來源"),
    sourceFamily: String(row.source_family ?? "UNKNOWN"), favoriteSupported: Boolean(row.vehicle_id),
    sourceRecordId: String(row.source_record_id), sourceAuid: String(row.source_auid), officialUrl: String(row.official_url),
    officialTitle: String(row.official_title ?? "未命名標售"), name: [row.brand_name, row.model_name].filter(Boolean).join(" ") || String(row.official_title),
    brand: row.brand_name as string | null, model: row.model_name as string | null, manufactureYear: row.manufacture_year as number | null,
    manufactureMonth: row.manufacture_month as number | null,
    vehicleClass: (row.vehicle_category ?? "UNKNOWN") as Motorcycle["vehicleClass"],
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
    riskBadges: [], imageUrl: row.primary_image_url as string | null, imageUrls: [], completeness: Number(row.completeness ?? 0),
    completenessGroups: (row.completeness_groups ?? {}) as Record<string, number>, favorite, evidence: [], history: [], duplicateCandidates: [], documents: [],
  };
  item.riskBadges = deriveRiskBadges(item);
  return item;
}

function applyDatabaseFilters(query: any, filters: MotorcycleFilters, favoriteIds: Set<string>, now: Date) {
  const nowIso = now.toISOString();
  if (filters.marketView === "scrap") {
    query = query.or("disposal_origin.eq.SCRAP_DISPOSAL,registration_status.in.(SCRAP_ONLY,CANNOT_RELICENSE),eligibility.eq.LICENSED_RECYCLER_ONLY");
  } else {
    query = query.not("disposal_origin", "eq", "SCRAP_DISPOSAL")
      .not("registration_status", "in", "(SCRAP_ONLY,CANNOT_RELICENSE)")
      .not("eligibility", "eq", "LICENSED_RECYCLER_ONLY");
  }
  if (filters.marketView === "active") query = query.not("auction_status", "in", "(SOLD,UNSOLD,WITHDRAWN,CANCELLED,EXPIRED)").or(`auction_at.is.null,auction_at.gte.${nowIso}`);
  if (filters.marketView === "ended") query = query.or(`auction_status.in.(SOLD,UNSOLD,WITHDRAWN,CANCELLED,EXPIRED),auction_at.lt.${nowIso}`);
  if (filters.marketView === "favorites") query = query.in("id", [...favoriteIds]);
  const keyword = filters.keyword ? safeSearchTerm(filters.keyword) : "";
  if (keyword) query = query.ilike("search_text", `%${keyword}%`);
  if (filters.source) query = query.eq("source_adapter", filters.source);
  if (filters.disposalOrigin) query = query.eq("disposal_origin", filters.disposalOrigin);
  if (filters.county) query = query.eq("county", filters.county);
  if (filters.brand) query = query.eq("brand_name", filters.brand);
  if (filters.eligibility) query = query.eq("eligibility", filters.eligibility);
  if (filters.registration) query = query.eq("registration_status", filters.registration);
  if (filters.vehicleClass) query = query.eq("vehicle_category", filters.vehicleClass);
  if (filters.displacementBands?.length) {
    const clauses = filters.displacementBands.map((band) => {
      if (band === "UNKNOWN") return "displacement_cc.is.null";
      if (band === "LE_50") return "displacement_cc.lte.50";
      if (band === "CC_51_125") return "and(displacement_cc.gte.51,displacement_cc.lte.125)";
      if (band === "CC_126_250") return "and(displacement_cc.gte.126,displacement_cc.lte.250)";
      if (band === "CC_251_550") return "and(displacement_cc.gte.251,displacement_cc.lte.550)";
      return "displacement_cc.gt.550";
    });
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
    const filtered = sortMotorcycles(withFavorites.filter((item) => matchesFilters(item, filters)), sort);
    const start = decodedCursor?.sort === sort ? Math.max(0, filtered.findIndex((item) => item.id === decodedCursor.id) + 1) : 0;
    const items = filtered.slice(start, start + limit);
    const last = items.at(-1);
    const nextCursor = last && start + items.length < filtered.length
      ? encodeMarketplaceCursor({ sort, value: cursorValue(last, sort), id: last.id })
      : null;
    return { items, nextCursor, total: filtered.length };
  }

  const supabase = await createSupabaseServerClient();
  const { data: favoriteRows } = await supabase.from("favorites").select("vehicle_id").eq("user_id", viewer.id);
  const favoriteIds = new Set((favoriteRows ?? []).map((row) => row.vehicle_id));
  if (filters.marketView === "favorites" && favoriteIds.size === 0) return { items: [], nextCursor: null, total: 0 };

  const now = new Date();
  let countQuery = supabase.from("motorcycle_marketplace_listing").select("id", { count: "exact", head: true });
  countQuery = applyDatabaseFilters(countQuery, filters, favoriteIds, now);

  let query = supabase.from("motorcycle_marketplace_listing").select("*");
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

  const [{ count, error: countError }, { data, error }] = await Promise.all([countQuery, query]);
  if (countError) throw new Error(`計算機車筆數失敗：${countError.message}`);
  if (error) throw new Error(`讀取機車資料失敗：${error.message}`);
  const rows = data ?? [];
  const pageRows = rows.slice(0, limit);
  const vehicleIds = pageRows.filter((row) => row.listing_entity === "vehicle").map((row) => row.id);
  const lotIds = pageRows.filter((row) => row.listing_entity === "lot").map((row) => row.id);
  const [{ data: vehiclePhotos }, { data: lotPhotos }] = await Promise.all([
    vehicleIds.length ? supabase.from("photos").select("vehicle_id,lot_id,storage_path").in("vehicle_id", vehicleIds).not("storage_path", "is", null).order("sort_order") : Promise.resolve({ data: [] }),
    lotIds.length ? supabase.from("photos").select("vehicle_id,lot_id,storage_path").in("lot_id", lotIds).not("storage_path", "is", null).order("sort_order") : Promise.resolve({ data: [] }),
  ]);
  const photoRows = [...(vehiclePhotos ?? []), ...(lotPhotos ?? [])];
  const paths = photoRows.map((row) => row.storage_path).filter((path): path is string => Boolean(path));
  const { data: signedRows } = paths.length ? await supabase.storage.from("raw-artifacts").createSignedUrls(paths, 3600) : { data: [] };
  const signedByPath = new Map<string, string>((signedRows ?? []).flatMap((row) =>
    row.path && row.signedUrl ? [[row.path, row.signedUrl] as [string, string]] : []
  ));
  const imagesByListing = groupSignedPhotoUrls(photoRows, signedByPath);
  const items = pageRows.map((row) => {
    const item = mapRow(row as Record<string, unknown>, favoriteIds.has(row.id));
    const imageUrls = imagesByListing.get(item.id) ?? [];
    return { ...item, imageUrl: imageUrls[0] ?? null, imageUrls };
  });
  const last = pageRows.at(-1);
  const nextCursor = rows.length > limit && last
    ? encodeMarketplaceCursor({ sort, value: (last as any)[sortColumn] as string | number | null, id: String(last.id) })
    : null;
  return { items, nextCursor, total: count ?? 0 };
}

export async function getMotorcycle(id: string, viewer: Viewer): Promise<Motorcycle | null> {
  if (viewer.fixture) {
    const motorcycle = fixtureMotorcycles.find((item) => item.id === id);
    return motorcycle ? { ...motorcycle, favorite: viewer.favoriteIds.includes(motorcycle.id) } : null;
  }
  if (!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id)) return null;
  const supabase = await createSupabaseServerClient();
  const { data: row, error } = await supabase.from("motorcycle_marketplace_listing").select("*").eq("id", id).maybeSingle();
  if (error || !row) return null;
  const listingEntity = row.listing_entity === "lot" ? "lot" : "vehicle";
  const photoKey = listingEntity === "lot" ? "lot_id" : "vehicle_id";
  const [{ data: evidence }, { data: observations }, { data: favorite }, { data: photos }, { data: duplicates }, { data: documents }] = await Promise.all([
    supabase.from("field_evidence").select("id,field_name,source_text,trust,confidence,source_records!inner(official_url)").eq("entity_type", listingEntity).eq("entity_id", id),
    supabase.from("vehicle_observations").select("observed_at,payload").eq("vehicle_id", id).order("observed_at"),
    supabase.from("favorites").select("vehicle_id").eq("user_id", viewer.id).eq("vehicle_id", id).maybeSingle(),
    supabase.from("photos").select("storage_path").eq(photoKey, id).not("storage_path", "is", null).order("sort_order"),
    supabase.from("probable_duplicates").select("id,left_vehicle_id,right_vehicle_id,score,matching_signals,review_status").or(`left_vehicle_id.eq.${id},right_vehicle_id.eq.${id}`),
    supabase.from("documents").select("id,title,document_type,official_url,raw_artifacts(storage_path)").eq("source_record_id", row.source_record_id),
  ]);
  const motorcycle = mapRow(row as Record<string, unknown>, Boolean(favorite));
  const photoPaths = (photos ?? []).map((photo) => photo.storage_path).filter((value): value is string => Boolean(value));
  if (photoPaths.length) {
    const { data: signed } = await supabase.storage.from("raw-artifacts").createSignedUrls(photoPaths, 3600);
    const signedUrls = (signed ?? []).map((entry) => entry.signedUrl).filter((url): url is string => Boolean(url));
    motorcycle.imageUrls = signedUrls;
    motorcycle.imageUrl = signedUrls[0] ?? null;
  } else {
    motorcycle.imageUrl = null;
    motorcycle.imageUrls = [];
  }
  motorcycle.evidence = (evidence ?? []).map((entry: any) => ({
    id: entry.id, fieldName: entry.field_name, sourceText: entry.source_text,
    officialUrl: entry.source_records.official_url, trust: entry.trust, confidence: Number(entry.confidence),
  }));
  motorcycle.history = (observations ?? []).map((entry: any) => ({
    observedAt: entry.observed_at, round: entry.payload.auction_round ?? null, reservePrice: entry.payload.reserve_price ?? null,
    currentPrice: entry.payload.current_price ?? null, soldPrice: entry.payload.sold_price ?? null, status: entry.payload.status ?? "UNKNOWN",
  }));
  motorcycle.duplicateCandidates = (duplicates ?? []).map((entry: any) => ({
    id: entry.id,
    counterpartVehicleId: entry.left_vehicle_id === id ? entry.right_vehicle_id : entry.left_vehicle_id,
    score: Number(entry.score),
    reviewStatus: entry.review_status,
    matchingSignals: entry.matching_signals ?? {},
  }));
  motorcycle.documents = (documents ?? []).map((entry: any) => mapOfficialDocument(entry));
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
