import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export type TrendPoint = { x: string | number; y: number | null };

type Props = {
  data: TrendPoint[];
  title?: string;
  height?: number;
  changepointX?: string | number | null;
  yDomain?: [number | "auto", number | "auto"];
  emptyMessage?: string;
};

export default function TrendChart({
  data,
  title,
  height = 200,
  changepointX,
  yDomain = ["auto", "auto"],
  emptyMessage = "No data.",
}: Props) {
  const points = data.filter((p) => p.y != null);

  return (
    <div>
      {title && (
        <div className="text-sm font-medium text-gray-700 mb-2">{title}</div>
      )}
      {points.length === 0 ? (
        <div className="text-xs text-gray-500 italic py-8 text-center bg-gray-50 rounded">
          {emptyMessage}
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={points} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="x"
              tick={{ fontSize: 11, fill: "#6b7280" }}
              minTickGap={20}
            />
            <YAxis
              domain={yDomain}
              tick={{ fontSize: 11, fill: "#6b7280" }}
              width={50}
            />
            <Tooltip
              contentStyle={{ fontSize: 12, borderRadius: 6 }}
              formatter={(v: number) => (typeof v === "number" ? v.toFixed(3) : v)}
            />
            <Line
              type="monotone"
              dataKey="y"
              stroke="#2f6a2f"
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
              isAnimationActive={false}
            />
            {changepointX != null && (
              <ReferenceLine
                x={changepointX}
                stroke="#dc2626"
                strokeDasharray="4 4"
                label={{ value: "changepoint", fontSize: 10, fill: "#dc2626" }}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
