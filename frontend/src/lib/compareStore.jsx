import { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api.js";

// Which professors are selected for comparison. Lives here, keyed by id, so
// every card and the compare bar read the same list (see I-1: state about
// which items are chosen belongs in the parent, not in each item).
const CompareContext = createContext(null);
const STORAGE_KEY = "profiq.compare";
const MAX_SELECTION = 4;

export function CompareProvider({ children }) {
  // Storage is user-controlled: it can be missing, stale, or corrupted by
  // an extension. A bad value must never take the app down.
  const [ids, setIds] = useState(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.filter((x) => Number.isInteger(x)) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
    } catch {
      /* storage unavailable, keep in-memory only */
    }
  }, [ids]);

  // Stored ids can outlive the professors they point at (the catalog was
  // replaced once already). The compare endpoint only returns rows that
  // exist, so ask it once on load and drop the rest. Otherwise the bar says
  // "4 selected" and the limit trips while the page shows one card.
  useEffect(() => {
    if (ids.length === 0) return;
    let cancelled = false;
    api
      .compare(ids)
      .then((rows) => {
        if (cancelled) return;
        const alive = new Set(rows.map((r) => r.id));
        setIds((prev) => {
          const kept = prev.filter((id) => alive.has(id));
          return kept.length === prev.length ? prev : kept;
        });
      })
      .catch(() => {
        /* offline or backend down: keep what we have */
      });
    return () => {
      cancelled = true;
    };
    // Runs once on mount on purpose; later toggles only add ids that were
    // just rendered from the API, so they are known to exist.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggle = (id) => {
    // React decides whether to re-render by comparing references. Mutating
    // the existing array and setting it back looks like "nothing changed".
    // Always build a new array.
    setIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= MAX_SELECTION) return prev;
      return [...prev, id];
    });
  };

  const clear = () => setIds([]);
  const has = (id) => ids.includes(id);
  const full = ids.length >= MAX_SELECTION;

  return (
    <CompareContext.Provider value={{ ids, toggle, clear, has, full }}>
      {children}
    </CompareContext.Provider>
  );
}

export function useCompare() {
  const ctx = useContext(CompareContext);
  if (!ctx) throw new Error("useCompare must be used within CompareProvider");
  return ctx;
}
