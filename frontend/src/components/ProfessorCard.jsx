function bucket(score) {
  if (score === null || score === undefined) return "none";
  if (score >= 65) return "good";
  if (score >= 50) return "meh";
  return "bad";
}

// `selected` is decided by the parent (a set of ids), never by the card:
// state about *which* items are chosen must be tied to an identity, not a slot.
export default function ProfessorCard({ prof, selected = false, onToggle }) {
  const score = prof.recommendation_score;
  return (
    <div className={`card${selected ? " selected" : ""}`}>
      <h3>{prof.name}</h3>
      <div className="sub">
        {prof.department ?? "No department"} · {prof.institution}
      </div>
      <div className={`score ${bucket(score)}`}>
        {score === null ? "Not analyzed" : `${score.toFixed(1)} / 100`}
        {prof.review_count > 0 && ` · ${prof.review_count} reviews`}
      </div>
      {onToggle && (
        <button className="btn" onClick={onToggle}>
          {selected ? "✓ Selected" : "Select to compare"}
        </button>
      )}
    </div>
  );
}
