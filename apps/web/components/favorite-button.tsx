"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Heart } from "lucide-react";

export function FavoriteButton({ id, initial, variant = "overlay" }: { id: string; initial: boolean; variant?: "overlay" | "inline" | "compact" }) {
  const router = useRouter();
  const [favorite, setFavorite] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(() => setMessage(""), 3_000);
    return () => window.clearTimeout(timer);
  }, [message]);
  async function toggle() {
    if (busy) return;
    const next = !favorite;
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch(`/api/favorites/${id}`, { method: next ? "POST" : "DELETE", keepalive: true });
      if (!response.ok) throw new Error("favorite request failed");
      setFavorite(next);
      setMessage(next ? "已加入收藏" : "已移除收藏");
      router.refresh();
    } catch {
      setMessage("收藏更新失敗，請稍後再試");
    } finally {
      setBusy(false);
    }
  }
  return <>
    <button type="button" className={`favorite ${variant === "inline" ? "favorite-inline" : variant === "compact" ? "favorite-compact" : ""}`} aria-label={favorite ? "移除收藏" : "加入收藏"} aria-pressed={favorite} aria-busy={busy} onClick={toggle} disabled={busy}>
      <Heart size={18} fill={favorite ? "currentColor" : "none"} />
      {variant === "inline" && <span>{busy ? "更新中" : favorite ? "已收藏" : "加入收藏"}</span>}
    </button>
    {message && <span className={`interaction-toast ${message.includes("失敗") ? "error" : ""}`} role="status" aria-live="polite">{message}</span>}
  </>;
}
