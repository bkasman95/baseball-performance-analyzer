import { ChangeDirection, Confidence, Severity } from "../api/client";

type Props = {
  children: React.ReactNode;
  tone?: "neutral" | "good" | "bad" | "warn" | "muted";
  className?: string;
};

const TONE_CLASSES: Record<NonNullable<Props["tone"]>, string> = {
  neutral: "bg-gray-100 text-gray-800 border-gray-200",
  good:    "bg-green-50 text-green-800 border-green-200",
  bad:     "bg-rose-50 text-rose-800 border-rose-200",
  warn:    "bg-amber-50 text-amber-800 border-amber-200",
  muted:   "bg-gray-50 text-gray-500 border-gray-200",
};

export function Badge({ children, tone = "neutral", className = "" }: Props) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full border ${TONE_CLASSES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const label = severity[0].toUpperCase() + severity.slice(1);
  const tone = severity === "high" ? "bad" : severity === "medium" ? "warn" : "muted";
  return <Badge tone={tone}>{label}</Badge>;
}

export function DirectionBadge({ direction }: { direction: ChangeDirection }) {
  if (direction === "improvement") return <Badge tone="good">▲ Improvement</Badge>;
  if (direction === "regression") return <Badge tone="bad">▼ Regression</Badge>;
  return <Badge tone="neutral">◆ Change</Badge>;
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  if (confidence === "low") return <Badge tone="warn">Low confidence — small sample</Badge>;
  return <Badge tone="muted">High confidence</Badge>;
}
