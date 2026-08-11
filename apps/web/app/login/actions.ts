"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { fixtureMode } from "@/lib/auth";
import { createSupabaseServerClient } from "@/lib/supabase-server";

export async function requestMagicLink(formData: FormData) {
  if (fixtureMode()) redirect("/motorcycles");
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const owner = process.env.OWNER_EMAIL?.toLowerCase();
  if (!owner || email !== owner) redirect("/login?error=owner");
  const requestHeaders = await headers();
  const origin = requestHeaders.get("origin") ?? "http://localhost:3000";
  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: `${origin}/auth/callback` } });
  if (error) redirect("/login?error=send");
  redirect("/login?sent=1");
}
