import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { ApiError, apiClient, NetworkError } from "@/api/client";
import { server } from "@/test/server";

describe("apiClient", () => {
  afterEach(() => server.resetHandlers());

  it("returns typed health data", async () => {
    server.use(http.get("/health", () => HttpResponse.json({ status: "ok", analyzer_backend: "fake" })));

    await expect(apiClient.health()).resolves.toEqual({
      status: "ok",
      analyzer_backend: "fake",
    });
  });

  it("normalizes HTTP errors", async () => {
    server.use(http.get("/health", () => HttpResponse.json({ detail: "No autorizado" }, { status: 401 })));

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
