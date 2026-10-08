import { useQuery } from "@tanstack/react-query";
import { CircleAlert } from "lucide-react";
import { toast } from "sonner";
import { HeaderCard, Page, usePageMeta } from "@/components/shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { PageHeading } from "@/components/PageHeading";
import { ChangePasswordForm } from "../components/ChangePasswordForm";
import { api } from "../lib/api";
import { useAuth } from "../lib/authStore";
import { initials } from "../lib/perfis";
import { roleLabel } from "../lib/users";

// /app/conta: "quem sou eu" e troca voluntária de senha.
export default function Account() {
  usePageMeta({ title: "Minha conta" });
  const storeUser = useAuth((s) => s.user);
  const { data, isError } = useQuery({ queryKey: ["me"], queryFn: () => api.auth.me() });
  const user = data?.user ?? storeUser;

  return (
    <Page>
      <PageHeading title="Minha conta" description="Seus dados de acesso e a troca de senha." />
      {isError && (
        <Alert variant="destructive">
          <CircleAlert aria-hidden="true" />
          <AlertDescription>Não foi possível carregar seus dados.</AlertDescription>
        </Alert>
      )}
      {user && (
        <div>
          <div className="h-28 rounded-xl bg-sidebar-gradient shadow-card sm:h-32" aria-hidden="true" />
          <div className="relative mx-3 -mt-12 flex flex-wrap items-center gap-4 rounded-xl bg-card p-4 shadow-card sm:mx-6">
            <span
              aria-hidden="true"
              className="tone-primary inline-flex size-16 shrink-0 items-center justify-center rounded-full text-lg font-semibold"
            >
              {initials(user.name)}
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="truncate text-xl font-bold">Seus dados</h2>
              <dl className="mt-1 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
                <dt className="font-medium text-muted-foreground">Nome</dt>
                <dd className="min-w-0 truncate">{user.name}</dd>
                <dt className="font-medium text-muted-foreground">E-mail</dt>
                <dd className="min-w-0 break-all">{user.email}</dd>
                <dt className="font-medium text-muted-foreground">Papel</dt>
                <dd>
                  <Badge variant="secondary">{roleLabel[user.role]}</Badge>
                </dd>
              </dl>
            </div>
          </div>
        </div>
      )}
      <HeaderCard title="Trocar senha" description="As outras sessões são encerradas depois da troca.">
        <div className="max-w-md">
          <ChangePasswordForm onSuccess={() => toast.success("Senha trocada. As outras sessões foram encerradas.")} />
        </div>
      </HeaderCard>
    </Page>
  );
}
