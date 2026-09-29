import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../lib/authStore";

export function RequireAuth({ children }: { children: ReactNode }) {
  const status = useAuth((s) => s.status);
  if (status === "unknown") {
    return <p className="p-8 text-sm" aria-live="polite">Carregando…</p>;
  }
  if (status === "guest") {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
