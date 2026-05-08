import { NavLink } from "react-router-dom";

export default function Navbar() {
  return (
    <header className="navbar">
      <div className="container navbar-inner">
        <NavLink to="/" className="brand">
          <span className="brand-mark">P</span>
          <span>
            Prof<span style={{ color: "var(--accent-2)" }}>IQ</span>
          </span>
        </NavLink>
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
      </div>
    </header>
  );
}
