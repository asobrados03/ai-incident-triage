import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { apiClient, NetworkError } from "@/api/client";
import { server } from "@/test/server";

describe("apiClient", () => {
  afterEach(() => server.resetHandlers());

  it("returns typed health data", async () => {
    server.use(
      http.get("/health", () => HttpResponse.json({ status: "ok", analyzer_backend: "fake" })),
    );

    await expect(apiClient.health()).resolves.toEqual({
      status: "ok",
      analyzer_backend: "fake",
    });
  });

  it("normalizes HTTP errors", async () => {
    server.use(
      http.get("/health", () => HttpResponse.json({ detail: "No autorizado" }, { status: 401 })),
    );

    await expect(apiClient.health()).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      message: "No autorizado",
    });
  });

  it("normalizes network errors", async () => {
    server.use(http.get("/health", () => HttpResponse.error()));

    await expect(apiClient.health()).rejects.toBeInstanceOf(NetworkError);
  });
});

it("loads the current principal and role", async () => {
  server.use(
    http.get("*/auth/me", () =>
      HttpResponse.json({
        name: "auditor",
        role: "reader",
        authenticated: true,
      }),
    ),
  );

  await expect(apiClient.me()).resolves.toEqual({
    name: "auditor",
    role: "reader",
    authenticated: true,
  });
});

it("sends user creation payloads to the admin endpoint", async () => {
  let received: unknown = null;
  server.use(
    http.post("*/users", async ({ request }) => {
      received = await request.json();
      return HttpResponse.json(
        {
          id: "user-1",
          username: "nuevo",
          role: "writer",
          active: true,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          last_login_at: null,
        },
        { status: 201 },
      );
    }),
  );

  await apiClient.createUser({
    username: "nuevo",
    password: "nuevo-password-0123456789",
    role: "writer",
  });

  expect(received).toEqual({
    username: "nuevo",
    password: "nuevo-password-0123456789",
    role: "writer",
  });
});
