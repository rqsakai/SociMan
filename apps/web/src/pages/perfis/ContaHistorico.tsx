import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { AppLayout } from "../../components/AppLayout";
import { Card, PageHeader } from "../../components/layout";
import { Alert } from "../../components/ui";
import { VersionHistory } from "../../components/VersionHistory";
import { api } from "../../lib/api";
import { contaFieldLabel, contaVersionsKey, errorText, formatContaValue, platformLabel } from "../../lib/perfis";

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

  return (
    <AppLayout>
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-text"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Voltar
      </button>
      <PageHeader
        title={handle ? `Histórico de @${handle}` : "Histórico da conta"}
        description={platformText || undefined}
      />
      <Card>
        {versions.isPending && <p aria-live="polite">Carregando…</p>}
        {versions.isError && <Alert tone="error">{errorText(versions.error)}</Alert>}
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
          />
        )}
      </Card>
    </AppLayout>
  );
}
