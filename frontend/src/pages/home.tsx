import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

export function HomePage() {
  return (
    <section className="space-y-6">
      <div className="space-y-3">
        <p className="text-sm font-medium text-primary">Panel operativo</p>
        <h1 className="text-4xl font-semibold tracking-tight">Gestiona el triaje con contexto.</h1>
        <p className="max-w-2xl text-lg text-muted-foreground">
          La base del frontend está lista para conectar la bandeja, análisis y revisión humana.
        </p>
      </div>
      <Link
        className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:opacity-90"
        to="/incidents"
      >
        Ver incidencias
      </Link>
    </section>
  );
}
