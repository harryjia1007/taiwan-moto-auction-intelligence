import { NextResponse } from "next/server";
import { fixtureMode } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json({
    status: "ok",
    service: "taiwan-moto-auction-intelligence-web",
    mode: fixtureMode() ? "fixture" : "authenticated",
    checkedAt: new Date().toISOString(),
  }, { headers: { "cache-control": "no-store" } });
}
