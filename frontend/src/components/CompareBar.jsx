import { useNavigate, useLocation } from "react-router-dom";
import { useCompare } from "../lib/compareStore.jsx";

export default function CompareBar() {
  const { ids, clear } = useCompare();
  const navigate = useNavigate();
  const location = useLocation();

  if (ids.length < 2) return null;
  if (location.pathname === "/compare") return null;

  return (
    <div className="compare-bar">
      <span className="count">{ids.length} selected</span>
      <button className="btn btn-ghost" onClick={clear}>
        Clear
      </button>
      <button
        className="btn btn-primary"
        onClick={() => navigate(`/compare?ids=${ids.join(",")}`)}
      >
        Compare →
      </button>
    </div>
  );
}
