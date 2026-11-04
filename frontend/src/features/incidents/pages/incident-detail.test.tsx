import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import type { IncidentResponse, TriageResult } from "@/api/types";
import { AuthProvider } from "@/auth";
import { IncidentDetailPage } from "@/features/incidents/pages/incident-detail";
import { server } from "@/test/server";

beforeEach(() => {
  server.use(
    http.get("*/auth/me", () =>
      HttpResponse.json({
        name: "editor",
        role: "writer",
        authenticated: true,
      }),
    ),
  );
});

const PROPOSAL: TriageResult = {
  category: "bug",
  severity: "medium",
  priority: "medium",
  summary: "El panel no carga",
  affected_components: ["frontend"],
  missing_information: ["logs del navegador"],
  justification: "Se detectan señales de error en la interfaz.",
  confidence: "medium",
};

function makeIncident(overrides: Partial<IncidentResponse> = {}): IncidentResponse {
  return {
    id: "inc-1",
    title: "El panel no carga",
    description: "Devuelve un error al abrirlo.",
    steps_to_reproduce: "Abrir el panel.",
    expected_behavior: null,
    actual_behavior: null,
    environment: "local",
    components: ["frontend"],
    status: "analyzed",
    created_at: "2026-01-01T00:00:00Z",
    triage: {
      ...PROPOSAL,
      id: "triage-1",
      created_at: "2026-01-01T00:01:00Z",
      review: null,
    },
    ...overrides,
  };
}

