import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { HistoryRow, HistoryStatus, getHistory } from "../api/client";
import { Badge } from "../components/Badge";

const PAGE_SIZE = 25;

export default function History() {
  const [offset, setOffset] = useState(0);
  const { data, isLoading, error } = useQuery({
    queryKey: ["history", offset],
    queryFn: () => getHistory({ limit: PAGE_SIZE, offset }),
    staleTime: 10_000,
  });

  if (isLoading) return <p className="text-gray-500">Loading…</p>;
  if (error)
    return (
      <p className="text-red-600">
        Couldn't load history: {(error as Error).message}
      </p>
    );
  if (!data) return null;

  const { rows, total } = data;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-gray-900">Query history</h1>
        <p className="text-sm text-gray-500 mt-1">
          Every analysis you've run. {total} total.
        </p>
      </header>

      {rows.length === 0 ? (
        <p className="text-sm text-gray-600 bg-white rounded-lg shadow p-5">
          No analyses yet. Run one from the{" "}
          <Link to="/" className="text-diamond-600 underline">
            search page
          </Link>
          .
        </p>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-4 py-2">Player</th>
                <th className="text-left px-4 py-2">Season</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-left px-4 py-2">When</th>
                <th className="text-right px-4 py-2">Duration</th>
                <th className="text-right px-4 py-2">Size</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <Row key={r.id} row={r} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Pagination
        offset={offset}
        total={total}
        pageSize={PAGE_SIZE}
        onChange={setOffset}
      />
    </div>
  );
}

function Row({ row }: { row: HistoryRow }) {
  return (
    <tr className="border-t border-gray-100 hover:bg-gray-50">
      <td className="px-4 py-2">
        <Link
          to={`/player/${row.player_id}`}
          className="text-diamond-600 hover:underline"
        >
          {row.player_name ?? `#${row.player_id}`}
        </Link>
      </td>
      <td className="px-4 py-2 font-mono text-gray-700">{row.season}</td>
      <td className="px-4 py-2">
        <StatusBadge status={row.status} cacheHit={row.cache_hit} />
      </td>
      <td className="px-4 py-2 text-gray-600">{fmtWhen(row.created_at)}</td>
      <td className="px-4 py-2 text-right font-mono text-gray-700">
        {fmtDuration(row.duration_ms)}
      </td>
      <td className="px-4 py-2 text-right font-mono text-gray-700">
        {fmtBytes(row.response_size_bytes)}
      </td>
    </tr>
  );
}

function StatusBadge({
  status,
  cacheHit,
}: {
  status: HistoryStatus;
  cacheHit: boolean;
}) {
  if (status === "complete") {
    return (
      <span className="inline-flex items-center gap-1.5">
        <Badge tone="good">complete</Badge>
        {cacheHit && <Badge tone="muted">cached</Badge>}
      </span>
    );
  }
  if (status === "running") return <Badge tone="warn">running</Badge>;
  if (status === "stale") return <Badge tone="muted">stale</Badge>;
  return <Badge tone="bad">failed</Badge>;
}

function Pagination({
  offset,
  total,
  pageSize,
  onChange,
}: {
  offset: number;
  total: number;
  pageSize: number;
  onChange: (o: number) => void;
}) {
  if (total <= pageSize) return null;
  const page = Math.floor(offset / pageSize) + 1;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between text-sm text-gray-600">
      <span>
        Page {page} of {pages}
      </span>
      <div className="space-x-2">
        <button
          type="button"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - pageSize))}
          className="px-3 py-1 rounded border border-gray-300 disabled:opacity-40"
        >
          Previous
        </button>
        <button
          type="button"
          disabled={offset + pageSize >= total}
          onClick={() => onChange(offset + pageSize)}
          className="px-3 py-1 rounded border border-gray-300 disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  );
}

function fmtWhen(iso: string): string {
  const d = new Date(iso);
  const now = Date.now();
  const secs = Math.round((now - d.getTime()) / 1000);
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`;
  return d.toLocaleString();
}

function fmtDuration(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function fmtBytes(n: number | null): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}
