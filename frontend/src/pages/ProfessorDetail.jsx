import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { api } from "../lib/api.js";
import {
  formatScore,
  scoreBucket,
  sourceChipClass,
  sentimentLabel,
} from "../lib/format.js";
import { useCompare } from "../lib/compareStore.jsx";

const COLORS = {
  positive: "#2ecc8f",
  neutral: "#f0c75e",
  negative: "#ff5c7a",
};

// Poll long enough for the background stats job to finish on slow RMP calls.
const POLL_INTERVAL_MS = 4000;
const POLL_MAX_ATTEMPTS = 45;

export default function ProfessorDetail() {
  const { id } = useParams();
  const [prof, setProf] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pollAttempts, setPollAttempts] = useState(0);
  const [pollGaveUp, setPollGaveUp] = useState(false);
  const { has, toggle, full } = useCompare();

  useEffect(() => {
    setLoading(true);
    setPollAttempts(0);
    setPollGaveUp(false);
    api
      .professor(id)
      .then(setProf)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  // Keep polling only for RMP-backed professors that still need stats/themes.
  const stats = prof?.stats || null;
  const analyzed = Boolean(stats && stats.review_count > 0);
  const hasThemes = Boolean(
    stats?.theme_counts && Object.keys(stats.theme_counts).length > 0,
  );
  const hasRmpRef = Boolean(
    prof &&
      typeof prof.external_ref === "string" &&
      prof.external_ref.startsWith("rmp:"),
  );
  const lazyEligible = Boolean(
    prof &&
      hasRmpRef &&
      (!analyzed || !hasThemes),
  );

  // Refresh the dashboard while the background analyzer is running.
  useEffect(() => {
    if (!prof || !lazyEligible || pollGaveUp) return;
    const handle = setTimeout(() => {
      api
        .professor(id)
        .then((next) => {
          setProf(next);
          setPollAttempts((n) => {
            const nextN = n + 1;
            const nextThemes = next.stats?.theme_counts || {};
            if (
              nextN >= POLL_MAX_ATTEMPTS &&
              (!next.stats || Object.keys(nextThemes).length === 0)
            ) {
              setPollGaveUp(true);
            }
            return nextN;
          });
        })
        .catch(() => {
          // Network blips shouldn't kill the loop; just count the attempt.
          setPollAttempts((n) => {
            const nextN = n + 1;
            if (nextN >= POLL_MAX_ATTEMPTS) setPollGaveUp(true);
            return nextN;
          });
        });
    }, POLL_INTERVAL_MS);
    return () => clearTimeout(handle);
  }, [id, prof, lazyEligible, pollAttempts, pollGaveUp]);

  if (loading) return <div className="spinner" />;
  if (error) return <div className="container empty">{error}</div>;
  if (!prof) return null;

  const sourceRating = prof.source_avg_rating;
  const sourceCount = prof.source_num_ratings || 0;

  // Use analyzed scores when present; otherwise show the RMP profile rating.
  const score = analyzed
    ? (stats.recommendation_score || 0)
    : (typeof sourceRating === "number" ? sourceRating * 20 : 0);
  const bucket = scoreBucket(score);
  const selected = has(prof.id);

  const sentimentData = !analyzed
    ? []
    : [
        { name: "Positive", value: stats.positive_count || 0, color: COLORS.positive },
        { name: "Neutral", value: stats.neutral_count || 0, color: COLORS.neutral },
        { name: "Negative", value: stats.negative_count || 0, color: COLORS.negative },
      ].filter((d) => d.value > 0);

  const themeData = !analyzed
    ? []
    : Object.entries(stats.theme_counts || {})
        .sort((a, b) => b[1] - a[1])
        .map(([name, count]) => ({ name, count }));

  return (
    <section className="container">
      <div className="detail-hero">
        <div>
          <Link
            to="/search"
            className="pill"
            style={{ display: "inline-block", marginBottom: 8 }}
          >
            ← Back to search
          </Link>
          <h1>{prof.name}</h1>
          <div className="muted">
            {prof.department?.name || "—"}
            {prof.institution ? ` · ${prof.institution}` : ""}
          </div>
          {prof.bio && (
            <p style={{ color: "var(--text-dim)", maxWidth: 620, marginTop: 14 }}>
              {prof.bio}
            </p>
          )}
          {prof.courses?.length > 0 && (
            <div className="pill-row" style={{ marginTop: 14 }}>
              {prof.courses.map((c) => (
                <span key={c.id} className="pill">
                  {c.code}
                </span>
              ))}
            </div>
          )}
          <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
            <button
              className={"btn " + (selected ? "btn-ghost active" : "btn-primary")}
              disabled={!selected && full}
              onClick={() => toggle(prof.id)}
            >
              {selected ? "✓ Added to compare" : full ? "Compare limit reached" : "+ Add to compare"}
            </button>
          </div>
        </div>
        <div className={"big-score"}>
          <div className="val">{formatScore(score)}</div>
          <div className="lbl">
            {analyzed ? "Recommendation" : "RMP rating"}
          </div>
          <div
            className={"pill " + bucket}
            style={{ marginTop: 10, fontSize: 10 }}
          >
            {analyzed
              ? bucket === "good"
                ? "Highly recommended"
                : bucket === "meh"
                  ? "Mixed reviews"
                  : "Not recommended"
              : sourceCount > 0
                ? `Based on ${sourceCount} RMP rating${sourceCount === 1 ? "" : "s"}`
                : lazyEligible
                  ? "Profile rating unavailable"
                  : "No reviews on RMP"}
          </div>
        </div>
      </div>

      {!analyzed && (
        <div
          className="card"
          style={{
            marginTop: 12,
            background: "var(--surface-2)",
            borderLeft: "3px solid var(--accent, #7c5cff)",
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          {lazyEligible && !pollGaveUp && (
            <div
              className="spinner"
              style={{ width: 18, height: 18, flexShrink: 0 }}
            />
          )}
          <div style={{ fontSize: 13, color: "var(--text-dim)" }}>
            {lazyEligible && !pollGaveUp ? (
              <>
                <strong style={{ color: "var(--text)" }}>
                  Computing aggregate dashboard…
                </strong>{" "}
                First visit to this professor — we&apos;re pulling their
                RateMyProfessors reviews and Reddit mentions, running
                VADER sentiment on both, and aggregating in the
                background. The charts and recommendation score will
                appear here automatically when it&apos;s done (usually
                10–30 seconds). Individual reviews below already include
                per-review sentiment.
              </>
            ) : lazyEligible && pollGaveUp ? (
              <>
                <strong style={{ color: "var(--text)" }}>
                  Analysis is taking longer than expected.
                </strong>{" "}
                The background job hasn&apos;t finished yet — RateMyProfessors
                may be rate-limiting us. Reload the page in a minute, or
                browse the live reviews below in the meantime.
              </>
            ) : (
              <>
                <strong style={{ color: "var(--text)" }}>
                  Aggregate dashboard unavailable.
                </strong>{" "}
                This professor has no RateMyProfessors reference to analyze.
                Showing the available profile information above.
              </>
            )}
          </div>
        </div>
      )}

      <div className="grid-2" style={{ marginTop: 12 }}>
        <div className="card">
          <h3>Overview</h3>
          {analyzed ? (
            <>
              <div className="kv"><span className="k">Reviews analyzed</span><span className="v">{stats.review_count || 0}</span></div>
              <div className="kv"><span className="k">Average sentiment (VADER)</span><span className="v">{(stats.avg_compound ?? 0).toFixed(3)}</span></div>
              <div className="kv"><span className="k">Positive</span><span className="v" style={{ color: COLORS.positive }}>{stats.positive_count || 0}</span></div>
              <div className="kv"><span className="k">Neutral</span><span className="v" style={{ color: COLORS.neutral }}>{stats.neutral_count || 0}</span></div>
              <div className="kv"><span className="k">Negative</span><span className="v" style={{ color: COLORS.negative }}>{stats.negative_count || 0}</span></div>
            </>
          ) : (
            <>
              <div className="kv"><span className="k">RMP average rating</span><span className="v">{typeof sourceRating === "number" ? `${sourceRating.toFixed(2)} / 5` : "—"}</span></div>
              <div className="kv"><span className="k">RMP rating count</span><span className="v">{sourceCount}</span></div>
              <div className="kv"><span className="k">Recommendation score</span><span className="v">{formatScore(score)}</span></div>
              <div className="kv"><span className="k">Sentiment analysis</span><span className="v" style={{ color: "var(--text-dim)" }}>not yet computed</span></div>
            </>
          )}
        </div>

        <div className="card">
          <h3>Sentiment distribution</h3>
          {sentimentData.length === 0 ? (
            <div className="empty" style={{ padding: 20 }}>
              {analyzed
                ? "No review data"
                : "Awaiting analysis pass — scroll down for live reviews."}
            </div>
          ) : (
            <div style={{ width: "100%", height: 220 }}>
              <ResponsiveContainer>
                <PieChart>
                  <Pie
                    data={sentimentData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={55}
                    outerRadius={85}
                    paddingAngle={2}
                  >
                    {sentimentData.map((d) => (
                      <Cell key={d.name} fill={d.color} stroke="transparent" />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: "var(--surface-2)",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      color: "var(--text)",
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
          <div style={{ display: "flex", gap: 14, justifyContent: "center", flexWrap: "wrap", marginTop: 8 }}>
            {sentimentData.map((d) => (
              <span
                key={d.name}
                style={{
                  fontSize: 12,
                  color: "var(--text-dim)",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <span style={{ width: 10, height: 10, borderRadius: 3, background: d.color, display: "inline-block" }} />
                {d.name} ({d.value})
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Theme mentions</h3>
        {themeData.length === 0 ? (
          <div className="empty" style={{ padding: 20 }}>
            {analyzed
              ? "No themes detected yet"
              : "Themes appear after the analyze pass runs on this professor."}
          </div>
        ) : (
          <div style={{ width: "100%", height: 260 }}>
            <ResponsiveContainer>
              <BarChart data={themeData} margin={{ top: 10, right: 16, left: -18, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fill: "var(--text-dim)", fontSize: 12 }}
                  axisLine={{ stroke: "var(--border)" }}
                  tickLine={false}
                />
                <YAxis
                  allowDecimals={false}
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
                <Bar dataKey="count" radius={[6, 6, 0, 0]} fill="url(#grad)" />
                <defs>
                  <linearGradient id="grad" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#7c5cff" />
                    <stop offset="100%" stopColor="#00d4ff" />
                  </linearGradient>
                </defs>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <SimilarProfessorsPanel professorId={prof.id} />

      <ReviewsSection professor={prof} />
    </section>
  );
}

// Similar-professor results come from the backend embedding index.
