import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, History } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Page, usePageMeta } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { VersionHistory } from "../../components/VersionHistory";
import { api } from "../../lib/api";
import { assetFieldLabel, assetKey, assetVersionsKey, formatAssetValue } from "../../lib/assets";
import { metaDetalhe, tipoEstudioDoAsset } from "../../lib/estudio";

// /app/assets/:id/historico: histórico do asset com antes/depois, inclusive a lista de arquivos
// (princípio VII). Reverter só aparece para o dono (VersionHistory) e cria uma versão nova; os
// arquivos que não existiam na versão alvo são arquivados, nunca apagados.
export default function AssetHistorico() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const detail = useQuery({ queryKey: assetKey(id), queryFn: () => api.assets.get(id) });
  const versions = useQuery({ queryKey: assetVersionsKey(id), queryFn: () => api.assets.versions(id) });
  const asset = detail.data?.asset;
  const meta = metaDetalhe(tipoEstudioDoAsset(asset?.tipo ?? "imagem"), asset?.perfilId);
  usePageMeta({
    title: "Histórico",
    ativo: meta.ativo,
    breadcrumbs: [...meta.breadcrumbs, ...(asset ? [{ label: asset.name, to: `/app/assets/${id}` }] : [])],
  });

  async function reload() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: assetKey(id) }),
      queryClient.invalidateQueries({ queryKey: assetVersionsKey(id) }),
      queryClient.invalidateQueries({ queryKey: ["assets"] }),
    ]);
  }

  return (
    <Page>
      <Button type="button" variant="ghost" size="sm" className="-ml-2 text-muted-foreground" asChild>
        <Link to={`/app/assets/${id}`}>
          <ArrowLeft aria-hidden="true" />
          Voltar para o asset
        </Link>
      </Button>
      <Card className="shadow-card">
        <CardHeader>
          <h1 className="flex items-center gap-2 text-lg leading-none font-semibold">
            <History className="size-5 text-muted-foreground" aria-hidden="true" />
            {asset ? `Histórico de ${asset.name}` : "Histórico do asset"}
          </h1>
          <CardDescription>
            Da versão mais recente para a mais antiga. Reverter cria uma versão nova; os arquivos que não existiam na versão
            escolhida são arquivados, nunca apagados.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {(versions.isPending || detail.isPending) && (
            <p aria-live="polite" className="text-sm text-muted-foreground">
              Carregando…
            </p>
          )}
          {versions.isError && <ApiErrorAlert error={versions.error} />}
          {detail.isError && <ApiErrorAlert error={detail.error} />}
          {versions.data && asset && (
            <VersionHistory
              versions={versions.data.items}
              labels={assetFieldLabel}
              formatValue={formatAssetValue}
              onRevert={async (toVersion) => {
                await api.assets.revert(id, asset.version, toVersion);
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
