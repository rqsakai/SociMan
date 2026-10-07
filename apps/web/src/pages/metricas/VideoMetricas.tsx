/*
 * /app/metricas/videos/:id (spec 016, US4): um vídeo coletado, sobretudo os de fora do SociMan (os
 * ligados abrem no conteúdo). Curva, marcos, link do post e a situação da coleta. Sem imagem da
 * CDN da TikTok (a capa expira e ficaria fora da CSP): o ícone da rede no lugar.
 */
import { ExternalLink } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { DiagnosticoDoPost } from "@/components/aprendizado/SinaisDistribuicao";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { CurvaVideo } from "@/components/metricas/CurvaVideo";
import { PageHeading } from "@/components/PageHeading";
import { PlatformIcon } from "@/components/PlatformIcon";
import { HeaderCard, usePageMeta } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDuracaoS, formatEngajamento, formatNumero, formatVelocidade, nomeDaConta, origemMetricasLabel, useMetricasVideo, vinculoMetodoLabel } from "@/lib/metricas";
import { formatDateTime } from "@/lib/tz";

export default function VideoMetricas() {
  const { id = "" } = useParams();
  const video = useMetricasVideo(id);
  const v = video.data;
  usePageMeta({ title: v ? nomeDaConta(v) : "Vídeo", breadcrumbs: [{ label: "Métricas", to: "/app/metricas" }] });

  if (video.isPending) return <Skeleton className="h-96 w-full" />;
  if (video.isError) return <ApiErrorAlert error={video.error} />;
  if (!v) return null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start gap-3">
        <span className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-muted">
          <PlatformIcon platform="tiktok" className="size-6" />
        </span>
        <PageHeading title={v.legenda || (v.origem === "anonima" ? "Vídeo anônimo" : "Sem legenda")} description={`${nomeDaConta(v)}${v.perfil ? ` · ${v.perfil.name}` : ""}`} />
      </div>

      <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
        <div>
          <dt className="text-xs text-muted-foreground">Origem</dt>
          <dd>
            <Badge variant="outline">{origemMetricasLabel[v.origem]}</Badge>
            {v.vinculoMetodo && <span className="ml-1 text-xs text-muted-foreground">({vinculoMetodoLabel[v.vinculoMetodo]})</span>}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Publicado</dt>
          <dd>{formatDateTime(v.publicadoEm)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Duração</dt>
          <dd className="tabular-nums">{formatDuracaoS(v.duracaoS)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Visualizações</dt>
          <dd className="tabular-nums">{formatNumero(v.ultima?.views)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Engajamento</dt>
          <dd className="tabular-nums">{formatEngajamento(v.engajamento)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Velocidade</dt>
          <dd className="tabular-nums">{formatVelocidade(v.velocidade)}</dd>
        </div>
      </dl>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {v.url && (
          <a href={v.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 underline">
            <ExternalLink className="size-3.5" aria-hidden="true" />
            ver post na TikTok
          </a>
        )}
        {v.conteudoId && (
          <Link to={`/app/conteudos/${v.conteudoId}${v.contaId ? `?conta=${v.contaId}` : ""}`} className="underline">
            abrir o conteúdo no SociMan
          </Link>
        )}
        {!v.disponivel && v.indisponivelDesde && <span className="text-destructive">Indisponível desde {formatDateTime(v.indisponivelDesde)} (deixou de ser público ou foi apagado).</span>}
        {v.perfil && v.origem !== "anonima" && (
          <Link to={`/app/perfis/${v.perfil.id}/aprendizado?aba=temas`} className="underline">
            tema e aprendizado do perfil
          </Link>
        )}
        {v.coletaParadaEm && <span className="text-muted-foreground">Coleta encerrada em {formatDateTime(v.coletaParadaEm)} (mais de 1 ano).</span>}
      </div>

      <HeaderCard title="Desempenho" description="Desde a publicação, pela idade do vídeo." tone="dark">
        <CurvaVideo video={v} />
      </HeaderCard>

      {/* spec 023: sinais de distribuição e o checklist do app, só para post estagnado ou com sinal */}
      <DiagnosticoDoPost videoId={v.id} perfilId={v.perfil?.id} />
    </div>
  );
}
