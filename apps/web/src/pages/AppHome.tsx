import { useQuery } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell, Card, PageHeader } from "../components/layout";
import { Alert, Button } from "../components/ui";
import { api } from "../lib/api";
import { logout } from "../lib/authActions";
import { useAuth } from "../lib/authStore";

// Rota protegida de exemplo (§7): placeholder do app real. Demonstra o padrão
// de dados de servidor via TanStack Query (não duplicar `user` no Zustand).
export default function AppHome() {
  const navigate = useNavigate();
  const storeUser = useAuth((s) => s.user);
  const [loggingOut, setLoggingOut] = useState(false);

  const { data, isPending, isError } = useQuery({
    queryKey: ["me"],
    queryFn: () => api.auth.me(),
  });

  const user = data?.user ?? storeUser;

  async function onLogout() {
    setLoggingOut(true);
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <AppShell
      nav={
        <Button className="!w-auto" variant="ghost" loading={loggingOut} onClick={onLogout}>
          {!loggingOut && <LogOut className="size-4" aria-hidden="true" />}
          Sair
        </Button>
      }
    >
      <PageHeader
        title="Seu app começa aqui"
        description="Rota protegida de exemplo — substitua pelo seu produto."
      />

      <div className="space-y-6">
        {user && !user.emailVerified && (
          <Alert tone="info">
            Confirme seu e-mail para poder entrar novamente depois — enviamos um link para{" "}
            <strong>{user.email}</strong>. (Em dev, o link aparece no console da API.)
          </Alert>
        )}

        {isPending && <p aria-live="polite">Carregando…</p>}
        {isError && <Alert tone="error">Não foi possível carregar seus dados.</Alert>}
        {user && (
          <Card>
            <h2 className="mb-2 text-lg font-medium">Sessão ativa</h2>
            <dl className="space-y-1 text-sm">
              <div className="flex gap-2">
                <dt className="font-medium">Nome:</dt>
                <dd>{user.name ?? "—"}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="font-medium">E-mail:</dt>
                <dd>{user.email}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="font-medium">Verificado:</dt>
                <dd>{user.emailVerified ? "sim" : "não"}</dd>
              </div>
            </dl>
          </Card>
        )}
      </div>
    </AppShell>
  );
}
