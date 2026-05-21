import { useState } from "react";

import { AnomalyFinding } from "../api/client";
import { fmt, fmtDelta } from "../utils/format";
import { ConfidenceBadge, DirectionBadge, SeverityBadge, Badge } from "./Badge";
import ProbableCauseList from "./ProbableCauseList";

type Props = {
  finding: AnomalyFinding;
};

const KIND_LABEL: Record<AnomalyFinding["kind"], string> = {
  year_over_year: "Year over year",
  changepoint: "In-season changepoint",
  multivariate: "Profile anomaly",
};

export default function AnomalyCard({ finding }: Props) {
  const [open, setOpen] = useState(false);

  const bgAccent =
    finding.direction === "regression"
      ? "border-l-rose-400"
      : finding.direction === "improvement"
      ? "border-l-green-500"
      : "border-l-gray-300";

  return (
    <div
      className={`bg-white rounded-lg shadow border border-l-4 ${bgAccent} border-gray-200`}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full text-left px-5 py-4 flex flex-wrap items-start gap-3 hover:bg-gray-50"
        aria-expanded={open}
      >
        <div className="flex-1 min-w-[200px]">
          <div className="flex items-center gap-3 flex-wrap">
            <h3 className="text-lg font-semibold text-gray-900">{finding.metric}</h3>
            <Badge tone="muted">{KIND_LABEL[finding.kind]}</Badge>
            <SeverityBadge severity={finding.severity} />
            <DirectionBadge direction={finding.direction} />
            <ConfidenceBadge confidence={finding.confidence} />
          </div>

          <p className="mt-2 text-sm text-gray-700">{finding.summary}</p>
        </div>

        <div className="text-right text-sm shrink-0">
          <div className="font-mono text-gray-900">
            {fmt(finding.before)} → <span className="font-semibold">{fmt(finding.after)}</span>
          </div>
          <div className="text-xs text-gray-500 mt-1">
            Δ {fmtDelta(finding.delta)}
            {finding.z_score != null && <> &middot; z {fmtDelta(finding.z_score, 2)}</>}
          </div>
          <div className="text-xs text-diamond-600 mt-2 underline">
            {open ? "Hide drivers" : "Show probable causes →"}
          </div>
        </div>
      </button>

      {open && (
        <div className="px-5 pb-5 pt-2 border-t border-gray-100">
          <h4 className="text-sm font-semibold text-gray-700 mb-3">
            Probable causes — ranked by combined SHAP + delta + domain-rule weight
          </h4>
          <ProbableCauseList causes={finding.probable_causes} />
        </div>
      )}
    </div>
  );
}
