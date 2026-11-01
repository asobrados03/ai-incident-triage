import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";

export function IncidentsPage() {
  const query = useQuery({
    queryKey: ["incidents"],
    queryFn: ({ signal }) => apiClient.listIncidents({ limit: 20 }, signal),
  });

  return (
    <section className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
        <h1 className="text-3xl font-semibold">Incidencias</h1>
        <p className="text-muted-foreground">Bandeja conectada al contrato paginado del backend.</p>
        </div>
        <Link className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground" to="/new">Nueva incidencia</Link>
      </div>
      {query.isPending && <p role="status">Cargando incidencias…</p>}
      {query.isError && <p role="alert">{query.error.message}</p>}
      {query.isSuccess && (
        <div className="rounded-lg border border-border">
          {query.data.items.length === 0 ? (
            <p className="p-6 text-muted-foreground">No hay incidencias todavía.</p>
          ) : (
            <ul className="divide-y divide-border">
              {query.data.items.map((incident) => (
                <li className="p-4" key={incident.id}>
                  <Link className="font-medium hover:text-primary" to={`/incidents/${incident.id}`}>{incident.title}</Link>
                  <p className="text-sm text-muted-foreground">
                    {incident.status} · confianza {incident.confidence ?? "—"}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
