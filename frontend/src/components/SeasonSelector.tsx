type Props = {
  seasons: number[];
  value: number;
  onChange: (s: number) => void;
};

export default function SeasonSelector({ seasons, value, onChange }: Props) {
  if (!seasons.length) return null;
  return (
    <label className="text-sm flex items-center gap-2">
      <span className="text-gray-500">Season</span>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="border border-gray-300 rounded px-2 py-1 bg-white text-gray-800"
      >
        {[...seasons]
          .sort((a, b) => b - a)
          .map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
      </select>
    </label>
  );
}
