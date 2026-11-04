import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { UserResponse } from "@/api/types";
import { UsersPage } from "@/pages/users";
import { server } from "@/test/server";

const ADMIN: UserResponse = {
  id: "user-admin",
  username: "root",
  role: "admin",
  active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  last_login_at: null,
};

const READER: UserResponse = {
  id: "user-reader",
  username: "lector",
  role: "reader",
  active: true,
  created_at: "2026-01-02T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  last_login_at: "2026-01-03T00:00:00Z",
};

function renderUsers() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <UsersPage />
    </QueryClientProvider>,
  );
}

function mockList(items: UserResponse[] = [ADMIN, READER]) {
  server.use(
    http.get("*/users", () =>
      HttpResponse.json({
        items,
        total: items.length,
        limit: 100,
        offset: 0,
      }),
    ),
  );
}

describe("users management", () => {
  it("lists users and creates one with the selected role", async () => {
    mockList();
    let received: Record<string, unknown> | null = null;
    server.use(
      http.post("*/users", async ({ request }) => {
        received = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            ...READER,
            id: "user-new",
            username: "nuevo",
            role: "writer",
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderUsers();

    expect(await screen.findByText("root")).toBeVisible();
    expect(screen.getByText("lector")).toBeVisible();

    await user.type(screen.getByLabelText("Usuario"), "nuevo");
    await user.type(screen.getByLabelText("Contraseña inicial"), "nuevo-password-0123456789");
    await user.selectOptions(screen.getByLabelText("Rol"), "writer");
    await user.click(screen.getByRole("button", { name: "Crear usuario" }));

    await waitFor(() => expect(received).not.toBeNull());
    expect(received).toEqual({
      username: "nuevo",
      password: "nuevo-password-0123456789",
      role: "writer",
    });
  });

  it("deactivates a user without deleting the record", async () => {
    mockList([READER]);
    let received: Record<string, unknown> | null = null;
    server.use(
      http.patch("*/users/user-reader", async ({ request }) => {
        received = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...READER, active: false });
      }),
    );
    const user = userEvent.setup();
    renderUsers();
    await screen.findByText("lector");

    await user.click(screen.getByRole("button", { name: "Desactivar lector" }));

    await waitFor(() => expect(received).toEqual({ active: false }));
  });

  it("changes a user role from the table", async () => {
    mockList([READER]);
    let received: Record<string, unknown> | null = null;
    server.use(
      http.patch("*/users/user-reader", async ({ request }) => {
        received = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...READER, role: "writer" });
      }),
    );
    const user = userEvent.setup();
    renderUsers();
    await screen.findByText("lector");

    await user.selectOptions(screen.getByLabelText("Rol de lector"), "writer");

    await waitFor(() => expect(received).toEqual({ role: "writer" }));
  });
});
