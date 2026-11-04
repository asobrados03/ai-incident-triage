import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AppLayout } from "@/app";
import { AuthProvider } from "@/auth";
import { ProtectedRoute } from "@/shared/components/protected-route";
import { server } from "@/test/server";
import { render, screen } from "@testing-library/react";

function renderWithProviders(ui: React.ReactNode, initialEntries = ["/"]) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

function mockHealth() {
  server.use(
    http.get("*/health", () => HttpResponse.json({ status: "ok", analyzer_backend: "fake" })),
  );
}

describe("authentication and roles", () => {
  it("allows anonymous access when the backend has auth disabled", async () => {
    renderWithProviders(
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<p>Contenido privado</p>} />
        </Route>
        <Route path="/login" element={<p>Pantalla de acceso</p>} />
      </Routes>,
    );

    expect(await screen.findByText("Contenido privado")).toBeVisible();
  });

  it("redirects to login when the backend requires a token", async () => {
    server.use(
      http.get("*/auth/me", () =>
        HttpResponse.json({ detail: "Missing or invalid bearer token" }, { status: 401 }),
      ),
    );

    renderWithProviders(
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<p>Contenido privado</p>} />
        </Route>
        <Route path="/login" element={<p>Pantalla de acceso</p>} />
      </Routes>,
    );

    expect(await screen.findByText("Pantalla de acceso")).toBeVisible();
  });

  it("hides write and admin navigation for readers", async () => {
    mockHealth();
    server.use(
      http.get("*/auth/me", () =>
        HttpResponse.json({ name: "auditor", role: "reader", authenticated: true }),
      ),
    );

    renderWithProviders(
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<p>Bandeja</p>} />
        </Route>
      </Routes>,
    );

    expect(await screen.findByText(/auditor · reader/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Bandeja" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Métricas" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Nueva" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Usuarios" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Salir" })).toBeVisible();
  });

  it("shows write and admin navigation for admins", async () => {
    mockHealth();
    server.use(
      http.get("*/auth/me", () =>
        HttpResponse.json({ name: "root", role: "admin", authenticated: true }),
      ),
    );

    renderWithProviders(
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<p>Bandeja</p>} />
        </Route>
      </Routes>,
    );

    expect(await screen.findByText(/root · admin/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Nueva" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Usuarios" })).toBeVisible();
  });
});
