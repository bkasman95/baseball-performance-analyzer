import { useQuery } from "@tanstack/react-query";
import { getHealth } from "../api/client";

export default function Health() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 5000,
  });

  return (
    <section>
      <h1 className="text-2xl font-semibold mb-4">System health</h1>
      {isLoading && <p className="text-gray-500">Checking…</p>}
      {error && <p className="text-red-600">API unreachable: {(error as Error).message}</p>}
      {data && (
        <div className="bg-white rounded-lg shadow p-6 space-y-2">
          <div>
            <span className="text-gray-500 mr-2">API:</span>
            <span className={data.status === "ok" ? "text-green-700" : "text-amber-700"}>
              {data.status}
            </span>
          </div>
          <div>
            <span className="text-gray-500 mr-2">Database:</span>
            <span className={data.db.ok ? "text-green-700" : "text-red-700"}>
              {data.db.ok ? "connected" : `error: ${data.db.error}`}
            </span>
          </div>
          <div>
            <span className="text-gray-500 mr-2">Version:</span>
            <span>{data.version}</span>
          </div>
        </div>
      )}
    </section>
  );
}
