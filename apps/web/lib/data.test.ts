import { describe, expect, it } from "vitest";
import {
  collectFavoriteListingIds,
  decodeMarketplaceCursor,
  displacementBandDatabaseClause,
  displacementFacetCountsForItems,
  deriveRiskBadges,
  encodeMarketplaceCursor,
  groupSignedPhotoUrls,
  isDatabaseListingFavorite,
  mapOfficialDocument,
  mapSnapshotHistory,
  matchesFilters,
} from "./data";
import { fixtureMotorcycles } from "./fixtures";

describe("marketplace filters", () => {
  it("tolerates spacing in keyword variants", () => expect(matchesFilters(fixtureMotorcycles[0]!, { keyword: "HM 12VB" })).toBe(true));
  it("excludes bulk lots from single-vehicle mode", () => expect(matchesFilters(fixtureMotorcycles[1]!, { singleVehicle: true })).toBe(false));
  it("recognizes privately cached official photos", () => {
    expect(matchesFilters(fixtureMotorcycles[2]!, { hasPhotos: true })).toBe(true);
    expect(fixtureMotorcycles[2]!.imageUrls).toHaveLength(3);
  });
  it("stores an official manufacture month separately from the plate", () => {
    expect(fixtureMotorcycles[5]!.manufactureMonth).toBe(12);
    expect(fixtureMotorcycles[7]!.manufactureMonth).toBeNull();
  });
  it("filters nationwide procurement and disposal origin independently", () => {
    expect(matchesFilters(fixtureMotorcycles[3]!, { source: "pcc", disposalOrigin: "SCRAP_DISPOSAL", marketView: "scrap" })).toBe(true);
    expect(matchesFilters(fixtureMotorcycles[4]!, { source: "pcc", disposalOrigin: "SCRAP_DISPOSAL" })).toBe(false);
  });
  it("filters Judicial Yuan execution auctions independently", () => {
    expect(matchesFilters(fixtureMotorcycles[5]!, { source: "judicial", disposalOrigin: "JUDICIAL_EXECUTION" })).toBe(true);
    expect(matchesFilters(fixtureMotorcycles[5]!, { source: "pcc" })).toBe(false);
  });
  it("supports favorites for every identified judicial vehicle", () => {
    const judicialVehicles = fixtureMotorcycles.filter((item) => item.source === "judicial");
    expect(judicialVehicles).toHaveLength(7);
    expect(judicialVehicles.every((item) => item.favoriteSupported)).toBe(true);
  });
  it("keeps scrap and recycler-only lots out of every normal shopping view", () => {
    expect(matchesFilters(fixtureMotorcycles[3]!, { marketView: "active" })).toBe(false);
    expect(matchesFilters(fixtureMotorcycles[3]!, { marketView: "all" })).toBe(false);
    expect(matchesFilters(fixtureMotorcycles[3]!, { marketView: "scrap" })).toBe(true);
    expect(matchesFilters(fixtureMotorcycles[0]!, { marketView: "scrap" })).toBe(false);
  });

  it("keeps a favorited scrap record discoverable from My Favorites", () => {
    const favoriteScrap = { ...fixtureMotorcycles[3]!, favorite: true };
    expect(matchesFilters(favoriteScrap, { marketView: "favorites" })).toBe(true);
    expect(matchesFilters({ ...favoriteScrap, favorite: false }, { marketView: "favorites" })).toBe(false);
  });
  it("filters official motorcycle class without inferring unknown bulk lots", () => {
    expect(matchesFilters(fixtureMotorcycles[5]!, { vehicleClass: "ORDINARY_HEAVY" })).toBe(true);
    expect(matchesFilters(fixtureMotorcycles[1]!, { vehicleClass: "ORDINARY_HEAVY" })).toBe(false);
  });
  it("separates cars, motorcycles, and car categories", () => {
    const car = { ...fixtureMotorcycles[0]!, vehicleType: "CAR" as const, carCategory: "SUV" as const, vehicleClass: "UNKNOWN" as const };
    expect(matchesFilters(car, { vehicleType: "CAR" })).toBe(true);
    expect(matchesFilters(car, { vehicleType: "MOTORCYCLE" })).toBe(false);
    expect(matchesFilters(car, { vehicleType: "CAR", carCategory: "SUV" })).toBe(true);
    expect(matchesFilters(car, { vehicleType: "CAR", carCategory: "TRUCK" })).toBe(false);
  });
  it("filters non-overlapping displacement bands and keeps missing CC explicit", () => {
    expect(matchesFilters(fixtureMotorcycles[0]!, { displacementBands: ["LE_125"] })).toBe(true);
    expect(matchesFilters(fixtureMotorcycles[0]!, { displacementBands: ["CC_126_150"] })).toBe(false);
    const unknownDisplacement = fixtureMotorcycles.find((item) => item.displacementCc === null);
    expect(unknownDisplacement).toBeDefined();
    expect(matchesFilters(unknownDisplacement!, { displacementBands: ["UNKNOWN"] })).toBe(true);
  });
  it("counts every fixed CC band under all other filters while ignoring the selected CC", () => {
    const base = fixtureMotorcycles[5]!;
    const candidates = [125, 126, 150, 151, 250, 251, 550, 551, null, 0].map((displacementCc, index) => ({
      ...base,
      id: `cc-boundary-${index}`,
      displacementCc,
      county: "高雄市",
    }));
    const distractor = { ...base, id: "other-source", displacementCc: 125, county: "高雄市", source: "shwoo" };
    const carDistractor = { ...base, id: "car-displacement", displacementCc: 125, county: "高雄市", vehicleType: "CAR" as const, carCategory: "PASSENGER" as const, vehicleClass: "UNKNOWN" as const };

    expect(displacementFacetCountsForItems([...candidates, distractor, carDistractor], {
      marketView: "all",
      source: "judicial",
      county: "高雄市",
      eligibility: "UNKNOWN",
      displacementBands: ["LE_125"],
    })).toEqual({
      LE_125: 1,
      CC_126_150: 2,
      CC_151_250: 2,
      CC_251_550: 2,
      GT_550: 1,
      UNKNOWN: 1,
    });
  });
  it("uses database predicates that match the same non-overlapping boundaries", () => {
    expect(displacementBandDatabaseClause("LE_125")).toBe("and(displacement_cc.gt.0,displacement_cc.lte.125)");
    expect(displacementBandDatabaseClause("CC_126_150")).toBe("and(displacement_cc.gte.126,displacement_cc.lte.150)");
    expect(displacementBandDatabaseClause("CC_151_250")).toBe("and(displacement_cc.gte.151,displacement_cc.lte.250)");
    expect(displacementBandDatabaseClause("CC_251_550")).toBe("and(displacement_cc.gte.251,displacement_cc.lte.550)");
    expect(displacementBandDatabaseClause("GT_550")).toBe("displacement_cc.gt.550");
    expect(displacementBandDatabaseClause("UNKNOWN")).toBe("displacement_cc.is.null");
  });
  it("excludes unknown auction dates from a future deadline filter", () => {
    const unknownDate = { ...fixtureMotorcycles[0]!, auctionAt: null };
    expect(matchesFilters(unknownDate, { marketView: "active", auctionWithinDays: 30 })).toBe(false);
  });
  it("keeps ended records out of the active marketplace without marking them sold", () => {
    const ended = { ...fixtureMotorcycles[0]!, auctionAt: "2020-01-01T00:00:00Z", auctionStatus: "SCHEDULED" as const };
    expect(matchesFilters(ended, { marketView: "active" })).toBe(false);
    expect(matchesFilters(ended, { marketView: "ended" })).toBe(true);
    expect(ended.auctionStatus).toBe("SCHEDULED");
  });
});

