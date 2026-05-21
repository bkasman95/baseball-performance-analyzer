import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../api/AuthContext";
import { isAxiosError } from "../api/client";

type LocationState = { from?: string };

export default function Login() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (isAuthenticated) {
    const from = (location.state as LocationState | null)?.from ?? "/";
    return <Navigate to={from} replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email.trim(), password);
      const from = (location.state as LocationState | null)?.from ?? "/";
      navigate(from, { replace: true });
    } catch (err) {
      let msg = "Sign in failed.";
      if (isAxiosError(err)) {
        if (err.response?.status === 401) msg = "Invalid email or password.";
        else if (err.response) msg = `Sign in failed (${err.response.status}).`;
        else msg = `Sign in failed: ${err.message}`;
      } else if (err instanceof Error) {
        msg = err.message;
      }
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="max-w-sm mx-auto py-12">
      <h1 className="text-2xl font-semibold mb-2 text-gray-900">Sign in</h1>
      <p className="text-sm text-gray-500 mb-6">
        DiamondScope is invite-only. Ask the admin for an account.
      </p>
      <form className="space-y-3 bg-white p-5 rounded-lg shadow" onSubmit={onSubmit}>
        <label className="block">
          <span className="block text-sm text-gray-700 mb-1">Email</span>
          <input
            type="email"
            autoComplete="username"
            autoFocus
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-diamond-400"
          />
        </label>
        <label className="block">
          <span className="block text-sm text-gray-700 mb-1">Password</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-diamond-400"
          />
        </label>

        {error && <p className="text-sm text-rose-700">{error}</p>}

        <button
          type="submit"
          disabled={submitting || !email || !password}
          className="w-full bg-diamond-600 hover:bg-diamond-800 text-white py-2 rounded disabled:opacity-50 transition"
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </section>
  );
}
