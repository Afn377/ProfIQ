import { Link } from "react-router-dom";
import SentimentBar from "./SentimentBar.jsx";
import { formatScore, scoreBucket, topThemes } from "../lib/format.js";
import { useCompare } from "../lib/compareStore.jsx";

export default function ProfessorCard({ prof }) {
  const { has, toggle, full } = useCompare();
  const selected = has(prof.id);

  const reviewCount = prof.review_count || 0;
  const analyzed = reviewCount > 0;
  const bucket = scoreBucket(prof.recommendation_score || 0);

  const onToggle = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!selected && full) return;
    toggle(prof.id);
  };

  const themes = topThemes(prof.theme_counts || {}, 3);

  return (
    <Link to={`/professors/${prof.id}`} className="prof-card">
      <button
        type="button"
        className={"compare-toggle" + (selected ? " active" : "")}
        onClick={onToggle}
        title={selected ? "Remove from compare" : full ? "Max 4 selected" : "Add to compare"}
        aria-label="Toggle compare"
      >
        {selected ? "✓" : "+"}
      </button>

      <div className="row">
        <div style={{ minWidth: 0 }}>
          <div className="name">{prof.name}</div>
          <div className="meta">
            {prof.department || "—"}
            {prof.institution ? ` · ${prof.institution}` : ""}
          </div>
        </div>
        {analyzed ? (
          <div className={"score-pill " + bucket}>
            {formatScore(prof.recommendation_score)}
            <small>/100</small>
          </div>
        ) : prof.source_avg_rating != null ? (
          <div className="score-pill unanalyzed" title="RateMyProfessors summary — not yet analyzed locally">
            {prof.source_avg_rating.toFixed(1)}
            <small>RMP</small>
          </div>
        ) : (
          <div className="score-pill unanalyzed">—</div>
        )}
      </div>

      {analyzed ? (
        <>
          <SentimentBar
            positive={prof.positive_count || 0}
            neutral={prof.neutral_count || 0}
            negative={prof.negative_count || 0}
          />
          {themes.length > 0 && (
            <div className="pill-row">
              {themes.map((t) => (
                <span key={t.name} className="pill accent">
                  {t.name} · {t.count}
                </span>
              ))}
            </div>
          )}
          <div className="prof-card-footer">
            <span>{reviewCount} reviews</span>
            <span>avg {((prof.avg_compound ?? 0) * 1).toFixed(2)}</span>
          </div>
        </>
      ) : (
        <div className="prof-card-footer unanalyzed-footer">
          {prof.source_num_ratings > 0 ? (
            <span>{prof.source_num_ratings.toLocaleString()} RMP ratings · click to analyze</span>
          ) : (
            <span>No reviews yet</span>
          )}
        </div>
      )}
    </Link>
  );
}
