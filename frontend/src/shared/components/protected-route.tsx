import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "@/auth-context";

export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return <p role="status">Comprobando sesión…</p>;
  }
  if (status === "authenticated" || status === "anonymous") {
    return <Outlet />;
  }
  return <Navigate to="/login" replace state={{ from: location }} />;
}
