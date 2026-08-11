import { NextResponse } from "next/server";
import { getViewer } from "@/lib/auth";
import { getMotorcycle } from "@/lib/data";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const viewer = await getViewer();
  if (!viewer) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const motorcycle = await getMotorcycle((await params).id, viewer);
  return motorcycle ? NextResponse.json(motorcycle) : NextResponse.json({ error: "Not found" }, { status: 404 });
}
