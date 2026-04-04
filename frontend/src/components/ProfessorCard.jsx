function bucket(score) {
  if (score === null || score === undefined) return "none";
  if (score >= 65) return "good";
  if (score >= 50) return "meh";
  return "bad";
}

export default function ProfessorCard({ prof }) {
  const score = prof.recommendation_score;
  return (
    <div className="card">
      <h3>{prof.name}</h3>
      <div className="sub">
        {prof.department ?? "No department"} · {prof.institution}
      </div>
      <div className={`score ${bucket(score)}`}>
        {score === null ? "Not analyzed" : `${score.toFixed(1)} / 100`}
        {prof.review_count > 0 && ` · ${prof.review_count} reviews`}
      </div>
    </div>
  );
}
