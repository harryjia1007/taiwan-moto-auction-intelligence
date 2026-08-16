import {
  BID_ELIGIBILITIES,
  CAR_CATEGORIES,
  DISPOSAL_ORIGINS,
  MOTORCYCLE_CLASSES,
  REGISTRATION_STATUSES,
  VEHICLE_TYPES,
  displacementBandFromQuery,
  type MotorcycleFilters,
} from "@tm-ai/shared";

export type PageSearchParams = Record<string, string | string[] | undefined>;

const SOURCES = new Set(["judicial", "moj_auction", "moj_enforcement", "pcc", "shwoo"]);
const VIEWS = new Set(["active", "ended", "favorites", "scrap", "all"]);
const SORTS = new Set(["auction_asc", "auction_desc", "price_asc", "price_desc", "completeness_desc"]);
const COUNTIES = new Set(["臺北市","新北市","桃園市","臺中市","臺南市","高雄市","基隆市","新竹市","嘉義市","新竹縣","苗栗縣","彰化縣","南投縣","雲林縣","嘉義縣","屏東縣","宜蘭縣","花蓮縣","臺東縣","澎湖縣","金門縣","連江縣"]);
const ORIGINS = new Set<string>(DISPOSAL_ORIGINS);
const ELIGIBILITIES = new Set<string>(BID_ELIGIBILITIES);
const REGISTRATIONS = new Set<string>(REGISTRATION_STATUSES);
const CLASSES = new Set<string>(MOTORCYCLE_CLASSES);
const VEHICLE_KINDS = new Set<string>(VEHICLE_TYPES);
const CAR_KINDS = new Set<string>(CAR_CATEGORIES);

function selected(value: string | null, allowed: Set<string>) {
  return value && allowed.has(value) ? value : undefined;
}

function numberParam(value: string | null, maximum = Number.MAX_SAFE_INTEGER) {
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= maximum ? parsed : undefined;
}

export function pageParamsToSearchParams(params: PageSearchParams): URLSearchParams {
  const query = new URLSearchParams();
  for (const [key, raw] of Object.entries(params)) {
    for (const value of Array.isArray(raw) ? raw : raw ? [raw] : []) query.append(key, value);
  }
  return query;
}

export function parseMarketplaceQuery(query: URLSearchParams): {
  filters: MotorcycleFilters;
  limit: number;
  cursor: string | null;
} {
  const marketView = (selected(query.get("view"), VIEWS) ?? "active") as NonNullable<MotorcycleFilters["marketView"]>;
  const sort = (selected(query.get("sort"), SORTS) ?? "auction_asc") as NonNullable<MotorcycleFilters["sort"]>;
  const ccValues = query.getAll("cc").flatMap((value) => value.split(","));
  const displacementBands = [...new Set(ccValues.map(displacementBandFromQuery).filter((value): value is NonNullable<typeof value> => Boolean(value)))];
  const price = query.get("price")?.split("-");
  const within = marketView === "ended" ? undefined : numberParam(query.get("within"), 365);
  const minPrice = numberParam(query.get("minPrice")) ?? (price?.[0] ? numberParam(price[0]) : undefined);
  const maxPrice = numberParam(query.get("maxPrice")) ?? (price?.[1] ? numberParam(price[1]) : undefined);
  const filters: MotorcycleFilters = {
    keyword: query.get("keyword")?.trim().slice(0, 120) || undefined,
    source: selected(query.get("source"), SOURCES),
    disposalOrigin: selected(query.get("origin"), ORIGINS) as MotorcycleFilters["disposalOrigin"],
    county: selected(query.get("county"), COUNTIES),
    brand: query.get("brand")?.trim().slice(0, 40) || undefined,
    eligibility: selected(query.get("eligibility"), ELIGIBILITIES) as MotorcycleFilters["eligibility"],
    registration: selected(query.get("registration"), REGISTRATIONS) as MotorcycleFilters["registration"],
    vehicleClass: selected(query.get("vehicleClass"), CLASSES) as MotorcycleFilters["vehicleClass"],
    vehicleType: selected(query.get("vehicleType"), VEHICLE_KINDS) as MotorcycleFilters["vehicleType"],
    carCategory: selected(query.get("carCategory"), CAR_KINDS) as MotorcycleFilters["carCategory"],
    displacementBands: displacementBands.length ? displacementBands : undefined,
    hasPhotos: query.get("hasPhotos") === "true",
    singleVehicle: query.get("singleVehicle") === "true",
    excludeScrap: query.get("excludeScrap") === "true",
    auctionWithinDays: within,
    minPrice,
    maxPrice,
    marketView,
    sort,
  };
  if (filters.carCategory) {
    filters.vehicleType = "CAR";
    filters.vehicleClass = undefined;
    filters.displacementBands = undefined;
  } else if (filters.vehicleClass || filters.displacementBands?.length) {
    filters.vehicleType = "MOTORCYCLE";
  } else if (filters.vehicleType === "CAR") {
    filters.vehicleClass = undefined;
    filters.displacementBands = undefined;
  } else if (filters.vehicleType !== "MOTORCYCLE") {
    filters.vehicleClass = undefined;
    filters.carCategory = undefined;
    filters.displacementBands = undefined;
  }
  return {
    filters,
    limit: Math.min(Math.max(Number(query.get("limit")) || 24, 1), 100),
    cursor: query.get("cursor"),
  };
}

export function sanitizedMarketplaceQuery(query: URLSearchParams): URLSearchParams {
  const parsed = parseMarketplaceQuery(query).filters;
  const clean = new URLSearchParams(query);
  for (const key of [...clean.keys()]) clean.delete(key);
  clean.set("view", parsed.marketView ?? "active");
  if (parsed.keyword) clean.set("keyword", parsed.keyword);
  if (parsed.county) clean.set("county", parsed.county);
  if (parsed.source) clean.set("source", parsed.source);
  if (parsed.disposalOrigin) clean.set("origin", parsed.disposalOrigin);
  if (parsed.brand) clean.set("brand", parsed.brand);
  if (parsed.vehicleClass) clean.set("vehicleClass", parsed.vehicleClass);
  if (parsed.vehicleType) clean.set("vehicleType", parsed.vehicleType);
  if (parsed.carCategory) clean.set("carCategory", parsed.carCategory);
  if (parsed.displacementBands?.length) for (const raw of query.getAll("cc")) for (const part of raw.split(",")) if (displacementBandFromQuery(part)) clean.append("cc", part);
  if (parsed.eligibility) clean.set("eligibility", parsed.eligibility);
  if (parsed.registration) clean.set("registration", parsed.registration);
  if (parsed.minPrice !== undefined || parsed.maxPrice !== undefined) clean.set("price", `${parsed.minPrice ?? ""}-${parsed.maxPrice ?? ""}`);
  if (parsed.hasPhotos) clean.set("hasPhotos", "true");
  if (parsed.singleVehicle) clean.set("singleVehicle", "true");
  if (parsed.excludeScrap) clean.set("excludeScrap", "true");
  if (parsed.auctionWithinDays) clean.set("within", String(parsed.auctionWithinDays));
  if (parsed.sort && parsed.sort !== "auction_asc") clean.set("sort", parsed.sort);
  return clean;
}
