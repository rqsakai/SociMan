import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, History } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { usePageMeta } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { VersionHistory } from "../../components/VersionHistory";
import { api } from "../../lib/api";
import { contaFieldLabel, contaVersionsKey, formatContaValue, platformLabel } from "../../lib/perfis";

// /app/contas/:id/historico: histórico de uma conta em página própria (FR-012). Não há rota de
// leitura da conta sozinha; o título e a versão atual vêm da versão mais recente.
export default function ContaHistorico() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const versions = useQuery({ queryKey: contaVersionsKey(id), queryFn: () => api.contas.versions(id) });

  const latest = versions.data?.items[0];
  const handle = typeof latest?.after.handle === "string" ? latest.after.handle : null;
  const platform = typeof latest?.after.platform === "string" ? latest.after.platform : null;
  const platformName = typeof latest?.after.platform_name === "string" ? latest.after.platform_name : "";
  const platformText =
    platform === "outra" ? platformName || platformLabel.outra : (platformLabel[platform as keyof typeof platformLabel] ?? "");

  const title = handle ? `Histórico de @${handle}` : "Histórico da conta";
  usePageMeta({ title, breadcrumbs: [{ label: "Perfis", to: "/app/perfis" }] });

  async function reload() {
    await queryClient.invalidateQueries({ queryKey: contaVersionsKey(id) });
  }

  return (
    <div className="space-y-6">
      <Button type="button" variant="ghost" size="sm" className="-ml-2 text-muted-foreground" onClick={() => navigate(-1)}>
        <ArrowLeft aria-hidden="true" />
        Voltar
      </Button>
      <Card className="shadow-card">
        <CardHeader>
          <h1 className="flex items-center gap-2 text-lg leading-none font-semibold">
            <History className="size-5 text-muted-foreground" aria-hidden="true" />
            {title}
          </h1>
          {platformText && <CardDescription>{platformText}</CardDescription>}
        </CardHeader>
        <CardContent>
          {versions.isPending && (
            <p aria-live="polite" className="text-sm text-muted-foreground">
              Carregando…
            </p>
          )}
          {versions.isError && <ApiErrorAlert error={versions.error} />}
          {versions.data && latest && (
            <VersionHistory
              versions={versions.data.items}
              labels={contaFieldLabel}
              formatValue={formatContaValue}
              onRevert={async (toVersion) => {
                const { conta } = await api.contas.revert(id, latest.version, toVersion);
                await Promise.all([
                  queryClient.invalidateQueries({ queryKey: contaVersionsKey(id) }),
                  queryClient.invalidateQueries({ queryKey: ["perfil", conta.perfilId] }),
                  queryClient.invalidateQueries({ queryKey: ["perfis"] }),
                ]);
              }}
              onReload={reload}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
