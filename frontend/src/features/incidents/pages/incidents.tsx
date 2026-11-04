import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState } from "react";

import { apiClient } from "@/api/client";
import type { AnalysisConfidence, IncidentStatus } from "@/api/types";
import { useAuth } from "@/auth-context";
import { ErrorAlert } from "@/shared/components/ui/error-alert";
import { TableSkeleton } from "@/shared/components/ui/skeleton";

const PAGE_SIZE = 20;

const STATUS_LABELS: Record<IncidentStatus, string> = {
  created: "Creada",
  analyzing: "Analizando",
  analyzed: "Analizada",
  analysis_failed: "Análisis fallido",
  reviewed: "Revisada",
};

const CONFIDENCE_LABELS: Record<AnalysisConfidence, string> = {
  low: "Baja",
  medium: "Media",
  high: "Alta",
};

const STATUS_OPTIONS: IncidentStatus[] = [
  "created",
  "analyzing",
  "analyzed",
  "analysis_failed",
  "reviewed",
];

const CONFIDENCE_OPTIONS: AnalysisConfidence[] = ["low", "medium", "high"];

export function IncidentsPage() {
  const { canWrite } = useAuth();
  const [status, setStatus] = useState<IncidentStatus | "">("");
  const [confidence, setConfidence] = useState<AnalysisConfidence | "">("");
  const [pendingOnly, setPendingOnly] = useState(false);
  const [offset, setOffset] = useState(0);

  const query = useQuery({
    queryKey: ["incidents", status, confidence, pendingOnly, offset],
    queryFn: ({ signal }) =>
      apiClient.listIncidents(
        {
          limit: PAGE_SIZE,
          offset,
          ...(pendingOnly
            ? { status: "analyzed", sort: "confidence" as const }
            : {
                ...(status ? { status } : {}),
                sort: "created_at" as const,
              }),
          ...(confidence ? { confidence } : {}),
        },
        signal,
      ),
  });

  const total = query.data?.total ?? 0;
  const page = query.data;
  const firstItem = total === 0 ? 0 : (page?.offset ?? offset) + 1;
  const lastItem = page ? page.offset + page.items.length : 0;
  const hasPrevious = offset > 0;
  const hasNext = page ? page.offset + page.items.length < total : false;

  function changeStatus(next: IncidentStatus | "") {
    setStatus(next);
    setPendingOnly(false);
    setOffset(0);
  }

  function changeConfidence(next: AnalysisConfidence | "") {
    setConfidence(next);
    setOffset(0);
  }

  function togglePending() {
    setPendingOnly((current) => {
      const next = !current;
      if (next) setStatus("");
      return next;
    });
    setOffset(0);
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold">Bandeja de revisión</h1>
          <p className="text-muted-foreground">
            Revisa las propuestas del analizador y prioriza las de confianza baja.
          </p>
        </div>
        {canWrite && (
          <Link
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            to="/new"
          >
            Nueva incidencia
          </Link>
        )}
      </div>

      <div className="grid gap-3 rounded-lg border border-border p-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="space-y-1 text-sm">
          <span className="font-medium">Estado</span>
          <select
            className="h-10 w-full rounded-md border border-border bg-background px-3"
            value={pendingOnly ? "analyzed" : status}
            onChange={(event) => changeStatus(event.target.value as IncidentStatus | "")}
            disabled={pendingOnly}
          >
            <option value="">Todos</option>
            {STATUS_OPTIONS.map((option) => (
              <option value={option} key={option}>
                {STATUS_LABELS[option]}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="font-medium">Confianza</span>
          <select
            className="h-10 w-full rounded-md border border-border bg-background px-3"
            value={confidence}
            onChange={(event) => changeConfidence(event.target.value as AnalysisConfidence | "")}
          >
            <option value="">Todas</option>
            {CONFIDENCE_OPTIONS.map((option) => (
              <option value={option} key={option}>
                {CONFIDENCE_LABELS[option]}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-end">
          <button
            type="button"
            aria-pressed={pendingOnly}
            className={`h-10 w-full rounded-md border px-4 text-sm font-medium ${
              pendingOnly
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-background hover:bg-muted"
            }`}
            onClick={togglePending}
          >
            Pendientes de revisión
          </button>
        </div>
        <div className="flex items-end">
          <button
            type="button"
            className="h-10 w-full rounded-md border border-border px-4 text-sm font-medium hover:bg-muted"
            onClick={() => {
              setStatus("");
              setConfidence("");
              setPendingOnly(false);
              setOffset(0);
            }}
          >
            Limpiar filtros
          </button>
        </div>
      </div>

      <p className="text-sm text-muted-foreground" aria-live="polite">
        {query.isSuccess
          ? `${total} incidencia${total === 1 ? "" : "s"}${
              pendingOnly ? " pendiente" + (total === 1 ? "" : "s") + " de revisión" : ""
            } · mostrando ${firstItem}–${lastItem}`
          : "Consultando la bandeja…"}
      </p>

      {query.isPending && (
        <div className="rounded-lg border border-border">
          <TableSkeleton label="Cargando incidencias" />
        </div>
      )}

      {query.isError && <ErrorAlert error={query.error} />}

      {query.isSuccess && (
        <div className="overflow-x-auto rounded-lg border border-border">
          {query.data.items.length === 0 ? (
            <p className="p-6 text-muted-foreground">
              {status || confidence || pendingOnly
                ? "No hay incidencias que cumplan los filtros seleccionados."
                : "No hay incidencias todavía. Crea la primera para empezar el triaje."}
            </p>
          ) : (
            <table className="w-full min-w-[820px] text-left text-sm">
              <caption className="sr-only">
                Incidencias ordenadas por fecha descendente, con la propuesta de la IA y su
                confianza.
              </caption>
              <thead className="bg-muted/60">
                <tr>
                  <th className="px-4 py-3 font-medium" scope="col">
                    Incidencia
                  </th>
                  <th className="px-4 py-3 font-medium" scope="col">
                    Estado
                  </th>
                  <th className="px-4 py-3 font-medium" scope="col">
                    Propuesta IA
                  </th>
                  <th className="px-4 py-3 font-medium" scope="col">
                    Confianza
                  </th>
                  <th className="px-4 py-3 font-medium" scope="col">
                    Fecha
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {query.data.items.map((incident) => {
                  const proposal = incident.final ?? incident.proposal;
                  return (
                    <tr className="align-top" key={incident.id}>
                      <th className="px-4 py-3 font-normal" scope="row">
                        <Link
                          className="font-medium text-primary hover:underline"
                          to={`/incidents/${incident.id}`}
                        >
                          {incident.title}
                        </Link>
                        <span className="block text-xs text-muted-foreground">
                          {incident.id.slice(0, 8)}
                        </span>
                      </th>
                      <td className="px-4 py-3">{STATUS_LABELS[incident.status]}</td>
                      <td className="px-4 py-3">
                        {proposal ? (
                          <>
                            <span className="block">{proposal.category}</span>
                            <span className="block text-xs text-muted-foreground">
                              {proposal.severity} · {proposal.priority}
                            </span>
                          </>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {incident.confidence ? (
                          <span
                            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                              incident.confidence === "low"
                                ? "bg-amber-200 text-amber-900 dark:bg-amber-800 dark:text-amber-50"
                                : "bg-muted text-foreground"
                            }`}
                          >
                            {CONFIDENCE_LABELS[incident.confidence]}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        <time dateTime={incident.created_at}>
                          {new Date(incident.created_at).toLocaleString()}
                        </time>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {query.isSuccess && total > PAGE_SIZE && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            Página {Math.floor(offset / PAGE_SIZE) + 1} de{" "}
            {Math.max(1, Math.ceil(total / PAGE_SIZE))}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              className="h-9 rounded-md border border-border px-3 text-sm font-medium disabled:opacity-50"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={!hasPrevious}
            >
              Anterior
            </button>
            <button
              type="button"
              className="h-9 rounded-md border border-border px-3 text-sm font-medium disabled:opacity-50"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={!hasNext}
            >
              Siguiente
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
