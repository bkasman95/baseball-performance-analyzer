import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  AnalysisAccepted,
  AnalysisReport,
  JobStatus,
  JobView,
  PlayerCard,
  PlayerProfile,
  TimeseriesResponse,
  getJob,
  getProfile,
  getTimeseries,
  searchPlayers,
  startAnalysis,
} from "./client";

// ---------------------------------------------------------------------------
// Debounced value
// ---------------------------------------------------------------------------

export function useDebounced<T>(value: T, ms = 200): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

// ---------------------------------------------------------------------------
// Player search
// ---------------------------------------------------------------------------

export function usePlayerSearch(query: string) {
  const debounced = useDebounced(query, 200);
  return useQuery<PlayerCard[]>({
    queryKey: ["search", debounced],
    queryFn: () => searchPlayers(debounced),
    enabled: debounced.trim().length >= 2,
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// Player profile
// ---------------------------------------------------------------------------

export function usePlayerProfile(mlbamId: number | undefined) {
  return useQuery<PlayerProfile>({
    queryKey: ["profile", mlbamId],
    queryFn: () => getProfile(mlbamId!),
    enabled: mlbamId != null,
    staleTime: 5 * 60_000,
  });
}

// ---------------------------------------------------------------------------
// Analysis with automatic job polling
// ---------------------------------------------------------------------------

export type AnalysisState =
  | { phase: "idle" }
  | { phase: "starting" }
  | { phase: "running"; status: JobStatus; jobId: string; startedAt: string | null }
  | { phase: "ready"; report: AnalysisReport }
  | { phase: "error"; message: string };

export function useAnalysis(
  mlbamId: number | undefined,
  season: number | undefined
): AnalysisState {
  // Step 1: kick off the analysis (GET returns either {report} or {job_id}).
  const start = useQuery({
    queryKey: ["analysis", mlbamId, season],
    queryFn: () => startAnalysis(mlbamId!, season),
    enabled: mlbamId != null && season != null,
    staleTime: Infinity, // we manage freshness via refresh action
    retry: false,
  });

  // If we got the report immediately (cached path), return it.
  const direct = start.data && "report" in start.data ? start.data.report : null;

  const accepted = start.data && "job_id" in start.data ? (start.data as AnalysisAccepted) : null;

  // Step 2: poll the job until complete or failed.
  const poll = useQuery<JobView>({
    queryKey: ["job", accepted?.job_id],
    queryFn: () => getJob(accepted!.job_id),
    enabled: !!accepted && !direct,
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      if (status === "complete" || status === "failed") return false;
      return 1500;
    },
    staleTime: 0,
  });

  if (start.isLoading) return { phase: "starting" };
  if (start.error)
    return { phase: "error", message: (start.error as Error).message || "analysis failed to start" };

  if (direct) return { phase: "ready", report: direct };

  if (accepted) {
    const status = poll.data?.status ?? accepted.job_status;
    if (status === "complete" && poll.data?.result) {
      return { phase: "ready", report: poll.data.result as AnalysisReport };
    }
    if (status === "failed") {
      return { phase: "error", message: poll.data?.error || "analysis job failed" };
    }
    return {
      phase: "running",
      status,
      jobId: accepted.job_id,
      startedAt: poll.data?.started_at ?? null,
    };
  }

  return { phase: "idle" };
}

// ---------------------------------------------------------------------------
// Timeseries
// ---------------------------------------------------------------------------

export function useTimeseries(
  mlbamId: number | undefined,
  metric: string | undefined,
  opts?: { grain?: "season" | "rolling"; season?: number; window?: number }
) {
  return useQuery<TimeseriesResponse>({
    queryKey: ["timeseries", mlbamId, metric, opts?.grain, opts?.season, opts?.window],
    queryFn: () =>
      getTimeseries(mlbamId!, metric!, {
        grain: opts?.grain ?? "season",
        season: opts?.season,
        window: opts?.window,
      }),
    enabled: mlbamId != null && !!metric,
    staleTime: 60_000,
  });
}
