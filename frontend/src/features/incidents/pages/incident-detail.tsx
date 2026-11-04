import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type {
  AnalysisConfidence,
  IncidentResponse,
  IncidentStatus,
  TriageResult,
} from "@/api/types";
import { useAuth } from "@/auth-context";
import { ReviewForm } from "@/features/review/components/review-form";
import { ErrorAlert } from "@/shared/components/ui/error-alert";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Spinner } from "@/shared/components/ui/spinner";

const STATUS_LABELS: Record<IncidentStatus, string> = {
  created: "Creada",
  analyzing: "Analizando",
  analyzed: "Analizada",
  analysis_failed: "Análisis fallido",
  reviewed: "Revisada",
};

const STATUS_STYLES: Record<IncidentStatus, string> = {
  created: "border-slate-300 bg-slate-100 text-slate-700",
  analyzing: "border-blue-300 bg-blue-100 text-blue-800",
  analyzed: "border-emerald-300 bg-emerald-100 text-emerald-800",
  analysis_failed: "border-red-300 bg-red-100 text-red-800",
  reviewed: "border-violet-300 bg-violet-100 text-violet-800",
};

const CONFIDENCE_LABELS: Record<AnalysisConfidence, string> = {
  low: "baja",
  medium: "media",
  high: "alta",
};

const COMPARISON_FIELDS = [
  { key: "category", label: "Categoría" },
  { key: "severity", label: "Severidad" },
  { key: "priority", label: "Prioridad" },
  { key: "confidence", label: "Confianza" },
  { key: "summary", label: "Resumen" },
  { key: "affected_components", label: "Componentes afectados" },
  { key: "missing_information", label: "Información faltante" },
  { key: "justification", label: "Justificación" },
] as const;

type ComparisonKey = (typeof COMPARISON_FIELDS)[number]["key"];

const SHORTCUTS = [
  { key: "a", description: "Analizar la incidencia" },
  { key: "r", description: "Ir a la revisión humana" },
  { key: "Ctrl+Enter", description: "Guardar corrección desde el formulario" },
  { key: "Ctrl+Shift+Enter", description: "Aceptar la propuesta tal cual" },
  { key: "?", description: "Mostrar u ocultar esta ayuda" },
  { key: "Esc", description: "Cerrar la ayuda" },
];

