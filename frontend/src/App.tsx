import { Routes, Route, Link } from "react-router-dom";
import Health from "./pages/Health";
import Search from "./pages/Search";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-diamond-800 text-white px-6 py-4 shadow">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link to="/" className="text-xl font-semibold tracking-tight">
            DiamondScope
          </Link>
          <nav className="text-sm space-x-4 opacity-90">
            <Link to="/" className="hover:underline">Search</Link>
            <Link to="/health" className="hover:underline">Health</Link>
            <Link to="/login" className="hover:underline">Login</Link>
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-8">
        <Routes>
          <Route path="/" element={<Search />} />
          <Route path="/health" element={<Health />} />
          <Route path="/login" element={<Login />} />
          <Route path="/player/:id" element={<Dashboard />} />
        </Routes>
      </main>
      <footer className="text-center text-xs text-gray-500 py-4">
        Probable causes, not proven causation.
      </footer>
    </div>
  );
}
