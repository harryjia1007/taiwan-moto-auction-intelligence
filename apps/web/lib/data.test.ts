import { describe, expect, it } from "vitest";
import { decodeMarketplaceCursor, deriveRiskBadges, encodeMarketplaceCursor, groupSignedPhotoUrls, matchesFilters } from "./data";
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
    expect(matchesFilters(fixtureMotorcycles[3]!, { source: "pcc", disposalOrigin: "SCRAP_DISPOSAL" })).toBe(true);
    expect(matchesFilters(fixtureMotorcycles[4]!, { source: "pcc", disposalOrigin: "SCRAP_DISPOSAL" })).toBe(false);
  });
  it("filters Judicial Yuan execution auctions independently", () => {
    expect(matchesFilters(fixtureMotorcycles[5]!, { source: "judicial", disposalOrigin: "JUDICIAL_EXECUTION" })).toBe(true);
    expect(matchesFilters(fixtureMotorcycles[5]!, { source: "pcc" })).toBe(false);
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
