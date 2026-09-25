const LOCAL_SUPABASE_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

/**
 * Return one exact Storage origin for CSP. Production accepts HTTPS only;
 * development additionally accepts the local Supabase HTTP origin.
 */
export function trustedSupabaseImageOrigin(rawUrl: string | undefined, production: boolean): string | null {
  if (!rawUrl) return null;
  try {
    const url = new URL(rawUrl);
    if (url.username || url.password) return null;
    if (url.protocol === "https:") return url.origin;
    if (!production && url.protocol === "http:" && LOCAL_SUPABASE_HOSTS.has(url.hostname)) return url.origin;
    return null;
  } catch {
    return null;
  }
}

export function imageSourcePolicy(rawSupabaseUrl: string | undefined, production: boolean): string {
  const storageOrigin = trustedSupabaseImageOrigin(rawSupabaseUrl, production);
  return ["'self'", "data:", "blob:", storageOrigin].filter(Boolean).join(" ");
}
