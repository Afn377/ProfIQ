import { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis } from "recharts";
import { api } from "../lib/api.js";

const COLORS = { positive: "#2ecc8f", neutral: "#f0c75e", negative: "#ff5c7a" };

export default function ProfessorDetail() {
  const { id } = useParams();
  const [prof, setProf] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setProf(null);
    api.professor(id).then(setProf).catch((e) => setError(e.message));
  }, [id]);

  // Naive polling: while there are no stats, ask again every 3 s.
  useEffect(() => {
    if (!prof || prof.stats) return;
    setInterval(() => {
      api.professor(id).then(setProf);
    }, 3000);
  }, [prof, id]);

  if (error) return <div className="container error">{error}</div>;
  if (!prof) return <div className="container spinner">Loading…</div>;

  const stats = prof.stats;
  const sentimentData = stats
    ? [
        { name: "Positive", value: stats.positive_count, color: COLORS.positive },
        { name: "Neutral", value: stats.neutral_count, color: COLORS.neutral },
        { name: "Negative", value: stats.negative_count, color: COLORS.negative },
      ].filter((d) => d.value > 0)
    : [];
  const themeData = stats
    ? Object.entries(stats.theme_counts).sort((a, b) => b[1] - a[1]).map(([name, count]) => ({ name, count }))
    : [];

  return (
    <div className="container">
      <Link to="/search" className="sub">← Back to browse</Link>
      <h1>{prof.name}</h1>
      <div className="sub">
        {prof.department?.name ?? "No department"} · {prof.institution}
        {prof.source_num_ratings > 0 && ` · ${prof.source_num_ratings} ratings on RMP`}
      </div>

      {!stats ? (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="spinner">Analyzing reviews… this takes a few seconds the first time.</div>
        </div>
      ) : (
        <div className="detail-grid">
          <div className="card">
            <h3>Recommendation</h3>
            <div className="big-score">{stats.recommendation_score.toFixed(1)}</div>
            <div className="sub">out of 100 · {stats.review_count} reviews analyzed</div>
          </div>
          <div className="card">
            <h3>Sentiment</h3>
            {/* ResponsiveContainer fills its parent, so the parent must have a height. */}
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={sentimentData} dataKey="value" nameKey="name" innerRadius={45} outerRadius={70} isAnimationActive={false}>
                  {sentimentData.map((d) => <Cell key={d.name} fill={d.color} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="card wide">
            <h3>What reviews talk about</h3>
            <ResponsiveContainer width="100%" height={Math.max(120, themeData.length * 32)}>
              <BarChart data={themeData} layout="vertical" margin={{ left: 20 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" width={90} />
                <Bar dataKey="count" fill="#6c8cff" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <ReviewsSection professorId={prof.id} hasRmp={prof.external_ref?.startsWith("rmp:")} />
    </div>
  );
}

function ReviewsSection({ professorId, hasRmp }) {
  const [reviews, setReviews] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  // State updates are async, so `loading` alone can't stop a double-click:
  // all the clicks in one tick see loading === false. A ref changes at once.
  const inFlight = useRef(false);

  const load = () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    api.professorReviews(professorId, { cursor })
      .then((data) => {
        setReviews((prev) => [...prev, ...data.results]);   // append, don't replace
        setCursor(data.next_cursor);
        setHasMore(data.has_more);
      })
      .catch((e) => setError(e.message))
      .finally(() => { inFlight.current = false; setLoading(false); });
  };

  useEffect(() => {
    // Fetch page one when the professor changes. `current` guards against a
    // superseded run (StrictMode double-run in dev, or a fast route change)
    // appending its page after a newer run has already started.
    if (!hasRmp) return;
    let current = true;
    setReviews([]);
    setCursor(null);
    setHasMore(true);
    api.professorReviews(professorId, { cursor: null })
      .then((data) => {
        if (!current) return;
        setReviews(data.results);
        setCursor(data.next_cursor);
        setHasMore(data.has_more);
      })
      .catch((e) => current && setError(e.message));
    return () => { current = false; };
  }, [professorId]);

  if (!hasRmp) return null;
  return (
    <section style={{ marginTop: 32 }}>
      <h2>Reviews</h2>
      {error && <div className="error">{error}</div>}
      {reviews.map((r, i) => (
        <div className="card" key={i} style={{ marginBottom: 12 }}>
          <div className="sub">
            <span className={`score ${r.sentiment.label === "positive" ? "good" : r.sentiment.label === "negative" ? "bad" : "meh"}`}>
              {r.sentiment.label}
            </span>
            {r.course && ` · ${r.course}`}
            {r.rating != null && ` · ${r.rating}/5`}
          </div>
          <p style={{ margin: "8px 0 0" }}>{r.text}</p>
        </div>
      ))}
      {hasMore && (
        <button className="btn" onClick={load} disabled={loading}>
          {loading ? "Loading…" : "Load more"}
        </button>
      )}
    </section>
  );
}
