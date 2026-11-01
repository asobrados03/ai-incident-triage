import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AuthProvider } from "@/auth";
import { NewIncidentPage } from "@/pages/new-incident";
import { IncidentsPage } from "@/pages/incidents";
import { render, screen } from "@testing-library/react";
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
    server.use(http.get("*/incidents", () => HttpResponse.json({
      items: [{ id: "1", title: "Fallo API", status: "created", created_at: "2026-01-01T00:00:00Z", confidence: null, proposal: null, final: null }],
      total: 1,
      limit: 20,
      offset: 0,
    })));
    renderWithProviders(<IncidentsPage />);
    expect(await screen.findByText("Fallo API")).toBeVisible();
  });

  it("submits a new incident through the API", async () => {
    localStorage.setItem("triage-access-token", "token");
    server.use(http.post("*/incidents", async () => HttpResponse.json({
      id: "created-id",
      title: "Nueva",
      description: "Descripción",
      status: "created",
      created_at: "2026-01-01T00:00:00Z",
      triage: null,
    }, { status: 201 })));
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
});
