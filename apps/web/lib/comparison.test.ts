import { describe, expect, it } from "vitest";
import {
  comparisonHref,
  isComparisonEligibleListing,
  parseComparisonIds,
  restoreComparisonItems,
  toggleComparisonItem,
  type ComparisonItem,
} from "./comparison";

const items: ComparisonItem[] = [
  { id: "fixture-one", name: "測試車一" },
  { id: "fixture-two", name: "測試車二" },
  { id: "fixture-three", name: "測試車三" },
];

describe("private vehicle comparison", () => {
  it("accepts only two or three unique, safe listing ids", () => {
    expect(parseComparisonIds("fixture-one,fixture-two")).toEqual(["fixture-one", "fixture-two"]);
    expect(parseComparisonIds("fixture-one,fixture-two,fixture-three")).toHaveLength(3);
    expect(parseComparisonIds("fixture-one")).toEqual([]);
    expect(parseComparisonIds("fixture-one,fixture-one")).toEqual([]);
    expect(parseComparisonIds("fixture-one,fixture-two,fixture-three,fixture-four")).toEqual([]);
    expect(parseComparisonIds("fixture-one,../unsafe")).toEqual([]);
  });

  it("rejects a fourth item without changing the three selected vehicles", () => {
    const update = toggleComparisonItem(items, { id: "fixture-four", name: "測試車四" });
    expect(update.rejected).toBe(true);
    expect(update.items).toEqual(items);
  });

  it("toggles an existing item off and builds the authenticated comparison URL", () => {
    const update = toggleComparisonItem(items, items[1]!);
    expect(update.rejected).toBe(false);
    expect(update.items.map((item) => item.id)).toEqual(["fixture-one", "fixture-three"]);
    expect(comparisonHref(update.items)).toBe("/motorcycles/compare?ids=fixture-one%2Cfixture-three");
  });

  it("restores only the first three valid, unique locally stored items", () => {
    const raw = JSON.stringify([
      { id: "fixture-one", name: "  測試   車一  " },
      { id: "fixture-one", name: "重複" },
      { id: "unsafe/id", name: "不安全" },
      { id: "fixture-two", name: "測試車二" },
      { id: "fixture-three", name: "測試車三" },
      { id: "fixture-four", name: "不應載入" },
    ]);
    expect(restoreComparisonItems(raw)).toEqual([
      { id: "fixture-one", name: "測試 車一" },
      { id: "fixture-two", name: "測試車二" },
      { id: "fixture-three", name: "測試車三" },
    ]);
  });

  it("permits only one identified vehicle, never a bulk or mixed lot", () => {
    const base = { favoriteSupported: true, bulkLot: false, lotSize: 1, vehicleType: "MOTORCYCLE" as const };
    expect(isComparisonEligibleListing(base)).toBe(true);
    expect(isComparisonEligibleListing({ ...base, bulkLot: true, lotSize: 3 })).toBe(false);
    expect(isComparisonEligibleListing({ ...base, vehicleType: "MIXED" })).toBe(false);
    expect(isComparisonEligibleListing({ ...base, favoriteSupported: false })).toBe(false);
  });
});
