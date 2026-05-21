import { Link, Routes, Route, useNavigate } from "react-router-dom";

import { useAuth } from "./api/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import Health from "./pages/Health";
import Search from "./pages/Search";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-8">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/health" element={<Health />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Search />
              </ProtectedRoute>
            }
          />
          <Route
            path="/player/:id"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
        </Routes>
      </main>
      <footer className="text-center text-xs text-gray-500 py-4">
        Probable causes, not proven causation.
      </footer>
    </div>
  );
}

function Header() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <header className="bg-diamond-800 text-white px-6 py-4 shadow">
      <div className="max-w-6xl mx-auto flex items-center justify-between">
        <Link to="/" className="text-xl font-semibold tracking-tight">
          DiamondScope
        </Link>
        <nav className="text-sm space-x-4 opacity-90 flex items-center">
          <Link to="/" className="hover:underline">Search</Link>
          <Link to="/health" className="hover:underline">Health</Link>
          {isAuthenticated && user ? (
            <>
              <span className="text-diamond-100/80">{user.display_name || user.email}</span>
              <button
                type="button"
                onClick={async () => {
                  await logout();
                  navigate("/login", { replace: true });
                }}
                className="px-2 py-1 rounded border border-diamond-400/50 hover:bg-diamond-800/40"
              >
                Sign out
              </button>
            </>
          ) : (
            <Link to="/login" className="hover:underline">Sign in</Link>
          )}
        </nav>
      </div>
    </header>
  );
}