describe("risk badges", () => {
  it("never hides recycler-only and scrap risks", () => {
    const badges = deriveRiskBadges({ bidEligibility: "LICENSED_RECYCLER_ONLY", registrationStatus: "SCRAP_ONLY", canStart: "UNKNOWN", bulkLot: false, lotSize: 1 });
    expect(badges).toEqual(["限合格回收商", "不得領牌上路"]);
  });
  it("warns when judicial eligibility is not stated", () => {
    const badges = deriveRiskBadges({ bidEligibility: "UNKNOWN", registrationStatus: "UNKNOWN", canStart: "UNKNOWN", bulkLot: false, lotSize: 1 });
    expect(badges).toEqual(["投標資格未確認", "牌照狀態未確認"]);
  });
});

describe("marketplace cursor", () => {
  it("round-trips an opaque cursor with its sort value", () => {
    const encoded = encodeMarketplaceCursor({ sort: "auction_asc", value: "2026-08-19T00:00:00+08:00", id: "53000000-0000-0000-0000-000000000001" });
    expect(encoded).not.toContain("2026-08-19");
    expect(decodeMarketplaceCursor(encoded)).toEqual({ version: 1, sort: "auction_asc", value: "2026-08-19T00:00:00+08:00", id: "53000000-0000-0000-0000-000000000001" });
  });

  it("rejects malformed and oversized cursors", () => {
    expect(decodeMarketplaceCursor("not-a-cursor")).toBeNull();
    expect(decodeMarketplaceCursor("x".repeat(513))).toBeNull();
  });

  it("rejects well-formed cursors with unsafe semantic values", () => {
    const unsafeId = Buffer.from(JSON.stringify({ version: 1, sort: "auction_asc", value: "2026-09-01T00:00:00Z", id: "id),auction_at.gt.0" })).toString("base64url");
    const invalidDate = Buffer.from(JSON.stringify({ version: 1, sort: "auction_asc", value: "not-a-date", id: "fixture-safe" })).toString("base64url");
    const invalidPrice = Buffer.from(JSON.stringify({ version: 1, sort: "price_asc", value: -1, id: "fixture-safe" })).toString("base64url");
    expect(decodeMarketplaceCursor(unsafeId)).toBeNull();
    expect(decodeMarketplaceCursor(invalidDate)).toBeNull();
    expect(decodeMarketplaceCursor(invalidPrice)).toBeNull();
  });
});

