import { describe, expect, it } from "vitest";
import { ADAPTER_STATUSES, AUCTION_STATUSES, calculateCompleteness, FOUR_STATES, isEndedAuction, quickSummary, sortMotorcycles, type Motorcycle } from "../src";

const base = {
  id: "1", source: "shwoo", sourceName: "臺北惜物網", sourceFamily: "SHWOO", favoriteSupported: true,
  sourceRecordId: "sr1", sourceAuid: "939528", officialUrl: "https://example.test", officialTitle: "機器腳踏車1台",
  name: "SYM HM12VB", brand: "SYM", model: "HM12VB", manufactureYear: 2011, manufactureMonth: 5, displacementCc: 125, plateNumber: "367-JSJ", color: "黃色",
  organization: "台灣電力股份有限公司台南區營業處", location: "臺南市永康區", county: "臺南市", disposalOrigin: "PUBLIC_ASSET_DISPOSAL",
  auctionStatus: "SCHEDULED", auctionRound: 1, auctionAt: "2026-08-12T04:00:00Z", reservePrice: 2000, currentPrice: 4300, soldPrice: null,
  deposit: null, paymentDeadline: null, pickupDeadline: null, feeNotes: [],
  bidEligibility: "NATURAL_PERSON_ALLOWED", registrationStatus: "RE_REGISTRATION_REQUIRED", hasKey: "UNKNOWN", canStart: "NO", canTest: "NO",
  mileageKm: null, lotSize: 1, bulkLot: false, conditionSummary: "目前無法發動", riskBadges: [], imageUrl: null, completeness: 80,
  completenessGroups: {}, favorite: false, evidence: [], history: [], duplicateCandidates: [],
} satisfies Motorcycle;

describe("quickSummary", () => {
  it("keeps unknown separate from no", () => {
    expect(quickSummary(base)).toContain("有鑰匙：未確認");
    expect(quickSummary(base)).toContain("可發動：否");
  });
});

describe("calculateCompleteness", () => {
  it("does not treat UNKNOWN as complete", () => {
    const result = calculateCompleteness({ identity: ["SYM", null], auction: [2000], condition: ["UNKNOWN"], registration: ["YES"], fees: [null], media: ["photo"] });
    expect(result.groups.identity).toBe(50);
    expect(result.groups.condition).toBe(0);
    expect(result.overall).toBe(65);
  });

  it("does not treat an empty evidence collection as complete", () => {
    const result = calculateCompleteness({ identity: [[]], auction: [], condition: [], registration: [], fees: [], media: [[]] });
    expect(result.groups.identity).toBe(0);
    expect(result.groups.media).toBe(0);
  });
});

describe("shared enum serialization", () => {
  it("keeps database/API wire values stable", () => {
    expect(JSON.parse(JSON.stringify({ status: AUCTION_STATUSES[2], fact: FOUR_STATES[3], adapter: ADAPTER_STATUSES[0] })))
      .toEqual({ status: "SCHEDULED", fact: "CONFLICTING", adapter: "PLANNED" });
  });
});

describe("marketplace lifecycle and sorting", () => {
  it("archives a passed deadline without claiming the vehicle was sold", () => {
    const item = { ...base, auctionStatus: "SCHEDULED" as const, auctionAt: "2026-08-10T00:00:00Z" };
    expect(isEndedAuction(item, new Date("2026-08-11T00:00:00Z"))).toBe(true);
    expect(item.auctionStatus).toBe("SCHEDULED");
  });

  it("sorts known prices while leaving unknown prices at the end", () => {
    const expensive = { ...base, id: "expensive", currentPrice: 5000 };
    const cheap = { ...base, id: "cheap", currentPrice: 1000 };
    const unknown = { ...base, id: "unknown", currentPrice: null, reservePrice: null };
    expect(sortMotorcycles([expensive, unknown, cheap], "price_asc").map((item) => item.id)).toEqual(["cheap", "expensive", "unknown"]);
  });
});
