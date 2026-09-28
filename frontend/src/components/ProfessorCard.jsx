import { Link } from "react-router-dom";
import { scoreBucket } from "../lib/format.js";
import { useCompare } from "../lib/compareStore.jsx";

// A directory entry for one professor. The list endpoints only send the
// score, review count and average sentiment, so that is all this shows.
export default function ProfessorCard({ prof }) {
  const { has, toggle, full } = useCompare();
  const selected = has(prof.id);

  const reviewCount = prof.review_count || 0;
  const analyzed = reviewCount > 0;
  const score = prof.recommendation_score ?? 0;

  const onToggle = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!selected && full) return;
    toggle(prof.id);
  };

  return (
    <article className="entry">
      <div className="entry-head">
        <div className="entry-main">
          <Link to={`/professors/${prof.id}`} className="entry-name">
            {prof.name}
          </Link>
          <div className="entry-meta">
            {prof.department || "Department not listed"}
          </div>
        </div>
        {analyzed ? (
          <span className={"entry-score num " + scoreBucket(score)}>
            {Math.round(score)}
          </span>
        ) : prof.source_avg_rating != null ? (
          <span
            className="entry-score num unanalyzed"
            title="RateMyProfessors average, not yet analyzed here"
          >
            {Number(prof.source_avg_rating).toFixed(1)}
            <small>/5</small>
          </span>
        ) : (
          <span className="entry-score num unanalyzed">&ndash;</span>
        )}
      </div>
      <div className="entry-foot">
        {analyzed ? (
          <span>
            {reviewCount.toLocaleString()} reviews, sentiment{" "}
            {prof.avg_compound > 0 ? "+" : ""}
            {(prof.avg_compound ?? 0).toFixed(2)}
          </span>
        ) : prof.source_num_ratings > 0 ? (
          <span>
            {prof.source_num_ratings.toLocaleString()} ratings on RMP, open to
            analyze
          </span>
        ) : (
          <span>No reviews yet</span>
        )}
        <button
          type="button"
          className={"rank-compare" + (selected ? " active" : "")}
          onClick={onToggle}
          disabled={!selected && full}
        >
          {selected ? "In compare" : "Compare"}
        </button>
      </div>
    </article>
  );
}
