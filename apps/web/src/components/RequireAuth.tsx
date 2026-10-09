import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../lib/authStore";

export const CHANGE_PASSWORD_PATH = "/trocar-senha";

export function RequireAuth({ children }: { children: ReactNode }) {
  const status = useAuth((s) => s.status);
  const mustChangePassword = useAuth((s) => s.user?.mustChangePassword ?? false);
  const location = useLocation();
  if (status === "unknown") {
    return <p className="p-8 text-sm" aria-live="polite">Carregando…</p>;
  }
  if (status === "guest") {
    // Guarda a rota pedida para o Login voltar a ela depois de entrar.
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  // Senha provisória: nada do app abre antes da troca (o servidor também recusa).
  if (mustChangePassword && location.pathname !== CHANGE_PASSWORD_PATH) {
    return <Navigate to={CHANGE_PASSWORD_PATH} replace />;
  }
  return <>{children}</>;
}
