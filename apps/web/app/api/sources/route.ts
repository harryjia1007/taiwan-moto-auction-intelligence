import { NextResponse } from "next/server";
import { getViewer } from "@/lib/auth";
import { getSources } from "@/lib/data";

export async function GET() {
  const viewer = await getViewer();
  if (!viewer) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  return NextResponse.json(await getSources(viewer));
}
