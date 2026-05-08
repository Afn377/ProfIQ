import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";

// Form used when a searched professor is missing from the local index.
export default function AddProfessorModal({
  open,
  onClose,
  defaultName = "",
  defaultInstitution = "",
  departments = [],
  schoolOptions = [],
  onSchoolInput = null,
}) {
  const navigate = useNavigate();
  const nameRef = useRef(null);
  const datalistId = useId();

  const [name, setName] = useState(defaultName);
  const [institution, setInstitution] = useState(defaultInstitution);
  const [department, setDepartment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState({});
  const [topError, setTopError] = useState("");

  // Refill fields when the modal opens from a new search.
  useEffect(() => {
    if (!open) return;
    setName(defaultName);
    setInstitution(defaultInstitution);
    setDepartment("");
    setErrors({});
    setTopError("");
    setSubmitting(false);
    // Put the cursor in the first field for quick entry.
    queueMicrotask(() => nameRef.current?.focus());
  }, [open, defaultName, defaultInstitution]);

  // Basic modal behavior: Escape closes it and the page behind it stays still.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  const handleSchoolChange = (value) => {
    setInstitution(value);
    onSchoolInput?.(value);
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setErrors({});
    setTopError("");

    const trimmedName = name.trim();
    const trimmedSchool = institution.trim();
    if (!trimmedName || !trimmedSchool) {
      setErrors({
        ...(trimmedName ? {} : { name: ["Please enter the professor's name."] }),
        ...(trimmedSchool ? {} : { institution: ["Please enter the school."] }),
      });
      return;
    }

    setSubmitting(true);
    try {
      const result = await api.createProfessor({
        name: trimmedName,
        institution: trimmedSchool,
        department: department || null,
      });
      // Created and deduped submissions both return a professor id.
      onClose?.();
      navigate(`/professors/${result.id}`);
    } catch (err) {
      if (err.payload && typeof err.payload === "object") {
        // Field errors stay beside inputs; general errors go in the banner.
        const { non_field_errors, detail, ...fields } = err.payload;
        if (non_field_errors) setTopError(non_field_errors.join(" "));
        else if (detail) setTopError(detail);
        else if (err.status === 429) setTopError("Too many submissions. Try again in a few minutes.");
        setErrors(fields);
      } else {
        setTopError(err.message || "Could not submit. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const fieldError = (key) =>
    Array.isArray(errors[key]) ? errors[key].join(" ") : errors[key] || "";

  return (
    <div
      onClick={(e) => e.target === e.currentTarget && onClose?.()}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 50,
        display: "grid",
        placeItems: "center",
        padding: 20,
        background: "rgba(7, 11, 22, 0.66)",
        backdropFilter: "blur(8px)",
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-prof-title"
    >
      <form
        onSubmit={onSubmit}
        style={{
          width: "min(520px, 100%)",
          background: "var(--surface)",
          border: "1px solid var(--border-strong)",
          borderRadius: 16,
          padding: 24,
          boxShadow: "0 30px 60px rgba(0,0,0,0.55)",
          display: "grid",
          gap: 16,
        }}
      >
        <header style={{ display: "flex", alignItems: "start", justifyContent: "space-between", gap: 12 }}>
          <div>
            <h3 id="add-prof-title" style={{ margin: 0, color: "var(--text)" }}>
              Add a professor
            </h3>
            <div style={{ marginTop: 4, color: "var(--text-dim)", fontSize: 13 }}>
              We'll fetch their reviews and run sentiment analysis as soon as
              their detail page opens.
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="btn btn-ghost"
            style={{ padding: "4px 10px", fontSize: 18, lineHeight: 1 }}
          >
            ×
          </button>
        </header>

        {topError && (
          <div
            role="alert"
            style={{
              background: "rgba(255, 80, 80, 0.08)",
              border: "1px solid rgba(255, 120, 120, 0.35)",
              color: "#ffb3b3",
              borderRadius: 10,
              padding: "10px 12px",
              fontSize: 14,
            }}
          >
            {topError}
          </div>
        )}

        <Field
          label="Professor name"
          error={fieldError("name")}
          input={
            <input
              ref={nameRef}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Jane Doolittle"
              maxLength={128}
              autoComplete="off"
              style={inputStyle(fieldError("name"))}
            />
          }
        />

        <Field
          label="School"
          hint="Start typing to autocomplete from existing schools."
          error={fieldError("institution")}
          input={
            <>
              <input
                list={datalistId}
                value={institution}
                onChange={(e) => handleSchoolChange(e.target.value)}
                placeholder="e.g., Stanford University"
                maxLength={128}
                autoComplete="off"
                style={inputStyle(fieldError("institution"))}
              />
              <datalist id={datalistId}>
                {schoolOptions.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.professor_count?.toLocaleString?.() ?? s.professor_count} professors
                  </option>
                ))}
              </datalist>
            </>
          }
        />

        <Field
          label="Department (optional)"
          error={fieldError("department")}
          input={
            <select
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              style={inputStyle(fieldError("department"))}
            >
              <option value="">— Not sure —</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          }
        />

        <footer style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 4 }}>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Adding…" : "Add professor"}
          </button>
        </footer>
      </form>
    </div>
  );
}

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
