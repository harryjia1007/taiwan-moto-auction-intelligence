"use client";

import Link from "next/link";
import { Columns3, X } from "lucide-react";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  COMPARISON_STORAGE_KEY,
  comparisonHref,
  restoreComparisonItems,
  toggleComparisonItem,
  type ComparisonItem,
} from "@/lib/comparison";

interface ComparisonContextValue {
  selected: ComparisonItem[];
  toggle: (candidate: ComparisonItem) => void;
}

const ComparisonContext = createContext<ComparisonContextValue | null>(null);

export function ComparisonProvider({ children }: { children: ReactNode }) {
  const [{ selected, message }, setComparisonState] = useState<{ selected: ComparisonItem[]; message: string }>({ selected: [], message: "" });
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      setComparisonState({ selected: restoreComparisonItems(window.localStorage.getItem(COMPARISON_STORAGE_KEY)), message: "" });
    } catch {
      setComparisonState({ selected: [], message: "" });
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      window.localStorage.setItem(COMPARISON_STORAGE_KEY, JSON.stringify(selected));
    } catch {
      setComparisonState((current) => ({ ...current, message: "瀏覽器無法保存比較清單；本頁仍可繼續使用。" }));
    }
    document.body.classList.toggle("comparison-tray-visible", selected.length > 0);
    return () => document.body.classList.remove("comparison-tray-visible");
  }, [ready, selected]);

  useEffect(() => {
    function syncAcrossTabs(event: StorageEvent) {
      if (event.key !== COMPARISON_STORAGE_KEY) return;
      setComparisonState({ selected: restoreComparisonItems(event.newValue), message: "已同步其他分頁的比較清單。" });
    }
    window.addEventListener("storage", syncAcrossTabs);
    return () => window.removeEventListener("storage", syncAcrossTabs);
  }, []);

  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(() => setComparisonState((current) => ({ ...current, message: "" })), 3_000);
    return () => window.clearTimeout(timer);
  }, [message]);

  const value = useMemo<ComparisonContextValue>(() => ({
    selected,
    toggle(candidate) {
      setComparisonState((current) => {
        const update = toggleComparisonItem(current.selected, candidate);
        const nextMessage = update.rejected
          ? "最多只能同時比較 3 輛，請先移除一輛再加入。"
          : update.items.some((item) => item.id === candidate.id)
            ? `已將「${candidate.name}」加入比較。`
            : `已將「${candidate.name}」移出比較。`;
        return { selected: update.items, message: nextMessage };
      });
    },
  }), [selected]);

  const href = comparisonHref(selected);
  function remove(item: ComparisonItem) {
    value.toggle(item);
  }
  function clear() {
    setComparisonState({ selected: [], message: "已清空比較清單。" });
  }

  return <ComparisonContext.Provider value={value}>
    {children}
    {ready && selected.length > 0 && <aside className="comparison-tray" aria-label="候選車輛比較列">
      <div className="comparison-tray-heading">
        <span><Columns3 size={16}/> 候選比較</span>
        <strong>{selected.length}／3 輛</strong>
      </div>
      <div className="comparison-candidates" aria-label="已選比較車輛">
        {selected.map((item) => <button type="button" key={item.id} onClick={() => remove(item)} aria-label={`從比較移除：${item.name}`}>
          <span>{item.name}</span><X size={14}/>
        </button>)}
      </div>
      <div className="comparison-tray-actions">
        <button type="button" className="comparison-clear" onClick={clear}>清空</button>
        {href
          ? <Link className="button comparison-open" href={href}>比較 {selected.length} 輛</Link>
          : <span className="comparison-hint">再選 1 輛即可比較</span>}
      </div>
    </aside>}
    {ready && message && <span className={`interaction-toast ${message.includes("最多") || message.includes("無法") ? "error" : ""}`} role="status" aria-live="polite">{message}</span>}
  </ComparisonContext.Provider>;
}

export function CompareButton({ id, name }: ComparisonItem) {
  const comparison = useContext(ComparisonContext);
  if (!comparison) return null;
  const selected = comparison.selected.some((item) => item.id === id);
  return <button
    type="button"
    className="compare-toggle"
    aria-label={`${selected ? "從比較移除" : "加入比較"}：${name}`}
    aria-pressed={selected}
    onClick={() => comparison.toggle({ id, name })}
  >
    <Columns3 size={15}/><span>{selected ? "已比較" : "比較"}</span>
  </button>;
}
