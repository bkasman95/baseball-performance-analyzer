import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { AnalysisReport, AnomalyFinding } from "../api/client";
import { useAnalysis, usePlayerProfile, useTimeseries } from "../api/hooks";
import AnomalyCard from "../components/AnomalyCard";
import { Badge } from "../components/Badge";
import SeasonSelector from "../components/SeasonSelector";
import { SkeletonCard } from "../components/Skeleton";
import TrendChart from "../components/TrendChart";

export default function Dashboard() {
  const { id } = useParams();
  const mlbamId = id ? Number(id) : undefined;
  const profile = usePlayerProfile(mlbamId);

  const seasons = profile.data?.seasons_available ?? [];
  const defaultSeason = useMemo(
    () =>
      profile.data?.last_year ??
      (seasons.length ? Math.max(...seasons) : undefined),
    [profile.data?.last_year, seasons]
  );
  const [season, setSeason] = useState<number | undefined>(undefined);
  useEffect(() => {
    if (season == null && defaultSeason != null) setSeason(defaultSeason);
  }, [defaultSeason, season]);

  const analysis = useAnalysis(mlbamId, season);

  if (mlbamId == null || Number.isNaN(mlbamId)) {
    return <p className="text-red-600">Invalid player id.</p>;
  }

  if (profile.isLoading) return <Header.Skeleton />;
  if (profile.error) {
    return (
      <p className="text-red-600">
        Couldn't load player profile: {(profile.error as Error).message}
      </p>
    );
  }
  if (!profile.data) return <p className="text-gray-500">No profile.</p>;

  return (
    <div className="space-y-8">
      <Header
        photo={profile.data.photo_url}
        name={profile.data.full_name}
        role={profile.data.role}
        debutYear={profile.data.debut_year}
        lastYear={profile.data.last_year}
        season={season ?? defaultSeason}
        seasons={seasons}
        onSeasonChange={setSeason}
      />

      <AnalysisSection state={analysis} mlbamId={mlbamId} season={season} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

type HeaderProps = {
  photo: string | null;
  name: string;
  role: string;
  debutYear: number | null;
  lastYear: number | null;
  season: number | undefined;
  seasons: number[];
  onSeasonChange: (s: number) => void;
};

function Header({
  photo,
  name,
  role,
  debutYear,
  lastYear,
  season,
  seasons,
  onSeasonChange,
}: HeaderProps) {
  return (
    <header className="bg-white rounded-lg shadow p-5 flex items-center gap-5">
      {photo && (
        <img
          src={photo}
          alt={name}
          className="w-20 h-20 rounded-full object-cover border border-gray-200 bg-gray-100"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = "none";
          }}
        />
      )}
      <div className="flex-1">
        <h1 className="text-2xl font-semibold text-gray-900">{name}</h1>
        <div className="text-sm text-gray-500 mt-1 flex items-center gap-3">
          <Badge tone="muted">{role}</Badge>
          <span>
            {debutYear ?? "?"}–{lastYear ?? "?"}
          </span>
        </div>
      </div>
      {season != null && (
        <SeasonSelector seasons={seasons} value={season} onChange={onSeasonChange} />
      )}
    </header>
  );
}

