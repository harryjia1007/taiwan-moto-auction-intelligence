import { describe, expect, it } from "vitest";
import { parseMarketplaceQuery, sanitizedMarketplaceQuery } from "./marketplace-query";

describe("marketplace query parsing", () => {
  it("accepts repeated reviewed CC bands and rejects unknown values", () => {
    const query = new URLSearchParams("cc=le-125&cc=126-150&cc=bad");
    expect(parseMarketplaceQuery(query).filters.displacementBands).toEqual(["LE_125", "CC_126_150"]);
  });

  it("clears future-only deadlines from the ended view", () => {
    const query = new URLSearchParams("view=ended&within=30&vehicleClass=ORDINARY_HEAVY");
    expect(parseMarketplaceQuery(query).filters.auctionWithinDays).toBeUndefined();
    const clean = sanitizedMarketplaceQuery(query);
    expect(clean.get("within")).toBeNull();
    expect(clean.get("vehicleClass")).toBe("ORDINARY_HEAVY");
  });

  it("falls back from malicious and unsupported enum values", () => {
    const filters = parseMarketplaceQuery(new URLSearchParams("view=<script>&source=evil&within=9999&county=unknown")).filters;
    expect(filters.marketView).toBe("active");
    expect(filters.source).toBeUndefined();
    expect(filters.auctionWithinDays).toBeUndefined();
    expect(filters.county).toBeUndefined();
  });

  it("keeps car and motorcycle filters mutually exclusive", () => {
    const car = parseMarketplaceQuery(new URLSearchParams("vehicleType=MOTORCYCLE&carCategory=SUV&cc=le-125")).filters;
    expect(car.vehicleType).toBe("CAR");
    expect(car.carCategory).toBe("SUV");
    expect(car.displacementBands).toBeUndefined();
    const motorcycle = parseMarketplaceQuery(new URLSearchParams("vehicleType=CAR&vehicleClass=ORDINARY_HEAVY")).filters;
    expect(motorcycle.vehicleType).toBe("MOTORCYCLE");
    expect(motorcycle.vehicleClass).toBe("ORDINARY_HEAVY");
    expect(motorcycle.carCategory).toBeUndefined();
  });

  it("round-trips reviewed vehicle and car categories", () => {
    const clean = sanitizedMarketplaceQuery(new URLSearchParams("vehicleType=CAR&carCategory=TRUCK&cc=le-125"));
    expect(clean.toString()).toContain("vehicleType=CAR");
    expect(clean.toString()).toContain("carCategory=TRUCK");
    expect(clean.has("cc")).toBe(false);
  });
});
