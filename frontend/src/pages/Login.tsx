export default function Login() {
  return (
    <section className="max-w-sm mx-auto">
      <h1 className="text-2xl font-semibold mb-4">Sign in</h1>
      <p className="text-gray-600 mb-6">Auth ships in Phase 5.</p>
      <form className="space-y-3" onSubmit={(e) => e.preventDefault()}>
        <input
          type="email"
          disabled
          placeholder="email"
          className="w-full px-3 py-2 border rounded bg-gray-50 text-gray-400"
        />
        <input
          type="password"
          disabled
          placeholder="password"
          className="w-full px-3 py-2 border rounded bg-gray-50 text-gray-400"
        />
        <button
          disabled
          className="w-full bg-diamond-600 text-white py-2 rounded disabled:opacity-50"
        >
          Sign in
        </button>
      </form>
    </section>
  );
}
