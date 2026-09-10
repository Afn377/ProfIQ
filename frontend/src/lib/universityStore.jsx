import { createContext, useContext, useEffect, useState } from "react";

const UniversityContext = createContext(null);
const STORAGE_KEY = "profiq.university";

export function UniversityProvider({ children }) {
  const [institution, setInstitutionState] = useState(() => {
    try {
      // Stored as a plain string (not JSON) since we only keep one school name.
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? raw : null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    try {
      if (institution) localStorage.setItem(STORAGE_KEY, institution);
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* storage unavailable — keep the in-memory value only */
    }
  }, [institution]);

  const setInstitution = (name) => {
    const trimmed = typeof name === "string" ? name.trim() : "";
    setInstitutionState(trimmed || null);
  };

  const clearInstitution = () => setInstitutionState(null);

  return (
    <UniversityContext.Provider
      value={{ institution, setInstitution, clearInstitution }}
    >
      {children}
    </UniversityContext.Provider>
  );
}

export function useUniversity() {
  const ctx = useContext(UniversityContext);
  if (!ctx) throw new Error("useUniversity must be used within UniversityProvider");
  return ctx;
}
