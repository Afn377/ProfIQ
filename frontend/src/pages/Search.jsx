import { useEffect, useId, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api.js";
import { useUniversity } from "../lib/universityStore.jsx";
import ProfessorCard from "../components/ProfessorCard.jsx";
import AddProfessorModal from "../components/AddProfessorModal.jsx";

export default function Search() {
  const { institution: savedInstitution } = useUniversity();
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
    // Guard against out-of-order responses: a stale request (superseded because
    // this effect re-ran for newer deps, e.g. the institution param being seeded
    // from the saved university right after mount) must never overwrite state
    // owned by the latest-issued request.
    let ignore = false;
    setLoading(true);
    setError(null);
    api
      .searchProfessors({ q, department, institution, sort })
      .then((data) => {
        if (ignore) return;
        setResults(data.results || data);
      })
      .catch((e) => {
        if (ignore) return;
        setError(e.message);
      })
      .finally(() => {
        if (ignore) return;
        setLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [q, department, institution, sort]);

  useEffect(() => setInput(q), [q]);
  useEffect(() => setSchoolInput(institution), [institution]);

  const updateParam = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  // Seed the school filter from the user's saved university on first arrival,
  // but only when the URL doesn't already carry an institution param. A one-shot
  // ref guard means later clears/changes by the user are left untouched.
  const seededSchoolRef = useRef(false);
  useEffect(() => {
    if (seededSchoolRef.current) return;
    seededSchoolRef.current = true;
    if (!institution && savedInstitution) updateParam("institution", savedInstitution);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Prompt to sync when the navbar switches schools out from under Browse.
  const prevSavedRef = useRef(savedInstitution);
  const [switchPrompt, setSwitchPrompt] = useState(null);
  useEffect(() => {
    const prev = prevSavedRef.current;
    prevSavedRef.current = savedInstitution;
    if (savedInstitution && savedInstitution !== prev && savedInstitution !== institution) {
      setSwitchPrompt(savedInstitution);
    }
  }, [savedInstitution, institution]);

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

  return (
    <section className="section container">
      <div className="section-head">
        <div>
          <h2>Browse professors</h2>
          <div className="sub">
            {loading
              ? "Searching"
              : `${results.length} result${results.length === 1 ? "" : "s"}`}
            {institution && <> at {institution}</>}
          </div>
        </div>
        <div className="sort-row" role="group" aria-label="Sort by">
          <span className="sort-label">Sort by</span>
          <button
            className={"sort-option" + (sort === "score" ? " active" : "")}
            onClick={() => updateParam("sort", "score")}
          >
            Top score
          </button>
          <button
            className={"sort-option" + (sort === "reviews" ? " active" : "")}
            onClick={() => updateParam("sort", "reviews")}
          >
            Most reviews
          </button>
          <button
            className={"sort-option" + (sort === "name" ? " active" : "")}
            onClick={() => updateParam("sort", "name")}
          >
            Name
          </button>
        </div>
      </div>

      {switchPrompt && (
        <div className="notice">
          <div className="notice-text">
            You switched to {switchPrompt}. Update this search to match?
          </div>
          <div className="notice-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                setSchoolInput(switchPrompt);
                updateParam("institution", switchPrompt);
                setSwitchPrompt(null);
              }}
            >
              Update
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setSwitchPrompt(null)}
            >
              Keep {institution || "current filter"}
            </button>
          </div>
        </div>
      )}

      <form className="filters" onSubmit={onSubmit}>
        <input
          className="field field-grow"
          placeholder="Professor, course, or department"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <input
          className="field field-school"
          list={datalistId}
          placeholder="School"
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
          >
            Clear school
          </button>
        )}
        <select
          value={department}
          className="field"
          onChange={(e) => updateParam("department", e.target.value)}
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
    <div className="empty empty-results">
      <p className="empty-title">No professors match your search.</p>
      <p>
        {target
          ? `If ${target}${institution ? ` at ${institution}` : ""} is missing, add them`
          : "If someone is missing, add them"}{" "}
        and their reviews will be fetched.
      </p>
      <div>
        <button type="button" className="btn btn-primary" onClick={onAddClick}>
          Add a professor
        </button>
      </div>
    </div>
  );
}
