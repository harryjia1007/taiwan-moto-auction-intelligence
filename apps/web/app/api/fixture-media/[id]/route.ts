import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { requireViewer } from "@/lib/auth";

const allowed = new Set([
  "939528-1", "939528-2", "939611-1", "939611-2", "939611-3", "939179-1", "939179-2", "939179-3",
]);

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const viewer = await requireViewer();
  const { id } = await params;
  if (!viewer.fixture || process.env.TM_FIXTURE_MODE !== "true" || !allowed.has(id)) return new NextResponse("Not found", { status: 404 });
  for (const [extension, contentType] of [["svg", "image/svg+xml"], ["png", "image/png"], ["jpg", "image/jpeg"], ["webp", "image/webp"]] as const) {
    try {
      const bytes = await readFile(path.join(process.cwd(), ".data", "fixture-media", `${id}.${extension}`));
      return new NextResponse(bytes, { headers: { "content-type": contentType, "cache-control": "private, max-age=3600" } });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
  }
  return new NextResponse("Fixture media cache missing; run pnpm fixtures:media", { status: 404 });
}
