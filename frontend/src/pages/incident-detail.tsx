import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { ReviewForm } from "@/components/review-form";

export function IncidentDetailPage() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["incident", id],
    queryFn: ({ signal }) => apiClient.getIncident(id, signal),
    enabled: Boolean(id),
  });
  const analyze = useMutation({
    mutationFn: () => apiClient.analyzeIncident(id),
    onSuccess: (incident) => queryClient.setQueryData(["incident", id], incident),
  });

  if (query.isPending) return <p role="status">Cargando incidencia…</p>;
  if (query.isError) return <p role="alert">{query.error.message}</p>;
  const incident = query.data;
  const review = incident.triage?.review?.final;

  return (
    <section className="space-y-6">
      <Link className="text-sm text-primary" to="/incidents">← Volver a la bandeja</Link>
      <div className="space-y-2">
        <p className="text-sm text-muted-foreground">{incident.status} · {new Date(incident.created_at).toLocaleString()}</p>
        <h1 className="text-3xl font-semibold">{incident.title}</h1>
        <p className="whitespace-pre-wrap text-muted-foreground">{incident.description}</p>
      </div>
      {!incident.triage && incident.status === "created" && (
        <button className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground" onClick={() => analyze.mutate()} disabled={analyze.isPending}>
          {analyze.isPending ? "Analizando…" : "Analizar incidencia"}
        </button>
      )}
      {analyze.isError && <p role="alert" className="text-sm text-red-600">{analyze.error.message}</p>}
      {incident.triage && (
        <div className="grid gap-4 md:grid-cols-2">
          <TriageCard title="Propuesta IA" result={incident.triage} />
          <TriageCard title="Resultado final" result={review ?? incident.triage} muted={!review} />
        </div>
      )}
      {incident.triage && !incident.triage.review && (
        <ReviewForm incident={incident} onSuccess={(updated) => queryClient.setQueryData(["incident", id], updated)} />
      )}
    </section>
  );
}

function TriageCard({ title, result, muted = false }: { title: string; result: { category: string; severity: string; priority: string; confidence: string; summary: string; justification: string }; muted?: boolean }) {
  return (
    <article className={`space-y-3 rounded-lg border p-5 ${muted ? "opacity-70" : ""}`}>
      <h2 className="font-semibold">{title}</h2>
      <p className="text-sm text-muted-foreground">{result.category} · {result.severity} · {result.priority} · confianza {result.confidence}</p>
      <p>{result.summary}</p>
      <p className="text-sm text-muted-foreground">{result.justification}</p>
    </article>
  );
}
