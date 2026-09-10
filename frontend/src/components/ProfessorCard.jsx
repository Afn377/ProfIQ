import { Link } from "react-router-dom";
import SentimentBar from "./SentimentBar.jsx";
import ScoreRing from "./ScoreRing.jsx";
import { scoreBucket, topThemes } from "../lib/format.js";
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
          <ScoreRing
            value={prof.recommendation_score}
            max={100}
            tier={bucket}
            label="/100"
            size={58}
          />
        ) : prof.source_avg_rating != null ? (
          <ScoreRing
            value={prof.source_avg_rating}
            max={5}
            tier="unanalyzed"
            label="RMP"
            size={58}
            title="RateMyProfessors summary — not yet analyzed locally"
          />
        ) : (
          <ScoreRing size={58} />
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
