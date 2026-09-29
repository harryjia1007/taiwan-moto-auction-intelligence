import { describe, expect, it } from "vitest";
import { imageSourcePolicy, trustedSupabaseImageOrigin } from "./content-security-policy";

describe("Content Security Policy image sources", () => {
  it("allows only the exact HTTPS Supabase origin in production", () => {
    expect(trustedSupabaseImageOrigin("https://project-ref.supabase.co/rest/v1", true)).toBe("https://project-ref.supabase.co");
    expect(imageSourcePolicy("https://project-ref.supabase.co/rest/v1", true)).toBe("'self' data: blob: https://project-ref.supabase.co");
    expect(imageSourcePolicy("https://project-ref.supabase.co", true)).not.toContain("*.supabase.co");
  });

  it("rejects credentials, malformed URLs, and external HTTP in production", () => {
    expect(trustedSupabaseImageOrigin("https://user:pass@project-ref.supabase.co", true)).toBeNull();
    expect(trustedSupabaseImageOrigin("not a url", true)).toBeNull();
    expect(trustedSupabaseImageOrigin("http://project-ref.supabase.co", true)).toBeNull();
  });

  it("permits a local HTTP Supabase origin only outside production", () => {
    expect(trustedSupabaseImageOrigin("http://127.0.0.1:54321", false)).toBe("http://127.0.0.1:54321");
    expect(trustedSupabaseImageOrigin("http://127.0.0.1:54321", true)).toBeNull();
  });
});
