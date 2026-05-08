import { createContext, useContext, useEffect, useState } from "react";

const CompareContext = createContext(null);
const STORAGE_KEY = "profiq.compare";
const MAX_SELECTION = 4;

export function CompareProvider({ children }) {
  const [ids, setIds] = useState(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  }, [ids]);

  const toggle = (id) => {
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
