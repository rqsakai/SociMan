import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, ArrowLeft, CircleAlert, ExternalLink, Loader2, RefreshCw, Save, Sparkles, Users } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { AnotacoesCard } from "@/components/anotacoes/AnotacoesDoItem";
import { ConfirmButton } from "@/components/ConfirmButton";
import { EmptyState, Page, usePageMeta } from "@/components/shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { DireitoBadge } from "../../components/canais/DireitoBadge";
import { ScoreBadge } from "../../components/canais/ScoreReason";
import { VideoThumb } from "../../components/canais/VideoCard";
import { HistoryHeading, VersionHistory } from "../../components/VersionHistory";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/authStore";
import {
  canalFieldLabel,
  canalKey,
  canalVersionsKey,
  DIREITOS,
  direitoHint,
  direitoLabel,
  formatCanalValue,
  formatCount,
  syncText,
  type CanalFonte,
  type Direito,
} from "../../lib/canais";
import { formatDateTime } from "../../lib/tz";
import { usePerfisAtivos } from "../../lib/usePerfis";

// /app/fontes/:id (spec 006, US1; T031): direito (editável só pelo dono, com evidência), perfis
// ligados, estado da busca com "Sincronizar agora", os vídeos mais recentes do canal e o histórico
// (reverter só pelo dono). Arquivar tira o canal da busca e da descoberta; vídeos e gerações ficam.
export default function CanalDetalhe() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<"archive" | "sync" | null>(null);

  const detail = useQuery({
    queryKey: canalKey(id),
    queryFn: () => api.canais.get(id),
    refetchInterval: (q) => {
      const s = q.state.data?.canal.sync.status;
      return s === "pendente" || s === "sincronizando" ? 5000 : false;
    },
  });
  const canal = detail.data?.canal;
  usePageMeta({ title: canal?.title ?? "Canal", breadcrumbs: [{ label: "Canais-fonte", to: "/app/fontes" }] });

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: canalKey(id) }),
      queryClient.invalidateQueries({ queryKey: canalVersionsKey(id) }),
      queryClient.invalidateQueries({ queryKey: ["canais"] }),
    ]);
  }

  async function run(kind: "archive" | "sync", fn: () => Promise<unknown>, done: string) {
    setError(null);
    setBusy(kind);
    try {
      await fn();
      toast.success(done);
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  if (detail.isPending) {
    return (
      <Page aria-live="polite">
        <span className="sr-only">Carregando…</span>
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </Page>
    );
  }
  if (detail.isError || !canal) return <ApiErrorAlert error={detail.error} />;

  const syncing = canal.sync.status === "pendente" || canal.sync.status === "sincronizando";

  return (
    <Page>
      <Button type="button" variant="ghost" size="sm" className="-ml-2 text-muted-foreground" asChild>
        <Link to="/app/fontes">
          <ArrowLeft aria-hidden="true" />
          Canais-fonte
        </Link>
      </Button>

      <section className="flex flex-wrap items-center gap-4 rounded-xl bg-card p-4 shadow-card">
        {canal.avatarUrl ? (
          <img src={canal.avatarUrl} alt={`Avatar de ${canal.title}`} className="size-20 rounded-full bg-muted object-cover" />
        ) : (
          <span className="tone-dark flex size-20 items-center justify-center rounded-full" aria-hidden="true">
            <Users className="size-8" />
          </span>
        )}
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-xl font-bold sm:text-2xl">{canal.title}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            {canal.handle && <span>@{canal.handle.replace(/^@/, "")}</span>}
            <DireitoBadge direito={canal.direito} />
            {canal.archived && <Badge className="bg-dark text-dark-foreground">Arquivado</Badge>}
          </div>
          <p className="mt-1 text-sm">
            <strong>{formatCount(canal.subscribers)}</strong> inscritos · <strong>{formatCount(canal.videosConhecidos)}</strong> vídeos
            encontrados{canal.videoCount ? ` de ${formatCount(canal.videoCount)}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" asChild>
            <a href={`https://www.youtube.com/channel/${canal.youtubeChannelId}`} target="_blank" rel="noreferrer noopener">
              <ExternalLink aria-hidden="true" />
              Abrir no YouTube
            </a>
          </Button>
          <Button asChild>
            <Link to={`/app/descobrir?canal=${canal.id}`}>
              <Sparkles aria-hidden="true" />
              Ver vídeos recomendados
            </Link>
          </Button>
          <ConfirmButton
            label={canal.archived ? "Restaurar" : "Arquivar"}
            icon={canal.archived ? ArchiveRestore : Archive}
            busy={busy === "archive"}
            title={canal.archived ? `Restaurar ${canal.title}?` : `Arquivar ${canal.title}?`}
            description={
              canal.archived
                ? "O canal volta para a busca de vídeos e para a descoberta."
                : "O canal sai da busca de vídeos e da descoberta. Os vídeos já encontrados e as gerações de cortes continuam."
            }
            onConfirm={() =>
              run(
                "archive",
                () => (canal.archived ? api.canais.restore(canal.id, canal.version) : api.canais.archive(canal.id, canal.version)),
                canal.archived ? "Canal restaurado." : "Canal arquivado.",
              )
            }
          />
        </div>
      </section>

      {error !== null && <ApiErrorAlert error={error} onReload={() => void refresh()} />}

      <div className="grid gap-6 lg:grid-cols-2">
        <DireitoCard key={`d-${canal.version}`} canal={canal} onSaved={refresh} />
        <div className="space-y-6">
          <Card className="shadow-card">
            <CardHeader>
              <CardTitle>
                <h2>Busca dos vídeos</h2>
              </CardTitle>
              <CardDescription>O SociMan busca os vídeos novos e atualiza as métricas sozinho.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="flex items-center gap-2 text-sm font-medium" aria-live="polite">
                {syncing && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
                {syncText(canal)}
              </p>
              {canal.sync.erro && (
                <Alert variant="destructive">
                  <CircleAlert aria-hidden="true" />
                  <AlertTitle>Erro na última busca</AlertTitle>
                  <AlertDescription>{canal.sync.erro}</AlertDescription>
                </Alert>
              )}
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <Detail label="Última atualização">{canal.sync.lastSyncedAt ? formatDateTime(canal.sync.lastSyncedAt) : "—"}</Detail>
                <Detail label="Próxima busca">{formatDateTime(canal.sync.nextSyncAt)}</Detail>
              </dl>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={syncing || canal.archived || busy !== null}
                aria-busy={busy === "sync"}
                onClick={() => void run("sync", () => api.canais.sincronizar(canal.id), "Busca agendada para agora.")}
              >
                {busy === "sync" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RefreshCw aria-hidden="true" />}
                Sincronizar agora
              </Button>
            </CardContent>
          </Card>
          <PerfisCard key={`p-${canal.version}`} canal={canal} onSaved={refresh} />
        </div>
      </div>

      <VideosRecentes canalId={canal.id} />

      <AnotacoesCard alvoTipo="canal" alvoId={canal.id} arquivado={canal.archived} titulo="Anotações do canal" />

      <Card className="shadow-card">
        <CardHeader>
          <HistoryHeading>Histórico do canal</HistoryHeading>
          <CardDescription>Da versão mais recente para a mais antiga. Reverter (só o dono) cria uma versão nova.</CardDescription>
        </CardHeader>
        <CardContent>
          <CanalHistorico canal={canal} onReverted={refresh} />
        </CardContent>
      </Card>
    </Page>
  );
}

function DireitoCard({ canal, onSaved }: { canal: CanalFonte; onSaved: () => Promise<void> }) {
  const isOwner = useAuth((s) => s.user?.role === "dono");
  const [direito, setDireito] = useState<Direito>(canal.direito);
  const [url, setUrl] = useState(canal.direitoEvidenciaUrl ?? "");
  const [nota, setNota] = useState(canal.direitoEvidenciaNota ?? "");
  const [urlError, setUrlError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const u = url.trim();
    if (u && (!/^https?:\/\/\S+$/i.test(u) || u.length > 500)) return setUrlError("Use um link http(s) de até 500 caracteres");
    setUrlError(null);
    setSaving(true);
    try {
      await api.canais.direito(canal.id, {
        version: canal.version,
        direito,
        evidenciaUrl: u || null,
        evidenciaNota: nota.trim(),
      });
      toast.success("Direito atualizado.");
      await onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="shadow-card">
      <CardHeader>
        <CardTitle>
          <h2>Direito autoral</h2>
        </CardTitle>
        <CardDescription>
          Informativo: não bloqueia nada. "Sem acordo" mostra o aviso antes de gerar cortes. Só o dono muda.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isOwner ? (
          <form onSubmit={(e) => void submit(e)} className="space-y-4" noValidate>
            <Field label="Status de direito" hint={direitoHint[direito]}>
              {({ id, describedBy }) => (
                <NativeSelect id={id} aria-describedby={describedBy} value={direito} onChange={(e) => setDireito(e.target.value as Direito)}>
                  {DIREITOS.map((d) => (
                    <option key={d} value={d}>
                      {direitoLabel[d]}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <Field label="Evidência (link)" error={urlError ?? undefined} hint="Opcional: e-mail, contrato ou página do programa de cortes.">
              {({ id, describedBy, invalid }) => (
                <Input id={id} type="url" value={url} maxLength={500} aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setUrl(e.target.value)} />
              )}
            </Field>
            <Field label="Evidência (nota)" hint={`${nota.length}/2000`}>
              {({ id, describedBy }) => (
                <Textarea id={id} rows={3} maxLength={2000} value={nota} aria-describedby={describedBy} onChange={(e) => setNota(e.target.value)} />
              )}
            </Field>
            {error !== null && <ApiErrorAlert error={error} onReload={() => void onSaved()} />}
            <Button type="submit" disabled={saving} aria-busy={saving}>
              {saving ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
              Salvar direito
            </Button>
          </form>
        ) : (
          <dl className="space-y-3 text-sm">
            <Detail label="Status de direito">
              <DireitoBadge direito={canal.direito} />
            </Detail>
            <Detail label="Evidência (link)">
              {canal.direitoEvidenciaUrl ? (
                <a href={canal.direitoEvidenciaUrl} target="_blank" rel="noreferrer noopener" className="break-all underline">
                  {canal.direitoEvidenciaUrl}
                </a>
              ) : (
                "—"
              )}
            </Detail>
            <Detail label="Evidência (nota)">
              <span className="whitespace-pre-wrap">{canal.direitoEvidenciaNota || "—"}</span>
            </Detail>
            <p className="text-xs text-muted-foreground">Só o dono muda o status de direito.</p>
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

function PerfisCard({ canal, onSaved }: { canal: CanalFonte; onSaved: () => Promise<void> }) {
  const perfis = usePerfisAtivos();
  const [ids, setIds] = useState<string[]>(canal.perfis.map((p) => p.id));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const changed = ids.length !== canal.perfis.length || canal.perfis.some((p) => !ids.includes(p.id));

  async function save() {
    setError(null);
    setSaving(true);
    try {
      await api.canais.update(canal.id, { version: canal.version, perfilIds: ids });
      toast.success("Perfis do canal atualizados.");
      await onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  }

  const options = [...(perfis.data ?? [])];
  for (const p of canal.perfis) if (!options.some((o) => o.id === p.id)) options.push(p as never);

  return (
    <Card className="shadow-card">
      <CardHeader>
        <CardTitle>
          <h2>Perfis</h2>
        </CardTitle>
        <CardDescription>Os perfis que cortam vídeos deste canal (filtram a descoberta).</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <fieldset className="grid gap-2 sm:grid-cols-2">
          <legend className="sr-only">Perfis ligados</legend>
          {options.map((p) => (
            <label key={p.id} className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm has-[:checked]:border-primary">
              <input
                type="checkbox"
                className="size-4 accent-primary"
                checked={ids.includes(p.id)}
                onChange={() => setIds((cur) => (cur.includes(p.id) ? cur.filter((x) => x !== p.id) : [...cur, p.id]))}
              />
              <span className="truncate">{p.name}</span>
            </label>
          ))}
        </fieldset>
        {error !== null && <ApiErrorAlert error={error} onReload={() => void onSaved()} />}
        <Button type="button" size="sm" disabled={!changed || saving} aria-busy={saving} onClick={() => void save()}>
          {saving ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
          Salvar perfis
        </Button>
      </CardContent>
    </Card>
  );
}

function VideosRecentes({ canalId }: { canalId: string }) {
  const videos = useQuery({
    queryKey: ["videos-fonte", { canal: canalId, recentes: true }],
    queryFn: () => api.videosFonte.list({ canalId: [canalId], recomendaveis: false, ordem: "data", limit: 8 }),
  });
  return (
    <Card className="shadow-card">
      <CardHeader>
        <CardTitle>
          <h2>Vídeos mais recentes</h2>
        </CardTitle>
        <CardDescription>
          {videos.data ? `${formatCount(videos.data.total)} vídeos encontrados. ` : ""}
          <Link to={`/app/descobrir?canal=${canalId}`} className="underline">
            Ver todos na descoberta
          </Link>
        </CardDescription>
      </CardHeader>
      <CardContent>
        {videos.isError && <ApiErrorAlert error={videos.error} />}
        {videos.data?.items.length === 0 && <EmptyState titulo="Nenhum vídeo ainda: a busca pode levar alguns minutos." className="py-6" />}
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {videos.data?.items.map((v) => (
            <li key={v.id} className="min-w-0 space-y-1.5">
              <VideoThumb video={v} className="w-full" />
              <p className="line-clamp-2 text-sm font-medium">{v.title}</p>
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <ScoreBadge score={v.score} className="h-5 min-w-7 text-xs" />
                {formatCount(v.views)} views · {formatDateTime(v.publishedAt)}
              </p>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function CanalHistorico({ canal, onReverted }: { canal: CanalFonte; onReverted: () => Promise<void> }) {
  const versions = useQuery({ queryKey: canalVersionsKey(canal.id), queryFn: () => api.canais.versions(canal.id) });
  const perfis = usePerfisAtivos();
  const perfilName = (id: string) => perfis.data?.find((p) => p.id === id)?.name ?? canal.perfis.find((p) => p.id === id)?.name ?? id.slice(0, 8);
  if (versions.isPending) return <p className="text-sm text-muted-foreground">Carregando…</p>;
  if (versions.isError) return <ApiErrorAlert error={versions.error} />;
  return (
    <VersionHistory
      versions={versions.data.items}
      labels={canalFieldLabel}
      formatValue={(field, value) => formatCanalValue(field, value, perfilName)}
      onRevert={async (toVersion) => {
        await api.canais.revert(canal.id, canal.version, toVersion);
        await onReverted();
      }}
      onReload={onReverted}
    />
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
