import { NextResponse, type NextRequest } from "next/server";
import { getViewer } from "@/lib/auth";
import { listMotorcycles } from "@/lib/data";
import { parseMarketplaceQuery } from "@/lib/marketplace-query";

export async function GET(request: NextRequest) {
  const viewer = await getViewer();
  if (!viewer) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const { filters, limit, cursor } = parseMarketplaceQuery(request.nextUrl.searchParams);
  return NextResponse.json(await listMotorcycles(filters, viewer, limit, cursor), { headers: { "cache-control": "private, no-store" } });
}
