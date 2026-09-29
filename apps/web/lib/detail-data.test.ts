import { afterEach, describe, expect, it, vi } from "vitest";
import { getMotorcycle } from "./data";
import { createSupabaseServerClient } from "./supabase-server";
import type { Viewer } from "./auth";

vi.mock("./supabase-server", () => ({ createSupabaseServerClient: vi.fn() }));

const vehicleId = "00000000-0000-0000-0000-000000000001";
const lotId = "00000000-0000-0000-0000-000000000002";
const viewer: Viewer = { id: "owner-id", email: "owner@example.com", fixture: false, favoriteIds: [] };

function fakeOwnerClient(includeVehiclePhoto: boolean) {
  const listing = {
    id: vehicleId,
    lot_id: lotId,
    listing_entity: "vehicle",
    source_record_id: "source-record-1",
    source_auid: "auction-1",
    source_adapter: "shwoo",
    source_name: "臺北惜物網",
    source_family: "GOVERNMENT",
    official_url: "https://shwoo.gov.taipei/official-record",
    official_title: "整批機車標售",
    brand_name: "本車廠牌",
    model_name: "本車型號",
    organization_name: "臺北市政府",
    disposal_origin: "PUBLIC_ASSET",
    auction_status: "SCHEDULED",
    eligibility: "GENERAL_PUBLIC",
    registration_status: "UNKNOWN",
    has_key: "UNKNOWN",
    can_start: "UNKNOWN",
    can_test: "UNKNOWN",
    reserve_price: 1000,
    current_price: null,
    sold_price: null,
    deposit: null,
    fee_notes: [],
    lot_size: 2,
    bulk_lot: true,
    completeness: 45,
    completeness_groups: {},
    has_cached_photo: true,
  };
  const photos = [
    ...(includeVehiclePhoto ? [{ vehicle_id: vehicleId, lot_id: lotId, storage_path: "own.jpg" }] : []),
    { vehicle_id: null, lot_id: lotId, storage_path: "shared.jpg" },
    // A different vehicle in the same lot is not a shared lot photo.
    { vehicle_id: "00000000-0000-0000-0000-000000000003", lot_id: lotId, storage_path: "other-vehicle.jpg" },
  ];
  const evidence = [
    { id: "own-evidence", entity_type: "vehicle", entity_id: vehicleId, field_name: "brand", source_text: "本車廠牌", trust: "OFFICIAL_EXPLICIT", confidence: 0.98, source_records: { official_url: listing.official_url } },
    { id: "lot-evidence", entity_type: "lot", entity_id: lotId, field_name: "eligibility", source_text: "整批投標條件", trust: "OFFICIAL_EXPLICIT", confidence: 0.95, source_records: { official_url: listing.official_url } },
  ];
  const allRows: Record<string, Record<string, unknown>[]> = {
    vehicle_marketplace_listing: [listing],
    photos,
    field_evidence: evidence,
    snapshots: [],
    favorites: [],
    probable_duplicates: [],
    documents: [],
  };

  function from(table: string) {
    const conditions: { column: string; value: unknown }[] = [];
    const rows = () => (allRows[table] ?? []).filter((row) => conditions.every(({ column, value }) => row[column] === value));
    const query = {
      select: () => query,
      eq: (column: string, value: unknown) => { conditions.push({ column, value }); return query; },
      is: (column: string, value: unknown) => { conditions.push({ column, value }); return query; },
      or: () => query,
      limit: () => query,
      order: () => query,
      maybeSingle: async () => ({ data: rows()[0] ?? null, error: null }),
      then: (resolve: (value: { data: Record<string, unknown>[]; error: null }) => unknown) => Promise.resolve(resolve({ data: rows(), error: null })),
    };
    return query;
  }

  return {
    from,
    storage: { from: () => ({
      createSignedUrls: async (paths: string[]) => ({
        data: paths.map((path) => ({ path, signedUrl: `https://signed.example/${path}` })),
        error: null,
      }),
    }) },
  };
}

afterEach(() => vi.resetAllMocks());

describe("owner-only vehicle detail media and evidence", () => {
  it("keeps vehicle-specific records first and labels only unassigned lot records as shared", async () => {
    vi.mocked(createSupabaseServerClient).mockResolvedValue(fakeOwnerClient(true) as any);

    const detail = await getMotorcycle(vehicleId, viewer);

    expect(detail?.imageUrls).toEqual(["https://signed.example/own.jpg"]);
    expect(detail?.sharedLotImageUrls).toEqual(["https://signed.example/shared.jpg"]);
    expect(detail?.imageUrl).toBe("https://signed.example/own.jpg");
    expect(detail?.evidence.map((item) => item.id)).toEqual(["own-evidence"]);
    expect(detail?.sharedLotEvidence?.map((item) => item.id)).toEqual(["lot-evidence"]);
    expect(detail?.mediaState).toBe("AVAILABLE");
  });

  it("shows a shared lot image when this vehicle has no dedicated image", async () => {
    vi.mocked(createSupabaseServerClient).mockResolvedValue(fakeOwnerClient(false) as any);

    const detail = await getMotorcycle(vehicleId, viewer);

    expect(detail?.imageUrls).toEqual([]);
    expect(detail?.sharedLotImageUrls).toEqual(["https://signed.example/shared.jpg"]);
    expect(detail?.mediaState).toBe("AVAILABLE");
  });
});
