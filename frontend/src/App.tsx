import { NavLink, Route, Routes } from "react-router-dom";
import BriefPage from "./pages/BriefPage";
import HoldingDetailPage from "./pages/HoldingDetailPage";
import HoldingsPage from "./pages/HoldingsPage";

export default function App() {
  return (
    <div className="shell">
      <main className="app">
        <Routes>
          <Route path="/" element={<HoldingsPage />} />
          <Route path="/brief" element={<BriefPage />} />
          <Route path="/holding/:ticker" element={<HoldingDetailPage />} />
        </Routes>
      </main>
      <nav className="tabbar">
        <NavLink to="/" className={({ isActive }) => (isActive ? "active" : "")} end>
          持仓
        </NavLink>
        <NavLink to="/brief" className={({ isActive }) => (isActive ? "active" : "")}>
          简报
        </NavLink>
      </nav>
    </div>
  );
}
