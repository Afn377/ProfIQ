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
    <div className="picker">
      <div className="picker-inner">
        <div className="brand picker-brand">ProfIQ</div>

        <h1 className="picker-title">Which university are you at?</h1>
        <p className="picker-lede">
          Scores and recommendations are scoped to one school, so every
          professor you see is directly comparable.
        </p>

        <form className="hero-search" onSubmit={onSubmit}>
          <input
            autoFocus
            role="combobox"
            aria-expanded={showList}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={
              activeIndex >= 0 ? `${listId}-option-${activeIndex}` : undefined
            }
            placeholder="Start typing your school"
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
          >
            Continue
          </button>
        </form>

        {hint && !resolved && (
          <p className="form-error picker-hint">
            Pick your school from the list to continue.
          </p>
        )}

        {showList && (
          <ul id={listId} role="listbox" className="picker-list">
            {options.map((s, i) => (
              <li
                key={s.name}
                id={`${listId}-option-${i}`}
                role="option"
                aria-selected={i === activeIndex}
                className={"picker-option" + (i === activeIndex ? " active" : "")}
                onMouseDown={(e) => e.preventDefault()}
                onMouseEnter={() => setActiveIndex(i)}
                onClick={() => choose(s.name)}
              >
                <span>{s.name}</span>
                <span className="picker-count num">
                  {s.professor_count.toLocaleString()} professors
                </span>
              </li>
            ))}
          </ul>
        )}

        {!showList && loading && <div className="spinner" />}

        {!showList && !loading && input.trim() && options.length === 0 && (
          <p className="report-note">No schools match "{input.trim()}".</p>
        )}
      </div>
    </div>
  );
}
