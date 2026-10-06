import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, History } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { usePageMeta } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { VersionHistory } from "@/components/VersionHistory";
import { api } from "@/lib/api";
import { cenaFieldLabel, cenaVersionsKey, formatCenaValue, invalidarCena, semRetry404, useCena } from "@/lib/cenas";
import { perfilKey } from "@/lib/perfis";

// /app/cenas/:id/historico (spec 010, FR-008): autor, antes e depois de cada mudança, inclusive o
// status, o prompt congelado, a origem do "Duplicar", os vínculos com conteúdos e o selo da IA.
// Reverter só aparece para o dono (VersionHistory) e cria uma versão nova; numa cena usada a API recusa.
export default function CenaHistorico() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const detail = useCena(id);
  const versions = useQuery({ queryKey: cenaVersionsKey(id), queryFn: () => api.cenas.versions(id), retry: semRetry404 });
  const cena = detail.data;
  const perfilId = cena?.perfilId ?? "";
  const perfil = useQuery({ queryKey: perfilKey(perfilId), queryFn: () => api.perfis.get(perfilId), enabled: perfilId !== "" });
  const perfilName = perfil.data?.perfil.name;
  usePageMeta({
    title: "Histórico",
    breadcrumbs: [
      { label: "Perfis", to: "/app/perfis" },
      ...(perfilName ? [{ label: perfilName, to: `/app/perfis/${perfilId}?aba=cenas` }] : []),
      ...(cena ? [{ label: cena.nome, to: `/app/cenas/${id}` }] : []),
    ],
  });

  const reload = () => invalidarCena(queryClient, id, perfilId || undefined);

  return (
    <div className="space-y-6">
      <Button type="button" variant="ghost" size="sm" className="-ml-2 text-muted-foreground" asChild>
        <Link to={`/app/cenas/${id}`}>
          <ArrowLeft aria-hidden="true" />
          Voltar para a cena
        </Link>
      </Button>
      <Card className="shadow-card">
        <CardHeader>
          <h1 className="flex items-center gap-2 text-lg leading-none font-semibold">
            <History className="size-5 text-muted-foreground" aria-hidden="true" />
            {cena ? `Histórico de ${cena.nome}` : "Histórico da cena"}
          </h1>
          <CardDescription>
            Da versão mais recente para a mais antiga. Reverter cria uma versão nova (só o dono); uma cena usada num vídeo não é
            revertida: duplique para variar.
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
          {versions.data && cena && (
            <VersionHistory
              versions={versions.data.items}
              labels={cenaFieldLabel}
              formatValue={formatCenaValue}
              onRevert={
                cena.status === "usada"
                  ? undefined
                  : async (toVersion) => {
                      await api.cenas.revert(id, cena.version, toVersion);
                      await reload();
                    }
              }
              onReload={reload}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
