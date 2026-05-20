import axios from "axios";

const baseURL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL,
  withCredentials: false,
});

export type HealthResponse = {
  status: "ok" | "degraded";
  db: { ok: boolean; error: string | null };
  version: string;
};

export async function getHealth(): Promise<HealthResponse> {
  const res = await api.get<HealthResponse>("/api/health");
  return res.data;
}
