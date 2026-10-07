/*
 * /app/descobrir (spec 006, US2; T042). A tela mais usada: escolher de quais vídeos fazer corte.
 *
 * - Seletor de perfil no topo ("Cortar para"): liga o "já cortado", filtra os canais do perfil e é o
 *   destino da seleção. Fica na URL (?perfil=…), com os filtros, para voltar e compartilhar.
 * - Filtros: canal, período, duração, "só não cortados", "mostrar não recomendados", texto e ordem.
 * - Tabela com paginação no servidor ("Carregar mais", cursor), miniatura, título, canal, duração,
 *   publicação, views, views/h, pontuação e o motivo em uma linha ("Por quê?" abre a conta).
 * - "Selecionar" em um clique, desfazível (toast com "Desfazer"); marcar vários e "Selecionar N".
 * - "Colar link" e "Enviar arquivo" para avulsos.
 * - Barra fixa "N selecionados para <perfil> → Gerar cortes" (abre o EnviarDialog).
 * - `?video=<id>` (spec 019, "Gerar cortes" das oportunidades do analytics): o vídeo aparece em
 *   destaque acima da lista, com o selo de direito e o mesmo "Selecionar"; a geração e o aviso de
 *   direito seguem o fluxo de sempre (princípio II).
 * - spec 023: com perfil, a pontuação soma a afinidade com o que funciona (o motivo cita o tema
 *   quando ele é o principal); vídeos de tema "cortar" ficam ocultos, com "N ocultos por tema
 *   cortado" e o filtro "Mostrar temas cortados" (`?cortados=1`), que os traz com o selo. O aviso de
 *   direito não muda.
 */
import { ApiError } from "@sociman/contract";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CircleAlert, Link2, ListChecks, Loader2, Plus, Scissors, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { PageHeading } from "@/components/PageHeading";
import { HeaderCard, usePageMeta } from "@/components/shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { DireitoBadge } from "../../components/canais/DireitoBadge";
import { ScoreBadge, ScoreReason } from "../../components/canais/ScoreReason";
import { VideoCard } from "../../components/canais/VideoCard";
import { ColarLinkDialog, EnviarArquivoDialog } from "../../components/envios/AvulsoDialogs";
import { EnviarDialog } from "../../components/envios/EnviarDialog";
import { api } from "../../lib/api";
import { canaisKey, formatSeconds, videosKey, type VideoFonte } from "../../lib/canais";
import { envioStatusLabel, enviosKey } from "../../lib/envios";
import { integracoesQuery, youtubeAviso } from "../../lib/integracoes";
import { usePerfisAtivos } from "../../lib/usePerfis";

const PAGE = 50;

const periodos: Record<string, { label: string; dias: number | null }> = {
  "": { label: "Qualquer data", dias: null },
  "7": { label: "Últimos 7 dias", dias: 7 },
  "30": { label: "Últimos 30 dias", dias: 30 },
  "90": { label: "Últimos 3 meses", dias: 90 },
  "365": { label: "Último ano", dias: 365 },
};

const duracoes: Record<string, { label: string; min?: number; max?: number }> = {
  "": { label: "Qualquer duração" },
  curto: { label: "Até 20 min", max: 20 * 60 },
  medio: { label: "20 min a 1 h", min: 20 * 60, max: 3600 },
  longo: { label: "Mais de 1 h", min: 3600 },
};

