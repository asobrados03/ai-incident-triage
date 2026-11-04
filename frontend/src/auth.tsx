import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, apiClient, clearAccessToken, setAccessToken } from "@/api/client";
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
          clearAccessToken();
          setStatus("anonymous");
        }
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiError && error.status === 401) {
          clearAccessToken();
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
    setAccessToken(response.access_token);
    setPrincipal({
      name: response.user.username,
      role: response.user.role,
      authenticated: true,
    });
    setStatus("authenticated");
  }, []);

  const logout = useCallback(() => {
    clearAccessToken();
    setPrincipal(null);
    setStatus("unauthenticated");
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
