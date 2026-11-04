import { createContext, useContext } from "react";

import type { PrincipalResponse, Role } from "@/api/types";

export type AuthStatus = "loading" | "authenticated" | "anonymous" | "unauthenticated";

export interface AuthContextValue {
  status: AuthStatus;
  principal: PrincipalResponse | null;
  role: Role | null;
  isAuthenticated: boolean;
  isAnonymous: boolean;
  canWrite: boolean;
  isAdmin: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