describe("car fixtures", () => {
  it("supports car-category filtering without treating a car as a motorcycle", () => {
    const passenger = fixtureMotorcycles.find((item) => item.id === "fixture-car-passenger");
    expect(passenger).toMatchObject({ vehicleType: "CAR", carCategory: "PASSENGER", vehicleClass: "UNKNOWN" });
    expect(matchesFilters(passenger!, { marketView: "all", vehicleType: "CAR", carCategory: "PASSENGER" })).toBe(true);
    expect(matchesFilters(passenger!, { marketView: "all", vehicleType: "MOTORCYCLE" })).toBe(false);
  });
});

describe("official photo aggregation", () => {
  it("keeps every ordered cached photo for a listing and ignores unsigned paths", () => {
    const grouped = groupSignedPhotoUrls([
      { vehicle_id: "vehicle-1", lot_id: null, storage_path: "aa/first.jpg" },
      { vehicle_id: "vehicle-1", lot_id: null, storage_path: "bb/second.jpg" },
      { vehicle_id: "vehicle-1", lot_id: null, storage_path: "cc/missing.jpg" },
      { vehicle_id: null, lot_id: "lot-1", storage_path: "dd/lot.jpg" },
    ], new Map([
      ["aa/first.jpg", "https://signed.test/first"],
      ["bb/second.jpg", "https://signed.test/second"],
      ["dd/lot.jpg", "https://signed.test/lot"],
    ]));

    expect(grouped.get("vehicle-1")).toEqual(["https://signed.test/first", "https://signed.test/second"]);
    expect(grouped.get("lot-1")).toEqual(["https://signed.test/lot"]);
  });
});

describe("official document links", () => {
  it("links to the publisher even when a private evidence copy exists", () => {
    expect(mapOfficialDocument({
      id: "doc-1",
      title: "法院拍賣公告",
      document_type: "PDF",
      official_url: "https://court.example.gov.tw/notice.pdf",
      raw_artifacts: { storage_path: "private/checksum.pdf" },
    })).toEqual({
      id: "doc-1",
      title: "法院拍賣公告",
      documentType: "PDF",
      url: "https://court.example.gov.tw/notice.pdf",
      cached: true,
    });
  });
});

describe("vehicle and lot favorites", () => {
  it("resolves both direct vehicle favorites and stable owning-lot favorites", () => {
    const favorites = collectFavoriteListingIds([
      { vehicle_id: "vehicle-1", lot_id: null },
      { vehicle_id: null, lot_id: "lot-2" },
    ]);

    expect(isDatabaseListingFavorite({ id: "vehicle-1", lot_id: "lot-1" }, favorites)).toBe(true);
    expect(isDatabaseListingFavorite({ id: "lot-2", lot_id: "lot-2" }, favorites)).toBe(true);
    expect(isDatabaseListingFavorite({ id: "vehicle-2", lot_id: "lot-2" }, favorites)).toBe(true);
    expect(isDatabaseListingFavorite({ id: "vehicle-3", lot_id: "lot-3" }, favorites)).toBe(false);
  });
});

describe("immutable snapshot history", () => {
  it("maps lot and vehicle history without requiring a vehicle observation", () => {
    expect(mapSnapshotHistory([
      {
        observed_at: "2026-08-20T08:00:00Z",
        normalized_payload: {
          auction_round: 2,
          reserve_price: 18_000,
          current_price: null,
          sold_price: null,
          status: "SCHEDULED",
        },
      },
    ])).toEqual([
      {
        observedAt: "2026-08-20T08:00:00Z",
        round: 2,
        reservePrice: 18_000,
        currentPrice: null,
        soldPrice: null,
        status: "SCHEDULED",
      },
    ]);
  });
});
