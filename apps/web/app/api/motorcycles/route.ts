import { NextResponse, type NextRequest } from "next/server";
import type { BidEligibility, DisposalOrigin, MotorcycleFilters, RegistrationStatus } from "@tm-ai/shared";
import { getViewer } from "@/lib/auth";
import { listMotorcycles } from "@/lib/data";

const origins = new Set(["JUDICIAL_EXECUTION","ADMINISTRATIVE_ENFORCEMENT","PUBLIC_ASSET_DISPOSAL","SCRAP_DISPOSAL","IMPOUNDED_UNCLAIMED","CRIMINAL_SEIZURE_OR_FORFEITURE","CUSTOMS_FORFEITURE","UNKNOWN"]);
const eligibilities = new Set(["NATURAL_PERSON_ALLOWED","LICENSED_RECYCLER_ONLY","UNKNOWN"]);
const registrations = new Set(["NORMAL_TRANSFER","RE_REGISTRATION_REQUIRED","INSPECTION_REQUIRED","SCRAP_ONLY","CANNOT_RELICENSE","REGISTRABILITY_UNKNOWN","UNKNOWN"]);
const views = new Set(["active","ended","favorites","all"]);
const sorts = new Set(["auction_asc","auction_desc","price_asc","price_desc","completeness_desc"]);
const allowedSources = new Set(["judicial","pcc","shwoo"]);

function selected(value: string | null, allowed: Set<string>) {
  return value && allowed.has(value) ? value : undefined;
}

function numberParam(value: string | null, maximum = Number.MAX_SAFE_INTEGER) {
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= maximum ? parsed : undefined;
}

export async function GET(request: NextRequest) {
  const viewer = await getViewer();
  if (!viewer) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const query = request.nextUrl.searchParams;
  const filters: MotorcycleFilters = {
    keyword: query.get("keyword")?.slice(0, 120) || undefined, source: selected(query.get("source"), allowedSources),
    disposalOrigin: selected(query.get("origin"), origins) as DisposalOrigin | undefined, county: query.get("county")?.slice(0, 12) || undefined,
    brand: query.get("brand") ?? undefined, eligibility: query.get("eligibility") as BidEligibility | undefined,
    registration: selected(query.get("registration"), registrations) as RegistrationStatus | undefined,
    hasPhotos: query.get("hasPhotos") === "true", singleVehicle: query.get("singleVehicle") === "true", excludeScrap: query.get("excludeScrap") === "true",
    auctionWithinDays: numberParam(query.get("within"), 365),
    minPrice: numberParam(query.get("minPrice")),
    maxPrice: numberParam(query.get("maxPrice")),
    marketView: (selected(query.get("view"), views) ?? "active") as MotorcycleFilters["marketView"],
    sort: (selected(query.get("sort"), sorts) ?? "auction_asc") as MotorcycleFilters["sort"],
  };
  filters.eligibility = selected(query.get("eligibility"), eligibilities) as BidEligibility | undefined;
  const limit = Math.min(Math.max(Number(query.get("limit")) || 24, 1), 100);
  return NextResponse.json(await listMotorcycles(filters, viewer, limit, query.get("cursor")), { headers: { "cache-control": "private, no-store" } });
}
