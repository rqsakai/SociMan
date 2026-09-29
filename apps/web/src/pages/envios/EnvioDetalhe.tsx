/*
 * /app/envios/:id (spec 006, US4; T059): o envio e a revisão dos clipes lado a lado.
 * Status ao vivo (polling de 5 s enquanto o envio anda ou há clipe na fila da marca), configuração
 * usada, direito no envio e as ações do status ("Tentar de novo", "Enviar mesmo assim"). Nos clipes:
 * player, trecho, gancho editável, título e pontuação do OpenShorts, "Arquivar", "mostrar
 * arquivados" e "Aplicar marca" em um, nos marcados ou em todos (lotes de até 30).
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CircleAlert, ExternalLink, Loader2, RotateCcw, Stamp } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { usePageMeta } from "@/components/shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { DireitoBadge } from "../../components/canais/DireitoBadge";
import { ClipReview } from "../../components/envios/ClipReview";
import { envioTitulo } from "../../components/envios/EnviarDialog";
import { EnvioStatus } from "../../components/envios/EnvioStatus";
import { HistoryHeading, VersionHistory } from "../../components/VersionHistory";
import { api } from "../../lib/api";
import {
  emAndamento,
  envioFieldLabel,
  envioKey,
  envioStatusLabel,
  envioVersionsKey,
  formatoLabel,
  layoutLabel,
  legendaLabel,
  origemLabel,
  type Envio,
} from "../../lib/envios";
import { errorText, perfilKey } from "../../lib/perfis";
import type { Corte } from "../../lib/marca";
import { formatDateTime } from "../../lib/tz";
import { direitoLabel, type Direito } from "../../lib/canais";

const LOTE = 30;

function formatEnvioValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (field === "status" && typeof value === "string") return envioStatusLabel[value as Envio["status"]] ?? value;
  if (field === "origem" && typeof value === "string") return origemLabel[value as Envio["origem"]] ?? value;
  if (field === "direito_no_envio" && typeof value === "string") return value === "avulso" ? "Avulso" : (direitoLabel[value as Direito] ?? value);
  if (field === "config" && typeof value === "object") {
    // Resumo legível; o `subtitle` do kit (tokens da legenda) fica fora.
    const c = value as Record<string, unknown>;
    const legenda = legendaLabel[c.legenda as keyof typeof legendaLabel] ?? String(c.legenda);
    return [
      `Duração: ${String(c.clip_min_s)} a ${String(c.clip_max_s)} s`,
      `Quantidade: ${c.quantidade === null || c.quantidade === undefined ? "automática" : String(c.quantidade)}`,
      `Layout: ${layoutLabel[c.layout as keyof typeof layoutLabel] ?? String(c.layout)}`,
      `Formato: ${formatoLabel[c.formato as keyof typeof formatoLabel] ?? String(c.formato)}`,
      `Legenda: ${legenda}${typeof c.kit_version === "number" ? ` (kit ${c.kit_version === 0 ? "padrão" : `v${c.kit_version}`})` : ""}`,
      `Marca automática: ${c.marca_automatica ? "sim" : "não"}`,
    ].join("\n");
  }
  if ((field === "canal_fonte_id" || field === "video_fonte_id") && typeof value === "string") return value.slice(0, 8);
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function EnvioDetalhe() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const [showArchived, setShowArchived] = useState(false);
  const [marcados, setMarcados] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const detail = useQuery({
    queryKey: envioKey(id),
    queryFn: () => api.envios.get(id),
    refetchInterval: (q) => {
      const d = q.state.data;
      if (!d) return false;
      const marcando = d.cortes.some((c) => c.status === "na_fila" || c.status === "processando");
      return emAndamento(d.envio) || marcando ? 5000 : false;
    },
  });
  const envio = detail.data?.envio;
  const cortes = useMemo(() => [...(detail.data?.cortes ?? [])].sort((a, b) => (a.clipIndex ?? 0) - (b.clipIndex ?? 0)), [detail.data]);
  const visiveis = cortes.filter((c) => showArchived || !c.archived);
  const emRevisao = cortes.filter((c) => c.status === "revisao" && !c.archived);

  const perfil = useQuery({ queryKey: perfilKey(envio?.perfilId ?? ""), queryFn: () => api.perfis.get(envio!.perfilId), enabled: Boolean(envio) });
  const perfilName = perfil.data?.perfil.name;
  usePageMeta({
    title: envio ? envioTitulo(envio).slice(0, 50) : "Envio",
    breadcrumbs: [{ label: "Envios", to: "/app/envios?aba=envios" }],
  });

  // Links de 1 h (players): o original em revisão; o marcado quando pronto.
  const linkKey = cortes.map((c) => `${c.id}:${c.status}`).join(",");
  const links = useQuery({
    queryKey: ["envio-links", id, linkKey],
    queryFn: () =>
      api.midia.links(cortes.map((c) => ({ kind: c.status === "pronto" ? ("corte_marcado" as const) : ("corte_original" as const), id: c.id }))),
    enabled: cortes.length > 0,
    staleTime: 50 * 60_000,
  });
  // A resposta vem na ordem do pedido.
  const urlOf = (c: Corte) => links.data?.items[cortes.findIndex((x) => x.id === c.id)]?.url ?? null;

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: envioKey(id) }),
      queryClient.invalidateQueries({ queryKey: envioVersionsKey(id) }),
      queryClient.invalidateQueries({ queryKey: ["envios"] }),
      ...(envio ? [queryClient.invalidateQueries({ queryKey: ["cortes", envio.perfilId] })] : []),
    ]);
  }

  async function act(kind: string, fn: () => Promise<unknown>, done: string) {
    setBusy(kind);
    try {
      await fn();
      toast.success(done);
      await refresh();
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setBusy(null);
    }
  }

  async function aplicarMarca(alvo: Corte[]) {
    await act(
      "marca",
      async () => {
        for (let i = 0; i < alvo.length; i += LOTE) {
          await api.cortes.aplicarMarca(alvo.slice(i, i + LOTE).map((c) => ({ corteId: c.id, version: c.version })));
        }
        setMarcados([]);
      },
      alvo.length === 1 ? "Marca na fila para 1 clipe." : `Marca na fila para ${alvo.length} clipes.`,
    );
  }

  if (detail.isPending) {
    return (
      <div className="space-y-4" aria-live="polite">
        <span className="sr-only">Carregando…</span>
        <Skeleton className="h-40 w-full rounded-xl" />
        <Skeleton className="h-96 w-full rounded-xl" />
      </div>
    );
  }
  if (detail.isError || !envio) return <ApiErrorAlert error={detail.error} />;

  const config = envio.config;
  const direito = envio.direitoNoEnvio ?? (envio.origem === "canal" && envio.canal ? envio.canal.direito : "avulso");

  return (
    <div className="space-y-6">
      <Button type="button" variant="ghost" size="sm" className="-ml-2 text-muted-foreground" asChild>
        <Link to="/app/envios?aba=envios">
          <ArrowLeft aria-hidden="true" />
          Envios
        </Link>
      </Button>

      <Card className="shadow-card">
        <CardHeader>
          <CardTitle>
            <h1 className="text-xl font-bold break-words">{envioTitulo(envio)}</h1>
          </CardTitle>
          <CardDescription className="flex flex-wrap items-center gap-2">
            <span>{perfilName ?? "Perfil"}</span>
            <span aria-hidden="true">·</span>
            <span>{envio.canal?.title ?? origemLabel[envio.origem]}</span>
            <DireitoBadge direito={direito} />
            {envio.sourceUrl && (
              <a href={envio.sourceUrl} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 underline">
                Fonte <ExternalLink className="size-3" aria-hidden="true" />
              </a>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div aria-live="polite">
            <EnvioStatus envio={envio} className="max-w-sm" />
          </div>
          {envio.status === "aguardando_openshorts" && (
            <Alert>
              <CircleAlert aria-hidden="true" />
              <AlertTitle>Aguardando o OpenShorts</AlertTitle>
              <AlertDescription>O OpenShorts está fora do ar. O envio é retomado sozinho quando ele voltar.</AlertDescription>
            </Alert>
          )}
          {(envio.status === "falhou" || envio.status === "sem_clipes") && (
            <Alert variant={envio.status === "falhou" ? "destructive" : "default"}>
              <CircleAlert aria-hidden="true" />
              <AlertTitle>{envioStatusLabel[envio.status]}</AlertTitle>
              <AlertDescription>
                <p>{envio.errorMessage ?? (envio.status === "sem_clipes" ? "O OpenShorts não gerou clipes deste vídeo." : "O envio falhou.")}</p>
                {envio.status === "falhou" && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-2"
                    disabled={busy !== null}
                    aria-busy={busy === "retry"}
                    onClick={() => void act("retry", () => api.envios.retry(envio.id, envio.version), "Envio de volta na fila.")}
                  >
                    {busy === "retry" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RotateCcw aria-hidden="true" />}
                    Tentar de novo
                  </Button>
                )}
              </AlertDescription>
            </Alert>
          )}
          {envio.status === "confirmar_qualidade" && (
            <Alert>
              <CircleAlert aria-hidden="true" />
              <AlertTitle>O OpenShorts pediu confirmação</AlertTitle>
              <AlertDescription>
                <p>{envio.errorMessage ?? "O vídeo tem qualidade baixa."}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <ConfirmButton
                    label="Enviar mesmo assim"
                    size="sm"
                    busy={busy === "q"}
                    title="Enviar mesmo com qualidade baixa?"
                    description="Os clipes podem sair piores."
                    onConfirm={() => act("q", () => api.envios.confirmarQualidade(envio.id, { version: envio.version, enviar: true }), "Enviado de novo.")}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={busy !== null}
                    onClick={() => void act("d", () => api.envios.confirmarQualidade(envio.id, { version: envio.version, enviar: false }), "Envio descartado.")}
                  >
                    Descartar
                  </Button>
                </div>
              </AlertDescription>
            </Alert>
          )}
          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <Detail label="Enviado por">{envio.createdBy?.name ?? "—"}</Detail>
            <Detail label="Enviado em">{envio.sentAt ? formatDateTime(envio.sentAt) : "—"}</Detail>
            <Detail label="Concluído em">{envio.finishedAt ? formatDateTime(envio.finishedAt) : "—"}</Detail>
            <Detail label="Clipes">{envio.clipsTotal === null || envio.clipsTotal === undefined ? "—" : `${envio.clipsImportados} de ${envio.clipsTotal}`}</Detail>
            {config && (
              <>
                <Detail label="Duração">
                  {config.clipMinS} a {config.clipMaxS} s
                </Detail>
                <Detail label="Quantidade">{config.quantidade ?? "Automática"}</Detail>
                <Detail label="Layout e formato">
                  {layoutLabel[config.layout]} · {formatoLabel[config.formato]}
                </Detail>
                <Detail label="Legenda">
                  {legendaLabel[config.legenda]}
                  {config.kitVersion ? ` (kit v${config.kitVersion})` : ""}
                </Detail>
              </>
            )}
          </dl>
        </CardContent>
      </Card>

      <section aria-labelledby="clipes-titulo" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 id="clipes-titulo" className="text-lg font-bold">
              Clipes
            </h2>
            <p className="text-sm text-muted-foreground">
              {cortes.length === 0
                ? "Os clipes aparecem aqui quando o OpenShorts terminar."
                : `${emRevisao.length} em revisão. Arquive os ruins e aplique a marca do kit nos bons.`}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="size-4 accent-primary" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
              Mostrar arquivados
            </label>
            {marcados.length > 0 && (
              <Button
                type="button"
                variant="outline"
                disabled={busy !== null}
                aria-busy={busy === "marca"}
                onClick={() => void aplicarMarca(emRevisao.filter((c) => marcados.includes(c.id)))}
              >
                <Stamp aria-hidden="true" />
                Aplicar marca nos {marcados.length} marcados
              </Button>
            )}
            <ConfirmButton
              label="Aplicar marca em todos"
              icon={Stamp}
              busy={busy === "marca"}
              disabled={emRevisao.length === 0}
              title={`Aplicar a marca em ${emRevisao.length} clipes?`}
              description="Os clipes em revisão (não arquivados) entram na fila da marca com o kit atual do perfil."
              onConfirm={() => aplicarMarca(emRevisao)}
            />
          </div>
        </div>
        {links.isError && <ApiErrorAlert error={links.error} />}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {visiveis.map((c) => (
            <ClipReview
              key={`${c.id}-${c.version}`}
              corte={c}
              videoUrl={urlOf(c)}
              checked={marcados.includes(c.id)}
              onCheck={(on) => setMarcados((m) => (on ? [...m, c.id] : m.filter((x) => x !== c.id)))}
              onChanged={refresh}
            />
          ))}
        </div>
      </section>

      <Card className="shadow-card">
        <CardHeader>
          <HistoryHeading>Histórico do envio</HistoryHeading>
          <CardDescription>Quem selecionou, quem enviou (e confirmou o aviso de direito) e as mudanças de status.</CardDescription>
        </CardHeader>
        <CardContent>
          <EnvioHistorico id={envio.id} />
        </CardContent>
      </Card>
    </div>
  );
}

function EnvioHistorico({ id }: { id: string }) {
  const versions = useQuery({ queryKey: envioVersionsKey(id), queryFn: () => api.envios.versions(id) });
  if (versions.isPending) return <p className="text-sm text-muted-foreground">Carregando…</p>;
  if (versions.isError) return <ApiErrorAlert error={versions.error} />;
  return <VersionHistory versions={versions.data.items} labels={envioFieldLabel} formatValue={formatEnvioValue} />;
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-medium break-words">{children}</dd>
    </div>
  );
}
