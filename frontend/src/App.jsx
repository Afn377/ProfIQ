import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import Home from "./pages/Home.jsx";
import Search from "./pages/Search.jsx";

export default function App() {
  return (
    <BrowserRouter>
      <nav className="nav container">
        <Link to="/" className="brand">ProfIQ</Link>
        <Link to="/search">Browse</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/search" element={<Search />} />
      </Routes>
    </BrowserRouter>
  );
}
