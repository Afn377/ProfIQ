// Thin SVG progress ring that visually encodes a score. Styling lives in
// index.css; size is a prop so call sites can go compact (cards) or large
// (detail page hero).
export default function ScoreRing({
  value = null,
  max = 100,
  tier = "unanalyzed",
  label,
  size = 58,
  title,
}) {
  const hasValue = typeof value === "number" && Number.isFinite(value);
  const fraction =
    hasValue && max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;

  const strokeWidth = Math.max(4, Math.round(size * 0.1));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - fraction);
  const center = size / 2;
  // Usable width inside the ring stroke — the hard budget for centered text.
  // Derived from `size` so every call site scales safely on its own.
  const innerDiameter = size - strokeWidth * 2;

  // The 0-5 RMP scale keeps one decimal ("4.7" is meaningful); the 0-100
  // recommendation scale is rendered whole ("100" fits where "100.0" cannot).
  const display = !hasValue
    ? "—"
    : max <= 5
      ? Number(value).toFixed(1)
      : String(Math.round(value));

  // Scale off the inner diameter (not raw size) so text stays clear of the
  // ring stroke at any size.
  const numFontSize = Math.max(9, Math.round(innerDiameter * 0.28));
  const subFontSize = Math.max(7, Math.round(innerDiameter * 0.16));
  const ariaLabel = hasValue
    ? `${display}${label ? ` ${label}` : ""}`
    : "No score";

  return (
    <div className={"score-ring " + tier} title={title}>
      <svg
        viewBox={`0 0 ${size} ${size}`}
        width={size}
        height={size}
        role="img"
        aria-label={ariaLabel}
      >
        <circle
          className="ring-track"
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
        />
        <circle
          className="ring-value"
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
        />
      </svg>
      <div className="score-ring-num" style={{ fontSize: numFontSize }}>
        {display}
        {label ? (
          <span className="score-ring-sub" style={{ fontSize: subFontSize }}>
            {label}
          </span>
        ) : null}
      </div>
    </div>
  );
}
