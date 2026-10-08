/*
 * Ranking dos vídeos (spec 016, US4; R15), na aba "Visão geral" de /app/metricas (spec 019).
 *
 * Filtros na URL (voltar e recarregar mantêm): perfil, conta, origem, período de publicação
 * (`de`, `ate`), ordem (views total, que é o padrão; views 24 h e 7 d, engajamento, velocidade,
 * data) e direção, também pelos cabeçalhos das colunas. A API ordena e pagina ("Carregar mais"); o
 * clique no vídeo leva ao conteúdo no SociMan, ou à página do vídeo quando ele é de fora (ou de uma
 * conta anônima). Linhas compactas: miniatura do conteúdo (ou ícone), legenda cortada em 40
 * caracteres e Views sempre visível; 24 h, 7 d, engajamento e velocidade somem no celular.
 */
import { ArrowDown, ArrowUp, ChevronsUpDown, Film } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns, FilterBar, type FiltroAtivo } from "@/components/data-table";
import { PlatformIcon } from "@/components/PlatformIcon";
import { HeaderCard } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { DateField } from "@/components/ui/date-field";
import { Field, NativeSelect } from "@/components/ui/field";
import {
  formatCompacto,
  formatEngajamento,
  formatVelocidade,
  linkDoVideo,
  nomeDaConta,
  ordemLabel,
  origemMetricasLabel,
  useRanking,
  type MarcoValor,
  type MetricasVideosFilters,
  type OrdemRanking,
  type OrigemMetricas,
  truncar,
  type VideoResumo,
} from "@/lib/metricas";
import { useFiltroUrl } from "@/lib/filtros";
import { formatDateKey, formatDateTime } from "@/lib/tz";
import { usePerfisAtivos } from "@/lib/usePerfis";
import { cn } from "@/lib/utils";
import { FiltroContas, useContasTikTok } from "./FiltroContas";

const col = dataTableColumns<VideoResumo>();
const ORDENS = Object.keys(ordemLabel) as OrdemRanking[];
const RANKING_PARAMS = ["perfil", "conta", "origem", "de", "ate", "ordem", "direcao"] as const;

// Escopo vindo de fora (analytics, spec 019): período e perfil/conta do filtro global da página,
// no lugar dos parâmetros da URL. Ordem, direção e origem continuam na URL.
export interface EscopoRanking {
  de: string;
  ate: string;
  perfilId?: string;
  contaId?: string;
}

export function rankingFilters(params: URLSearchParams, escopo?: EscopoRanking): MetricasVideosFilters {
  if (escopo) {
    const f: MetricasVideosFilters = {
      ...rankingFilters(new URLSearchParams()),
      de: escopo.de,
      ate: escopo.ate,
    };
    const origem = params.get("origem");
    const ordem = params.get("ordem") as OrdemRanking | null;
    if (escopo.perfilId) f.perfilId = escopo.perfilId;
    if (escopo.contaId) f.contaId = escopo.contaId;
    if (origem) f.origem = origem;
    f.ordem = ordem && ORDENS.includes(ordem) ? ordem : "views";
    f.direcao = params.get("direcao") === "asc" ? "asc" : "desc";
    return f;
  }
  const f: MetricasVideosFilters = {};
  const perfil = params.get("perfil");
  const conta = params.get("conta");
  const origem = params.get("origem");
  const de = params.get("de");
  const ate = params.get("ate");
  if (perfil) f.perfilId = perfil;
  if (conta) f.contaId = conta;
  if (origem) f.origem = origem;
  // período invertido: o filtro mostra o aviso e a lista ignora o período
  if (!(de && ate && de > ate)) {
    if (de) f.de = de;
    if (ate) f.ate = ate;
  }
  const ordem = params.get("ordem") as OrdemRanking | null;
  f.ordem = ordem && ORDENS.includes(ordem) ? ordem : "views";
  f.direcao = params.get("direcao") === "asc" ? "asc" : "desc";
  return f;
}

