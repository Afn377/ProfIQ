import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
  Legend,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { api } from "../lib/api.js";
import { useCompare } from "../lib/compareStore.jsx";
import { formatScore, scoreBucket } from "../lib/format.js";

const LINE_COLORS = ["#7c5cff", "#00d4ff", "#2ecc8f", "#f0c75e"];

export default function Compare() {
  const [params] = useSearchParams();
  const { ids: ctxIds, toggle } = useCompare();
  const urlIds = (params.get("ids") || "")
    .split(",")
    .map((x) => parseInt(x, 10))
    .filter(Boolean);
  const ids = urlIds.length > 0 ? urlIds : ctxIds;

  const [profs, setProfs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (ids.length === 0) {
      setProfs([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .compare(ids)
      .then(setProfs)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [ids.join(",")]);

  if (loading) return <div className="spinner" />;

  if (ids.length === 0) {
    return (
      <section className="section container">
        <div className="empty" style={{ padding: 80 }}>
          <h2 style={{ color: "var(--text)" }}>No professors selected</h2>
          <p>
            Pick 2–4 professors to compare.{" "}
            <Link to="/search" style={{ color: "var(--accent-2)" }}>
              Browse professors →
            </Link>
          </p>
        </div>
      </section>
    );
  }

  if (error) return <div className="container empty">{error}</div>;

  // Build radar data: unify all themes across compared professors.
  const themeSet = new Set();
  profs.forEach((p) => {
    Object.keys(p.theme_counts || {}).forEach((k) => themeSet.add(k));
  });
  const themes = Array.from(themeSet).sort();

  const radarData = themes.map((theme) => {
    const row = { theme };
    profs.forEach((p) => {
      const count = p.theme_counts?.[theme] || 0;
      const reviews = p.review_count || 0;
      row[p.name] = reviews > 0 ? Number(((count / reviews) * 100).toFixed(1)) : 0;
      row[`${p.name}__count`] = count;
    });
    return row;
  });

  const scoreData = profs.map((p) => ({
    name: p.name,
    score: p.recommendation_score,
    reviews: p.review_count,
  }));

  return (
    <section className="section container">
      <div className="section-head">
        <div>
          <h2>Compare professors</h2>
          <div className="sub">
            Side-by-side recommendation scores, review volume, and topic breakdown.
          </div>
        </div>
      </div>

      <div className="prof-grid" style={{ marginBottom: 20 }}>
        {profs.map((p) => {
          const bucket = scoreBucket(p.recommendation_score || 0);
          return (
            <div key={p.id} className="card" style={{ padding: 18 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <div style={{ minWidth: 0 }}>
                  <Link to={`/professors/${p.id}`} className="name" style={{ fontWeight: 700 }}>
                    {p.name}
                  </Link>
                  <div className="meta" style={{ color: "var(--text-muted)", fontSize: 13 }}>
                    {p.department || "—"}
                  </div>
                </div>
                <div className={"score-pill " + bucket}>
                  {formatScore(p.recommendation_score)}
                  <small>/100</small>
                </div>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: "var(--text-dim)", marginTop: 12 }}>
                <span>{p.review_count} reviews</span>
                <span>avg {(p.avg_compound || 0).toFixed(2)}</span>
              </div>
              <button
                className="btn btn-ghost"
                style={{ marginTop: 12, width: "100%" }}
                onClick={() => toggle(p.id)}
              >
                Remove
              </button>
            </div>
          );
        })}
      </div>

      <div className="grid-2">
        <div className="card">
          <h3>Recommendation score</h3>
          <div style={{ width: "100%", height: 260 }}>
            <ResponsiveContainer>
              <BarChart data={scoreData} margin={{ top: 10, right: 16, left: -18, bottom: 20 }}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fill: "var(--text-dim)", fontSize: 11 }}
                  axisLine={{ stroke: "var(--border)" }}
                  tickLine={false}
                  interval={0}
                  angle={-15}
                  textAnchor="end"
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fill: "var(--text-dim)", fontSize: 12 }}
                  axisLine={{ stroke: "var(--border)" }}
                  tickLine={false}
                />
                <Tooltip
                  cursor={{ fill: "rgba(124,92,255,0.08)" }}
                  contentStyle={{
                    background: "var(--surface-2)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    color: "var(--text)",
                  }}
                />
                <Bar dataKey="score" radius={[6, 6, 0, 0]} fill="url(#compareGrad)" />
                <defs>
                  <linearGradient id="compareGrad" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#7c5cff" />
                    <stop offset="100%" stopColor="#00d4ff" />
                  </linearGradient>
                </defs>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h3>Theme breakdown</h3>
          {radarData.length > 0 && (
            <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
              Normalized as percentage of analyzed reviews, so professors with
              more reviews do not dominate the chart.
            </div>
          )}
          {radarData.length === 0 ? (
            <div className="empty" style={{ padding: 20 }}>No themes detected</div>
          ) : (
            <div style={{ width: "100%", height: 300 }}>
              <ResponsiveContainer>
                <RadarChart data={radarData} outerRadius="78%">
                  <PolarGrid stroke="var(--border)" />
                  <PolarAngleAxis
                    dataKey="theme"
                    tick={{ fill: "var(--text-dim)", fontSize: 11 }}
                  />
                  <PolarRadiusAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
                  {profs.map((p, i) => (
                    <Radar
                      key={p.id}
                      name={p.name}
                      dataKey={p.name}
                      stroke={LINE_COLORS[i % LINE_COLORS.length]}
                      fill={LINE_COLORS[i % LINE_COLORS.length]}
                      fillOpacity={0.15}
                    />
                  ))}
                  <Tooltip
                    formatter={(value, name, item) => [
                      `${value}% (${item.payload[`${name}__count`] || 0} mentions)`,
                      name,
                    ]}
                    contentStyle={{
                      background: "var(--surface-2)",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      color: "var(--text)",
                    }}
                  />
                  <Legend wrapperStyle={{ color: "var(--text-dim)", fontSize: 12 }} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
