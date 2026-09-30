import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { usePageMeta } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { HistoryHeading, VersionHistory } from "../../components/VersionHistory";
import { GuiaConflitos } from "../../components/guia/GuiaConflitos";
import { GuiaForm } from "../../components/guia/GuiaForm";
import { GuiaHerdado } from "../../components/guia/GuiaHerdado";
import { api } from "../../lib/api";
import {
  formatGuiaValue,
  guiaFieldLabel,
  guiaPerfilPath,
  useGuiaConta,
  useGuiaContaVersions,
  useGuiaMutations,
} from "../../lib/guia";
import { contaPlatformText, perfilKey } from "../../lib/perfis";

// /app/contas/:id/guia (spec 017, US1): o guia da conta, com o que vem do perfil (só leitura), os
// conflitos (avisos; vale a conta), o formulário da conta e o histórico. Não há leitura da conta
// sozinha: o rótulo e o arquivamento vêm do detalhe do perfil.
export default function ContaGuia() {
  const { id = "" } = useParams();
  const guia = useGuiaConta(id);
  const versions = useGuiaContaVersions(id);
  const { reverterConta, aposConta } = useGuiaMutations();
  const perfilId = guia.data?.guia.perfilId ?? "";
  const perfil = useQuery({ queryKey: perfilKey(perfilId), queryFn: () => api.perfis.get(perfilId), enabled: Boolean(perfilId) });
  const conta = perfil.data?.contas.find((c) => c.id === id);

  const title = conta ? `Guia de @${conta.handle}` : "Guia da conta";
  usePageMeta({
    title,
    breadcrumbs: [
      { label: "Perfis", to: "/app/perfis" },
      ...(perfil.data ? [{ label: perfil.data.perfil.name, to: `/app/perfis/${perfilId}` }] : []),
    ],
  });

  if (guia.isError) return <ApiErrorAlert error={guia.error} />;
  if (guia.isPending) {
    return (
      <div className="space-y-4" aria-live="polite">
        <span className="sr-only">Carregando…</span>
        <Skeleton className="h-40 w-full rounded-xl" />
        <Skeleton className="h-96 w-full rounded-xl" />
      </div>
    );
  }

  const { guia: daConta, perfil: doPerfil, conflitos } = guia.data;
  const arquivado = Boolean(conta?.archived || perfil.data?.perfil.archived);

  return (
    <div className="space-y-6">
      <Link to={guiaPerfilPath(perfilId)} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" aria-hidden="true" />
        Guia do perfil
      </Link>
      <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
        <div className="space-y-6">
          <Card className="shadow-card">
            <CardHeader>
              <CardTitle>
                <h1 className="flex flex-wrap items-center gap-2 text-lg">
                  {title}
                  {conta && <Badge variant="secondary">{contaPlatformText(conta)}</Badge>}
                  {arquivado && <Badge className="bg-dark text-dark-foreground">arquivada</Badge>}
                </h1>
              </CardTitle>
              <CardDescription>
                Complementa o guia do perfil para esta rede. Em conflito, vale o da conta.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <GuiaConflitos conflitos={conflitos} />
              <GuiaForm
                key={daConta.version}
                nivel="conta"
                perfilId={perfilId}
                contaId={id}
                guia={daConta}
                fixasPerfil={doPerfil.campos.hashtagsFixas ?? []}
                contas={perfil.data?.contas ?? []}
                arquivado={arquivado}
              />
            </CardContent>
          </Card>
        </div>
        <div className="space-y-6">
          <Card className="shadow-card">
            <CardHeader>
              <CardTitle>
                <h2>Vem do perfil</h2>
              </CardTitle>
              <CardDescription>Só leitura aqui; edite na aba Guia do perfil.</CardDescription>
            </CardHeader>
            <CardContent>
              <GuiaHerdado perfil={doPerfil} />
            </CardContent>
          </Card>
          <Card className="shadow-card">
            <CardHeader>
              <HistoryHeading>Histórico do guia da conta</HistoryHeading>
              <CardDescription>Reverter cria uma versão nova; nada é apagado.</CardDescription>
            </CardHeader>
            <CardContent>
              {versions.isPending && (
                <p aria-live="polite" className="text-sm text-muted-foreground">
                  Carregando…
                </p>
              )}
              {versions.isError && <ApiErrorAlert error={versions.error} />}
              {versions.data && (
                <VersionHistory
                  versions={versions.data.items}
                  labels={guiaFieldLabel}
                  formatValue={formatGuiaValue}
                  onRevert={async (toVersion) => {
                    await reverterConta(id, daConta.version, toVersion);
                  }}
                  onReload={async () => {
                    await aposConta(id);
                  }}
                />
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
