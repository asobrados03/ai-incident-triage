import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AppLayout } from "@/app";
import { AuthProvider } from "@/auth";
import { render, screen } from "@testing-library/react";

describe("AppLayout", () => {
  it("renders navigation and backend health", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(["health"], { status: "ok", analyzer_backend: "fake" });

    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <MemoryRouter>
            <AppLayout />
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("link", { name: "Triaje de incidencias" })).toBeVisible();
    expect(await screen.findByText("API ok")).toBeVisible();
    expect(screen.getByRole("button", { name: "Cambiar tema" })).toBeVisible();
  });
});
