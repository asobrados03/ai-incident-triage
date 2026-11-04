import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import type { ReviewMetricsResponse } from "@/api/types";
import { ErrorAlert } from "@/shared/components/ui/error-alert";
import { CardsSkeleton } from "@/shared/components/ui/skeleton";

const FIELD_LABELS: Record<string, string> = {
  category: "Categoría",
  severity: "Severidad",
  priority: "Prioridad",
  confidence: "Confianza",
  summary: "Resumen",
  affected_components: "Componentes afectados",
  missing_information: "Información faltante",
  justification: "Justificación",
};

export function MetricsPage() {
  const query = useQuery({
    queryKey: ["review-metrics"],
    queryFn: ({ signal }) => apiClient.reviewMetrics(signal),
  });

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold">Métricas de revisión</h1>
        <p className="text-muted-foreground">
          Calidad y correcciones del triaje asistido, calculadas solo con incidencias revisadas.
        </p>
      </div>

      {query.isPending && <CardsSkeleton />}
      {query.isError && <ErrorAlert error={query.error} />}

      {query.isSuccess && <MetricsContent metrics={query.data} />}
    </section>
  );
}

function MetricsContent({ metrics }: { metrics: ReviewMetricsResponse }) {
  const fewReviews = metrics.total_reviewed < 10;
  return (
    <div className="space-y-6" aria-live="polite">
      <div className="grid gap-4 md:grid-cols-3">
        <Metric label="Revisadas" value={metrics.total_reviewed} />
        <Metric label="Aceptadas sin cambios" value={metrics.accepted_without_changes} />
        <Metric
          label="Tasa de aceptación"
          value={`${Math.round(metrics.acceptance_rate * 100)}%`}
        />
      </div>

      <div
        className={`rounded-lg border p-4 text-sm ${
          fewReviews
            ? "border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100"
            : "border-border bg-muted/40 text-muted-foreground"
        }`}
        role="note"
        aria-label="Aviso de fiabilidad de las métricas"
      >
        <p className="font-medium">Cómo interpretar estas cifras</p>
        <p className="mt-1">
          {fewReviews
            ? `Solo hay ${metrics.total_reviewed} ${
                metrics.total_reviewed === 1 ? "revisión" : "revisiones"
              }: con pocas revisiones las cifras no son fiables y pueden cambiar mucho con cada nueva muestra.`
            : "Las cifras son orientativas: interpreta cada campo junto con su volumen de revisiones."}
        </p>
        <p className="mt-1">
          El analizador <code>fake</code> mide el funcionamiento del flujo (plumbing), no la calidad
          real de un LLM. Para evaluar calidad, usa Ollama y un conjunto de casos representativo.
        </p>
      </div>

      {metrics.total_reviewed === 0 ? (
        <p className="rounded-lg border border-border p-6 text-muted-foreground">
          Todavía no hay revisiones humanas. Cuando revises una incidencia aparecerán aquí el
          acierto por campo, las matrices de confusión y la corrección por confianza.
        </p>
      ) : (
        <>
          <div className="rounded-lg border border-border p-5">
            <h2 className="mb-4 font-semibold">Acierto por campo</h2>
            <div className="grid gap-3 md:grid-cols-2">
              {Object.entries(metrics.field_accuracy).map(([field, value]) => (
                <div
                  className="flex justify-between border-b border-border pb-2 text-sm"
                  key={field}
                >
                  <span>{FIELD_LABELS[field] ?? field}</span>
                  <span>
                    {Math.round(value.accuracy * 100)}% ({value.correct}/{value.total})
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-border p-5">
            <h2 className="mb-4 font-semibold">Correcciones por confianza</h2>
            <div className="grid gap-3 md:grid-cols-3">
              {Object.entries(metrics.corrections_by_confidence).map(([confidence, value]) => (
                <div className="rounded-md bg-muted p-3" key={confidence}>
                  <p className="font-medium">{confidence}</p>
                  <p className="text-sm text-muted-foreground">
                    {value.corrected_reviews} corregidas de {value.total_reviews} ·{" "}
                    {Math.round(value.correction_rate * 100)}% de corrección
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-6 rounded-lg border border-border p-5">
            <div>
              <h2 className="font-semibold">Matriz de confusión propuesta → final</h2>
              <p className="text-sm text-muted-foreground">
                Filas: valor propuesto por la IA. Columnas: valor final del revisor.
              </p>
            </div>
            {Object.entries(metrics.confusion_matrices)
              .filter(([, matrix]) => Object.keys(matrix).length > 0)
              .map(([field, matrix]) => (
                <ConfusionMatrix field={field} matrix={matrix} key={field} />
              ))}
          </div>
        </>
      )}
    </div>
  );
}

function ConfusionMatrix({
  field,
  matrix,
}: {
  field: string;
  matrix: Record<string, Record<string, number>>;
}) {
  const rows = Object.keys(matrix).sort();
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(matrix[row] ?? {})))).sort();
  const label = FIELD_LABELS[field] ?? field;

  if (rows.length === 0 || columns.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Sin datos de matriz para {label.toLowerCase()}.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">{label}</h3>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] border-collapse text-left text-sm">
          <caption className="sr-only">
            Matriz de confusión de {label}: valor propuesto por la IA frente al valor final.
          </caption>
          <thead>
            <tr className="bg-muted/60">
              <th className="border border-border px-3 py-2 font-medium" scope="col">
                IA ↓ / Humano →
              </th>
              {columns.map((column) => (
                <th className="border border-border px-3 py-2 font-medium" scope="col" key={column}>
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row}>
                <th className="border border-border px-3 py-2 font-medium" scope="row">
                  {row}
                </th>
                {columns.map((column) => (
                  <td className="border border-border px-3 py-2" key={column}>
                    {matrix[row]?.[column] ?? 0}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-border p-5">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-2 text-3xl font-semibold">{value}</p>
    </div>
  );
}
