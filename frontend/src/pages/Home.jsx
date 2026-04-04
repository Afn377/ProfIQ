import { useState } from "react";
import ProfessorCard from "../components/ProfessorCard.jsx";

export default function Home() {
  const [summary, setSummary] = useState(null);

  // Naive: fetch straight from the backend, right here in the component body.
  fetch("http://127.0.0.1:8000/api/summary/")
    .then((res) => res.json())
    .then(setSummary);

  return (
    <div className="container">
      <section className="hero">
        <h1>Find the right professor</h1>
        <p>Sentiment-scored reviews, searchable by name, school, or course.</p>
        <div className="stats">
          <div className="stat">
            <div className="value">{summary.professor_count}</div>
            <div className="label">Professors</div>
          </div>
          <div className="stat">
            <div className="value">{summary.analyzed_count}</div>
            <div className="label">Analyzed</div>
          </div>
        </div>
      </section>
      <section>
        <h2>Top recommended</h2>
        <div className="grid">
          {summary.top_professors.map((p) => (
            <ProfessorCard prof={p} />
          ))}
        </div>
      </section>
    </div>
  );
}
