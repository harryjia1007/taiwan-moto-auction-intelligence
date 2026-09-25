import { describe, expect, it } from "vitest";
import { marketplacePresetHref, marketplaceViewHref, parseMarketplaceQuery, sanitizedMarketplaceQuery } from "./marketplace-query";

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

  it("uses the explicit vehicle type and clears stale incompatible filters", () => {
    const motorcycle = parseMarketplaceQuery(new URLSearchParams("vehicleType=MOTORCYCLE&carCategory=SUV&cc=le-125")).filters;
    expect(motorcycle.vehicleType).toBe("MOTORCYCLE");
    expect(motorcycle.carCategory).toBeUndefined();
    expect(motorcycle.displacementBands).toEqual(["LE_125"]);
    const car = parseMarketplaceQuery(new URLSearchParams("vehicleType=CAR&vehicleClass=ORDINARY_HEAVY&cc=le-125&carCategory=TRUCK")).filters;
    expect(car.vehicleType).toBe("CAR");
    expect(car.carCategory).toBe("TRUCK");
    expect(car.vehicleClass).toBeUndefined();
    expect(car.displacementBands).toBeUndefined();
  });

  it("round-trips reviewed vehicle and car categories", () => {
    const clean = sanitizedMarketplaceQuery(new URLSearchParams("vehicleType=CAR&carCategory=TRUCK&cc=le-125"));
    expect(clean.toString()).toContain("vehicleType=CAR");
    expect(clean.toString()).toContain("carCategory=TRUCK");
    expect(clean.has("cc")).toBe(false);
  });

  it.each(["judicial_notices", "moj_enforcement_cms", "customs"])("round-trips the implemented source %s", (source) => {
    const clean = sanitizedMarketplaceQuery(new URLSearchParams(`view=all&source=${source}`));
    expect(parseMarketplaceQuery(clean).filters.source).toBe(source);
    expect(clean.get("source")).toBe(source);
  });

  it("parses cursor and limit defensively", () => {
    expect(parseMarketplaceQuery(new URLSearchParams("limit=2.5")).limit).toBe(24);
    expect(parseMarketplaceQuery(new URLSearchParams("limit=1000")).limit).toBe(100);
    expect(parseMarketplaceQuery(new URLSearchParams("limit=0")).limit).toBe(1);
    expect(parseMarketplaceQuery(new URLSearchParams(`cursor=${"x".repeat(513)}`)).cursor).toBeNull();
  });

  it("adds a quick preset without losing the current search, region, source, or vehicle type", () => {
    const query = new URLSearchParams("view=active&keyword=機車&county=臺中市&source=judicial&vehicleType=MOTORCYCLE&cc=le-125&cursor=stale");
    const preset = new URL(marketplacePresetHref(query, "photo-single"), "http://localhost").searchParams;
    expect(preset.get("keyword")).toBe("機車");
    expect(preset.get("county")).toBe("臺中市");
    expect(preset.get("source")).toBe("judicial");
    expect(preset.get("vehicleType")).toBe("MOTORCYCLE");
    expect(preset.getAll("cc")).toEqual(["le-125"]);
    expect(preset.get("hasPhotos")).toBe("true");
    expect(preset.get("singleVehicle")).toBe("true");
    expect(preset.has("cursor")).toBe(false);
  });

  it("moves out of the scrap area for regular bidding while keeping compatible context", () => {
    const query = new URLSearchParams("view=scrap&county=臺中市&source=pcc&origin=SCRAP_DISPOSAL&eligibility=LICENSED_RECYCLER_ONLY&registration=SCRAP_ONLY&excludeScrap=true");
    const preset = new URL(marketplacePresetHref(query, "public-bidding"), "http://localhost").searchParams;
    expect(preset.get("view")).toBe("active");
    expect(preset.get("county")).toBe("臺中市");
    expect(preset.get("source")).toBe("pcc");
    expect(preset.has("origin")).toBe(false);
    expect(preset.get("eligibility")).toBe("NATURAL_PERSON_ALLOWED");
    expect(preset.has("registration")).toBe(false);
  });

  it("switches lifecycle views without silently keeping contradictory scrap and deadline filters", () => {
    const normal = new URLSearchParams("view=active&source=judicial&county=臺南市&eligibility=NATURAL_PERSON_ALLOWED&registration=NORMAL_TRANSFER&excludeScrap=true&within=30");
    const scrap = new URL(marketplaceViewHref(normal, "scrap"), "http://localhost").searchParams;
    expect(scrap.get("view")).toBe("scrap");
    expect(scrap.get("source")).toBe("judicial");
    expect(scrap.get("county")).toBe("臺南市");
    expect(scrap.has("eligibility")).toBe(false);
    expect(scrap.has("registration")).toBe(false);
    expect(scrap.has("excludeScrap")).toBe(false);
    expect(scrap.has("within")).toBe(false);
    const sameArea = new URL(marketplaceViewHref(new URLSearchParams("view=scrap&eligibility=LICENSED_RECYCLER_ONLY"), "scrap"), "http://localhost").searchParams;
    expect(sameArea.get("eligibility")).toBe("LICENSED_RECYCLER_ONLY");

    const ended = new URL(marketplaceViewHref(normal, "ended"), "http://localhost").searchParams;
    expect(ended.has("within")).toBe(false);
    expect(ended.get("source")).toBe("judicial");
    expect(parseMarketplaceQuery(new URLSearchParams("view=scrap&excludeScrap=true")).filters.excludeScrap).toBe(false);
  });
});
