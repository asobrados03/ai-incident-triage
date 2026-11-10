import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, apiClient, clearTokens, setTokens } from "@/api/client";
import type { PrincipalResponse } from "@/api/types";
import { AuthContext, type AuthContextValue, type AuthStatus } from "@/auth-context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [principal, setPrincipal] = useState<PrincipalResponse | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadPrincipal() {
      try {
        const current = await apiClient.me();
        if (cancelled) return;
        setPrincipal(current);
        if (current.authenticated) {
          setStatus("authenticated");
        } else {
          clearTokens();
          setStatus("anonymous");
        }
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiError && error.status === 401) {
          clearTokens();
        }
        setPrincipal(null);
        setStatus("unauthenticated");
      }
    }

    function handleExpired() {
      if (cancelled) return;
      setPrincipal(null);
      setStatus("unauthenticated");
    }

    window.addEventListener("auth:expired", handleExpired);
    void loadPrincipal();
    return () => {
      cancelled = true;
      window.removeEventListener("auth:expired", handleExpired);
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const response = await apiClient.login(username, password);
    setTokens({
      access_token: response.access_token,
      refresh_token: response.refresh_token,
    });
    setPrincipal({
      name: response.user.username,
      role: response.user.role,
      authenticated: true,
    });
    setStatus("authenticated");
  }, []);

  const logout = useCallback(async () => {
    try {
      // Revoca el JWT en el backend antes de borrar el token local.
      await apiClient.logout();
    } catch {
      // El cierre de sesión local no debe depender de la disponibilidad del backend.
    } finally {
      clearTokens();
      setPrincipal(null);
      setStatus("unauthenticated");
    }
  }, []);

  const value = useMemo<AuthContextValue>(() => {
    const role = principal?.role ?? null;
    return {
      status,
      principal,
      role,
      isAuthenticated: status === "authenticated",
      isAnonymous: status === "anonymous",
      canWrite: role === "writer" || role === "admin",
      isAdmin: role === "admin",
      login,
      logout,
    };
  }, [login, logout, principal, status]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
