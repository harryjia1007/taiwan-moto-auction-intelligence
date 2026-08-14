import { describe, expect, it } from "vitest";
import { displacementBandFromQuery, matchesDisplacementBand } from "../src";

describe("displacement bands", () => {
  it.each([
    [50, "LE_50", true], [51, "CC_51_125", true], [125, "CC_51_125", true],
    [126, "CC_126_250", true], [250, "CC_126_250", true], [251, "CC_251_550", true],
    [550, "CC_251_550", true], [551, "GT_550", true], [null, "UNKNOWN", true],
  ] as const)("matches %s against %s", (cc, band, expected) => {
    expect(matchesDisplacementBand(cc, band)).toBe(expected);
  });

  it("does not treat a missing value as a numeric class", () => {
    expect(matchesDisplacementBand(null, "LE_50")).toBe(false);
    expect(matchesDisplacementBand(125, "UNKNOWN")).toBe(false);
  });

  it("serializes only documented URL values", () => {
    expect(displacementBandFromQuery("51-125")).toBe("CC_51_125");
    expect(displacementBandFromQuery("125cc<script>")).toBeNull();
  });
});
