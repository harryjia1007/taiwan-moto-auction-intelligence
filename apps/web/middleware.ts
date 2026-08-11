import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
  if (process.env.TM_FIXTURE_MODE === "true" && process.env.NODE_ENV !== "production") return NextResponse.next();
  const response = NextResponse.next({ request });
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  const publicPath = request.nextUrl.pathname === "/login" || request.nextUrl.pathname.startsWith("/auth/") || request.nextUrl.pathname === "/api/health";
  if (!url || !key) return publicPath ? response : NextResponse.redirect(new URL("/login?error=config", request.url));
  const supabase = createServerClient(url, key, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (values) => values.forEach(({ name, value, options }) => response.cookies.set(name, value, options)),
    },
  });
  const { data: { user } } = await supabase.auth.getUser();
  const owner = process.env.OWNER_EMAIL?.toLowerCase();
  const authorized = Boolean(user?.email && owner && user.email.toLowerCase() === owner);
  if (!authorized && !publicPath) {
    if (request.nextUrl.pathname.startsWith("/api/")) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (authorized && request.nextUrl.pathname === "/login") return NextResponse.redirect(new URL("/motorcycles", request.url));
  return response;
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"] };
