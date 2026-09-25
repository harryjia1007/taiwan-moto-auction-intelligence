import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Motorcycle } from "@tm-ai/shared";
import { fixtureMotorcycles } from "@/lib/fixtures";
import { getMotorcycle } from "@/lib/data";
import MotorcycleDetailPage from "./page";

vi.mock("@/lib/auth", () => ({ requireViewer: vi.fn(async () => ({ id: "fixture-owner", email: "owner@example.com", fixture: true, favoriteIds: [] })) }));
vi.mock("@/lib/data", () => ({ getMotorcycle: vi.fn() }));

const sharedEvidence = {
  id: "shared-evidence",
  fieldName: "can_start",
  sourceText: "整批公告記載，未逐車說明。",
  officialUrl: "https://example.gov.tw/notice",
  trust: "OFFICIAL_EXPLICIT" as const,
  confidence: 0.9,
};

function vehicleDetail(overrides: Partial<Motorcycle> = {}): Motorcycle {
  return {
    ...fixtureMotorcycles[0]!,
    id: "fixture-shared-lot-vehicle",
    name: "本車",
    imageUrl: "https://signed.example/own.jpg",
    imageUrls: ["https://signed.example/own.jpg"],
    sharedLotImageUrls: ["https://signed.example/shared.jpg"],
    evidence: [{ ...sharedEvidence, id: "own-evidence", sourceText: "本車專屬記載。" }],
    sharedLotEvidence: [sharedEvidence],
    favoriteSupported: false,
    ...overrides,
  };
}

async function renderDetail(detail: Motorcycle) {
  vi.mocked(getMotorcycle).mockResolvedValue(detail);
  return renderToStaticMarkup(await MotorcycleDetailPage({ params: Promise.resolve({ id: detail.id }) }));
}

beforeEach(() => vi.resetAllMocks());

describe("private detail shared-lot attribution", () => {
  it("shows dedicated media first and keeps shared photos and evidence in separate sections", async () => {
    const html = await renderDetail(vehicleDetail());

    expect(html).toContain("本車專屬證據");
    expect(html).toContain("整批共用證據");
    expect(html).toContain("整批共用照片");
    expect(html.indexOf("本車專屬記載。")).toBeLessThan(html.indexOf("整批公告記載，未逐車說明。"));
    expect(html).toContain("https://signed.example/own.jpg");
    expect(html).toContain("https://signed.example/shared.jpg");
  });

  it("labels the hero as shared when the vehicle has no dedicated photo", async () => {
    const html = await renderDetail(vehicleDetail({ imageUrl: null, imageUrls: [] }));

    expect(html).toContain("這些照片屬於整批標的");
    expect(html).not.toContain("官方未附照片");
    expect(html).toContain("整批標的 官方照片");
  });
});
