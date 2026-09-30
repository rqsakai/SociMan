/*
 * /app/conteudos/:id (spec 014, US1–US3, US5): player, título editável, origem (link para o corte
 * ou o envio), "Agendar", uma aba por conta de destino (`?conta=` escolhe a aba; é o link do sino)
 * com o painel do destino, "Adicionar conta", arquivar/restaurar e o histórico do conteúdo.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, ArrowLeft, CalendarClock, ClipboardCopy, Download, ExternalLink, Loader2, Save, TriangleAlert } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { AgendarDialog } from "@/components/conteudos/AgendarDialog";
import { DestinosSection } from "@/components/conteudos/DestinoPanel";
import { HistoryHeading, VersionHistory } from "@/components/VersionHistory";
import { usePageMeta } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import {
  conteudoFieldLabel,
  conteudoVersionsKey,
  formatDuracao,
  invalidarConteudos,
  origemLabel,
  propostaDe,
  situacaoLabel,
  useConteudo,
  type Conteudo,
} from "@/lib/conteudos";
import { formatBytes } from "@/lib/marca";
import { copyText, TITULO_MAX } from "@/lib/postagem";
import { formatDateTime } from "@/lib/tz";

export default function ConteudoDetalhe() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const queryClient = useQueryClient();
  const q = useConteudo(id);
  const c = q.data?.conteudo;

  usePageMeta({
    title: c ? `Conteúdo: ${(c.titulo || "sem título").slice(0, 40)}` : "Conteúdo",
    breadcrumbs: [{ label: "Conteúdos", to: "/app/conteudos" }],
  });

  async function refresh() {
    await invalidarConteudos(queryClient, id);
  }

  if (q.isPending) {
    return (
      <div className="space-y-4" aria-live="polite">
        <span className="sr-only">Carregando…</span>
        <Skeleton className="h-96 w-full rounded-xl" />
      </div>
    );
  }
  if (q.isError || !c) return <ApiErrorAlert error={q.error} />;

  return (
    <div className="space-y-6">
      <Button type="button" variant="ghost" size="sm" className="-ml-2 text-muted-foreground" asChild>
        <Link to="/app/conteudos">
          <ArrowLeft aria-hidden="true" />
          Conteúdos
        </Link>
      </Button>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_1fr]">
        <Player conteudo={c} />
        <div className="min-w-0 space-y-6">
          <Cabecalho key={`${c.id}-${c.version}`} conteudo={c} onChanged={refresh} />
          <PropostaCard conteudo={c} />
          <DestinosSection
            conteudo={c}
            conta={params.get("conta")}
            onContaChange={(conta) =>
              setParams(
                (cur) => {
                  const next = new URLSearchParams(cur);
                  next.set("conta", conta);
                  return next;
                },
                { replace: true },
              )
            }
            onChanged={refresh}
          />
          <Historico conteudo={c} onReverted={refresh} />
        </div>
      </div>
    </div>
  );
}

function Player({ conteudo: c }: { conteudo: Conteudo }) {
  const kind = c.origem === "video_proprio" ? "conteudo_video" : c.situacao === "pronto" ? "corte_marcado" : "corte_original";
  // Links de 1 h; renovados quando o corte fica pronto (a chave inclui o kind).
  const links = useQuery({
    queryKey: ["conteudo-links", c.id, kind],
    queryFn: () => api.midia.links([{ kind, id: c.id }]),
    staleTime: 50 * 60_000,
  });
  const url = links.data?.items[0]?.url ?? null;
  return (
    <Card className="h-fit gap-3 shadow-card">
      <CardContent className="space-y-3">
        {url ? (
          <video
            key={url}
            controls
            playsInline
            preload="metadata"
            src={url}
            poster={c.posterUrl ?? undefined}
            aria-label="Vídeo do conteúdo"
            className="mx-auto max-h-[70vh] w-full rounded-lg bg-black"
          />
        ) : (
          <Skeleton className="aspect-[9/16] w-full rounded-lg" />
        )}
        {kind === "corte_original" && <p className="text-center text-xs text-muted-foreground">Original (sem a marca ainda).</p>}
        {links.isError && <ApiErrorAlert error={links.error} />}
        {url && kind !== "corte_original" && (
          <div className="flex justify-center">
            <Button asChild>
              <a href={`${url}${url.includes("?") ? "&" : "?"}download=1`} download>
                <Download aria-hidden="true" />
                Baixar vídeo
              </a>
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Cabecalho({ conteudo: c, onChanged }: { conteudo: Conteudo; onChanged: () => Promise<void> }) {
  const [titulo, setTitulo] = useState(c.titulo);
  const [busy, setBusy] = useState<"titulo" | "arquivo" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [agendarOpen, setAgendarOpen] = useState(false);
  useEffect(() => setTitulo(c.titulo), [c.titulo]);

  async function run(kind: "titulo" | "arquivo", fn: () => Promise<unknown>, msg: string) {
    setError(null);
    setBusy(kind);
    try {
      await fn();
      toast.success(msg);
      await onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  const agendados = c.destinos.filter((d) => d.estado === "agendado" && !d.archived).length;

  return (
    <Card className="shadow-card">
      <CardHeader>
        <CardTitle>
          <h1 className="text-xl font-bold break-words">{c.titulo || "Conteúdo sem título"}</h1>
        </CardTitle>
        <CardDescription className="flex flex-wrap items-center gap-2">
          {c.archived ? <Badge className="bg-dark text-dark-foreground">Arquivado</Badge> : <Badge variant="outline">{situacaoLabel[c.situacao]}</Badge>}
          <Badge variant="secondary">{origemLabel[c.origem]}</Badge>
          {c.naoVertical && (
            <Badge className="bg-warning text-warning-foreground">
              <TriangleAlert aria-hidden="true" />
              não é vertical
            </Badge>
          )}
          <span>{c.perfil.name}</span>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!c.archived && (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void run("titulo", () => api.conteudos.update(c.id, { version: c.version, titulo: titulo.trim() }), "Título salvo.");
            }}
          >
            <Field label="Título do conteúdo" hint={`${titulo.length}/${TITULO_MAX}`} className="min-w-0 flex-1">
              {({ id, describedBy }) => <Input id={id} value={titulo} maxLength={TITULO_MAX} aria-describedby={describedBy} onChange={(e) => setTitulo(e.target.value)} />}
            </Field>
            <Button type="submit" variant="outline" disabled={busy !== null || titulo === c.titulo} aria-busy={busy === "titulo"} className="mb-5">
              {busy === "titulo" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
              Salvar título
            </Button>
          </form>
        )}
        {error !== null && <ApiErrorAlert error={error} onReload={() => void onChanged()} />}
        <div className="flex flex-wrap gap-2">
          {!c.archived && (
            <Button type="button" disabled={c.situacao !== "pronto"} title={c.situacao === "pronto" ? undefined : "Aplique a marca antes de agendar"} onClick={() => setAgendarOpen(true)}>
              <CalendarClock aria-hidden="true" />
              Agendar
            </Button>
          )}
          <ConfirmButton
            label={c.archived ? "Restaurar" : "Arquivar"}
            icon={c.archived ? ArchiveRestore : Archive}
            busy={busy === "arquivo"}
            title={c.archived ? "Restaurar este conteúdo?" : "Arquivar este conteúdo?"}
            description={
              c.archived
                ? "O conteúdo volta para a lista. Os agendamentos cancelados não voltam sozinhos."
                : agendados > 0
                  ? `Arquivar cancela ${agendados} agendamento(s) deste conteúdo. Nada é apagado e dá para restaurar.`
                  : "O conteúdo sai da lista; nada é apagado e dá para restaurar."
            }
            onConfirm={() =>
              run(
                "arquivo",
                () => (c.archived ? api.conteudos.restore(c.id, c.version) : api.conteudos.archive(c.id, c.version)),
                c.archived ? "Conteúdo restaurado." : "Conteúdo arquivado.",
              )
            }
          />
        </div>
        <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          <Detail label="Origem">
            {c.corteId ? (
              <Link to={`/app/cortes/${c.corteId}`} className="inline-flex items-center gap-1 underline">
                Corte <ExternalLink className="size-3" aria-hidden="true" />
              </Link>
            ) : (
              origemLabel[c.origem]
            )}
            {c.envioId && (
              <>
                {" · "}
                <Link to={`/app/envios/${c.envioId}`} className="inline-flex items-center gap-1 underline">
                  Envio <ExternalLink className="size-3" aria-hidden="true" />
                </Link>
              </>
            )}
          </Detail>
          <Detail label="Duração">{formatDuracao(c.durationMs)}</Detail>
          {c.width && c.height && (
            <Detail label="Resolução">
              {c.width}×{c.height}
            </Detail>
          )}
          {c.videoBytes !== null && c.videoBytes !== undefined && <Detail label="Tamanho">{formatBytes(c.videoBytes)}</Detail>}
          {c.originalFilename && <Detail label="Arquivo">{c.originalFilename}</Detail>}
          <Detail label="Criado em">{formatDateTime(c.createdAt)}</Detail>
          <Detail label="Alterado por">{c.updatedBy?.name ?? "—"}</Detail>
        </dl>
      </CardContent>
      <AgendarDialog
        open={agendarOpen}
        onOpenChange={setAgendarOpen}
        conteudo={{ id: c.id, perfilId: c.perfil.id, titulo: c.titulo, situacao: c.situacao, proposta: propostaDe(c), origem: c.origem, posterUrl: c.posterUrl }}
        destinos={c.destinos}
        onDone={onChanged}
      />
    </Card>
  );
}

// T075: o que o OpenShorts propôs (título, descrição, gancho e nota), para o operador conferir e
// copiar; os textos vazios dos destinos já vêm com esta proposta.
function PropostaCard({ conteudo }: { conteudo: Conteudo }) {
  const p = propostaDe(conteudo);
  if (!p) return null;
  const campos = [
    { rotulo: "Título", valor: p.titulo },
    { rotulo: "Descrição", valor: p.descricao },
    { rotulo: "Gancho", valor: p.gancho },
  ].filter((x): x is { rotulo: string; valor: string } => Boolean(x.valor?.trim()));

  async function copiar(rotulo: string, texto: string) {
    if (await copyText(texto)) toast.success(`${rotulo} copiado.`);
    else toast.error("Não foi possível copiar.");
  }

  return (
    <Card className="shadow-card" aria-labelledby="proposta-openshorts">
      <CardHeader>
        <CardTitle>
          <h2 id="proposta-openshorts">Proposta do OpenShorts</h2>
        </CardTitle>
        <CardDescription>
          O que o OpenShorts sugeriu para este corte{p.score !== null && p.score !== undefined ? ` (nota ${p.score})` : ""}. Confira antes de usar.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="space-y-3 text-sm">
          {campos.map((x) => (
            <div key={x.rotulo} className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <dt className="text-xs text-muted-foreground">{x.rotulo}</dt>
                <dd className="break-words whitespace-pre-wrap">{x.valor}</dd>
              </div>
              <Button type="button" variant="ghost" size="sm" aria-label={`Copiar ${x.rotulo.toLowerCase()} da proposta`} onClick={() => void copiar(x.rotulo, x.valor)}>
                <ClipboardCopy aria-hidden="true" />
                Copiar
              </Button>
            </div>
          ))}
          {p.score !== null && p.score !== undefined && (
            <div>
              <dt className="text-xs text-muted-foreground">Nota</dt>
              <dd className="font-medium tabular-nums">{p.score}</dd>
            </div>
          )}
        </dl>
      </CardContent>
    </Card>
  );
}

function Historico({ conteudo: c, onReverted }: { conteudo: Conteudo; onReverted: () => Promise<void> }) {
  const versions = useQuery({ queryKey: conteudoVersionsKey(c.id), queryFn: () => api.conteudos.versions(c.id) });
  return (
    <Card className="shadow-card">
      <CardHeader>
        <HistoryHeading>Histórico do conteúdo</HistoryHeading>
      </CardHeader>
      <CardContent>
        {versions.isError && <ApiErrorAlert error={versions.error} />}
        {versions.data && (
          <VersionHistory
            versions={versions.data.items}
            labels={conteudoFieldLabel}
            formatValue={(_, value) => (value === null || value === undefined || value === "" ? "—" : typeof value === "boolean" ? (value ? "Sim" : "Não") : String(value))}
            onRevert={async (toVersion) => {
              await api.conteudos.revert(c.id, c.version, toVersion);
              await onReverted();
            }}
            onReload={onReverted}
          />
        )}
      </CardContent>
    </Card>
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
