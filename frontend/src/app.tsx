import { Activity, Moon, Sun } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link, Outlet, useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import { Button } from "@/shared/components/ui/button";
import { useTheme } from "@/hooks/use-theme";
import { useAuth } from "@/auth-context";

export function AppLayout() {
  const { theme, toggleTheme } = useTheme();
  const { canWrite, isAdmin, isAnonymous, isAuthenticated, logout, principal } = useAuth();
  const navigate = useNavigate();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => apiClient.health(signal),
    staleTime: 30_000,
    retry: 1,
  });

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border bg-background/95">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link className="font-semibold tracking-tight" to="/">
            Triaje de incidencias
          </Link>
          <div className="flex items-center gap-3">
            <nav className="hidden items-center gap-3 text-sm md:flex">
              <Link to="/">Bandeja</Link>
              {canWrite && <Link to="/new">Nueva</Link>}
              <Link to="/metrics">Métricas</Link>
              {isAdmin && <Link to="/users">Usuarios</Link>}
            </nav>
            {principal && (
              <span
                className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground"
                aria-label="Sesión actual"
              >
                {principal.name} · {principal.role}
                {isAnonymous && " · auth desactivada"}
              </span>
            )}
            <span
              className="inline-flex items-center gap-2 text-sm text-muted-foreground"
              aria-label="Estado del backend"
              aria-live="polite"
            >
              <Activity className="h-4 w-4" aria-hidden="true" />
              {health.isPending && "Comprobando API…"}
              {health.isSuccess && (
                <>
                  <span>API {health.data.status}</span>
                  <span className="rounded-full border border-border px-2 py-0.5 text-xs">
                    analizador: {health.data.analyzer_backend}
                  </span>
                </>
              )}
              {health.isError && "API no disponible"}
            </span>
            <Button variant="ghost" size="sm" onClick={toggleTheme} aria-label="Cambiar tema">
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
            {isAuthenticated && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  logout();
                  navigate("/login");
                }}
              >
                Salir
              </Button>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
