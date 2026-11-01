import type {
  ApiErrorPayload,
  HealthResponse,
  IncidentListPage,
  IncidentCreatePayload,
  IncidentResponse,
  LoginResponse,
  ReviewMetricsResponse,
  TriageReviewPayload,
} from "@/api/types";

const API_BASE_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const TOKEN_KEY = "triage-access-token";

export function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly payload?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class NetworkError extends Error {
  constructor(message = "No se pudo conectar con el backend") {
    super(message);
    this.name = "NetworkError";
  }
}

function url(path: string) {
  return `${API_BASE_URL}${path}`;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url(path), {
      ...init,
      ...(signal && typeof window === "undefined" ? { signal } : {}),
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}),
        ...init.headers,
      },
    });
  } catch (error) {
    throw new NetworkError(error instanceof Error ? error.message : undefined);
  }

  const payload = await response.json().catch(() => undefined);
  if (!response.ok) {
    if (response.status === 401) {
      clearAccessToken();
      window.dispatchEvent(new Event("auth:expired"));
    }
    const detail =
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof (payload as ApiErrorPayload).detail === "string"
        ? (payload as ApiErrorPayload).detail!
        : `La API respondió con ${response.status}`;
    throw new ApiError(response.status, detail, payload);
  }
  return payload as T;
}

export const apiClient = {
  health: (signal?: AbortSignal) => request<HealthResponse>("/health", {}, signal),
  login: (username: string, password: string) =>
    request<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  createIncident: (payload: IncidentCreatePayload) =>
    request<IncidentResponse>("/incidents", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getIncident: (id: string, signal?: AbortSignal) =>
    request<IncidentResponse>(`/incidents/${id}`, {}, signal),
  analyzeIncident: (id: string) =>
    request<IncidentResponse>(`/incidents/${id}/analysis`, { method: "POST" }),
  reviewIncident: (id: string, payload: TriageReviewPayload) =>
    request<IncidentResponse>(`/incidents/${id}/triage`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  reviewMetrics: (signal?: AbortSignal) =>
    request<ReviewMetricsResponse>("/review-metrics", {}, signal),
  listIncidents: (
    params: { limit?: number; offset?: number; status?: string; confidence?: string } = {},
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) query.set(key, String(value));
    });
    return request<IncidentListPage>(
      `/incidents${query.size ? `?${query.toString()}` : ""}`,
      {},
      signal,
    );
  },
};
