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
      className="modal-backdrop"
      onClick={(e) => e.target === e.currentTarget && onClose?.()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-prof-title"
    >
      <form onSubmit={onSubmit} className="modal">
        <header className="modal-head">
          <div>
            <h3 id="add-prof-title">Add a professor</h3>
            <p className="report-note">
              Their reviews are fetched and scored the first time their page
              opens.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="modal-close"
          >
            &times;
          </button>
        </header>

        {topError && (
          <div role="alert" className="notice notice-error">
            <div className="notice-text">{topError}</div>
          </div>
        )}

        <Field
          label="Professor name"
          error={fieldError("name")}
          input={
            <input
              ref={nameRef}
              className={"field" + (fieldError("name") ? " field-error" : "")}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Jane Doolittle"
              maxLength={128}
              autoComplete="off"
            />
          }
        />

        <Field
          label="School"
          hint="Start typing to pick from schools already indexed."
          error={fieldError("institution")}
          input={
            <>
              <input
                className={"field" + (fieldError("institution") ? " field-error" : "")}
                list={datalistId}
                value={institution}
                onChange={(e) => handleSchoolChange(e.target.value)}
                placeholder="Stanford University"
                maxLength={128}
                autoComplete="off"
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
              className={"field" + (fieldError("department") ? " field-error" : "")}
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
            >
              <option value="">Not sure</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          }
        />

        <footer className="modal-foot">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Adding" : "Add professor"}
          </button>
        </footer>
      </form>
    </div>
  );
}

function Field({ label, hint, error, input }) {
  return (
    <label className="form-field">
      <span className="form-label">{label}</span>
      {input}
      {hint && !error && <span className="form-hint">{hint}</span>}
      {error && <span className="form-error">{error}</span>}
    </label>
  );
}
