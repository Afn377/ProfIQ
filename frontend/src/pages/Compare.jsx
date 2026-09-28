import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { api } from "../lib/api.js";
import { useCompare } from "../lib/compareStore.jsx";
import { scoreBucket } from "../lib/format.js";

// Compare is one table: professors across the top, measures down the side.
// The best value in each row is bold so the eye can scan for it.
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
        <div className="empty">
          <p className="empty-title">Nothing to compare yet.</p>
          <p>
            Pick two to four professors from{" "}
            <Link to="/search" className="section-link">
              Browse
            </Link>{" "}
            and they will line up here.
          </p>
        </div>
      </section>
    );
  }

  if (error) return <div className="container empty">{error}</div>;

  const themes = Array.from(
    new Set(profs.flatMap((p) => Object.keys(p.theme_counts || {}))),
  ).sort();

  const share = (p, theme) => {
    const count = p.theme_counts?.[theme] || 0;
    const reviews = p.review_count || 0;
    return reviews > 0 ? (count / reviews) * 100 : 0;
  };

  const maxOf = (values) => Math.max(...values);
  const scores = profs.map((p) => p.recommendation_score || 0);
  const reviews = profs.map((p) => p.review_count || 0);
  const sentiments = profs.map((p) => p.avg_compound || 0);

  const best = (value, values) =>
    profs.length > 1 && value === maxOf(values) ? " best" : "";

  return (
    <section className="section container">
      <div className="section-head">
        <div>
          <h2>Compare professors</h2>
          <div className="sub">
            Scores, review volume and how often each theme comes up. Theme
            figures are the share of that professor's reviews, so a professor
            with more reviews does not dominate.
          </div>
        </div>
      </div>

      <div className="compare-scroll">
        <table className="compare">
          <thead>
            <tr>
              <th scope="col" className="compare-label">
                <span className="visually-hidden">Measure</span>
              </th>
              {profs.map((p) => (
                <th scope="col" key={p.id} className="compare-prof">
                  <Link to={`/professors/${p.id}`} className="compare-name">
                    {p.name}
                  </Link>
                  <div className="compare-meta">
                    {p.department || "Department not listed"}
                  </div>
                  <button
                    type="button"
                    className="rank-compare"
                    onClick={() => toggle(p.id)}
                  >
                    Remove
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="compare-score-row">
              <th scope="row" className="compare-label">
                Recommendation score
              </th>
              {profs.map((p, i) => (
                <td
                  key={p.id}
                  className={
                    "num compare-score " +
                    scoreBucket(scores[i]) +
                    best(scores[i], scores)
                  }
                >
                  {Math.round(scores[i])}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row" className="compare-label">
                Reviews analyzed
              </th>
              {profs.map((p, i) => (
                <td key={p.id} className={"num" + best(reviews[i], reviews)}>
                  {reviews[i].toLocaleString()}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row" className="compare-label">
                Average sentiment
              </th>
              {profs.map((p, i) => (
                <td
                  key={p.id}
                  className={"num" + best(sentiments[i], sentiments)}
                >
                  {sentiments[i] > 0 ? "+" : ""}
                  {sentiments[i].toFixed(2)}
                </td>
              ))}
            </tr>
            {themes.length > 0 && (
              <tr className="compare-group">
                <th scope="row" colSpan={profs.length + 1}>
                  Share of reviews mentioning
                </th>
              </tr>
            )}
            {themes.map((theme) => {
              const shares = profs.map((p) => share(p, theme));
              return (
                <tr key={theme}>
                  <th scope="row" className="compare-label compare-theme">
                    {theme}
                  </th>
                  {profs.map((p, i) => (
                    <td key={p.id} className={"num" + best(shares[i], shares)}>
                      <span className="share-bar" aria-hidden="true">
                        <span
                          className="share-bar-fill"
                          style={{ width: `${shares[i]}%` }}
                        />
                      </span>
                      {Math.round(shares[i])}%
                      <span className="compare-count">
                        {" "}
                        ({p.theme_counts?.[theme] || 0})
                      </span>
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
