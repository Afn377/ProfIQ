import { createContext, useContext, useEffect, useState } from "react";

// Which professors are selected for comparison. Lives here, keyed by id, so
// every card and the compare bar read the same list (see I-1: state about
// which items are chosen belongs in the parent, not in each item).
const CompareContext = createContext(null);
const STORAGE_KEY = "profiq.compare";
const MAX_SELECTION = 4;

export function CompareProvider({ children }) {
  // Naive: trust whatever is in storage.
  const [ids, setIds] = useState(() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  }, [ids]);

  const toggle = (id) => {
    // Naive: mutate the array in place, then set it.
    const i = ids.indexOf(id);
    if (i >= 0) ids.splice(i, 1);
    else if (ids.length < MAX_SELECTION) ids.push(id);
    setIds(ids);
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
