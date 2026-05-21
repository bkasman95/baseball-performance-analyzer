import { ProbableCause } from "../api/client";
import { fmt, fmtDelta } from "../utils/format";
import { DirectionBadge } from "./Badge";

type Props = {
  causes: ProbableCause[];
};

export default function ProbableCauseList({ causes }: Props) {
  if (!causes.length) {
    return (
      <p className="text-sm text-gray-500 italic">
        No driver attribution available — likely insufficient data overlap.
      </p>
    );
  }

  return (
    <ol className="space-y-3">
      {causes.map((c, i) => (
        <li
          key={`${c.driver}-${i}`}
          className="bg-gray-50 rounded-md border border-gray-200 p-3"
        >
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-gray-500">#{i + 1}</span>
              <span className="font-medium text-gray-900">{c.driver}</span>
              <DirectionBadge direction={c.direction} />
            </div>
            <span className="text-xs text-gray-500">
              attribution {Math.round(c.attribution_weight * 100)}%
            </span>
          </div>

          <div className="text-sm text-gray-700">{c.sentence}</div>

          <div className="mt-2 flex items-center gap-4 text-xs text-gray-500">
            <span>
              Before <span className="font-mono text-gray-700">{fmt(c.before)}</span>
            </span>
            <span>→</span>
            <span>
              After <span className="font-mono text-gray-700">{fmt(c.after)}</span>
            </span>
            <span>
              Δ <span className="font-mono text-gray-700">{fmtDelta(c.delta)}</span>
            </span>
            {c.standardized_delta != null && (
              <span>
                Std Δ{" "}
                <span className="font-mono text-gray-700">
                  {fmtDelta(c.standardized_delta, 2)}σ
                </span>
              </span>
            )}
          </div>

          <AttributionBar weight={c.attribution_weight} />
        </li>
      ))}
    </ol>
  );
}

function AttributionBar({ weight }: { weight: number }) {
  const pct = Math.max(0, Math.min(1, weight)) * 100;
  return (
    <div className="mt-2 h-1 rounded-full bg-gray-200 overflow-hidden">
      <div
        className="h-full bg-diamond-600"
        style={{ width: `${pct}%` }}
        aria-label={`attribution weight ${pct.toFixed(0)}%`}
      />
    </div>
  );
}
