import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, History } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Page, usePageMeta } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { VersionHistory } from "../../components/VersionHistory";
import { api } from "../../lib/api";
import { formatKitValue, kitFieldLabel, kitKey, kitVersionsKey } from "../../lib/marca";
import { perfilKey } from "../../lib/perfis";

// /app/perfis/:id/kit/historico: histórico do kit com antes/depois por seção (FR-007). Reverter
// só aparece para o dono (VersionHistory) e cria uma versão nova.
export default function KitHistorico() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const perfil = useQuery({ queryKey: perfilKey(id), queryFn: () => api.perfis.get(id) });
  const kit = useQuery({ queryKey: kitKey(id), queryFn: () => api.kit.get(id) });
  const versions = useQuery({ queryKey: kitVersionsKey(id), queryFn: () => api.kit.versions(id) });
  const name = perfil.data?.perfil.name;
  usePageMeta({
    title: "Histórico do kit",
    breadcrumbs: [{ label: "Perfis", to: "/app/perfis" }, ...(name ? [{ label: name, to: `/app/perfis/${id}?aba=marca` }] : [])],
  });

  async function reload() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: kitKey(id) }),
      queryClient.invalidateQueries({ queryKey: kitVersionsKey(id) }),
    ]);
  }

  return (
    <Page>
      <Button type="button" variant="ghost" size="sm" className="-ml-2 text-muted-foreground" asChild>
        <Link to={`/app/perfis/${id}?aba=marca`}>
          <ArrowLeft aria-hidden="true" />
          Voltar para a marca
        </Link>
      </Button>
      <Card className="shadow-card">
        <CardHeader>
          <h1 className="flex items-center gap-2 text-lg leading-none font-semibold">
            <History className="size-5 text-muted-foreground" aria-hidden="true" />
            {name ? `Histórico do kit de ${name}` : "Histórico do kit"}
          </h1>
          <CardDescription>Da versão mais recente para a mais antiga. Reverter cria uma versão nova; nada é apagado.</CardDescription>
        </CardHeader>
        <CardContent>
          {(versions.isPending || kit.isPending) && (
            <p aria-live="polite" className="text-sm text-muted-foreground">
              Carregando…
            </p>
          )}
          {versions.isError && <ApiErrorAlert error={versions.error} />}
          {kit.isError && <ApiErrorAlert error={kit.error} />}
          {versions.data && kit.data && (
            <VersionHistory
              versions={versions.data.items}
              labels={kitFieldLabel}
              formatValue={formatKitValue}
              onRevert={async (toVersion) => {
                await api.kit.revert(id, kit.data.kit.version, toVersion);
                await reload();
              }}
              onReload={reload}
            />
          )}
        </CardContent>
      </Card>
    </Page>
  );
}
