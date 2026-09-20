import { useEffect, useId, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { api } from "../lib/api.js";
import { useUniversity } from "../lib/universityStore.jsx";

export default function Navbar() {
  const { institution, setInstitution } = useUniversity();
  const [switching, setSwitching] = useState(false);
  const [switchInput, setSwitchInput] = useState("");
  const [schoolOptions, setSchoolOptions] = useState([]);

  const datalistId = useId();
  const debounceRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!switching) return;
    api.institutions({ limit: 15 }).then(setSchoolOptions).catch(() => {});
    inputRef.current?.focus();
  }, [switching]);

  // Debounced autocomplete while typing, matching Search's school filter.
  useEffect(() => {
    if (!switching) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      api
        .institutions({ q: switchInput.trim(), limit: 15 })
        .then(setSchoolOptions)
        .catch(() => {});
    }, 200);
    return () => clearTimeout(debounceRef.current);
  }, [switchInput, switching]);

  // Only commits on an exact match from the suggestions — this changes the
  // school in place (setInstitution) rather than clearing it, so the app
  // never unmounts to the full-page onboarding picker and pages like Browse
  // stay mounted to notice and react to the switch.
  const commitSwitch = () => {
    const trimmed = switchInput.trim();
    if (trimmed) {
      const exact = schoolOptions.find(
        (s) => s.name.toLowerCase() === trimmed.toLowerCase(),
      );
      if (exact) setInstitution(exact.name);
    }
    setSwitching(false);
    setSwitchInput("");
  };

  return (
    <header className="navbar">
      <div className="container navbar-inner">
        <NavLink to="/" className="brand">
          <span className="brand-mark">P</span>
          <span>
            Prof<span style={{ color: "var(--accent-2)" }}>IQ</span>
          </span>
        </NavLink>
        <div className="navbar-right">
          <nav className="nav-links">
            <NavLink
              to="/"
              end
              className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
            >
              Home
            </NavLink>
            <NavLink
              to="/search"
              className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
            >
              Browse
            </NavLink>
            <NavLink
              to="/compare"
              className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
            >
              Compare
            </NavLink>
          </nav>
          {institution && !switching && (
            <div className="school-chip" title={institution}>
              <span className="school-chip-name">
                {institution.length > 24 ? institution.slice(0, 21) + "…" : institution}
              </span>
              <button
                type="button"
                className="school-chip-change"
                onClick={() => setSwitching(true)}
                title="Change university"
              >
                change
              </button>
            </div>
          )}
          {switching && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                commitSwitch();
              }}
            >
              <input
                ref={inputRef}
                list={datalistId}
                value={switchInput}
                placeholder="Switch school…"
                onChange={(e) => setSwitchInput(e.target.value)}
                onBlur={commitSwitch}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setSwitching(false);
                    setSwitchInput("");
                  }
                }}
                style={{
                  background: "var(--surface-2)",
                  color: "var(--text)",
                  border: "1px solid var(--border)",
                  borderRadius: 999,
                  padding: "6px 12px",
                  fontSize: 13,
                  width: 200,
                }}
              />
              <datalist id={datalistId}>
                {schoolOptions.map((s) => (
                  <option key={s.name} value={s.name} />
                ))}
              </datalist>
            </form>
          )}
        </div>
      </div>
    </header>
  );
}
