import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
  const publicPath = request.nextUrl.pathname === "/login" || request.nextUrl.pathname.startsWith("/auth/") || request.nextUrl.pathname === "/api/health" || request.nextUrl.pathname === "/demo" || request.nextUrl.pathname.startsWith("/legal/");
  const forwardedHeaders = new Headers(request.headers);
  if (publicPath) forwardedHeaders.set("x-tm-public-surface", "1");
  else forwardedHeaders.delete("x-tm-public-surface");
  const response = NextResponse.next({ request: { headers: forwardedHeaders } });
  const secure = (target: NextResponse) => {
    target.headers.set("X-Content-Type-Options", "nosniff");
    target.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
    target.headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()");
    const devEval = process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : "";
    target.headers.set("Content-Security-Policy", `default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'${devEval}; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`);
    target.headers.set("Cache-Control", request.nextUrl.pathname === "/demo" || request.nextUrl.pathname.startsWith("/legal/") ? "public, max-age=300, stale-while-revalidate=3600" : "private, no-store");
    if (!publicPath) target.headers.set("X-Robots-Tag", "noindex, nofollow, noarchive");
    return target;
  };
  if (process.env.TM_FIXTURE_MODE === "true" && process.env.NODE_ENV !== "production") return secure(response);
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return publicPath ? secure(response) : secure(NextResponse.redirect(new URL("/login?error=config", request.url)));
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
    if (request.nextUrl.pathname.startsWith("/api/")) return secure(NextResponse.json({ error: "Unauthorized" }, { status: 401 }));
    return secure(NextResponse.redirect(new URL("/login", request.url)));
  }
  if (authorized && request.nextUrl.pathname === "/login") return secure(NextResponse.redirect(new URL("/motorcycles", request.url)));
  return secure(response);
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"] };
