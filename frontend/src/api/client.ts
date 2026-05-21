import axios, { AxiosError } from "axios";

const baseURL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL,
  withCredentials: false,
  // Accept 2xx and 202 transparently.
  validateStatus: (s) => s >= 200 && s < 400,
});

// Attach bearer token to every request when present.
api.interceptors.request.use((config) => {
  try {
    const token = localStorage.getItem("ds_token");
    if (token) {
      config.headers = config.headers ?? {};
      (config.headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
    }
  } catch {
    // localStorage unavailable; proceed unauthenticated.
  }
  return config;
});

// On 401, clear stored auth so the next render sends the user to /login.
// We don't navigate here — let the AuthContext / ProtectedRoute handle that.
api.interceptors.response.use(
  (r) => r,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      try {
        localStorage.removeItem("ds_token");
        localStorage.removeItem("ds_user");
        window.dispatchEvent(new CustomEvent("ds:unauthorized"));
      } catch {
        // ignore
      }
    }
    return Promise.reject(error);
  }
);

// ---------------------------------------------------------------------------
// Shared types — mirror backend/app/api/schemas.py
// ---------------------------------------------------------------------------

export type Role = "pitcher" | "hitter" | "two_way" | "unknown";

export type PlayerCard = {
  mlbam_id: number;
  fangraphs_id: number | null;
  full_name: string;
  first_name: string;
  last_name: string;
  role: Role;
  debut_year: number | null;
  last_year: number | null;
};

export type PlayerProfile = PlayerCard & {
  seasons_available: number[];
  photo_url: string | null;
};

export type Severity = "low" | "medium" | "high";
export type Confidence = "low" | "high";
export type AnomalyKind = "year_over_year" | "changepoint" | "multivariate";
export type ChangeDirection = "improvement" | "regression" | "change";
export type JobStatus = "pending" | "running" | "complete" | "failed";

export type ProbableCause = {
  driver: string;
  before: number | null;
  after: number | null;
  delta: number | null;
  standardized_delta: number | null;
  attribution_weight: number;
  direction: ChangeDirection;
  sentence: string;
  detail: Record<string, unknown>;
};

export type AnomalyFinding = {
  metric: string;
  kind: AnomalyKind;
  season: number | null;
  before: number | null;
  after: number | null;
  delta: number | null;
  z_score: number | null;
  severity: Severity;
  direction: ChangeDirection;
  confidence: Confidence;
  period: string | null;
  before_period: string | null;
  after_period: string | null;
  detail: Record<string, unknown>;
  probable_causes: ProbableCause[];
  summary: string;
};

export type AnalysisReport = {
  player_id: number;
  role: "pitcher" | "hitter";
  season: number;
  seasons_analyzed: number[];
  findings: AnomalyFinding[];
  multivariate: Record<string, unknown> | null;
  headline: string;
  generated_at: string;
  sample: Record<string, number>;
  notes: string[];
};

export type AnalysisAccepted = {
  status: "accepted";
  job_id: string;
  job_status: JobStatus;
  status_url: string;
  message: string;
};

export type AnalysisOk = {
  status: "ok";
  report: AnalysisReport;
  job_id: string;
};

export type AnalysisResponse = AnalysisAccepted | AnalysisOk;

export type JobView<T = AnalysisReport> = {
  id: string;
  key: string;
  kind: string;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  progress: number;
  error: string | null;
  result: T | null;
  meta: Record<string, unknown>;
};

export type TimeseriesPoint = { x: number | string; y: number | null };

export type TimeseriesResponse = {
  player_id: number;
  metric: string;
  grain: "season" | "rolling";
  points: TimeseriesPoint[];
  notes: string[];
};

export type HealthResponse = {
  status: "ok" | "degraded";
  db: { ok: boolean; error: string | null };
  version: string;
};

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export async function getHealth(): Promise<HealthResponse> {
  return (await api.get<HealthResponse>("/api/health")).data;
}

export async function searchPlayers(
  query: string,
  opts?: { limit?: number; activeOnly?: boolean }
): Promise<PlayerCard[]> {
  const q = query.trim();
  if (q.length < 2) return [];
  const res = await api.get<{ query: string; results: PlayerCard[] }>(
    "/api/players/search",
    { params: { q, limit: opts?.limit ?? 8, active_only: opts?.activeOnly ?? true } }
  );
  return res.data.results;
}

export async function getProfile(mlbamId: number): Promise<PlayerProfile> {
  return (await api.get<PlayerProfile>(`/api/players/${mlbamId}/profile`)).data;
}

export async function startAnalysis(
  mlbamId: number,
  season?: number
): Promise<AnalysisResponse> {
  const res = await api.get<AnalysisResponse>(`/api/players/${mlbamId}/analysis`, {
    params: season != null ? { season } : undefined,
  });
  return res.data;
}

export async function getJob(jobId: string): Promise<JobView> {
  return (await api.get<JobView>(`/api/jobs/${jobId}`)).data;
}

export async function getTimeseries(
  mlbamId: number,
  metric: string,
  opts?: { grain?: "season" | "rolling"; season?: number; window?: number }
): Promise<TimeseriesResponse> {
  return (
    await api.get<TimeseriesResponse>(
      `/api/players/${mlbamId}/metrics/timeseries`,
      {
        params: {
          metric,
          grain: opts?.grain ?? "season",
          season: opts?.season,
          window: opts?.window,
        },
      }
    )
  ).data;
}

export async function refreshPlayer(
  mlbamId: number,
  season?: number
): Promise<{ status: string; invalidated_keys: number; job_id: string | null }> {
  return (
    await api.post(`/api/players/${mlbamId}/refresh`, null, {
      params: season != null ? { season } : undefined,
    })
  ).data;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function isAxiosError(e: unknown): e is AxiosError {
  return axios.isAxiosError(e);
}
