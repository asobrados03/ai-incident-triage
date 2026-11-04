import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AuthProvider } from "@/auth";
import { NewIncidentPage } from "@/features/incidents/pages/new-incident";
import { IncidentsPage } from "@/features/incidents/pages/incidents";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/server";

function renderWithProviders(ui: React.ReactNode, initialEntries = ["/"]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("incident flows", () => {
  it("renders the inbox from the paginated API", async () => {
    localStorage.setItem("triage-access-token", "token");
    server.use(
      http.get("*/incidents", () =>
        HttpResponse.json({
          items: [
            {
              id: "1",
              title: "Fallo API",
              status: "created",
              created_at: "2026-01-01T00:00:00Z",
              confidence: null,
              proposal: null,
              final: null,
            },
          ],
          total: 1,
          limit: 20,
          offset: 0,
        }),
      ),
    );
    renderWithProviders(<IncidentsPage />);
    expect(await screen.findByText("Fallo API")).toBeVisible();
  });

  it("hides the create link for readers", async () => {
    server.use(
      http.get("*/auth/me", () =>
        HttpResponse.json({
          name: "auditor",
          role: "reader",
          authenticated: true,
        }),
      ),
      http.get("*/incidents", () =>
        HttpResponse.json({
          items: [
            {
              id: "1",
              title: "Fallo API",
              status: "created",
              created_at: "2026-01-01T00:00:00Z",
              confidence: null,
              proposal: null,
              final: null,
            },
          ],
          total: 1,
          limit: 20,
          offset: 0,
        }),
      ),
    );
    renderWithProviders(<IncidentsPage />);

    expect(await screen.findByText("Fallo API")).toBeVisible();
    expect(screen.queryByRole("link", { name: "Nueva incidencia" })).not.toBeInTheDocument();
  });

  it("submits a new incident through the API", async () => {
    localStorage.setItem("triage-access-token", "token");
    server.use(
      http.post("*/incidents", async () =>
        HttpResponse.json(
          {
            id: "created-id",
            title: "Nueva",
            description: "Descripción",
            status: "created",
            created_at: "2026-01-01T00:00:00Z",
            triage: null,
          },
          { status: 201 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="*" element={<NewIncidentPage />} />
      </Routes>,
      ["/new"],
    );
    await user.type(screen.getByLabelText("title"), "Nueva");
    await user.type(screen.getByLabelText("description"), "Descripción");
    await user.click(screen.getByRole("button", { name: "Crear incidencia" }));
    expect(await screen.findByText("Nueva incidencia")).toBeVisible();
  });

  it("sends status, confidence and pending filters to the API", async () => {
    localStorage.setItem("triage-access-token", "token");
    const urls: string[] = [];
    server.use(
      http.get("*/incidents", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json({
          items: [
            {
              id: "1",
              title: "Fallo API",
              status: "analyzed",
              created_at: "2026-01-01T00:00:00Z",
              confidence: "low",
              proposal: {
                category: "bug",
                severity: "high",
                priority: "urgent",
                summary: "Fallo",
              },
              final: null,
            },
          ],
          total: 1,
          limit: 20,
          offset: 0,
        });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<IncidentsPage />);
    await screen.findByText("Fallo API");

    await user.selectOptions(screen.getByLabelText("Estado"), "reviewed");
    await user.selectOptions(screen.getByLabelText("Confianza"), "high");

    await waitFor(() => {
      const params = new URL(urls.at(-1)!).searchParams;
      expect(params.get("status")).toBe("reviewed");
      expect(params.get("confidence")).toBe("high");
      expect(params.get("sort")).toBe("created_at");
    });

    await user.click(screen.getByRole("button", { name: "Pendientes de revisión" }));

    await waitFor(() => {
      const params = new URL(urls.at(-1)!).searchParams;
      expect(params.get("status")).toBe("analyzed");
      expect(params.get("sort")).toBe("confidence");
    });
  });

  it("paginates the inbox with limit and offset", async () => {
    localStorage.setItem("triage-access-token", "token");
    const urls: string[] = [];
    server.use(
      http.get("*/incidents", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json({
          items: [
            {
              id: "1",
              title: "Fallo API",
              status: "created",
              created_at: "2026-01-01T00:00:00Z",
              confidence: null,
              proposal: null,
              final: null,
            },
          ],
          total: 45,
          limit: 20,
          offset: 0,
        });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<IncidentsPage />);
    await screen.findByText("Fallo API");

    await user.click(screen.getByRole("button", { name: "Siguiente" }));

    await waitFor(() => {
      const params = new URL(urls.at(-1)!).searchParams;
      expect(params.get("limit")).toBe("20");
      expect(params.get("offset")).toBe("20");
    });
  });

  it("sends component chips in the creation payload", async () => {
    localStorage.setItem("triage-access-token", "token");
    let received: Record<string, unknown> | null = null;
    server.use(
      http.post("*/incidents", async ({ request }) => {
        received = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            id: "created-id",
            title: "Nueva",
            description: "Descripción",
            status: "created",
            created_at: "2026-01-01T00:00:00Z",
            triage: null,
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="*" element={<NewIncidentPage />} />
      </Routes>,
      ["/new"],
    );
    await user.type(screen.getByLabelText("title"), "Nueva");
    await user.type(screen.getByLabelText("description"), "Descripción");
    const components = screen.getByLabelText("Componentes afectados");
    await user.type(components, "frontend{Enter}");
    await user.type(components, "api{Enter}");
    await user.click(screen.getByRole("button", { name: "Crear incidencia" }));

    await waitFor(() => expect(received).not.toBeNull());
    expect(received).toMatchObject({ components: ["frontend", "api"] });
  });

  it("shows 422 validation errors next to the field", async () => {
    localStorage.setItem("triage-access-token", "token");
    server.use(
      http.post("*/incidents", () =>
        HttpResponse.json(
          {
            detail: [
              {
                loc: ["body", "title"],
                msg: "String should have at least 1 character",
                type: "string_too_short",
              },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="*" element={<NewIncidentPage />} />
      </Routes>,
      ["/new"],
    );
    await user.type(screen.getByLabelText("title"), "Nueva");
    await user.type(screen.getByLabelText("description"), "Descripción");
    await user.click(screen.getByRole("button", { name: "Crear incidencia" }));

    expect(await screen.findByText(/El campo título es demasiado corto/)).toBeVisible();
    expect(screen.getByText("Revisa los campos del formulario")).toBeVisible();
  });
});
