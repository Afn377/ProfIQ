import { useEffect, useState } from "react";
import ProfessorCard from "../components/ProfessorCard.jsx";

export default function Home() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);

  // Runs once, after the first render — not on every render.
  useEffect(() => {
    fetch("/api/summary/")
      .then((res) => res.json())
      .then(setSummary)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="container error">{error}</div>;
  if (!summary) return <div className="container spinner">Loading…</div>;

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
