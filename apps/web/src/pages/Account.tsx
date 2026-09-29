import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { AppLayout } from "../components/AppLayout";
import { ChangePasswordForm } from "../components/ChangePasswordForm";
import { Card, PageHeader } from "../components/layout";
import { Alert } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/authStore";
import { roleLabel } from "../lib/users";

// /app/conta: "quem sou eu" e troca voluntária de senha.
export default function Account() {
  const storeUser = useAuth((s) => s.user);
  const [changed, setChanged] = useState(false);
  const { data, isError } = useQuery({ queryKey: ["me"], queryFn: () => api.auth.me() });
  const user = data?.user ?? storeUser;

  return (
    <AppLayout>
      <PageHeader title="Minha conta" />
      <div className="space-y-6">
        {isError && <Alert tone="error">Não foi possível carregar seus dados.</Alert>}
        {user && (
          <Card>
            <h2 className="mb-2 text-lg font-medium">Seus dados</h2>
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
        <Card className="max-w-md">
          <h2 className="mb-4 text-lg font-medium">Trocar senha</h2>
          <div className="space-y-4">
            {changed && (
              <Alert tone="success">Senha trocada. As outras sessões foram encerradas.</Alert>
            )}
            <ChangePasswordForm onSuccess={() => setChanged(true)} />
          </div>
        </Card>
      </div>
    </AppLayout>
  );
}
