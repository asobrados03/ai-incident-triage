import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { apiClient, clearAccessToken, getAccessToken, setAccessToken } from "@/api/client";

interface AuthContextValue {
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setAuthenticated] = useState(Boolean(getAccessToken()));
  useEffect(() => {
    const handleExpired = () => setAuthenticated(false);
    window.addEventListener("auth:expired", handleExpired);
    return () => window.removeEventListener("auth:expired", handleExpired);
  }, []);
  const value = useMemo(
    () => ({
      isAuthenticated,
      login: async (username: string, password: string) => {
        const response = await apiClient.login(username, password);
        setAccessToken(response.access_token);
        setAuthenticated(true);
      },
      logout: () => {
        clearAccessToken();
        setAuthenticated(false);
      },
    }),
    [isAuthenticated],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
