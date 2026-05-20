export default function Search() {
  return (
    <section className="text-center py-16">
      <h1 className="text-3xl font-semibold mb-3">Find a player</h1>
      <p className="text-gray-600 mb-8">
        Search-as-you-type and full anomaly analysis arrive in Phase 3/4. Phase 0+1
        scaffolding is in place: the API, DB, and Parquet cache are wired.
      </p>
      <input
        type="text"
        disabled
        placeholder="Player search (coming in Phase 4)"
        className="px-4 py-3 border border-gray-300 rounded-lg w-96 max-w-full bg-white disabled:bg-gray-50 disabled:text-gray-400"
      />
    </section>
  );
}
