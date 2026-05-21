import SearchBar from "../components/SearchBar";

export default function Search() {
  return (
    <section className="py-12 text-center">
      <h1 className="text-4xl font-semibold mb-3 text-gray-900">
        Find a player
      </h1>
      <p className="text-gray-600 mb-8 max-w-xl mx-auto">
        Type a name. DiamondScope will pull their FanGraphs / Statcast data, flag
        meaningful spikes or dips year over year and within the season, and rank
        the most likely drivers behind each change.
      </p>
      <SearchBar autoFocus />
      <p className="mt-8 text-xs text-gray-400">
        Findings are <strong>probable causes</strong>, not proven causation —
        correlational analysis guided by domain knowledge.
      </p>
    </section>
  );
}