export function IncidentDetailPage() {
  const { id = "" } = useParams();
  const { canWrite } = useAuth();
  const queryClient = useQueryClient();
  const [showShortcuts, setShowShortcuts] = useState(false);
  const query = useQuery({
    queryKey: ["incident", id],
    queryFn: ({ signal }) => apiClient.getIncident(id, signal),
    enabled: Boolean(id),
  });
  const health = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => apiClient.health(signal),
    staleTime: 30_000,
    retry: 1,
  });
  const analyze = useMutation({
    mutationFn: () => apiClient.analyzeIncident(id),
    onSuccess: (incident) => {
      queryClient.setQueryData(["incident", id], incident);
      void queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  const incident = query.data;
  const canAnalyze = incident?.status === "created" || incident?.status === "analysis_failed";

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (
        event.defaultPrevented ||
        event.repeat ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey
      ) {
        return;
      }
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest("input, textarea, select, [contenteditable='true']")
      ) {
        return;
      }
      if (event.key === "?") {
        setShowShortcuts((visible) => !visible);
        return;
      }
      if (event.key === "Escape") {
        setShowShortcuts(false);
        return;
      }
      if (event.key.toLowerCase() === "a" && canWrite && canAnalyze && !analyze.isPending) {
        analyze.mutate();
        return;
      }
      if (event.key.toLowerCase() === "r") {
        document.getElementById("review-form")?.scrollIntoView({ behavior: "smooth" });
        const focusable = document.querySelector<HTMLElement>(
          "#review-form select, #review-form input, #review-form textarea",
        );
        focusable?.focus();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [analyze, canAnalyze, canWrite]);

  if (query.isPending)
    return (
      <div role="status" aria-label="Cargando incidencia" className="space-y-4">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  if (query.isError) return <ErrorAlert error={query.error} />;
  if (!incident) return <p role="alert">Incidencia no encontrada</p>;

  const review = incident.triage?.review;

  return (
    <section className="space-y-6">
      <Link className="text-sm text-primary" to="/incidents">
        ← Volver a la bandeja
      </Link>
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span
            className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[incident.status]}`}
          >
            {STATUS_LABELS[incident.status]}
          </span>
          <span>{new Date(incident.created_at).toLocaleString()}</span>
        </div>
        <h1 className="text-3xl font-semibold">{incident.title}</h1>
        <p className="whitespace-pre-wrap text-muted-foreground">{incident.description}</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {canWrite && canAnalyze && (
          <button
            className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60"
            onClick={() => analyze.mutate()}
            disabled={analyze.isPending}
          >
            {analyze.isPending && <Spinner label="Analizando incidencia" />}
            {analyze.isPending
              ? "Analizando…"
              : incident.status === "analysis_failed"
                ? "Reintentar análisis"
                : "Analizar incidencia"}
          </button>
        )}
        {canWrite && canAnalyze && health.data?.analyzer_backend === "ollama" && (
          <p className="max-w-md text-sm text-amber-700 dark:text-amber-400" role="status">
            El backend usa Ollama: el análisis puede tardar varios minutos. El botón se deshabilita
            para evitar envíos duplicados.
          </p>
        )}
        {!canAnalyze && !incident.triage && (
          <p className="text-sm text-muted-foreground">
            El análisis no está disponible en este estado.
          </p>
        )}
        {!canWrite && (
          <p className="text-sm text-muted-foreground">
            Modo solo lectura: tu rol no permite analizar ni revisar.
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          {canWrite && (
            <>
              Atajos: <kbd className="rounded border px-1">a</kbd> analizar ·{" "}
              <kbd className="rounded border px-1">r</kbd> revisar ·{" "}
            </>
          )}
          <kbd className="rounded border px-1">?</kbd> ayuda
        </p>
      </div>
      <div aria-live="polite" className="sr-only">
        {analyze.isSuccess ? "Análisis completado." : ""}
      </div>
      {analyze.isError && <ErrorAlert error={analyze.error} />}

      {showShortcuts && (
        <aside
          role="note"
          aria-label="Atajos de teclado"
          className="rounded-lg border border-border bg-muted/40 p-4 text-sm"
        >
          <h2 className="mb-2 font-semibold">Atajos de teclado</h2>
          <ul className="space-y-1">
            {SHORTCUTS.map((shortcut) => (
              <li key={shortcut.key}>
                <kbd className="rounded border px-1">{shortcut.key}</kbd> {shortcut.description}
              </li>
            ))}
          </ul>
        </aside>
      )}

      {incident.triage && !review && incident.triage.confidence === "low" && (
        <div
          role="status"
          aria-live="polite"
          className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100"
        >
          <p className="font-medium">Confianza baja de la propuesta</p>
          <p className="mt-1">
            La IA tiene poca seguridad en este triaje. Revisa con especial atención la categoría, la
            severidad y la información faltante antes de guardar.
          </p>
        </div>
      )}

      {incident.triage && (
        <ComparisonTable proposal={incident.triage} final={review?.final ?? null} />
      )}

      {review && <ReviewSummary review={review} />}

      {canWrite && incident.triage && !review && (
        <ReviewForm
          incident={incident}
          onSuccess={(updated) => queryClient.setQueryData(["incident", id], updated)}
        />
      )}
    </section>
  );
}

function ComparisonTable({
  proposal,
  final,
}: {
  proposal: TriageResult;
  final: TriageResult | null;
}) {
  return (
    <section className="space-y-3" aria-label="Comparación entre propuesta y revisión">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-xl font-semibold">Comparación IA → humano</h2>
          <p className="text-sm text-muted-foreground">
            {final
              ? "Las filas modificadas se resaltan para revisar solo las diferencias."
              : "Todavía no hay revisión humana: se muestra la propuesta original."}
          </p>
        </div>
        {!final && <span className="text-sm text-muted-foreground">Sin revisar</span>}
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="bg-muted/60">
            <tr>
              <th className="px-4 py-3 font-medium">Campo</th>
              <th className="px-4 py-3 font-medium">Propuesta IA</th>
              <th className="px-4 py-3 font-medium">Resultado humano</th>
              {final && <th className="px-4 py-3 font-medium">Estado</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {COMPARISON_FIELDS.map((field) => {
              const changed = final ? !sameValue(proposal[field.key], final[field.key]) : false;
              return (
                <tr
                  key={field.key}
                  className={changed ? "bg-amber-50 dark:bg-amber-950/30" : undefined}
                >
                  <th className="px-4 py-3 align-top font-medium" scope="row">
                    {field.label}
                  </th>
                  <td className="px-4 py-3 align-top">
                    {formatValue(field.key, proposal[field.key])}
                  </td>
                  <td className="px-4 py-3 align-top">
                    {final ? (
                      formatValue(field.key, final[field.key])
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  {final && (
                    <td className="px-4 py-3 align-top">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          changed
                            ? "bg-amber-200 text-amber-900 dark:bg-amber-800 dark:text-amber-50"
                            : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {changed ? "modificado" : "igual"}
                      </span>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ReviewSummary({ review }: { review: NonNullable<IncidentResponse["triage"]>["review"] }) {
  if (!review) return null;
  return (
    <section
      aria-label="Resumen de la revisión"
      className="space-y-3 rounded-lg border border-violet-300 bg-violet-50/60 p-5 dark:border-violet-800 dark:bg-violet-950/30"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Revisión humana</h2>
        <p className="text-sm text-muted-foreground">
          {review.source} · {new Date(review.reviewed_at).toLocaleString()}
        </p>
      </div>
      {review.review_checklist.length > 0 && (
        <div>
          <h3 className="text-sm font-medium">Checklist completada</h3>
          <ul
            aria-label="Checklist de revisión"
            className="mt-1 list-inside list-disc text-sm text-muted-foreground"
          >
            {review.review_checklist.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {review.review_comment && (
        <p className="text-sm">
          <span className="font-medium">Comentario: </span>
          {review.review_comment}
        </p>
      )}
    </section>
  );
}

function sameValue(left: unknown, right: unknown) {
  if (Array.isArray(left) && Array.isArray(right)) {
    return [...left].sort().join("\u0000") === [...right].sort().join("\u0000");
  }
  return left === right;
}

function formatValue(key: ComparisonKey, value: TriageResult[ComparisonKey]) {
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-muted-foreground">—</span>;
    return (
      <span className="flex flex-wrap gap-1">
        {value.map((item) => (
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs" key={item}>
            {item}
          </span>
        ))}
      </span>
    );
  }
  if (key === "confidence") {
    return CONFIDENCE_LABELS[value as AnalysisConfidence] ?? String(value);
  }
  if (key === "summary" || key === "justification") {
    return <span className="whitespace-pre-wrap">{String(value)}</span>;
  }
  return String(value);
}
