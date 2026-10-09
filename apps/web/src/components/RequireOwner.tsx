import { ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useAuth } from "../lib/authStore";

// Esconde as telas de gestão de quem não é dono. A autoridade continua sendo o
// servidor (403 forbidden); isto só evita mostrar uma tela que não funcionaria.
// Fica dentro do AppShell (rota de layout), então o aviso já sai com o menu.
export function RequireOwner({ children }: { children: ReactNode }) {
  const role = useAuth((s) => s.user?.role);
  if (role !== "dono") {
    return (
      <Alert variant="destructive" className="mt-2">
        <ShieldAlert aria-hidden="true" />
        <AlertTitle>Sem permissão</AlertTitle>
        <AlertDescription>Esta área é só para o dono.</AlertDescription>
      </Alert>
    );
  }
  return <>{children}</>;
}
