import { useParams } from "react-router-dom";

export default function Dashboard() {
  const { id } = useParams();
  return (
    <section>
      <h1 className="text-2xl font-semibold mb-2">Player {id}</h1>
      <p className="text-gray-600">
        Dashboard (anomaly cards, drill-downs, trend charts, arsenal/pitch-type views)
        arrives in Phase 4.
      </p>
    </section>
  );
}
