import { useEffect, useId, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api.js";
import ProfessorCard from "../components/ProfessorCard.jsx";
import AddProfessorModal from "../components/AddProfessorModal.jsx";

export default function Search() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") || "";
  const department = params.get("department") || "";
  const institution = params.get("institution") || "";
  const sort = params.get("sort") || "score";

  const [input, setInput] = useState(q);
  const [schoolInput, setSchoolInput] = useState(institution);
  const [departments, setDepartments] = useState([]);
  const [schoolOptions, setSchoolOptions] = useState([]);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [addOpen, setAddOpen] = useState(false);

  const datalistId = useId();
  const schoolDebounceRef = useRef(null);

  useEffect(() => {
    api.departments().then(setDepartments).catch(() => {});
    // Seed the datalist with the largest schools so it's useful before typing.
    api.institutions({ limit: 15 }).then(setSchoolOptions).catch(() => {});
  }, []);

  // Debounced school autocomplete — fires 200ms after the user stops typing.
  useEffect(() => {
    if (schoolDebounceRef.current) clearTimeout(schoolDebounceRef.current);
    schoolDebounceRef.current = setTimeout(() => {
      api
        .institutions({ q: schoolInput.trim(), limit: 15 })
        .then(setSchoolOptions)
        .catch(() => {});
    }, 200);
    return () => clearTimeout(schoolDebounceRef.current);
  }, [schoolInput]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .searchProfessors({ q, department, institution, sort })
      .then((data) => setResults(data.results || data))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [q, department, institution, sort]);

  useEffect(() => setInput(q), [q]);
  useEffect(() => setSchoolInput(institution), [institution]);

  const updateParam = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const onSubmit = (e) => {
    e.preventDefault();
    const next = new URLSearchParams(params);
    const trimmedQ = input.trim();
    const trimmedSchool = schoolInput.trim();
    if (trimmedQ) next.set("q", trimmedQ);
    else next.delete("q");
    if (trimmedSchool) next.set("institution", trimmedSchool);
    else next.delete("institution");
    setParams(next, { replace: true });
  };

  const clearSchool = () => {
    setSchoolInput("");
    updateParam("institution", "");
  };

  const fieldStyle = {
    background: "var(--surface-2)",
    color: "var(--text)",
    border: "1px solid var(--border)",
    borderRadius: 10,
    padding: "8px 12px",
  };

  return (
    <section className="section container">
      <div className="section-head">
        <div>
          <h2>Browse professors</h2>
          <div className="sub">
            {loading ? "Searching…" : `${results.length} result${results.length === 1 ? "" : "s"}`}
            {institution && (
              <>
                {" "}· at <strong style={{ color: "var(--text)" }}>{institution}</strong>
              </>
            )}
          </div>
        </div>
        <div className="filter-row">
          <button
            className={"btn btn-ghost" + (sort === "score" ? " active" : "")}
            onClick={() => updateParam("sort", "score")}
          >
            Top score
          </button>
          <button
            className={"btn btn-ghost" + (sort === "reviews" ? " active" : "")}
            onClick={() => updateParam("sort", "reviews")}
          >
            Most reviews
          </button>
          <button
            className={"btn btn-ghost" + (sort === "name" ? " active" : "")}
            onClick={() => updateParam("sort", "name")}
          >
            A – Z
          </button>
        </div>
      </div>

      <form
        className="search-bar"
        onSubmit={onSubmit}
        style={{ margin: "0 0 20px", flexWrap: "wrap", gap: 8 }}
      >
        <input
          placeholder="Search professor, course, or department…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <input
          list={datalistId}
          placeholder="Filter by school…"
          value={schoolInput}
          onChange={(e) => setSchoolInput(e.target.value)}
          onBlur={() => {
            // Commit on blur if user typed an exact match in the suggestions.
            const trimmed = schoolInput.trim();
            if (trimmed !== institution) {
              const exact = schoolOptions.find(
                (s) => s.name.toLowerCase() === trimmed.toLowerCase(),
              );
              if (exact) updateParam("institution", exact.name);
            }
          }}
          style={{ ...fieldStyle, minWidth: 240 }}
        />
        <datalist id={datalistId}>
          {schoolOptions.map((s) => (
            <option key={s.name} value={s.name}>
              {s.professor_count.toLocaleString()} professors
            </option>
          ))}
        </datalist>
        {institution && (
          <button
            type="button"
            className="btn btn-ghost"
            onClick={clearSchool}
            title="Clear school filter"
          >
            ✕ {institution.length > 28 ? institution.slice(0, 25) + "…" : institution}
          </button>
        )}
        <select
          value={department}
          onChange={(e) => updateParam("department", e.target.value)}
          style={fieldStyle}
        >
          <option value="">All departments</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <button type="submit" className="btn btn-primary">
          Search
        </button>
      </form>

      {loading ? (
        <div className="spinner" />
      ) : error ? (
        <div className="empty">{error}</div>
      ) : results.length === 0 ? (
        <EmptyResults
          query={q}
          institution={institution}
          onAddClick={() => setAddOpen(true)}
        />
      ) : (
        <div className="prof-grid">
          {results.map((p) => (
            <ProfessorCard key={p.id} prof={p} />
          ))}
        </div>
      )}

      <AddProfessorModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        defaultName={q}
        defaultInstitution={institution}
        departments={departments}
        schoolOptions={schoolOptions}
        onSchoolInput={setSchoolInput}
      />
    </section>
  );
}

// Empty search state with add-professor entry point.
function EmptyResults({ query, institution, onAddClick }) {
  const target = query?.trim();
  return (
    <div
      className="empty"
      style={{
        display: "grid",
        gap: 12,
        textAlign: "center",
        padding: "32px 20px",
      }}
    >
      <div style={{ fontSize: 16, color: "var(--text)" }}>
        No professors match your search.
      </div>
      <div style={{ color: "var(--text-dim)", fontSize: 14 }}>
        {target
          ? `Don't see ${target}${institution ? ` at ${institution}` : ""}?`
          : "Don't see who you're looking for?"}{" "}
        Add them and we'll fetch their reviews.
      </div>
      <div>
        <button type="button" className="btn btn-primary" onClick={onAddClick}>
          + Add a professor
        </button>
      </div>
    </div>
  );
}
