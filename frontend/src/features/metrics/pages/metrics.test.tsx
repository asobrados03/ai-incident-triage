import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { MetricsPage } from "@/features/metrics/pages/metrics";
import { server } from "@/test/server";

function renderMetrics() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MetricsPage />
    </QueryClientProvider>,
  );
}

describe("review metrics", () => {
  it("shows a valid empty state without reviews", async () => {
    server.use(
      http.get("*/review-metrics", () =>
        HttpResponse.json({
          total_reviewed: 0,
          accepted_without_changes: 0,
          acceptance_rate: 0,
          field_accuracy: {},
          confusion_matrices: {},
          corrections_by_confidence: {},
        }),
      ),
    );

    renderMetrics();

    expect(await screen.findByText(/Todavía no hay revisiones humanas/)).toBeVisible();
    expect(screen.getByLabelText("Aviso de fiabilidad de las métricas")).toHaveTextContent(
      "Solo hay 0 revisiones",
    );
    expect(screen.getByLabelText("Aviso de fiabilidad de las métricas")).toHaveTextContent(
      "plumbing",
    );
  });

  it("renders accuracy, confusion matrices and corrections with data", async () => {
    server.use(
      http.get("*/review-metrics", () =>
        HttpResponse.json({
          total_reviewed: 2,
          accepted_without_changes: 1,
          acceptance_rate: 0.5,
          field_accuracy: {
            category: { total: 2, correct: 1, accuracy: 0.5 },
            severity: { total: 2, correct: 2, accuracy: 1 },
          },
          confusion_matrices: {
            category: { bug: { bug: 1, feature: 1 } },
            severity: { medium: { critical: 1, medium: 1 } },
          },
          corrections_by_confidence: {
            low: {
              total_reviews: 1,
              corrected_reviews: 1,
              accepted_without_changes: 0,
              correction_rate: 1,
            },
            medium: {
              total_reviews: 1,
              corrected_reviews: 0,
              accepted_without_changes: 1,
              correction_rate: 0,
            },
          },
        }),
      ),
    );

    renderMetrics();

    expect(await screen.findByText("Tasa de aceptación")).toBeVisible();
    expect(screen.getByText("Acierto por campo")).toBeVisible();
    expect(screen.getByText("50% (1/2)")).toBeVisible();

    const categoryTable = screen.getByRole("table", {
      name: "Matriz de confusión de Categoría: valor propuesto por la IA frente al valor final.",
    });
    expect(categoryTable).toBeVisible();
    expect(categoryTable).toHaveTextContent("bug");
    expect(categoryTable).toHaveTextContent("feature");

    expect(screen.getByLabelText("Aviso de fiabilidad de las métricas")).toHaveTextContent(
      "Solo hay 2 revisiones",
    );
    expect(screen.getByLabelText("Aviso de fiabilidad de las métricas")).toHaveTextContent(
      "plumbing",
    );
  });
});
