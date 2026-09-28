import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../lib/api.js";
import {
  formatScore,
  scoreBucket,
  sentimentLabel,
} from "../lib/format.js";
import { useCompare } from "../lib/compareStore.jsx";
import SentimentBar from "../components/SentimentBar.jsx";

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
        { key: "positive", name: "Positive", value: stats.positive_count || 0 },
        { key: "neutral", name: "Neutral", value: stats.neutral_count || 0 },
        { key: "negative", name: "Negative", value: stats.negative_count || 0 },
      ].filter((d) => d.value > 0);

  const themeData = !analyzed
    ? []
    : Object.entries(stats.theme_counts || {})
        .sort((a, b) => b[1] - a[1])
        .map(([name, count]) => ({ name, count }));
  const themeMax = themeData.reduce((m, t) => Math.max(m, t.count), 0);

  const verdict = analyzed
    ? bucket === "good"
      ? "Highly recommended"
      : bucket === "meh"
        ? "Mixed reviews"
        : "Not recommended"
    : sourceCount > 0
      ? `Based on ${sourceCount.toLocaleString()} RMP rating${sourceCount === 1 ? "" : "s"}`
      : lazyEligible
        ? "Profile rating unavailable"
        : "No reviews on RMP";

  return (
    <section className="container report">
      <header className="report-head">
        <div className="report-title">
          <Link to="/search" className="back-link">
            Back to browse
          </Link>
          <h1>{prof.name}</h1>
          <p className="report-meta">
            {prof.department?.name || "Department not listed"}
            {prof.institution ? `, ${prof.institution}` : ""}
          </p>
          {prof.bio && <p className="report-bio">{prof.bio}</p>}
          {prof.courses?.length > 0 && (
            <p className="report-courses">
              Teaches {prof.courses.map((c) => c.code).join(", ")}
            </p>
          )}
          <button
            className={"btn " + (selected ? "btn-ghost" : "btn-primary")}
            disabled={!selected && full}
            onClick={() => toggle(prof.id)}
          >
            {selected
              ? "Remove from compare"
              : full
                ? "Compare is full"
                : "Add to compare"}
          </button>
        </div>
        <div className={"verdict " + (analyzed ? bucket : "unanalyzed")}>
          <div className="verdict-num num">
            {analyzed ? Math.round(score) : typeof sourceRating === "number" ? sourceRating.toFixed(1) : "\u2013"}
            <span className="verdict-max">
              {analyzed ? "out of 100" : "out of 5 on RMP"}
            </span>
          </div>
          <div className="verdict-label">{verdict}</div>
        </div>
      </header>

      {!analyzed && (
        <div className="notice">
          {lazyEligible && !pollGaveUp && <div className="spinner spinner-sm" />}
          <div className="notice-text">
            {lazyEligible && !pollGaveUp
              ? "First visit to this professor. Their RateMyProfessors reviews are being fetched and scored in the background. The score and charts appear here on their own, usually within 30 seconds. The reviews below already carry per-review sentiment."
              : lazyEligible && pollGaveUp
                ? "The analysis has not finished. RateMyProfessors may be rate limiting requests. Reload in a minute, or read the reviews below meanwhile."
                : "Nothing to analyze. This professor has no RateMyProfessors reference, so only the profile above is available."}
          </div>
        </div>
      )}

      <div className="report-grid">
        <section className="report-section">
          <h2>Overview</h2>
          <dl className="facts">
            {analyzed ? (
              <>
                <div className="fact"><dt>Reviews analyzed</dt><dd className="num">{(stats.review_count || 0).toLocaleString()}</dd></div>
                <div className="fact"><dt>Average sentiment</dt><dd className="num">{(stats.avg_compound ?? 0).toFixed(3)}</dd></div>
                <div className="fact"><dt>Positive</dt><dd className="num positive">{stats.positive_count || 0}</dd></div>
                <div className="fact"><dt>Neutral</dt><dd className="num neutral">{stats.neutral_count || 0}</dd></div>
                <div className="fact"><dt>Negative</dt><dd className="num negative">{stats.negative_count || 0}</dd></div>
              </>
            ) : (
              <>
                <div className="fact"><dt>RMP average rating</dt><dd className="num">{typeof sourceRating === "number" ? `${sourceRating.toFixed(2)} / 5` : "\u2013"}</dd></div>
                <div className="fact"><dt>RMP ratings</dt><dd className="num">{sourceCount.toLocaleString()}</dd></div>
                <div className="fact"><dt>Recommendation score</dt><dd className="num">{formatScore(score)}</dd></div>
                <div className="fact"><dt>Sentiment analysis</dt><dd>Not yet run</dd></div>
              </>
            )}
          </dl>
          <p className="report-note">
            Sentiment comes from VADER with a lexicon tuned to professor reviews.
          </p>
        </section>

        <section className="report-section">
          <h2>Sentiment</h2>
          {sentimentData.length === 0 ? (
            <p className="report-note">
              {analyzed
                ? "No review data."
                : "Appears after the analysis pass. The reviews below are live."}
            </p>
          ) : (
            <>
              <SentimentBar
                positive={stats.positive_count || 0}
                neutral={stats.neutral_count || 0}
                negative={stats.negative_count || 0}
                tall
              />
              <ul className="legend">
                {sentimentData.map((d) => (
                  <li key={d.key} className={"legend-item " + d.key}>
                    <span className="legend-swatch" aria-hidden="true" />
                    {d.name}
                    <span className="num">
                      {d.value} ({Math.round((d.value / (stats.review_count || 1)) * 100)}%)
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>

      <section className="report-section">
        <h2>Themes mentioned</h2>
        {themeData.length === 0 ? (
          <p className="report-note">
            {analyzed
              ? "No themes detected yet."
              : "Themes appear after the analysis pass runs on this professor."}
          </p>
        ) : (
          <ol className="theme-bars">
            {themeData.map((t) => (
              <li key={t.name} className="theme-row">
                <span className="theme-name">{t.name}</span>
                <span className="theme-track">
                  <span
                    className="theme-fill"
                    style={{ width: `${(t.count / themeMax) * 100}%` }}
                  />
                </span>
                <span className="theme-count num">{t.count}</span>
              </li>
            ))}
          </ol>
        )}
      </section>

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
      <section className="report-section">
        <h2>Similar professors</h2>
        <div className="spinner" />
        {warming && (
          <p className="report-note">
            Encoding this professor with MiniLM. This can take up to a minute
            if the server has been idle.
          </p>
        )}
      </section>
    );
  }

  if (error) return null;
  if (!data || data.available === false) return null;

  const results = data.results || [];
  if (results.length === 0) {
    return (
      <section className="report-section">
        <h2>Similar professors</h2>
        <p className="report-note">
          No other similar professors have been analyzed at this university
          yet.
        </p>
      </section>
    );
  }

  const matchLevel = data?.match_level || "department";
  const src = data?.source || {};
  const scopeLine =
    matchLevel === "department" && src.institution && src.department
      ? `Closest by review content in ${src.department} at ${src.institution}.`
      : matchLevel === "institution" && src.institution
        ? `Closest by review content at ${src.institution}.`
        : matchLevel === "global"
          ? src.institution
            ? `No matches at ${src.institution} yet, so these are the closest anywhere.`
            : "Closest by review content anywhere."
          : "Closest by review content.";

  return (
    <section className="report-section">
      <h2>Similar professors</h2>
      <p className="report-note">
        {scopeLine} Similarity is the cosine between MiniLM sentence embeddings
        of their reviews.
      </p>
      <ol className="similar-list">
        {results.map((r) => (
          <li key={r.id} className="similar-row">
            <div className="similar-main">
              <Link to={`/professors/${r.id}`} className="similar-name">
                {r.name}
              </Link>
              <div className="similar-meta">
                {r.department || "Department not listed"}
                {r.institution ? `, ${r.institution}` : ""}
                {typeof r.review_count === "number" && r.review_count > 0
                  ? `, ${r.review_count} reviews`
                  : ""}
              </div>
            </div>
            <div className="similar-score">
              <span className="num">{(r.score ?? 0).toFixed(2)}</span>
              <span className="similar-score-label">similarity</span>
            </div>
          </li>
        ))}
      </ol>
    </section>
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
      <section className="report-section">
        <h2>
          Reviews <span className="count num">{fallbackReviews.length}</span>
        </h2>
        {fallbackReviews.length === 0 && (
          <p className="report-note">No reviews yet.</p>
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
      </section>
    );
  }

  return (
    <section className="report-section">
      <h2>
        Reviews{" "}
        <span className="count num">
          {reviews.length}
          {headingCount > reviews.length ? ` of ${headingCount}` : ""}
        </span>
      </h2>
      <p className="report-note">
        Fetched live from RateMyProfessors and scored as they load. Nothing
        is stored. Scroll for more.
      </p>

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

      {loading && <div className="spinner" />}

      {!loading && !hasMore && reviews.length > 0 && (
        <p className="report-note">That is every review.</p>
      )}

      {!loading && reviews.length === 0 && initialized && !error && (
        <p className="report-note">No reviews available.</p>
      )}

      {error && (
        <div className="notice notice-error">
          <div className="notice-text">Reviews stopped loading: {error}</div>
          {hasMore && (
            <button className="btn btn-ghost" onClick={fetchNext}>
              Try again
            </button>
          )}
        </div>
      )}

      {hasMore && !error && <div ref={sentinelRef} className="sentinel" />}
    </section>
  );
}

function ReviewItem({ source, rating, course, text, sentiment, sourceUrl }) {
  const label = sentimentLabel(sentiment?.label);
  return (
    <article className="review">
      <p className="review-body">{text}</p>
      <div className="review-foot">
        <span className={"review-sentiment " + label}>
          <span className="legend-swatch" aria-hidden="true" />
          <span className="word">{label}</span>
          <span className="num">{(sentiment?.compound ?? 0).toFixed(2)}</span>
        </span>
        {sentiment?.ml_label && (
          <span
            className={"review-sentiment " + sentimentLabel(sentiment.ml_label)}
            title={`Prediction from the trained ${sentiment.ml_model || "ML"} classifier`}
          >
            classifier says {sentiment.ml_label}
            {typeof sentiment.ml_confidence === "number" && (
              <span className="num">{(sentiment.ml_confidence * 100).toFixed(0)}%</span>
            )}
          </span>
        )}
        {course && <span>{course}</span>}
        {rating != null && (
          <span>
            Rated <span className="num">{Number(rating).toFixed(1)}</span>
          </span>
        )}
        {sentiment?.themes?.length > 0 && (
          <span>Themes: {sentiment.themes.join(", ")}</span>
        )}
        {sourceUrl && (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="review-source"
          >
            Source
            {source && source !== "rmp" ? ` (${source})` : ""}
          </a>
        )}
      </div>
    </article>
  );
}
