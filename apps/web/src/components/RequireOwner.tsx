import type { ReactNode } from "react";
import { useAuth } from "../lib/authStore";
import { AppLayout } from "./AppLayout";
import { Alert } from "./ui";

// Esconde as telas de gestão de quem não é dono. A autoridade continua sendo o
// servidor (403 forbidden); isto só evita mostrar uma tela que não funcionaria.
export function RequireOwner({ children }: { children: ReactNode }) {
  const role = useAuth((s) => s.user?.role);
  if (role !== "dono") {
    return (
      <AppLayout>
        <Alert tone="error">Sem permissão. Esta área é só para o dono.</Alert>
      </AppLayout>
    );
  }
  return <>{children}</>;
}
