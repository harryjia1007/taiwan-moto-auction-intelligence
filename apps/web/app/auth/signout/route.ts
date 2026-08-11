import { NextResponse, type NextRequest } from "next/server";
import { createSupabaseServerClient, hasSupabaseConfig } from "@/lib/supabase-server";

export async function GET(request: NextRequest) {
  if (hasSupabaseConfig()) await (await createSupabaseServerClient()).auth.signOut();
  return NextResponse.redirect(new URL("/login", request.url));
}
