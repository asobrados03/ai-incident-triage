import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/api/client";

export function MetricsPage() {
  const query = useQuery({
    queryKey: ["review-metrics"],
    queryFn: ({ signal }) => apiClient.reviewMetrics(signal),
  });
  if (query.isPending) return <p role="status">Cargando métricas…</p>;
  if (query.isError) return <p role="alert">{query.error.message}</p>;
  const metrics = query.data;
  return (
    <section className="space-y-6">
      <div><h1 className="text-3xl font-semibold">Métricas de revisión</h1><p className="text-muted-foreground">Calidad y correcciones del triaje asistido.</p></div>
      <div className="grid gap-4 md:grid-cols-3">
        <Metric label="Revisadas" value={metrics.total_reviewed} />
        <Metric label="Aceptadas sin cambios" value={metrics.accepted_without_changes} />
        <Metric label="Tasa de aceptación" value={`${Math.round(metrics.acceptance_rate * 100)}%`} />
      </div>
      <div className="rounded-lg border border-border p-5">
        <h2 className="mb-4 font-semibold">Acierto por campo</h2>
        <div className="grid gap-3 md:grid-cols-2">{Object.entries(metrics.field_accuracy).map(([field, value]) => <div className="flex justify-between border-b pb-2 text-sm" key={field}><span>{field}</span><span>{Math.round(value.accuracy * 100)}% ({value.correct}/{value.total})</span></div>)}</div>
      </div>
      <div className="rounded-lg border border-border p-5">
        <h2 className="mb-4 font-semibold">Correcciones por confianza</h2>
        <div className="grid gap-3 md:grid-cols-3">{Object.entries(metrics.corrections_by_confidence).map(([confidence, value]) => <div className="rounded-md bg-muted p-3" key={confidence}><p className="font-medium">{confidence}</p><p className="text-sm text-muted-foreground">{value.corrected_reviews} corregidas de {value.total_reviews}</p></div>)}</div>
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded-lg border border-border p-5"><p className="text-sm text-muted-foreground">{label}</p><p className="mt-2 text-3xl font-semibold">{value}</p></div>;
}
