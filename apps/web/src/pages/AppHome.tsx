import { useQuery } from "@tanstack/react-query";
import { AppLayout } from "../components/AppLayout";
import { Card, PageHeader } from "../components/layout";
import { Alert } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/authStore";
import { roleLabel } from "../lib/users";

// Rota protegida de exemplo (§7): placeholder do app real. Demonstra o padrão
// de dados de servidor via TanStack Query (não duplicar `user` no Zustand).
export default function AppHome() {
  const storeUser = useAuth((s) => s.user);

  const { data, isPending, isError } = useQuery({
    queryKey: ["me"],
    queryFn: () => api.auth.me(),
  });

  const user = data?.user ?? storeUser;

  return (
    <AppLayout>
      <PageHeader
        title="Seu app começa aqui"
        description="Rota protegida de exemplo — substitua pelo seu produto."
      />

      <div className="space-y-6">
        {isPending && <p aria-live="polite">Carregando…</p>}
        {isError && <Alert tone="error">Não foi possível carregar seus dados.</Alert>}
        {user && (
          <Card>
            <h2 className="mb-2 text-lg font-medium">Sessão ativa</h2>
            <dl className="space-y-1 text-sm">
              <div className="flex gap-2">
                <dt className="font-medium">Nome:</dt>
                <dd>{user.name}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="font-medium">E-mail:</dt>
                <dd>{user.email}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="font-medium">Papel:</dt>
                <dd>{roleLabel[user.role]}</dd>
              </div>
            </dl>
          </Card>
        )}
      </div>
    </AppLayout>
  );
}
