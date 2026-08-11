import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { getViewer } from "@/lib/auth";
import { createSupabaseServerClient } from "@/lib/supabase-server";

async function mutate(id: string, method: "POST" | "DELETE") {
  const viewer = await getViewer();
  if (!viewer) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  if (viewer.fixture) {
    if (!/^(?:fixture-[a-z0-9-]+|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$/i.test(id)) return NextResponse.json({ error: "Invalid motorcycle id" }, { status: 400 });
    const cookieStore = await cookies();
    const favorites = new Set(viewer.favoriteIds);
    if (method === "POST") favorites.add(id); else favorites.delete(id);
    const response = new NextResponse(null, { status: 204 });
    response.cookies.set("tm_fixture_favorites", [...favorites].join(","), { httpOnly: true, sameSite: "lax", path: "/", maxAge: 60 * 60 * 24 * 365 });
    return response;
  }
  if (!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id)) {
    return NextResponse.json({ error: "Invalid motorcycle id" }, { status: 400 });
  }
  const supabase = await createSupabaseServerClient();
  const result = method === "POST"
    ? await supabase.from("favorites").upsert({ user_id: viewer.id, vehicle_id: id })
    : await supabase.from("favorites").delete().eq("user_id", viewer.id).eq("vehicle_id", id);
  return result.error ? NextResponse.json({ error: result.error.message }, { status: 400 }) : new NextResponse(null, { status: 204 });
}

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) { return mutate((await params).id, "POST"); }
export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) { return mutate((await params).id, "DELETE"); }
