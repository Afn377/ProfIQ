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
function SimilarProfessorsPanel({ professorId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [warming, setWarming] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setWarming(false);
    setError(null);

    // Try the existing index first; warm up on demand only if needed.
    api
      .similarProfessors(professorId, { k: 5, warm: 0, scope: "department" })
      .then((res) => {
        if (cancelled) return;
        setData(res);
        const empty = !res?.results?.length;
        if (empty && res?.available !== false) {
          setWarming(true);
          return api.similarProfessors(professorId, {
            k: 5, warm: 1, scope: "department",
          });
        }
        return null;
      })
      .then((res) => {
        if (cancelled || !res) return;
        setData(res);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e.message || "Could not load similar professors");
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
        setWarming(false);
      });
    return () => {
      cancelled = true;
    };
  }, [professorId]);

  if (loading) {
    return (
      <div className="card" style={{ marginTop: 16 }}>
        <h3>Similar professors</h3>
        <div className="empty" style={{ padding: 20, textAlign: "center" }}>
          <div className="spinner" />
          {warming && (
            <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>
              Encoding this professor on the fly with MiniLM…
            </div>
          )}
        </div>
      </div>
    );
  }

  if (error) return null;
  if (!data || data.available === false) return null;

  const results = data.results || [];
  if (results.length === 0) {
    return (
      <div className="card" style={{ marginTop: 16 }}>
        <h3>Similar professors</h3>
        <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
          Powered by MiniLM sentence embeddings + cosine KNN.
        </div>
        <div className="empty" style={{ padding: 20 }}>
          We couldn&apos;t find similar professors for this one yet — either
          they have no public reviews to embed, or RateMyProfessors is
          unreachable right now.
        </div>
      </div>
    );
  }

  const matchLevel = data?.match_level || "department";
  const src = data?.source || {};
  const scopeLine = (() => {
    if (matchLevel === "department" && src.institution && src.department) {
      return `In ${src.department} at ${src.institution}.`;
    }
    if (matchLevel === "institution" && src.institution) {
      return `No same-department matches in the index — showing closest at ${src.institution}.`;
    }
    if (matchLevel === "global") {
      return src.institution
        ? `No matches at ${src.institution} yet — showing closest globally.`
        : "Closest globally.";
    }
    return null;
  })();
  const badgeStyle = {
    department: { bg: "rgba(46, 204, 143, 0.15)", color: "#2ecc8f" },
    institution: { bg: "rgba(240, 199, 94, 0.18)", color: "#f0c75e" },
    global: { bg: "rgba(124, 92, 255, 0.18)", color: "#a18bff" },
  }[matchLevel] || { bg: "rgba(255,255,255,0.08)", color: "var(--muted)" };
  const badgeLabel = {
    department: "Same dept",
    institution: "Same university",
    global: "Global",
  }[matchLevel] || matchLevel;

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
        <h3 style={{ margin: 0 }}>Similar professors</h3>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            padding: "2px 8px",
            borderRadius: 999,
            background: badgeStyle.bg,
            color: badgeStyle.color,
            textTransform: "uppercase",
            letterSpacing: 0.4,
          }}
        >
          {badgeLabel}
        </span>
      </div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
        {scopeLine && <div style={{ marginBottom: 4 }}>{scopeLine}</div>}
        Top {results.length} by review-content similarity. Powered by
        MiniLM sentence embeddings + cosine KNN
        {data.model ? ` (${data.model})` : ""}.
      </div>
      <div style={{ display: "grid", gap: 10 }}>
        {results.map((r) => {
          const pct = Math.round(((r.score ?? 0) + 1) * 50); // -1..1 -> 0..100
          return (
            <Link
              key={r.id}
              to={`/professors/${r.id}`}
              className="card"
              style={{
                display: "grid",
                gridTemplateColumns: "1fr auto",
                alignItems: "center",
                gap: 12,
                margin: 0,
                padding: 12,
                background: "var(--surface-2)",
                textDecoration: "none",
              }}
            >
              <div>
                <div style={{ fontWeight: 600, color: "var(--text)" }}>
                  {r.name}
                </div>
                <div className="muted" style={{ fontSize: 12 }}>
                  {r.department || "—"}
                  {r.institution ? ` · ${r.institution}` : ""}
                  {typeof r.review_count === "number" && r.review_count > 0
                    ? ` · ${r.review_count} reviews`
                    : ""}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div
                  style={{
                    fontSize: 18,
                    fontWeight: 700,
                    color: "var(--accent, #7c5cff)",
                  }}
                >
                  {pct}%
                </div>
                <div className="muted" style={{ fontSize: 11 }}>
                  similarity
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

// Review feed: RMP-backed professors use live pages; seed data uses embedded reviews.
function ReviewsSection({ professor }) {
  const liveCapable = Boolean(professor.external_ref);
  const fallbackReviews = professor.reviews || [];

  const [reviews, setReviews] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [error, setError] = useState(null);

  const sentinelRef = useRef(null);
  const inFlight = useRef(false);

  const fetchNext = useCallback(async () => {
    if (!liveCapable || inFlight.current || !hasMore) return;
    inFlight.current = true;
    setLoading(true);
    setError(null);
    try {
      const data = await api.professorReviews(professor.id, {
        cursor,
        limit: 20,
      });
      setReviews((prev) => [...prev, ...(data.results || [])]);
      setCursor(data.next_cursor);
      setHasMore(Boolean(data.has_more));
    } catch (e) {
      setError(e.message || "Could not load reviews");
      setHasMore(false);
    } finally {
      setLoading(false);
      setInitialized(true);
      inFlight.current = false;
    }
  }, [liveCapable, professor.id, cursor, hasMore]);

  useEffect(() => {
    setReviews([]);
    setCursor(null);
    setHasMore(true);
    setInitialized(false);
    setError(null);
  }, [professor.id]);

  useEffect(() => {
    if (!liveCapable || initialized || reviews.length > 0) return;
    fetchNext();
  }, [liveCapable, initialized, reviews.length, fetchNext]);

  useEffect(() => {
    if (!liveCapable || !sentinelRef.current || !hasMore) return;
    const el = sentinelRef.current;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) fetchNext();
      },
      { rootMargin: "400px 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [liveCapable, hasMore, fetchNext]);

  const headingCount = useMemo(() => {
    if (!liveCapable) return fallbackReviews.length;
    if (professor.stats?.review_count) return professor.stats.review_count;
    return reviews.length;
  }, [liveCapable, fallbackReviews.length, professor.stats, reviews.length]);

  if (!liveCapable) {
    return (
      <div className="card" style={{ marginTop: 16 }}>
        <h3>Reviews ({fallbackReviews.length})</h3>
        {fallbackReviews.length === 0 && (
          <div className="empty">No reviews yet.</div>
        )}
        {fallbackReviews.map((r) => (
          <ReviewItem
            key={r.id}
            source={r.source}
            rating={r.rating}
            course={r.course}
            text={r.text}
            sentiment={r.sentiment}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3>
        Reviews{" "}
        <span style={{ color: "var(--text-dim)", fontWeight: 400, fontSize: 13 }}>
          ({reviews.length}
          {headingCount > reviews.length ? ` of ${headingCount}` : ""} loaded)
        </span>
      </h3>
      <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
        Live from RateMyProfessors and Reddit, analyzed on the fly.
        Reddit comments appear at the top of the first page; scroll for
        more RMP reviews — nothing is persisted.
      </div>

      {reviews.map((r, idx) => (
        <ReviewItem
          key={`${r.source_url || idx}-${idx}`}
          source={r.source || "rmp"}
          rating={r.rating}
          course={r.course}
          text={r.text}
          sentiment={r.sentiment}
          sourceUrl={r.source_url}
        />
      ))}

      {loading && (
        <div style={{ padding: "14px 0", textAlign: "center" }}>
          <div className="spinner" />
        </div>
      )}

      {!loading && !hasMore && reviews.length > 0 && (
        <div
          className="muted"
          style={{ textAlign: "center", padding: "14px 0", fontSize: 12 }}
        >
          End of reviews.
        </div>
      )}

      {!loading && reviews.length === 0 && initialized && !error && (
        <div className="empty">No reviews available.</div>
      )}

      {error && (
        <div
          className="empty"
          style={{ color: "var(--neg)", padding: 16 }}
        >
          {error}
          {hasMore && (
            <button
              className="btn btn-ghost"
              style={{ marginLeft: 10 }}
              onClick={fetchNext}
            >
              Retry
            </button>
          )}
        </div>
      )}

      {hasMore && !error && <div ref={sentinelRef} style={{ height: 1 }} />}
    </div>
  );
}

function ReviewItem({ source, rating, course, text, sentiment, sourceUrl }) {
  return (
    <div className="review">
      <div className="review-head">
        <span className={"source-chip " + sourceChipClass(source)}>
          {source}
        </span>
        {course && <span className="pill">{course}</span>}
        {rating != null && (
          <span className="pill">★ {Number(rating).toFixed(1)}</span>
        )}
        <span
          className={"sentiment-chip " + sentimentLabel(sentiment?.label)}
          title="Rule-based VADER sentiment (compound score)"
        >
          VADER · {sentiment?.label || "neutral"} ·{" "}
          {(sentiment?.compound ?? 0).toFixed(2)}
        </span>
        {sentiment?.ml_label && (
          <span
            className={"sentiment-chip " + sentimentLabel(sentiment.ml_label)}
            title={`Trained ${sentiment.ml_model || "ML"} classifier prediction`}
            style={{ opacity: 0.9, borderStyle: "dashed" }}
          >
            ML · {sentiment.ml_label}
            {typeof sentiment.ml_confidence === "number"
              ? ` · ${(sentiment.ml_confidence * 100).toFixed(0)}%`
              : ""}
          </span>
        )}
        {sourceUrl && (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="pill"
            style={{ marginLeft: "auto" }}
          >
            source ↗
          </a>
        )}
      </div>
      <div className="review-body">{text}</div>
      {sentiment?.themes?.length > 0 && (
        <div className="review-themes">
          {sentiment.themes.map((t) => (
            <span key={t} className="pill accent">
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
