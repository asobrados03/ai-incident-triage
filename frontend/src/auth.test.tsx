import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import userEvent from "@testing-library/user-event";

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

  it("revokes the token on logout, clears it and returns to login", async () => {
    const user = userEvent.setup();
    localStorage.setItem("triage-access-token", "session-token");
    localStorage.setItem("triage-refresh-token", "refresh-session-token");
    let logoutCalls = 0;
    let authorization: string | null = null;
    server.use(
      http.get("*/auth/me", () =>
        HttpResponse.json({ name: "root", role: "admin", authenticated: true }),
      ),
      http.post("*/auth/logout", ({ request }) => {
        logoutCalls += 1;
        authorization = request.headers.get("Authorization");
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderWithProviders(
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<p>Bandeja</p>} />
        </Route>
        <Route path="/login" element={<p>Pantalla de acceso</p>} />
      </Routes>,
    );

    await user.click(await screen.findByRole("button", { name: "Salir" }));

    expect(await screen.findByText("Pantalla de acceso")).toBeVisible();
    expect(logoutCalls).toBe(1);
    expect(authorization).toBe("Bearer session-token");
    expect(localStorage.getItem("triage-access-token")).toBeNull();
    expect(localStorage.getItem("triage-refresh-token")).toBeNull();
  });

  it("silently refreshes the access token using refresh token on 401 without user disruption", async () => {
    const { apiClient } = await import("@/api/client");
    localStorage.setItem("triage-access-token", "old-access-token");
    localStorage.setItem("triage-refresh-token", "valid-refresh-token");

    let usersCallCount = 0;
    let refreshCallCount = 0;

    server.use(
      http.get("*/auth/me", () =>
        HttpResponse.json({ name: "admin", role: "admin", authenticated: true }),
      ),
      http.get("*/users", ({ request }) => {
        usersCallCount += 1;
        const authHeader = request.headers.get("Authorization");
        if (authHeader === "Bearer old-access-token") {
          return HttpResponse.json({ detail: "Token expired" }, { status: 401 });
        }
        if (authHeader === "Bearer new-access-token") {
          return HttpResponse.json({ items: [], total: 0, limit: 10, offset: 0 });
        }
        return HttpResponse.json({ detail: "Unauthorized" }, { status: 401 });
      }),
      http.post("*/auth/refresh", async ({ request }) => {
        refreshCallCount += 1;
        const body = (await request.json()) as { refresh_token: string };
        if (body.refresh_token === "valid-refresh-token") {
          return HttpResponse.json({
            access_token: "new-access-token",
            refresh_token: "rotated-refresh-token",
            token_type: "bearer",
            expires_in: 900,
            refresh_expires_in: 604800,
          });
        }
        return HttpResponse.json({ detail: "Invalid refresh token" }, { status: 401 });
      }),
    );

    const result = await apiClient.listUsers();
    expect(result).toEqual({ items: [], total: 0, limit: 10, offset: 0 });
    expect(usersCallCount).toBe(2);
    expect(refreshCallCount).toBe(1);
    expect(localStorage.getItem("triage-access-token")).toBe("new-access-token");
    expect(localStorage.getItem("triage-refresh-token")).toBe("rotated-refresh-token");
  });

  it("redirects from any protected route to login when both access and refresh tokens expire", async () => {
    localStorage.setItem("triage-access-token", "expired-token");
    localStorage.setItem("triage-refresh-token", "expired-refresh-token");
    server.use(
      http.get("*/auth/me", () =>
        HttpResponse.json({ name: "analyst", role: "writer", authenticated: true }),
      ),
      http.post("*/auth/refresh", () =>
        HttpResponse.json({ detail: "Refresh token expired" }, { status: 401 }),
      ),
      http.get("*/review-metrics", () =>
        HttpResponse.json({ detail: "Token expired or invalid" }, { status: 401 }),
      ),
    );

    function MetricsComponent() {
      return (
        <div>
          <h2>Métricas protegidas</h2>
          <button
            onClick={() => {
              void fetch("/review-metrics", {
                headers: { Authorization: `Bearer ${localStorage.getItem("triage-access-token")}` },
              }).then((res) => {
                if (res.status === 401) {
                  localStorage.removeItem("triage-access-token");
                  window.dispatchEvent(new Event("auth:expired"));
                }
              });
            }}
          >
            Cargar métricas
          </button>
        </div>
      );
    }

    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/metrics" element={<MetricsComponent />} />
        </Route>
        <Route path="/login" element={<p>Pantalla de acceso</p>} />
      </Routes>,
      ["/metrics"],
    );

    expect(await screen.findByText("Métricas protegidas")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Cargar métricas" }));

    expect(await screen.findByText("Pantalla de acceso")).toBeVisible();
    expect(localStorage.getItem("triage-access-token")).toBeNull();
  });

  it("handles apiClient 401 response anywhere in the app and redirects to login", async () => {
    const { apiClient } = await import("@/api/client");
    localStorage.setItem("triage-access-token", "expiring-token");
    server.use(
      http.get("*/auth/me", () =>
        HttpResponse.json({ name: "admin", role: "admin", authenticated: true }),
      ),
      http.get("*/users", () =>
        HttpResponse.json({ detail: "Missing or invalid bearer token" }, { status: 401 }),
      ),
    );

    function UsersView() {
      return (
        <div>
          <h2>Gestión de usuarios</h2>
          <button
            onClick={() => {
              void apiClient.listUsers().catch(() => {});
            }}
          >
            Consultar usuarios
          </button>
        </div>
      );
    }

    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/users" element={<UsersView />} />
        </Route>
        <Route path="/login" element={<p>Pantalla de acceso</p>} />
      </Routes>,
      ["/users"],
    );

    expect(await screen.findByText("Gestión de usuarios")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Consultar usuarios" }));

    expect(await screen.findByText("Pantalla de acceso")).toBeVisible();
    expect(localStorage.getItem("triage-access-token")).toBeNull();
  });
});
