import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api.js";
import ProfessorCard from "../components/ProfessorCard.jsx";

export default function Search() {
  // Filters live in the URL, so Back/refresh/share all keep them.
  const [params, setParams] = useSearchParams();
  const q = params.get("q") || "";
  const department = params.get("department") || "";
  const sort = params.get("sort") || "score";

  const updateParam = (key, value) => {
    const next = new URLSearchParams(params);
    value ? next.set(key, value) : next.delete(key);
    setParams(next, { replace: true });
  };

  // The input updates on every keystroke; the URL (and so the request) only
  // updates after a 300 ms pause. Typing "lee" sends one request, not three.
  const [draft, setDraft] = useState(q);
  useEffect(() => {
    if (draft === q) return;
    const handle = setTimeout(() => updateParam("q", draft), 300);
    return () => clearTimeout(handle);
  }, [draft]);

  const [selected, setSelected] = useState(new Set());
  const [departments, setDepartments] = useState([]);
  const [results, setResults] = useState([]);
  const [count, setCount] = useState(0);

  useEffect(() => {
    api.departments().then(setDepartments).catch(() => {});
  }, []);

  useEffect(() => {
    // Two requests can be in flight at once (type "d", then "a"). If the
    // older one arrives last it must not overwrite the newer results, so
    // each run marks itself stale in its cleanup and ignores its response.
    let current = true;
    api.searchProfessors({ q, department, sort }).then((data) => {
      if (!current) return;
      setResults(data.results);
      setCount(data.count);
    });
    return () => { current = false; };
  }, [q, department, sort]);

  const toggle = (id) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  return (
    <div className="container">
      <h2>Browse professors</h2>
      <div className="filters">
        <input
          placeholder="Search professor, course, or department…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <select value={department} onChange={(e) => updateParam("department", e.target.value)}>
          <option value="">All departments</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
        <select value={sort} onChange={(e) => updateParam("sort", e.target.value)}>
          <option value="score">Best score</option>
          <option value="name">Name A–Z</option>
        </select>
      </div>
      <p className="sub">{count} professors</p>
      <div className="grid">
        {results.map((p) => (
          <ProfessorCard key={p.id} prof={p} selected={selected.has(p.id)} onToggle={() => toggle(p.id)} />
        ))}
      </div>
    </div>
  );
}
