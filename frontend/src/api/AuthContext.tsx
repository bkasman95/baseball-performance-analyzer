import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  AuthUser,
  clearAuth,
  getStoredUser,
  getToken,
  login as loginRequest,
  logoutServer,
  setStoredUser,
} from "./auth";

type AuthState = {
  user: AuthUser | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());

  useEffect(() => {
    // When the axios interceptor catches a 401 it dispatches this event;
    // we reset state so ProtectedRoute redirects.
    const handler = () => setUser(null);
    window.addEventListener("ds:unauthorized", handler);
    return () => window.removeEventListener("ds:unauthorized", handler);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await loginRequest(email, password);
    setUser(res.user);
  }, []);

  const logout = useCallback(async () => {
    await logoutServer();
    clearAuth();
    setUser(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      isAuthenticated: !!getToken() && !!user,
      login,
      logout,
    }),
    [user, login, logout]
  );

  // Keep stored user in sync if the in-memory user changes.
  useEffect(() => {
    setStoredUser(user);
  }, [user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
