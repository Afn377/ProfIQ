import { useEffect, useId, useRef, useState } from "react";

function Field({ label, hint, error, input }) {
  return (
    <label style={{ display: "grid", gap: 6 }}>
      <span style={{ color: "var(--text)", fontSize: 13, fontWeight: 600 }}>
        {label}
      </span>
      {input}
      {hint && !error && (
        <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{hint}</span>
      )}
      {error && (
        <span style={{ color: "#ff9aa2", fontSize: 12 }}>{error}</span>
      )}
    </label>
  );
}

function inputStyle(hasError) {
  return {
    background: "var(--surface-2)",
    color: "var(--text)",
    border: `1px solid ${hasError ? "rgba(255, 120, 120, 0.55)" : "var(--border)"}`,
    borderRadius: 10,
    padding: "10px 12px",
    fontSize: 14,
    width: "100%",
    boxSizing: "border-box",
  };
}
