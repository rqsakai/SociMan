import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, Loader2, RotateCcw } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { usePageMeta } from "@/components/shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { CorteStatusBadge, ProgressBar } from "../../components/marca/CorteStatusBadge";
import { HistoryHeading, VersionHistory } from "../../components/VersionHistory";
import { api } from "../../lib/api";
import { corteKey, cortesKey, corteStatusLabel, formatBytes, formatDuration, type Corte } from "../../lib/marca";
import { perfilKey } from "../../lib/perfis";

const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "medium" });
const busy = (c: Corte | undefined) => c?.status === "na_fila" || c?.status === "processando";

const corteFieldLabel: Record<string, string> = { hook_text: "Gancho", kit_version: "Versão do kit", status: "Status" };
function formatCorteValue(field: string, value: unknown): string {
  if (field === "status" && typeof value === "string") return corteStatusLabel[value as Corte["status"]] ?? value;
  if (field === "kit_version" && typeof value === "number") return value === 0 ? "padrão" : `v${value}`;
  return value === null || value === undefined ? "—" : String(value);
}

// /app/cortes/:id (US4, T027): status com polling de 2 s enquanto está na fila ou processando;
// player com o resultado (ou o original enquanto não fica pronto) por link de mídia assinado;
// "Baixar", "Baixar original", "Tentar de novo" (só em "Falhou") e os detalhes do envio (FR-017).
export default function CorteDetalhe() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [retrying, setRetrying] = useState(false);

  const corte = useQuery({
    queryKey: corteKey(id),
    queryFn: () => api.cortes.get(id),
    refetchInterval: (q) => (busy(q.state.data?.corte) ? 2000 : false),
  });
  const c = corte.data?.corte;
  // Quando o corte sai da fila ou do processamento, a lista do perfil (e o pôster da prévia do
  // kit) ficam velhos: invalida.
  const status = c?.status;
  const perfilId = c?.perfilId;
  useEffect(() => {
    if (perfilId && (status === "pronto" || status === "falhou")) {
      void queryClient.invalidateQueries({ queryKey: cortesKey(perfilId) });
    }
  }, [status, perfilId, queryClient]);
  const perfil = useQuery({
    queryKey: perfilKey(c?.perfilId ?? ""),
    queryFn: () => api.perfis.get(c!.perfilId),
    enabled: Boolean(c),
  });
  const ready = c?.status === "pronto";
  // Links de 1 h; renovados quando o corte fica pronto (a chave inclui o status).
  const links = useQuery({
    queryKey: ["corte-links", id, ready],
    queryFn: () =>
      api.midia.links([
        { kind: "corte_original", id },
        ...(ready ? [{ kind: "corte_marcado" as const, id }] : []),
      ]),
    enabled: Boolean(c),
    staleTime: 50 * 60_000,
  });
  const versions = useQuery({ queryKey: ["corte-versions", id], queryFn: () => api.cortes.versions(id) });

  const perfilName = perfil.data?.perfil.name;
  usePageMeta({
    title: c ? `Corte: ${c.hookText.slice(0, 40)}` : "Corte",
    breadcrumbs: [
      { label: "Perfis", to: "/app/perfis" },
      ...(perfilName && c ? [{ label: perfilName, to: `/app/perfis/${c.perfilId}?aba=cortes` }] : []),
    ],
  });

  async function retry() {
    if (!c) return;
    setError(null);
    setRetrying(true);
    try {
      await api.cortes.retry(c.id, c.version);
      toast.success("Corte de volta na fila.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: corteKey(id) }),
        queryClient.invalidateQueries({ queryKey: cortesKey(c.perfilId) }),
        queryClient.invalidateQueries({ queryKey: ["corte-versions", id] }),
      ]);
    } catch (err) {
      setError(err);
    } finally {
      setRetrying(false);
    }
  }

  if (corte.isPending) {
    return (
      <div className="space-y-4" aria-live="polite">
        <span className="sr-only">Carregando…</span>
        <Skeleton className="h-96 w-full rounded-xl" />
      </div>
    );
  }
  if (corte.isError || !c) return <ApiErrorAlert error={corte.error} />;

  const originalUrl = links.data?.items[0]?.url ?? null;
  const resultUrl = ready ? (links.data?.items[1]?.url ?? null) : null;
  const playing = resultUrl ?? originalUrl;
  const withDownload = (url: string) => `${url}${url.includes("?") ? "&" : "?"}download=1`;

  return (
    <div className="space-y-6">
      <Button type="button" variant="ghost" size="sm" className="-ml-2 text-muted-foreground" asChild>
        <Link to={`/app/perfis/${c.perfilId}?aba=cortes`}>
          <ArrowLeft aria-hidden="true" />
          Cortes do perfil
        </Link>
      </Button>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_1fr]">
        <Card className="gap-3 shadow-card">
          <CardContent className="space-y-3">
            {playing ? (
              <video
                key={playing}
                controls
                playsInline
                preload="metadata"
                src={playing}
                poster={c.posterUrl ?? undefined}
                aria-label={resultUrl ? "Vídeo com a marca" : "Vídeo original"}
                className="mx-auto max-h-[70vh] w-full rounded-lg bg-black"
              />
            ) : (
              <Skeleton className="aspect-[9/16] w-full rounded-lg" />
            )}
            <p className="text-center text-xs text-muted-foreground">
              {resultUrl ? "Resultado com a marca aplicada." : "Original (o resultado aparece aqui quando ficar pronto)."}
            </p>
            {links.isError && <ApiErrorAlert error={links.error} />}
            <div className="flex flex-wrap justify-center gap-2">
              {resultUrl && (
                <Button asChild>
                  <a href={withDownload(resultUrl)} download>
                    <Download aria-hidden="true" />
                    Baixar
                  </a>
                </Button>
              )}
              {originalUrl && (
                <Button variant="outline" asChild>
                  <a href={withDownload(originalUrl)} download>
                    <Download aria-hidden="true" />
                    Baixar original
                  </a>
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        <div className="min-w-0 space-y-6">
          <Card className="shadow-card">
            <CardHeader>
              <CardTitle>
                <h1 className="text-xl font-bold break-words whitespace-pre-line">{c.hookText}</h1>
              </CardTitle>
              <CardDescription className="flex flex-wrap items-center gap-2">
                <CorteStatusBadge corte={c} />
                <span>
                  Kit {c.kitVersion === 0 ? "padrão" : `v${c.kitVersion}`}
                  {perfilName ? ` de ${perfilName}` : ""}
                </span>
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {c.status === "processando" && <ProgressBar value={c.progress / 100} label="Processamento" />}
              {c.status === "na_fila" && (
                <p className="text-sm text-muted-foreground" aria-live="polite">
                  Na fila{c.queuePosition ? `: posição ${c.queuePosition}` : ""}. Os cortes são processados um de cada vez.
                </p>
              )}
              {c.status === "falhou" && (
                <Alert variant="destructive">
                  <AlertTitle>Falhou</AlertTitle>
                  <AlertDescription>
                    <p>{c.errorMessage ?? "O processamento falhou."}</p>
                    <Button type="button" variant="outline" size="sm" className="mt-2" disabled={retrying} aria-busy={retrying} onClick={() => void retry()}>
                      {retrying ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RotateCcw aria-hidden="true" />}
                      Tentar de novo
                    </Button>
                  </AlertDescription>
                </Alert>
              )}
              {error !== null && <ApiErrorAlert error={error} onReload={() => void corte.refetch()} />}
              <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
                <Detail label="Enviado por">{c.createdBy?.name ?? "—"}</Detail>
                <Detail label="Enviado em">{dateFormat.format(new Date(c.createdAt))}</Detail>
                <Detail label="Arquivo original">{c.originalFilename}</Detail>
                <Detail label="Tamanho do original">{formatBytes(c.bytes)}</Detail>
                <Detail label="Duração">{formatDuration(c.durationMs)}</Detail>
                <Detail label="Resolução">
                  {c.width}×{c.height}
                </Detail>
                <Detail label="Áudio">{c.hasAudio ? "Sim" : "Sem áudio"}</Detail>
                <Detail label="Tentativas">{c.attempts}</Detail>
                <Detail label="Tamanho do resultado">{formatBytes(c.resultBytes)}</Detail>
                <Detail label="Tempo de processamento">{c.processingMs === null ? "—" : `${(c.processingMs / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} s`}</Detail>
                <Detail label="Concluído em">{c.finishedAt ? dateFormat.format(new Date(c.finishedAt)) : "—"}</Detail>
              </dl>
            </CardContent>
          </Card>

          <Card className="shadow-card">
            <CardHeader>
              <HistoryHeading>Histórico do corte</HistoryHeading>
            </CardHeader>
            <CardContent>
              {versions.isError && <ApiErrorAlert error={versions.error} />}
              {versions.data && <VersionHistory versions={versions.data.items} labels={corteFieldLabel} formatValue={formatCorteValue} />}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-medium break-words">{children}</dd>
    </div>
  );
}
