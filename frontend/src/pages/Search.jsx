import { useEffect, useState } from "react";
import { api } from "../lib/api.js";
import ProfessorCard from "../components/ProfessorCard.jsx";

export default function Search() {
  // Naive: filters live in component state.
  const [q, setQ] = useState("");
  const [department, setDepartment] = useState("");
  const [sort, setSort] = useState("score");

  const [departments, setDepartments] = useState([]);
  const [results, setResults] = useState([]);
  const [count, setCount] = useState(0);

  useEffect(() => {
    api.departments().then(setDepartments).catch(() => {});
  }, []);

  // Naive: fire a request on every change, keep whatever comes back last.
  useEffect(() => {
    api.searchProfessors({ q, department, sort }).then((data) => {
      setResults(data.results);
      setCount(data.count);
    });
  }, [q, department, sort]);

  return (
    <div className="container">
      <h2>Browse professors</h2>
      <div className="filters">
        <input
          placeholder="Search professor, course, or department…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select value={department} onChange={(e) => setDepartment(e.target.value)}>
          <option value="">All departments</option>
          {departments.map((d) => (
            <option value={d.id}>{d.name}</option>
          ))}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="score">Best score</option>
          <option value="name">Name A–Z</option>
        </select>
      </div>
      <p className="sub">{count} professors</p>
      <div className="grid">
        {results.map((p) => (
          <ProfessorCard prof={p} selectable />
        ))}
      </div>
    </div>
  );
}
