export default function SentimentBar({ positive = 0, neutral = 0, negative = 0 }) {
  const total = positive + neutral + negative;
  if (total === 0) {
    return <div className="sentiment-bar" title="No reviews yet" />;
  }
  const p = (positive / total) * 100;
  const n = (neutral / total) * 100;
  const g = (negative / total) * 100;
  return (
    <div
      className="sentiment-bar"
      title={`${positive} positive · ${neutral} neutral · ${negative} negative`}
    >
      {p > 0 && <div className="pos" style={{ width: `${p}%` }} />}
      {n > 0 && <div className="neu" style={{ width: `${n}%` }} />}
      {g > 0 && <div className="neg" style={{ width: `${g}%` }} />}
    </div>
  );
}
