import { Route, Routes } from "react-router-dom";
import Navbar from "./components/Navbar.jsx";
import CompareBar from "./components/CompareBar.jsx";
import Home from "./pages/Home.jsx";
import Search from "./pages/Search.jsx";
import ProfessorDetail from "./pages/ProfessorDetail.jsx";
import Compare from "./pages/Compare.jsx";
import { CompareProvider } from "./lib/compareStore.jsx";

export default function App() {
  return (
    <CompareProvider>
      <div className="app">
        <Navbar />
        <main style={{ flex: 1 }}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/search" element={<Search />} />
            <Route path="/professors/:id" element={<ProfessorDetail />} />
            <Route path="/compare" element={<Compare />} />
            <Route
              path="*"
              element={
                <div className="container empty" style={{ padding: 80 }}>
                  Page not found.
                </div>
              }
            />
          </Routes>
        </main>
        <CompareBar />
        <footer className="footer">
          <div className="container">
            ProfIQ · CS 210 — Multi-Source Sentiment Analysis MVP
          </div>
        </footer>
      </div>
    </CompareProvider>
  );
}
