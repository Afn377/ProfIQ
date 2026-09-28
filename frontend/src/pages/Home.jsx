import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { useUniversity } from "../lib/universityStore.jsx";
import { useCompare } from "../lib/compareStore.jsx";
import { scoreBucket } from "../lib/format.js";

const fmt = (n) => (n ?? 0).toLocaleString();

// One row of the ranked list. The rank is a real sequence, so it gets a
// number. Everything else in the row stays quiet so the score reads first.
function RankRow({ prof, rank }) {
  const { has, toggle, full } = useCompare();
  const selected = has(prof.id);
  const score = prof.recommendation_score ?? 0;

  const onToggle = (e) => {
    e.preventDefault();
    if (!selected && full) return;
    toggle(prof.id);
  };

  return (
    <li className="rank-row">
      <span className="rank-num num">{rank}</span>
      <div className="rank-main">
        <Link to={`/professors/${prof.id}`} className="rank-name">
          {prof.name}
        </Link>
        <div className="rank-meta">
          {prof.department || "Department not listed"}
          <span className="rank-sep" aria-hidden="true" />
          {fmt(prof.review_count)} reviews
          {prof.avg_compound != null && (
            <>
              <span className="rank-sep" aria-hidden="true" />
              <span title="Average sentiment, from -1 to 1">
                Sentiment {prof.avg_compound > 0 ? "+" : ""}
                {prof.avg_compound.toFixed(2)}
              </span>
            </>
          )}
        </div>
      </div>
      <div className="rank-side">
        <span className={"rank-score num " + scoreBucket(score)}>
          {Math.round(score)}
        </span>
        <button
          type="button"
          className={"rank-compare" + (selected ? " active" : "")}
          onClick={onToggle}
          disabled={!selected && full}
        >
          {selected ? "In compare" : "Compare"}
        </button>
      </div>
    </li>
  );
}

export default function Home() {
  const { institution } = useUniversity();
  const [summary, setSummary] = useState(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .summary({ institution })
      .then(setSummary)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [institution]);

  const onSearch = (e) => {
    e.preventDefault();
    const q = query.trim();
    navigate(q ? `/search?q=${encodeURIComponent(q)}` : "/search");
  };

  return (
    <>
      <section className="hero container">
        <h1 className="hero-title">
          Pick a professor by what students said about them.
        </h1>
        <p className="hero-lede">
          ProfIQ reads every RateMyProfessors review for your school, scores
          each one for sentiment, and ranks instructors from that evidence.
        </p>
        <form className="hero-search" onSubmit={onSearch}>
          <label htmlFor="home-q" className="visually-hidden">
            Search professors
          </label>
          <input
            id="home-q"
            placeholder="Professor, course, or department"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <button type="submit" className="btn btn-primary">
            Search
          </button>
        </form>
        {summary && (
          <p className="hero-coverage">
            Covering <span className="num">{fmt(summary.professor_count)}</span>{" "}
            professors in <span className="num">{fmt(summary.department_count)}</span>{" "}
            departments, from{" "}
            <span className="num">{fmt(summary.review_count)}</span> reviews.
          </p>
        )}
      </section>

      <section className="section container">
        <div className="section-head">
          <div>
            <h2>Top recommended</h2>
            <div className="sub">
              {summary
                ? `Ranked by sentiment score. ${fmt(summary.analyzed_count)} of ${fmt(summary.professor_count)} professors analyzed so far.`
                : "Ranked by sentiment score."}
            </div>
          </div>
          <Link to="/search" className="section-link">
            Browse everyone
          </Link>
        </div>
        {loading ? (
          <div className="spinner" />
        ) : error ? (
          <div className="empty">{error}</div>
        ) : summary.top_professors.length === 0 ? (
          <div className="empty">
            No one has been analyzed at this school yet. Open a professor from
            Browse to start.
          </div>
        ) : (
          <ol className="rank-list">
            {summary.top_professors.map((p, i) => (
              <RankRow key={p.id} prof={p} rank={i + 1} />
            ))}
          </ol>
        )}
      </section>
    </>
  );
}
