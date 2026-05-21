import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { PlayerCard } from "../api/client";
import { usePlayerSearch } from "../api/hooks";
import { Badge } from "./Badge";

const ROLE_LABEL: Record<PlayerCard["role"], string> = {
  pitcher: "P",
  hitter: "H",
  two_way: "P+H",
  unknown: "?",
};

export default function SearchBar({ autoFocus = false }: { autoFocus?: boolean }) {
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const { data: results = [], isFetching, error } = usePlayerSearch(query);

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus();
  }, [autoFocus]);

  useEffect(() => {
    setHighlight(0);
  }, [results.length]);

  const pick = (p: PlayerCard) => {
    setOpen(false);
    setQuery("");
    navigate(`/player/${p.mlbam_id}`);
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!results.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      pick(results[highlight]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="relative w-full max-w-xl mx-auto">
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 100)}
        onKeyDown={onKey}
        placeholder="Search a player… (e.g. Ohtani, Mookie Betts)"
        className="w-full px-4 py-3 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-diamond-400 bg-white"
      />

      {open && query.trim().length >= 2 && (
        <div className="absolute z-20 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg overflow-hidden">
          {error && (
            <div className="px-4 py-3 text-sm text-red-600">
              Search unavailable: {(error as Error).message}
            </div>
          )}
          {!error && results.length === 0 && !isFetching && (
            <div className="px-4 py-3 text-sm text-gray-500">No matches.</div>
          )}
          {!error && isFetching && results.length === 0 && (
            <div className="px-4 py-3 text-sm text-gray-500">Searching…</div>
          )}
          {!error && results.length > 0 && (
            <ul role="listbox">
              {results.map((p, i) => (
                <li
                  key={p.mlbam_id}
                  role="option"
                  aria-selected={i === highlight}
                  className={`flex items-center justify-between px-4 py-2 cursor-pointer ${
                    i === highlight ? "bg-diamond-50" : "hover:bg-gray-50"
                  }`}
                  onMouseEnter={() => setHighlight(i)}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    pick(p);
                  }}
                >
                  <div className="flex items-center gap-3">
                    <span className="font-medium text-gray-900">{p.full_name}</span>
                    <Badge tone="muted">{ROLE_LABEL[p.role]}</Badge>
                  </div>
                  <span className="text-xs text-gray-500">
                    {p.debut_year ?? "?"}–{p.last_year ?? "?"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