function Marco({ m }: { m: MarcoValor }) {
  if (m.valor === null) return <span className="text-xs text-muted-foreground">{m.motivo === "ainda_nao" ? "ainda não" : "—"}</span>;
  return (
    <span className="tabular-nums" title={m.estimado ? "estimado" : undefined}>
      {formatCompacto(Math.round(m.valor))}
      {m.estimado && <span className="text-muted-foreground">*</span>}
    </span>
  );
}

const numero = { className: "text-right", headerClassName: "text-right" };

// `semFiltroContas`: no analytics (spec 019) o perfil e a conta vêm dos filtros globais da página.
// `escopo`: período, perfil e conta do filtro global (some o "Publicado"; o "Limpar filtros" só
// limpa origem, ordem e direção). `semMoldura`: sem o HeaderCard (o CardAnalytics do analytics já
// dá o título).
export function RankingTable({
  semFiltroContas = false,
  escopo,
  semMoldura = false,
}: {
  semFiltroContas?: boolean;
  escopo?: EscopoRanking;
  semMoldura?: boolean;
} = {}) {
  const [params, set] = useFiltroUrl();
  const filtros = useMemo(() => rankingFilters(params, escopo), [params, escopo]);
  const proprios = escopo ? (["origem", "ordem", "direcao"] as const) : RANKING_PARAMS;
  const lista = useRanking(filtros);
  const rows = useMemo(() => lista.data?.pages.flatMap((p) => p.items) ?? [], [lista.data]);
  const total = lista.data?.pages[0]?.total;
  const de = params.get("de") ?? "";
  const ate = params.get("ate") ?? "";
  const origem = params.get("origem") as OrigemMetricas | null;
  const perfilId = params.get("perfil") ?? "";
  const contaId = params.get("conta") ?? "";
  // perfil, conta e "Publicado" só fora do analytics (sem `escopo`): ficam em "Mais filtros"
  const perfis = usePerfisAtivos();
  const contas = useContasTikTok(escopo || semFiltroContas ? "" : perfilId);
  const ativos: FiltroAtivo[] = [
    ...(origem ? [{ chave: "origem", rotulo: "Origem", valor: origemMetricasLabel[origem] ?? origem, limpar: () => set({ origem: null }) }] : []),
    ...(!escopo && !semFiltroContas && perfilId
      ? [{ chave: "perfil", rotulo: "Perfil", valor: perfis.data?.find((p) => p.id === perfilId)?.name ?? "…", limpar: () => set({ perfil: null, conta: null }), mais: true }]
      : []),
    ...(!escopo && !semFiltroContas && contaId
      ? [{ chave: "conta", rotulo: "Conta", valor: `@${contas.find((c) => c.id === contaId)?.handle ?? "…"}`, limpar: () => set({ conta: null }), mais: true }]
      : []),
    ...(!escopo && (de || ate)
      ? [{ chave: "publicado", rotulo: "Publicado", valor: `${de ? formatDateKey(de) : "…"} a ${ate ? formatDateKey(ate) : "…"}`, limpar: () => set({ de: null, ate: null }), mais: true }]
      : []),
  ];

  const columns = useMemo(() => {
    // Cabeçalho que muda a ordem da API (a mesma do "Ordenar por"): 1º clique, maior primeiro;
    // na coluna ativa, inverte a direção.
    const cabecalho = (ordem: OrdemRanking, titulo: string) => {
      const ativa = filtros.ordem === ordem;
      const Icon = !ativa ? ChevronsUpDown : filtros.direcao === "asc" ? ArrowUp : ArrowDown;
      return (
        <button
          type="button"
          title={`Ordenar por ${ordemLabel[ordem].toLowerCase()}`}
          onClick={() =>
            set({
              ordem: ordem === "views" ? null : ordem,
              direcao: ativa && filtros.direcao === "desc" ? "asc" : null,
            })
          }
          className={cn(
            "-mx-1 inline-flex items-center gap-1 rounded px-1 uppercase hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring",
            ativa && "text-foreground",
          )}
        >
          {titulo}
          <Icon className={cn("size-3.5", !ativa && "opacity-50")} aria-hidden="true" />
        </button>
      );
    };
    return col.columns([
      col.display({
        id: "pos",
        header: "#",
        cell: (c) => <span className="text-xs text-muted-foreground tabular-nums">{c.row.index + 1}</span>,
        meta: {
          className: "hidden w-8 sm:table-cell",
          headerClassName: "hidden w-8 sm:table-cell",
        },
      }),
      col.display({
        id: "video",
        header: "Vídeo",
        cell: (c) => {
          const v = c.row.original;
          const texto = v.legenda || (v.origem === "anonima" ? "Vídeo anônimo" : "Sem legenda");
          return (
            <div className="flex max-w-72 min-w-0 items-center gap-2.5">
              {v.miniaturaUrl ? (
                <img src={v.miniaturaUrl} alt="" loading="lazy" className="h-12 w-7 shrink-0 rounded bg-muted object-cover" />
              ) : (
                <span className="flex h-12 w-7 shrink-0 items-center justify-center rounded bg-muted">
                  {v.origem === "fora" || v.origem === "anonima" ? (
                    <PlatformIcon platform="tiktok" className="size-3.5 text-muted-foreground" />
                  ) : (
                    <Film className="size-3.5 text-muted-foreground" aria-hidden="true" />
                  )}
                </span>
              )}
              <div className="min-w-0">
                <Link to={linkDoVideo(v)} title={texto} aria-label={texto} className="block truncate font-semibold hover:underline">
                  {truncar(texto)}
                </Link>
                <span className="mt-0.5 flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
                  <span className="truncate" title={`${nomeDaConta(v)}${v.perfil ? ` · ${v.perfil.name}` : ""} · ${formatDateTime(v.publicadoEm)}`}>
                    {nomeDaConta(v)} · {formatDateTime(v.publicadoEm)}
                  </span>
                  <Badge variant="outline" className="hidden shrink-0 text-[0.65rem] sm:inline-flex">
                    {origemMetricasLabel[v.origem]}
                  </Badge>
                  {!v.disponivel && <Badge className="shrink-0 bg-destructive text-[0.65rem] text-destructive-foreground">Indisponível</Badge>}
                </span>
              </div>
            </div>
          );
        },
        meta: { className: "py-2" },
      }),
      col.display({
        id: "total",
        header: () => cabecalho("views", "Views"),
        cell: (c) => <span className="font-semibold tabular-nums">{formatCompacto(c.row.original.ultima?.views)}</span>,
        meta: numero,
      }),
      col.display({
        id: "views24h",
        header: () => cabecalho("views24h", "24 h"),
        cell: (c) => <Marco m={c.row.original.views24h} />,
        meta: {
          className: "hidden text-right sm:table-cell",
          headerClassName: "hidden text-right sm:table-cell",
        },
      }),
      col.display({
        id: "views7d",
        header: () => cabecalho("views7d", "7 d"),
        cell: (c) => <Marco m={c.row.original.views7d} />,
        meta: {
          className: "hidden text-right sm:table-cell",
          headerClassName: "hidden text-right sm:table-cell",
        },
      }),
      col.display({
        id: "engajamento",
        header: () => cabecalho("engajamento", "Engaj."),
        cell: (c) => <span className="tabular-nums">{formatEngajamento(c.row.original.engajamento)}</span>,
        meta: {
          className: "hidden text-right md:table-cell",
          headerClassName: "hidden text-right md:table-cell",
        },
      }),
      col.display({
        id: "velocidade",
        header: () => cabecalho("velocidade", "Veloc."),
        cell: (c) => <span className="tabular-nums">{formatVelocidade(c.row.original.velocidade)}</span>,
        meta: {
          className: "hidden text-right lg:table-cell",
          headerClassName: "hidden text-right lg:table-cell",
        },
      }),
    ]);
  }, [filtros.ordem, filtros.direcao, set]);

  const corpo = (
    <>
      {lista.isError ? (
        <ApiErrorAlert error={lista.error} />
      ) : (
        <DataTable
          manual
          label="Ranking de vídeos"
          columns={columns}
          data={rows}
          loading={lista.isPending}
          getRowId={(r) => r.id}
          emptyMessage="Nenhum vídeo coletado neste filtro. A coleta começa depois de conectar a conta com as permissões de métricas."
          pagination={{
            total,
            hasMore: Boolean(lista.hasNextPage),
            onLoadMore: () => void lista.fetchNextPage(),
            loadingMore: lista.isFetchingNextPage,
          }}
        />
      )}
      <p className="pt-2 text-xs text-muted-foreground">
        * estimado: interpolado entre fotos distantes do marco. Engajamento = (curtidas + comentários + compartilhamentos) ÷ visualizações na última foto.
        Velocidade = visualizações por hora nas últimas 24 h de idade.
      </p>
    </>
  );

  return (
    <div className="space-y-4">
      <FilterBar
        principais={
          <>
            <Field label="Origem" className="w-full sm:w-44">
              {({ id }) => (
                <NativeSelect id={id} value={params.get("origem") ?? ""} onChange={(e) => set({ origem: e.target.value || null })}>
                  <option value="">Todas</option>
                  {(Object.keys(origemMetricasLabel) as OrigemMetricas[]).map((o) => (
                    <option key={o} value={o}>
                      {origemMetricasLabel[o]}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <Field label="Ordenar por" className="w-full sm:w-56">
              {({ id }) => (
                <NativeSelect
                  id={id}
                  value={filtros.ordem}
                  onChange={(e) =>
                    set({
                      ordem: e.target.value === "views" ? null : e.target.value,
                    })
                  }
                >
                  {ORDENS.map((o) => (
                    <option key={o} value={o}>
                      {ordemLabel[o]}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <Field label="Direção" className="w-full sm:w-40">
              {({ id }) => (
                <NativeSelect
                  id={id}
                  value={filtros.direcao}
                  onChange={(e) =>
                    set({
                      direcao: e.target.value === "desc" ? null : e.target.value,
                    })
                  }
                >
                  <option value="desc">Maior primeiro</option>
                  <option value="asc">Menor primeiro</option>
                </NativeSelect>
              )}
            </Field>
          </>
        }
        mais={
          escopo ? undefined : (
            <>
              {!semFiltroContas && <FiltroContas perfilId={perfilId} contaId={contaId} set={set} />}
              <fieldset className="space-y-1.5">
                <legend className="text-sm font-medium">Publicado</legend>
                <div className="flex items-center gap-1.5">
                  <DateField aria-label="Publicado de" value={de} onChange={(iso) => set({ de: iso || null })} className="w-40" />
                  <span className="text-sm text-muted-foreground">a</span>
                  <DateField
                    aria-label="Publicado até"
                    value={ate}
                    aria-invalid={Boolean(de && ate && de > ate)}
                    onChange={(iso) => set({ ate: iso || null })}
                    className="w-40"
                  />
                </div>
                {de && ate && de > ate && (
                  <p role="alert" className="text-xs text-destructive">
                    O início é depois do fim; o período foi ignorado.
                  </p>
                )}
              </fieldset>
            </>
          )
        }
        ativos={ativos}
        // "Limpar filtros" também volta a ordem ao padrão, como antes
        onLimpar={() => set(Object.fromEntries(proprios.map((k) => [k, null])))}
      />

      {semMoldura ? (
        <div>{corpo}</div>
      ) : (
        <HeaderCard
          title="Ranking"
          description={
            total === undefined
              ? ordemLabel[filtros.ordem ?? "views"]
              : `${total.toLocaleString("pt-BR")} ${total === 1 ? "vídeo" : "vídeos"} · ${ordemLabel[filtros.ordem ?? "views"]}`
          }
        >
          {corpo}
        </HeaderCard>
      )}
    </div>
  );
}
