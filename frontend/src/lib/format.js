export function scoreBucket(score) {
  if (score >= 65) return "good";
  if (score >= 50) return "meh";
  return "bad";
}

export function formatScore(score) {
  if (score === null || score === undefined) return "—";
  return Number(score).toFixed(1);
}

export function sourceChipClass(source) {
  if (!source) return "";
  const s = source.toLowerCase();
  if (s.includes("reddit")) return "reddit";
  if (s.includes("rate")) return "rmp";
  return "";
}

export function sentimentLabel(label) {
  if (!label) return "neutral";
  return label.toLowerCase();
}

export function topThemes(themeCounts = {}, limit = 3) {
  return Object.entries(themeCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([name, count]) => ({ name, count }));
}