function renderDetail() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={["/incidents/inc-1"]}>
          <Routes>
            <Route path="/incidents/:id" element={<IncidentDetailPage />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

function mockIncident(incident: IncidentResponse) {
  server.use(http.get("*/incidents/inc-1", () => HttpResponse.json(incident)));
}

describe("incident detail", () => {
  it("renders the AI to human diff and the persisted checklist", async () => {
    mockIncident(
      makeIncident({
        status: "reviewed",
        triage: {
          ...PROPOSAL,
          id: "triage-1",
          created_at: "2026-01-01T00:01:00Z",
          review: {
            reviewed: true,
            source: "human",
            review_comment: "Impacto confirmado por soporte.",
            review_checklist: ["Revisé la severidad y la prioridad"],
            reviewed_at: "2026-01-01T00:02:00Z",
            final: { ...PROPOSAL, severity: "critical" },
          },
        },
      }),
    );

    renderDetail();

    expect(await screen.findByText("Comparación IA → humano")).toBeVisible();
    expect(screen.getByText("modificado")).toBeVisible();
    expect(screen.getAllByText("igual").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Checklist de revisión")).toHaveTextContent(
      "Revisé la severidad y la prioridad",
    );
    expect(screen.getByText(/Impacto confirmado por soporte/)).toBeVisible();
  });

  it("marks the review as pending and shows the review form", async () => {
    mockIncident(makeIncident());

    renderDetail();

    expect(await screen.findByText("Sin revisar")).toBeVisible();
    expect(screen.getByRole("button", { name: "Guardar revisión" })).toBeVisible();
    expect(screen.getByRole("group", { name: "Checklist de revisión (0/4)" })).toBeVisible();
  });

  it("triggers the analysis with the 'a' shortcut", async () => {
    mockIncident(makeIncident({ status: "created", triage: null }));
    server.use(
      http.post("*/incidents/inc-1/analysis", () =>
        HttpResponse.json(
          makeIncident({
            status: "analyzed",
            triage: {
              ...PROPOSAL,
              id: "triage-1",
              created_at: "2026-01-01T00:01:00Z",
              review: null,
            },
          }),
        ),
      ),
    );

    renderDetail();
    expect(await screen.findByText("Creada")).toBeVisible();

    fireEvent.keyDown(window, { key: "a" });

    expect(await screen.findByText("Analizada")).toBeVisible();
    expect(await screen.findByText("Comparación IA → humano")).toBeVisible();
  });

  it("toggles the keyboard shortcut help with '?' and closes it with Escape", async () => {
    mockIncident(makeIncident());
    renderDetail();
    await screen.findByText("Comparación IA → humano");

    fireEvent.keyDown(window, { key: "?" });
    expect(screen.getByRole("note", { name: "Atajos de teclado" })).toBeVisible();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("note", { name: "Atajos de teclado" })).not.toBeInTheDocument();
  });

  it("shows read-only mode for readers", async () => {
    server.use(
      http.get("*/auth/me", () =>
        HttpResponse.json({
          name: "auditor",
          role: "reader",
          authenticated: true,
        }),
      ),
    );
    mockIncident(makeIncident());

    renderDetail();

    expect(await screen.findByText(/Modo solo lectura/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Guardar revisión" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aceptar propuesta" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Analizar incidencia" })).not.toBeInTheDocument();
  });

  it("submits corrections and checklist items", async () => {
    mockIncident(makeIncident());
    let received: Record<string, unknown> | null = null;
    server.use(
      http.patch("*/incidents/inc-1/triage", async ({ request }) => {
        received = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          makeIncident({
            status: "reviewed",
            triage: {
              ...PROPOSAL,
              id: "triage-1",
              created_at: "2026-01-01T00:01:00Z",
              review: {
                reviewed: true,
                source: "human",
                review_comment: "Severidad corregida.",
                review_checklist: ["Revisé la severidad y la prioridad"],
                reviewed_at: "2026-01-01T00:02:00Z",
                final: { ...PROPOSAL, severity: "critical" },
              },
            },
          }),
        );
      }),
    );
    const user = userEvent.setup();
    renderDetail();
    await screen.findByText("Comparación IA → humano");

    await user.selectOptions(screen.getByLabelText("Severidad"), "critical");
    await user.click(screen.getByLabelText("Revisé la severidad y la prioridad"));
    await user.click(screen.getByLabelText("logs del navegador"));
    await user.type(screen.getByLabelText("Comentario de revisión"), "Severidad corregida.");
    await user.click(screen.getByRole("button", { name: "Guardar revisión" }));

    await waitFor(() => expect(received).not.toBeNull());
    expect(received).toMatchObject({
      severity: "critical",
      affected_components: ["frontend"],
      missing_information: ["logs del navegador"],
      review_checklist: ["Revisé la severidad y la prioridad"],
      review_comment:
        "Severidad corregida.\n\nInformación faltante necesaria:\n- logs del navegador",
    });
    expect(await screen.findByText("Severidad corregida.")).toBeVisible();
  });

  it("shows the pre-send diff and restores the AI value", async () => {
    mockIncident(makeIncident());
    const user = userEvent.setup();
    renderDetail();
    await screen.findByText("Comparación IA → humano");

    await user.selectOptions(screen.getByLabelText("Severidad"), "critical");

    const summary = screen.getByLabelText("Resumen previo al envío");
    expect(summary).toHaveTextContent("Severidad: medium → critical");

    await user.click(screen.getByRole("button", { name: "Aceptar valor IA" }));

    expect(summary).toHaveTextContent("Sin cambios respecto a la propuesta de la IA.");
  });

  it("blocks saving when the structured comment exceeds the limit", async () => {
    mockIncident(makeIncident());
    const user = userEvent.setup();
    renderDetail();
    await screen.findByText("Comparación IA → humano");

    fireEvent.change(screen.getByLabelText("Comentario de revisión"), {
      target: { value: "x".repeat(1960) },
    });
    await user.click(screen.getByLabelText("logs del navegador"));

    expect(screen.getByText(/supera los 2000 caracteres/i)).toBeVisible();
    expect(screen.getByText(/supera el límite/i)).toBeVisible();
    expect(screen.getByRole("button", { name: "Guardar revisión" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Aceptar propuesta" })).toBeDisabled();
  });

  it("warns when the proposal confidence is low", async () => {
    mockIncident(
      makeIncident({
        triage: {
          ...PROPOSAL,
          confidence: "low",
          id: "triage-1",
          created_at: "2026-01-01T00:01:00Z",
          review: null,
        },
      }),
    );

    renderDetail();

    expect(await screen.findByText("Confianza baja de la propuesta")).toBeVisible();
  });

  it("warns about Ollama delays before analyzing", async () => {
    server.use(
      http.get("*/health", () => HttpResponse.json({ status: "ok", analyzer_backend: "ollama" })),
    );
    mockIncident(makeIncident({ status: "created", triage: null }));

    renderDetail();

    expect(await screen.findByText(/El backend usa Ollama/)).toBeVisible();
  });

  it("saves the review with Ctrl+Enter", async () => {
    mockIncident(makeIncident());
    let received: Record<string, unknown> | null = null;
    server.use(
      http.patch("*/incidents/inc-1/triage", async ({ request }) => {
        received = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeIncident({ status: "reviewed" }));
      }),
    );
    renderDetail();
    await screen.findByText("Comparación IA → humano");

    fireEvent.keyDown(window, { key: "Enter", ctrlKey: true });

    await waitFor(() => expect(received).not.toBeNull());
    expect(received).toMatchObject({ category: "bug", severity: "medium" });
  });
});