const ordens: Record<string, string> = { score: "Pontuação", vph: "Views por hora", views: "Views", data: "Mais recentes" };

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function Descobrir() {
  usePageMeta({ title: "Descobrir vídeos" });
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const perfis = usePerfisAtivos();
  const integracoes = useQuery(integracoesQuery);
  const aviso = youtubeAviso(integracoes.data);

  // Filtros em estado local (fonte da verdade) e espelhados na URL (?perfil=…&canal=…) para o
  // voltar do navegador e o link direto; a URL só é lida na entrada.
  const [f, setF] = useState<Record<string, string>>(() => Object.fromEntries(params.entries()));
  const get = (k: string) => f[k] ?? "";
  const setParam = (k: string, v: string) => setF((cur) => ({ ...cur, [k]: v }));
  const setParamsRef = useRef(setParams);
  setParamsRef.current = setParams;
  useEffect(() => {
    setParamsRef.current(Object.fromEntries(Object.entries(f).filter(([, v]) => v)), { replace: true });
  }, [f]);

  // Perfil padrão: o primeiro perfil ativo (a seleção sempre tem um destino).
  const perfilId = get("perfil") || perfis.data?.[0]?.id || "";
  const perfil = perfis.data?.find((p) => p.id === perfilId);
  const canalId = get("canal");
  const periodo = get("periodo");
  const duracao = get("duracao");
  const naoCortados = get("naoCortados") === "1";
  const todos = get("todos") === "1";
  // spec 023: com perfil, os vídeos de tema "cortar" ficam ocultos; o filtro os traz com o selo
  const mostrarCortados = get("cortados") === "1";
  const ordem = get("ordem") || "score";
  const [texto, setTexto] = useState(get("q"));
  const q = useDebounced(texto.trim(), 300);
  useEffect(() => setParam("q", q), [q]); // eslint-disable-line react-hooks/exhaustive-deps

  const canais = useQuery({ queryKey: canaisKey({}), queryFn: () => api.canais.list({}) });

  // Vídeo vindo das oportunidades do analytics (spec 019): buscado à parte, porque os filtros da
  // lista (recomendados, período) podem escondê-lo. A chave fica sob ["videos-fonte"], que o
  // refreshSelecao já invalida.
  const videoDestaqueId = get("video");
  const destaque = useQuery({
    queryKey: ["videos-fonte", "destaque", videoDestaqueId],
    queryFn: () => api.videosFonte.get(videoDestaqueId),
    enabled: Boolean(videoDestaqueId),
  });
  const videoDestaque = destaque.data?.video;

  const filters = useMemo(() => {
    const dias = periodos[periodo]?.dias;
    const dur: { min?: number; max?: number } = duracoes[duracao] ?? {};
    return {
      ...(perfilId ? { perfilId } : {}),
      ...(canalId ? { canalId: [canalId] } : {}),
      ...(q ? { q } : {}),
      ...(dias ? { publicadoDesde: new Date(Math.floor(Date.now() / 3_600_000) * 3_600_000 - dias * 86_400_000).toISOString() } : {}),
      ...(dur.min ? { duracaoMin: dur.min } : {}),
      ...(dur.max ? { duracaoMax: dur.max } : {}),
      ...(naoCortados && perfilId ? { naoCortados: true } : {}),
      recomendaveis: !todos,
      ...(mostrarCortados && perfilId ? { mostrarCortados: true } : {}),
      ordem: ordem as "score" | "views" | "vph" | "data",
      limit: PAGE,
    };
  }, [perfilId, canalId, q, periodo, duracao, naoCortados, todos, ordem, mostrarCortados]);

  const videos = useInfiniteQuery({
    queryKey: videosKey(filters),
    queryFn: ({ pageParam }) => api.videosFonte.list({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: "",
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    enabled: perfis.isSuccess,
  });
  const rows = useMemo(() => videos.data?.pages.flatMap((p) => p.items) ?? [], [videos.data]);
  const total = videos.data?.pages[0]?.total;
  const ocultosPorTema = videos.data?.pages[0]?.ocultosPorTema ?? 0;

  // Selecionados do perfil (envios em "selecionado"): alimentam a barra fixa e o diálogo de geração.
  const selecionados = useQuery({
    queryKey: enviosKey({ perfilId, status: ["selecionado"] }),
    queryFn: () => api.envios.list({ perfilId, status: ["selecionado"], limit: 100 }),
    enabled: Boolean(perfilId),
  });
  const selecionadosItems = selecionados.data?.items ?? [];

  const [marcados, setMarcados] = useState<string[]>([]);
  useEffect(() => setMarcados([]), [perfilId]);
  const [busy, setBusy] = useState<string | null>(null);
  const [duplicado, setDuplicado] = useState<VideoFonte | null>(null);
  const [link, setLink] = useState(false);
  const [arquivo, setArquivo] = useState(false);
  const [enviar, setEnviar] = useState(false);

  async function refreshSelecao() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["videos-fonte"] }),
      queryClient.invalidateQueries({ queryKey: ["envios"] }),
    ]);
  }

  async function desfazer(envioId: string) {
    try {
      const { envio } = await api.envios.get(envioId);
      await api.envios.archive(envio.id, envio.version);
      toast.success("Seleção desfeita.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível desfazer.");
    }
    await refreshSelecao();
  }

  async function selecionar(video: VideoFonte, confirmarDuplicado = false) {
    if (!perfilId) return;
    setBusy(video.id);
    try {
      const { envio } = await api.envios.selecionar(perfilId, { videoFonteId: video.id, confirmarDuplicado: confirmarDuplicado || undefined });
      toast.success(`Selecionado para ${perfil?.name ?? "o perfil"}.`, {
        description: video.title,
        action: { label: "Desfazer", onClick: () => void desfazer(envio.id) },
      });
      await refreshSelecao();
    } catch (err) {
      if (err instanceof ApiError && err.code === "already_sent") setDuplicado(video);
      else if (err instanceof ApiError && err.code === "already_selected") toast.info("Este vídeo já está nos selecionados do perfil.");
      else toast.error(err instanceof ApiError ? err.message : "Não foi possível selecionar.");
    } finally {
      setBusy(null);
    }
  }

  async function selecionarMarcados() {
    if (!perfilId || marcados.length === 0) return;
    setBusy("lote");
    let ok = 0;
    const skipped: string[] = [];
    for (const id of marcados) {
      try {
        await api.envios.selecionar(perfilId, { videoFonteId: id });
        ok++;
      } catch (err) {
        skipped.push(err instanceof ApiError ? err.message : "erro");
      }
    }
    setBusy(null);
    setMarcados([]);
    await refreshSelecao();
    if (ok > 0) toast.success(ok === 1 ? "1 vídeo selecionado." : `${ok} vídeos selecionados.`);
    if (skipped.length > 0) {
      toast.info(`${skipped.length} ${skipped.length === 1 ? "vídeo ficou" : "vídeos ficaram"} de fora`, {
        description: "Já selecionados, já com cortes gerados ou indisponíveis. Selecione um por um para confirmar duplicados.",
      });
    }
  }

  const selecionavel = (v: VideoFonte) => v.disponivel && !v.selecionado.some((s) => s.perfilId === perfilId);

  const col = dataTableColumns<VideoFonte>();
  const columns = col.columns([
    col.display({
      id: "marcar",
      header: () => {
        const pageIds = rows.filter(selecionavel).map((v) => v.id);
        const all = pageIds.length > 0 && pageIds.every((id) => marcados.includes(id));
        return (
          <input
            type="checkbox"
            className="size-4 accent-primary"
            aria-label="Marcar todos os vídeos da lista"
            checked={all}
            disabled={pageIds.length === 0 || !perfilId}
            onChange={() => setMarcados(all ? [] : pageIds)}
          />
        );
      },
      cell: (c) => {
        const v = c.row.original;
        return (
          <input
            type="checkbox"
            className="size-4 accent-primary"
            aria-label={`Marcar ${v.title}`}
            disabled={!selecionavel(v) || !perfilId}
            checked={marcados.includes(v.id)}
            onChange={() => setMarcados((m) => (m.includes(v.id) ? m.filter((x) => x !== v.id) : [...m, v.id]))}
          />
        );
      },
      meta: { className: "w-8" },
    }),
    col.accessor("title", {
      header: "Vídeo",
      enableSorting: false,
      cell: (c) => {
        const v = c.row.original;
        const corte = v.jaCortado.find((j) => j.perfilId === perfilId);
        return (
          <div className="min-w-64 space-y-1.5">
            {v.afinidade?.cortado && (
              <Badge variant="outline" data-tema-cortado>
                tema cortado{v.afinidade.temaNome ? `: ${v.afinidade.temaNome}` : ""}
              </Badge>
            )}
            <VideoCard
              video={v}
              jaCortado={corte ? `Já cortado para ${perfil?.name ?? "o perfil"} (${envioStatusLabel[corte.status as keyof typeof envioStatusLabel] ?? corte.status})` : null}
              className={v.id === videoDestaqueId ? "rounded-md ring-2 ring-primary ring-offset-2 ring-offset-card" : undefined}
            />
            <div className="sm:hidden">
              <ScoreReason video={v} compact />
            </div>
          </div>
        );
      },
      meta: { className: "whitespace-normal" },
    }),
    col.accessor("score", {
      header: "Pontuação",
      enableSorting: false,
      enableGlobalFilter: false,
      cell: (c) => (
        <div className="flex max-w-72 min-w-48 items-start gap-2">
          <ScoreBadge score={c.getValue()} />
          <ScoreReason video={c.row.original} />
        </div>
      ),
      meta: { className: "hidden sm:table-cell whitespace-normal", headerClassName: "hidden sm:table-cell" },
    }),
    col.accessor("durationS", {
      header: "Duração",
      enableSorting: false,
      enableGlobalFilter: false,
      cell: (c) => formatSeconds(c.getValue()),
      meta: { className: "hidden xl:table-cell tabular-nums", headerClassName: "hidden xl:table-cell" },
    }),
    col.display({
      id: "acao",
      header: "",
      cell: (c) => {
        const v = c.row.original;
        const sel = v.selecionado.find((s) => s.perfilId === perfilId);
        if (sel) {
          return (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              aria-label={`Desfazer seleção: ${v.title}`}
              title="Clique para desfazer"
              onClick={() => void desfazer(sel.envioId)}
            >
              <Check aria-hidden="true" />
              Selecionado
            </Button>
          );
        }
        return (
          <Button
            type="button"
            size="sm"
            disabled={!v.disponivel || !perfilId || busy !== null}
            aria-busy={busy === v.id}
            aria-label={`Selecionar para corte: ${v.title}`}
            onClick={() => void selecionar(v)}
          >
            {busy === v.id ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Plus aria-hidden="true" />}
            Selecionar
          </Button>
        );
      },
      meta: { className: "text-right" },
    }),
  ]);

  const canaisOptions = canais.data?.items.filter((c) => !c.archived && (!perfilId || c.perfis.length === 0 || c.perfis.some((p) => p.id === perfilId) || c.id === canalId)) ?? [];
  const semCanais = canais.isSuccess && canais.data.items.filter((c) => !c.archived).length === 0;

  return (
    <div className="flex flex-col gap-6 pb-24">
      <PageHeading
        title="Descobrir vídeos"
        description="Os vídeos dos canais-fonte, do maior potencial de corte para o menor. Selecione os que quer cortar e envie de uma vez."
      />

      {aviso && (
        <Alert variant="destructive">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{aviso.titulo}</AlertTitle>
          <AlertDescription>{aviso.texto}</AlertDescription>
        </Alert>
      )}

      <section aria-label="Destino da seleção" className="flex flex-wrap items-end gap-3 rounded-xl bg-card p-4 shadow-card">
        <Field label="Cortar para o perfil" className="w-full sm:w-72">
          {({ id }) => (
            <NativeSelect id={id} value={perfilId} onChange={(e) => setParam("perfil", e.target.value)} disabled={!perfis.data?.length}>
              {perfis.data?.length === 0 && <option value="">Nenhum perfil ativo</option>}
              {perfis.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" disabled={!perfilId} onClick={() => setLink(true)}>
            <Link2 aria-hidden="true" />
            Colar link
          </Button>
          <Button type="button" variant="outline" disabled={!perfilId} onClick={() => setArquivo(true)}>
            <Upload aria-hidden="true" />
            Enviar arquivo
          </Button>
        </div>
      </section>

      {semCanais && (
        <Alert>
          <CircleAlert aria-hidden="true" />
          <AlertTitle>Nenhum canal-fonte cadastrado</AlertTitle>
          <AlertDescription>
            <p>
              Cadastre um canal em{" "}
              <Link to="/app/fontes" className="underline">
                Canais-fonte
              </Link>{" "}
              para ver os vídeos aqui. Enquanto isso, dá para colar um link ou enviar um arquivo.
            </p>
          </AlertDescription>
        </Alert>
      )}

      {videoDestaqueId && (destaque.isError ? (
        <ApiErrorAlert error={destaque.error} />
      ) : videoDestaque ? (
        <section aria-label="Vídeo escolhido nas métricas" className="flex flex-col gap-3 rounded-xl bg-card p-4 shadow-card ring-2 ring-primary/60">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base font-semibold">Vídeo escolhido nas métricas</h2>
            <div className="flex items-center gap-2">
              <DireitoBadge direito={videoDestaque.canal.direito} />
              <Button type="button" size="sm" variant="ghost" onClick={() => setParam("video", "")}>
                Dispensar
              </Button>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <VideoCard video={videoDestaque} className="flex-1" />
            {(() => {
              const sel = videoDestaque.selecionado.find((s) => s.perfilId === perfilId);
              return sel ? (
                <Button type="button" variant="secondary" size="sm" aria-label={`Desfazer seleção: ${videoDestaque.title}`} onClick={() => void desfazer(sel.envioId)}>
                  <Check aria-hidden="true" />
                  Selecionado
                </Button>
              ) : (
                <Button
                  type="button"
                  size="sm"
                  disabled={!videoDestaque.disponivel || !perfilId || busy !== null}
                  aria-busy={busy === videoDestaque.id}
                  aria-label={`Selecionar para corte: ${videoDestaque.title}`}
                  onClick={() => void selecionar(videoDestaque)}
                >
                  {busy === videoDestaque.id ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Plus aria-hidden="true" />}
                  Selecionar
                </Button>
              );
            })()}
          </div>
          <p className="text-xs text-muted-foreground">
            Selecione e use &quot;Gerar cortes&quot; na barra de baixo, como sempre; o aviso de direito do canal aparece no envio.
          </p>
        </section>
      ) : null)}

      <HeaderCard
        title="Vídeos recomendados"
        description={
          total !== undefined
            ? `${total.toLocaleString("pt-BR")} vídeos com estes filtros${!mostrarCortados && ocultosPorTema > 0 ? ` · ${ocultosPorTema.toLocaleString("pt-BR")} ocultos por tema cortado` : ""}`
            : "Carregando…"
        }
      >
        <div className="grid gap-3 pb-4 sm:grid-cols-2 lg:grid-cols-4">
          <Input type="search" aria-label="Buscar no título" placeholder="Buscar no título" value={texto} onChange={(e) => setTexto(e.target.value)} />
          <NativeSelect aria-label="Canal" value={canalId} onChange={(e) => setParam("canal", e.target.value)}>
            <option value="">Todos os canais{perfil ? " do perfil" : ""}</option>
            {canaisOptions.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect aria-label="Período" value={periodo} onChange={(e) => setParam("periodo", e.target.value)}>
            {Object.entries(periodos).map(([k, p]) => (
              <option key={k} value={k}>
                {p.label}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect aria-label="Duração" value={duracao} onChange={(e) => setParam("duracao", e.target.value)}>
            {Object.entries(duracoes).map(([k, d]) => (
              <option key={k} value={k}>
                {d.label}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect aria-label="Ordenar por" value={ordem} onChange={(e) => setParam("ordem", e.target.value === "score" ? "" : e.target.value)}>
            {Object.entries(ordens).map(([k, label]) => (
              <option key={k} value={k}>
                Ordenar: {label}
              </option>
            ))}
          </NativeSelect>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-primary"
              checked={naoCortados}
              disabled={!perfilId}
              onChange={(e) => setParam("naoCortados", e.target.checked ? "1" : "")}
            />
            Só não cortados
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="size-4 accent-primary" checked={todos} onChange={(e) => setParam("todos", e.target.checked ? "1" : "")} />
            Mostrar não recomendados
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-primary"
              checked={mostrarCortados}
              disabled={!perfilId}
              onChange={(e) => setParam("cortados", e.target.checked ? "1" : "")}
            />
            Mostrar temas cortados
          </label>
          {marcados.length > 0 && (
            <Button type="button" variant="secondary" disabled={busy !== null} aria-busy={busy === "lote"} onClick={() => void selecionarMarcados()}>
              {busy === "lote" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <ListChecks aria-hidden="true" />}
              Selecionar {marcados.length} {marcados.length === 1 ? "marcado" : "marcados"}
            </Button>
          )}
        </div>
        {videos.isError ? (
          <ApiErrorAlert error={videos.error} />
        ) : (
          <DataTable
            label="Vídeos recomendados"
            columns={columns}
            data={rows}
            loading={videos.isPending}
            getRowId={(v) => v.id}
            emptyMessage={
              todos ? "Nenhum vídeo com estes filtros." : "Nenhum vídeo recomendado com estes filtros. Tente \"Mostrar não recomendados\"."
            }
            pagination={{
              hasMore: Boolean(videos.hasNextPage),
              onLoadMore: () => void videos.fetchNextPage(),
              loadingMore: videos.isFetchingNextPage,
            }}
          />
        )}
      </HeaderCard>

      {perfilId && selecionadosItems.length > 0 && (
        <div
          role="region"
          aria-label="Selecionados"
          className="fixed inset-x-4 bottom-4 z-30 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-sidebar-gradient px-4 py-3 text-white shadow-float lg:left-80"
        >
          <p className="text-sm">
            <strong>{selecionadosItems.length}</strong> {selecionadosItems.length === 1 ? "vídeo selecionado" : "vídeos selecionados"} para{" "}
            <strong>{perfil?.name}</strong>
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" className="text-white hover:bg-white/10 hover:text-white" asChild>
              <Link to={`/app/envios?perfil=${perfilId}`}>Ver selecionados</Link>
            </Button>
            <Button size="sm" className="tone-primary" onClick={() => setEnviar(true)}>
              <Scissors aria-hidden="true" />
              Gerar cortes
            </Button>
          </div>
        </div>
      )}

      {perfilId && (
        <>
          <ColarLinkDialog open={link} onOpenChange={setLink} perfilId={perfilId} />
          <EnviarArquivoDialog open={arquivo} onOpenChange={setArquivo} perfilId={perfilId} />
          <EnviarDialog open={enviar} onOpenChange={setEnviar} perfilId={perfilId} perfilName={perfil?.name} envios={selecionadosItems} />
        </>
      )}

      <AlertDialog open={duplicado !== null} onOpenChange={(open) => !open && setDuplicado(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Este vídeo já teve cortes gerados para {perfil?.name ?? "este perfil"}</AlertDialogTitle>
            <AlertDialogDescription>{duplicado?.title}. Selecionar de novo cria outra geração de cortes.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={() => duplicado && void selecionar(duplicado, true)}>Selecionar de novo</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
