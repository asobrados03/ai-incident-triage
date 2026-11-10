import type {
  ApiErrorPayload,
  HealthResponse,
  IncidentListPage,
  IncidentCreatePayload,
  IncidentResponse,
  LoginResponse,
  PrincipalResponse,
  ReviewMetricsResponse,
  TokenRefreshResponse,
  TriageReviewPayload,
  UserCreatePayload,
  UserListPage,
  UserResponse,
  UserUpdatePayload,
} from "@/api/types";

const configuredApiUrl = import.meta.env.VITE_API_URL;
const API_BASE_URL = (
  configuredApiUrl ?? (import.meta.env.MODE === "test" ? "" : "http://127.0.0.1:8000")
).replace(/\/$/, "");
const ACCESS_TOKEN_KEY = "triage-access-token";
const REFRESH_TOKEN_KEY = "triage-refresh-token";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setRefreshToken(token: string): void {
  localStorage.setItem(REFRESH_TOKEN_KEY, token);
}

export function clearRefreshToken(): void {
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function setTokens(tokens: { access_token: string; refresh_token: string }): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
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

let refreshPromise: Promise<string | null> | null = null;

async function performTokenRefresh(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return null;
  }
  try {
    const response = await fetch(url("/auth/refresh"), {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) {
      clearTokens();
      return null;
    }
    const data = (await response.json()) as TokenRefreshResponse;
    setTokens({
      access_token: data.access_token,
      refresh_token: data.refresh_token,
    });
    return data.access_token;
  } catch {
    clearTokens();
    return null;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
  isRetry = false,
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

  if (response.status === 401) {
    if (path === "/auth/login" || path === "/auth/refresh" || isRetry) {
      clearTokens();
      if (path !== "/auth/login") {
        window.dispatchEvent(new Event("auth:expired"));
      }
    } else {
      const refreshToken = getRefreshToken();
      if (refreshToken) {
        if (!refreshPromise) {
          refreshPromise = performTokenRefresh().finally(() => {
            refreshPromise = null;
          });
        }
        const refreshedToken = await refreshPromise;
        if (refreshedToken) {
          return request<T>(path, init, signal, true);
        }
      }
      clearTokens();
      window.dispatchEvent(new Event("auth:expired"));
    }
  }

  const payload = await response.json().catch(() => undefined);
  if (!response.ok) {
    const rawDetail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? (payload as ApiErrorPayload).detail
        : undefined;
    const detail =
      typeof rawDetail === "string" ? rawDetail : `La API respondió con ${response.status}`;
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
  refreshToken: (refreshToken: string) =>
    request<TokenRefreshResponse>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    }),
  me: (signal?: AbortSignal) => request<PrincipalResponse>("/auth/me", {}, signal),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  listUsers: (params: { limit?: number; offset?: number } = {}, signal?: AbortSignal) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) query.set(key, String(value));
    });
    return request<UserListPage>(`/users${query.size ? `?${query.toString()}` : ""}`, {}, signal);
  },
  createUser: (payload: UserCreatePayload) =>
    request<UserResponse>("/users", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateUser: (id: string, payload: UserUpdatePayload) =>
    request<UserResponse>(`/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deactivateUser: (id: string) => request<UserResponse>(`/users/${id}`, { method: "DELETE" }),
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
    params: {
      limit?: number;
      offset?: number;
      status?: string;
      confidence?: string;
      sort?: "created_at" | "confidence";
    } = {},
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
