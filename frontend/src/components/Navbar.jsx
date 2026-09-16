import { NavLink } from "react-router-dom";
import { useUniversity } from "../lib/universityStore.jsx";

export default function Navbar() {
  const { institution, clearInstitution } = useUniversity();
  return (
    <header className="navbar">
      <div className="container navbar-inner">
        <NavLink to="/" className="brand">
          <span className="brand-mark">P</span>
          <span>
            Prof<span style={{ color: "var(--accent-2)" }}>IQ</span>
          </span>
        </NavLink>
        <div className="navbar-right">
          <nav className="nav-links">
            <NavLink
              to="/"
              end
              className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
            >
              Home
            </NavLink>
            <NavLink
              to="/search"
              className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
            >
              Browse
            </NavLink>
            <NavLink
              to="/compare"
              className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
            >
              Compare
            </NavLink>
          </nav>
          {institution && (
            <div className="school-chip" title={institution}>
              <span className="school-chip-name">
                {institution.length > 24 ? institution.slice(0, 21) + "…" : institution}
              </span>
              <button
                type="button"
                className="school-chip-change"
                onClick={clearInstitution}
                title="Change university"
              >
                change
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
