import { api } from "./client";

const TOKEN_KEY = "ds_token";
const USER_KEY = "ds_user";

export type AuthUser = {
  id: number;
  email: string;
  display_name: string | null;
};

export type LoginResponse = {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: AuthUser;
};

export async function login(email: string, password: string): Promise<LoginResponse> {
  // Backend uses OAuth2PasswordRequestForm — must be x-www-form-urlencoded
  // with `username` / `password` fields.
  const params = new URLSearchParams();
  params.set("username", email);
  params.set("password", password);
  const res = await api.post<LoginResponse>("/api/auth/login", params, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  setToken(res.data.access_token);
  setStoredUser(res.data.user);
  return res.data;
}

export async function logoutServer(): Promise<void> {
  try {
    await api.post("/api/auth/logout");
  } catch {
    // server-side logout is best-effort; client-side state is authoritative.
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token == null) localStorage.removeItem(TOKEN_KEY);
    else localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // localStorage may throw in private mode or when disabled.
  }
}

export function getStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function setStoredUser(user: AuthUser | null): void {
  try {
    if (user == null) localStorage.removeItem(USER_KEY);
    else localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    // ignore
  }
}

export function clearAuth(): void {
  setToken(null);
  setStoredUser(null);
}
