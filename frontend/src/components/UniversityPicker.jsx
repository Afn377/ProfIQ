import { useEffect, useId, useRef, useState } from "react";
import { api } from "../lib/api.js";
import { useUniversity } from "../lib/universityStore.jsx";

// Fallback school name typed by the user when nothing in the list matches.
// Returns the name to persist, or null when the input is ambiguous/empty.
function resolveInstitution(input, options) {
  const trimmed = input.trim();
  if (!trimmed) return null;
  const lower = trimmed.toLowerCase();
  const exact = options.find((s) => s.name.toLowerCase() === lower);
  if (exact) return exact.name;
  if (options.length === 1) return options[0].name;
  const prefix = options.filter((s) => s.name.toLowerCase().startsWith(lower));
  if (prefix.length === 1) return prefix[0].name;
  return null;
}

export default function UniversityPicker() {
  const { setInstitution } = useUniversity();

  const [input, setInput] = useState("");
  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [hint, setHint] = useState(false);

  const listId = useId();
  const debounceRef = useRef(null);

  // Seed with the largest schools so there's something to click before typing.
  useEffect(() => {
    api.institutions({ limit: 15 }).then(setOptions).catch(() => {}).finally(() => setLoading(false));
  }, []);

  // Debounced autocomplete — fires 200ms after the user stops typing, matching Search.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      api
        .institutions({ q: input.trim(), limit: 15 })
        .then((data) => {
          setOptions(data);
          setActiveIndex(-1);
        })
        .catch(() => {});
    }, 200);
    return () => clearTimeout(debounceRef.current);
  }, [input]);

  const choose = (name) => {
    if (!name) return;
    setInstitution(name);
  };

  // Name we'd persist if the user submitted right now (null = ambiguous).
  const resolved = resolveInstitution(input, options);

  const onSubmit = (e) => {
    e.preventDefault();
    if (activeIndex >= 0 && options[activeIndex]) {
      choose(options[activeIndex].name);
      return;
    }
    if (resolved) {
      choose(resolved);
      return;
    }
    setHint(true);
  };

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActiveIndex((i) => (options.length ? (i + 1) % options.length : -1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      setActiveIndex((i) =>
        options.length ? (i <= 0 ? options.length - 1 : i - 1) : -1,
      );
    } else if (e.key === "Escape") {
      setOpen(false);
      setActiveIndex(-1);
    }
  };

  const showList = open && options.length > 0;

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: "48px 24px",
      }}
    >
      <div style={{ width: "100%", maxWidth: 560 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            fontFamily: "var(--font-heading)",
            fontWeight: 700,
            letterSpacing: "-0.02em",
            fontSize: 18,
            marginBottom: 26,
            justifyContent: "center",
          }}
        >
          <span className="brand-mark">P</span>
          <span>ProfIQ</span>
        </div>

        <h1
          style={{
            fontFamily: "var(--font-heading)",
            fontSize: "clamp(28px, 4vw, 38px)",
            letterSpacing: "-0.03em",
            lineHeight: 1.1,
            textAlign: "center",
            margin: "0 0 14px",
          }}
        >
          Which university are you at?
        </h1>
        <p
          style={{
            color: "var(--text-dim)",
            fontSize: 15,
            lineHeight: 1.55,
            textAlign: "center",
            margin: "0 0 28px",
          }}
        >
          ProfIQ scopes its recommendations and sentiment scores to your school so
          every professor you see is directly comparable.
        </p>

        <form
          className="search-bar"
          onSubmit={onSubmit}
          style={{ maxWidth: "none", margin: 0 }}
        >
          <input
            autoFocus
            role="combobox"
            aria-expanded={showList}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={
              activeIndex >= 0 ? `${listId}-option-${activeIndex}` : undefined
            }
            placeholder="Start typing your school name…"
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              setOpen(true);
              setHint(false);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => setOpen(false)}
            onKeyDown={onKeyDown}
          />
          <button
            type="submit"
            className="btn btn-primary"
            aria-disabled={!resolved}
            style={{
              opacity: resolved ? 1 : 0.5,
            }}
          >
            Continue
          </button>
        </form>

        {hint && !resolved && (
          <div
            className="empty"
            style={{ padding: "16px 0 0", fontSize: 14 }}
          >
            Pick your school from the list to continue.
          </div>
        )}

        {showList && (
          <div
            id={listId}
            role="listbox"
            style={{
              marginTop: 10,
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 14,
              boxShadow: "var(--shadow)",
              overflowX: "hidden",
              maxHeight: 340,
              overflowY: "auto",
            }}
          >
            {options.map((s, i) => (
              <div
                key={s.name}
                id={`${listId}-option-${i}`}
                role="option"
                aria-selected={i === activeIndex}
                onMouseDown={(e) => e.preventDefault()}
                onMouseEnter={() => setActiveIndex(i)}
                onClick={() => choose(s.name)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 12,
                  padding: "12px 16px",
                  cursor: "pointer",
                  background: i === activeIndex ? "var(--surface-2)" : "transparent",
                  borderBottom: i === options.length - 1 ? "none" : "1px solid var(--border)",
                }}
              >
                <span style={{ fontSize: 15 }}>{s.name}</span>
                <span
                  className="pill"
                  style={{ flexShrink: 0, whiteSpace: "nowrap" }}
                >
                  {s.professor_count.toLocaleString()} profs
                </span>
              </div>
            ))}
          </div>
        )}

        {!showList && loading && <div className="spinner" />}

        {!showList && !loading && input.trim() && options.length === 0 && (
          <div className="empty" style={{ padding: "24px 0", fontSize: 14 }}>
            No schools match “{input.trim()}”.
          </div>
        )}
      </div>
    </div>
  );
}
