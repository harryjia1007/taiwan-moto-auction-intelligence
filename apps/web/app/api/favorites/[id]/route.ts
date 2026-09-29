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
  const { data: listing, error: listingError } = await supabase
    .from("vehicle_marketplace_listing")
    .select("id,listing_entity,lot_id")
    .eq("id", id)
    .maybeSingle();
  if (listingError) return NextResponse.json({ error: "目前無法確認收藏項目" }, { status: 503 });
  if (!listing) return NextResponse.json({ error: "找不到這筆拍賣資料" }, { status: 404 });

  if (method === "POST") {
    const result = listing.listing_entity === "lot"
      ? await supabase.from("favorites").insert({ user_id: viewer.id, lot_id: id })
      : await supabase.from("favorites").insert({ user_id: viewer.id, vehicle_id: id });
    if (result.error && result.error.code !== "23505") {
      return NextResponse.json({ error: "收藏失敗，請稍後再試" }, { status: 400 });
    }
    return new NextResponse(null, { status: 204 });
  }

  const clauses = [`vehicle_id.eq.${id}`];
  if (typeof listing.lot_id === "string") clauses.push(`lot_id.eq.${listing.lot_id}`);
  const result = await supabase.from("favorites")
    .delete()
    .eq("user_id", viewer.id)
    .or(clauses.join(","));
  return result.error
    ? NextResponse.json({ error: "取消收藏失敗，請稍後再試" }, { status: 400 })
    : new NextResponse(null, { status: 204 });
}

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) { return mutate((await params).id, "POST"); }
export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) { return mutate((await params).id, "DELETE"); }
