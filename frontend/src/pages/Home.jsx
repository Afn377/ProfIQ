import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import ProfessorCard from "../components/ProfessorCard.jsx";

export default function Home() {
  const [summary, setSummary] = useState(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    api
      .summary()
      .then(setSummary)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const onSearch = (e) => {
    e.preventDefault();
    const q = query.trim();
    navigate(q ? `/search?q=${encodeURIComponent(q)}` : "/search");
  };

  return (
    <>
      <section className="hero container">
        <h1>
          Find the right professor,
          <br />
          <span className="grad">powered by real feedback.</span>
        </h1>
        <p>
          ProfIQ aggregates reviews from RateMyProfessors and Reddit, runs NLP
          sentiment analysis on every comment, and ranks instructors by an
          evidence-based recommendation score.
        </p>
        <form className="search-bar" onSubmit={onSearch}>
          <input
            placeholder="Search by professor, course, or department…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <button type="submit" className="btn btn-primary">
            Search
          </button>
        </form>

        {summary && (
          <div className="hero-stats">
            <div className="stat-chip">
              <div className="value">{summary.professor_count}</div>
              <div className="label">Professors</div>
            </div>
            <div className="stat-chip">
              <div className="value">{summary.review_count}</div>
              <div className="label">Reviews analyzed</div>
            </div>
            <div className="stat-chip">
              <div className="value">{summary.departments.length}</div>
              <div className="label">Departments</div>
            </div>
            <div className="stat-chip">
              <div className="value">2</div>
              <div className="label">Data sources</div>
            </div>
          </div>
        )}
      </section>

      <section className="section container">
        <div className="section-head">
          <div>
            <h2>Top recommended</h2>
            <div className="sub">Ranked by aggregated sentiment score</div>
          </div>
        </div>
        {loading ? (
          <div className="spinner" />
        ) : error ? (
          <div className="empty">{error}</div>
        ) : (
          <div className="prof-grid">
            {summary.top_professors.map((p) => (
              <ProfessorCard key={p.id} prof={p} />
            ))}
          </div>
        )}
      </section>
    </>
  );
}
