import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { createSupabaseServerClient, hasSupabaseConfig } from "./supabase-server";

export interface Viewer { id: string; email: string; fixture: boolean; favoriteIds: string[] }

export function fixtureMode() {
  return process.env.TM_FIXTURE_MODE === "true" && process.env.NODE_ENV !== "production";
}

export async function getViewer(): Promise<Viewer | null> {
  if (fixtureMode()) {
    const cookieStore = await cookies();
    const favoriteIds = (cookieStore.get("tm_fixture_favorites")?.value ?? "").split(",").filter((id) => /^(?:fixture-[a-z0-9-]+|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$/i.test(id));
    return { id: "fixture-owner", email: process.env.OWNER_EMAIL ?? "owner@example.com", fixture: true, favoriteIds };
  }
  if (!hasSupabaseConfig()) return null;
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  const email = user?.email?.toLowerCase();
  const owner = process.env.OWNER_EMAIL?.toLowerCase();
  if (!user || !email || !owner || email !== owner) return null;
  return { id: user.id, email, fixture: false, favoriteIds: [] };
}

export async function requireViewer(): Promise<Viewer> {
  const viewer = await getViewer();
  if (!viewer) redirect("/login");
  return viewer;
}