Header.Skeleton = function HeaderSkeleton() {
  return (
    <div className="bg-white rounded-lg shadow p-5 animate-pulse h-28 flex items-center gap-5">
      <div className="w-20 h-20 rounded-full bg-gray-200" />
      <div className="flex-1 space-y-3">
        <div className="h-5 bg-gray-200 rounded w-1/3" />
        <div className="h-3 bg-gray-200 rounded w-1/4" />
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Analysis body
// ---------------------------------------------------------------------------

function AnalysisSection({
  state,
  mlbamId,
  season,
}: {
  state: ReturnType<typeof useAnalysis>;
  mlbamId: number;
  season: number | undefined;
}) {
  if (state.phase === "idle" || state.phase === "starting") {
    return <LoadingState message="Starting analysis…" />;
  }

  if (state.phase === "running") {
    return (
      <LoadingState
        message={`Analysis ${state.status}. Cold-cache pulls hit FanGraphs + Statcast; first run can take 30–60 s. The result is cached for next time.`}
      />
    );
  }

  if (state.phase === "error") {
    return (
      <section className="bg-rose-50 border border-rose-200 text-rose-800 rounded-lg p-5">
        <h2 className="font-semibold">Analysis failed</h2>
        <p className="mt-1 text-sm">{state.message}</p>
      </section>
    );
  }

  return <ReportView report={state.report} mlbamId={mlbamId} season={season} />;
}

function LoadingState({ message }: { message: string }) {
  return (
    <section className="space-y-4">
      <div className="bg-white rounded-lg shadow p-5">
        <p className="text-sm text-gray-600">{message}</p>
      </div>
      <SkeletonCard height="h-28" />
      <SkeletonCard height="h-28" />
      <SkeletonCard height="h-28" />
    </section>
  );
}

// ---------------------------------------------------------------------------
// Report view
// ---------------------------------------------------------------------------

function ReportView({
  report,
  mlbamId,
  season,
}: {
  report: AnalysisReport;
  mlbamId: number;
  season: number | undefined;
}) {
  const sampleEntries = Object.entries(report.sample);

  return (
    <div className="space-y-8">
      <section className="bg-white rounded-lg shadow p-5">
        <h2 className="text-sm uppercase tracking-wide text-gray-500 mb-1">
          Headline
        </h2>
        <p className="text-lg text-gray-900">{report.headline}</p>
        {sampleEntries.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {sampleEntries.map(([k, v]) => (
              <Badge key={k} tone="muted">
                {k}: {typeof v === "number" ? v : String(v)}
              </Badge>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-3 text-gray-900">Anomalies</h2>
        {report.findings.length === 0 ? (
          <p className="text-sm text-gray-600 bg-white rounded-lg shadow p-5">
            No significant outcome anomalies were detected this season.
          </p>
        ) : (
          <div className="space-y-3">
            {report.findings.map((f, i) => (
              <AnomalyCard key={`${f.metric}-${i}`} finding={f} />
            ))}
          </div>
        )}
      </section>

      <TrendsSection
        report={report}
        mlbamId={mlbamId}
        season={season ?? report.season}
      />

      {report.notes.length > 0 && (
        <section className="text-xs text-gray-500">
          <details>
            <summary className="cursor-pointer">
              Notes ({report.notes.length})
            </summary>
            <ul className="list-disc pl-5 mt-1">
              {report.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </details>
        </section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trend charts: one season-grain chart per anomaly metric.
// ---------------------------------------------------------------------------

function TrendsSection({
  report,
  mlbamId,
  season,
}: {
  report: AnalysisReport;
  mlbamId: number;
  season: number;
}) {
  const topMetrics = uniqueMetrics(report.findings).slice(0, 4);
  const changepointFindings = report.findings.filter((f) => f.kind === "changepoint");

  if (topMetrics.length === 0 && changepointFindings.length === 0) return null;

  // Drive the X-axis range from the analyzed-seasons array so a sparse
  // multi-year chart still shows all 6 years on the axis.
  const seasonsAnalyzed = report.seasons_analyzed ?? [];
  const seasonRange: [number, number] | undefined = seasonsAnalyzed.length
    ? [Math.min(...seasonsAnalyzed), Math.max(...seasonsAnalyzed)]
    : undefined;

  // Without an explicit role the timeseries endpoint falls back to "hitter"
  // for any player whose role table entry is "unknown", which silently makes
  // pitcher charts look empty (they have ~0 batter PAs since universal-DH).
  const role = report.role;

  return (
    <section className="space-y-6">
      {topMetrics.length > 0 && (
        <div>
          <h2 className="text-xl font-semibold mb-3 text-gray-900">
            Year-over-year trends
          </h2>
          <p className="text-xs text-gray-500 mb-3">
            One chart per anomaly metric. Red dashed line marks the analyzed
            season ({season}).
          </p>
          <div className="grid md:grid-cols-2 gap-4">
            {topMetrics.map((metric) => (
              <div key={metric} className="bg-white rounded-lg shadow p-4">
                <SeasonTrend
                  mlbamId={mlbamId}
                  metric={metric}
                  season={season}
                  seasonRange={seasonRange}
                  role={role}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {changepointFindings.length > 0 && (
        <div>
          <h2 className="text-xl font-semibold mb-3 text-gray-900">
            In-season changepoints
          </h2>
          <p className="text-xs text-gray-500 mb-3">
            Rolling per-event chart for the analyzed season. Red dashed line
            marks where the level shift was detected.
          </p>
          <div className="grid md:grid-cols-2 gap-4">
            {changepointFindings.map((f, i) => (
              <div key={`cp-${f.metric}-${i}`} className="bg-white rounded-lg shadow p-4">
                <RollingTrend
                  mlbamId={mlbamId}
                  metric={f.metric}
                  season={season}
                  changepointDate={
                    (f.detail?.["changepoint_date"] as string | undefined) ?? null
                  }
                  period={f.period}
                  role={role}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function SeasonTrend({
  mlbamId,
  metric,
  season,
  seasonRange,
  role,
}: {
  mlbamId: number;
  metric: string;
  season: number;
  seasonRange?: [number, number];
  role: "pitcher" | "hitter";
}) {
  const ts = useTimeseries(mlbamId, metric, { grain: "season", role });
  const data = (ts.data?.points ?? []).map((p) => ({
    x: typeof p.x === "string" ? Number(p.x) || p.x : p.x,
    y: p.y,
  }));
  const subtitle = seasonRange
    ? `${seasonRange[0]} – ${seasonRange[1]}`
    : undefined;
  return (
    <TrendChart
      title={`${metric} by season`}
      subtitle={subtitle}
      data={data}
      changepointX={season}
      changepointLabel={`${season}`}
      xNumericDomain={seasonRange}
      emptyMessage={
        ts.isLoading ? "Loading…" : ts.data?.notes.length ? ts.data.notes.join(", ") : "No data."
      }
    />
  );
}

function RollingTrend({
  mlbamId,
  metric,
  season,
  changepointDate,
  period,
  role,
}: {
  mlbamId: number;
  metric: string;
  season: number;
  changepointDate: string | null;
  period: string | null;
  role: "pitcher" | "hitter";
}) {
  const ts = useTimeseries(mlbamId, metric, { grain: "rolling", season, window: 30, role });
  const data = (ts.data?.points ?? []).map((p) => ({ x: p.x, y: p.y }));
  return (
    <TrendChart
      title={`${metric} — ${season} rolling`}
      subtitle={period ?? undefined}
      data={data}
      changepointX={changepointDate ?? undefined}
      changepointLabel={changepointDate ?? "changepoint"}
      emptyMessage={
        ts.isLoading
          ? "Loading…"
          : ts.data?.notes.length
          ? ts.data.notes.join(", ")
          : "No pitch-level data."
      }
    />
  );
}

function uniqueMetrics(findings: AnomalyFinding[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const f of findings) {
    if (!seen.has(f.metric)) {
      seen.add(f.metric);
      out.push(f.metric);
    }
  }
  return out;
}
