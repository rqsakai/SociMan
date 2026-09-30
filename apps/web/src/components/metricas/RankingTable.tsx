/*
 * Ranking dos vídeos (spec 016, US4; R15), na aba "Ranking" de /app/metricas.
 *
 * Filtros na URL (voltar e recarregar mantêm): perfil, conta, origem, período de publicação
 * (`de`, `ate`), ordem (views 24 h, views 7 d, engajamento, velocidade, data) e direção. A API
 * ordena e pagina ("Carregar mais"); o clique no vídeo leva ao conteúdo no SociMan, ou à página do
 * vídeo quando ele é de fora (ou de uma conta anônima).
 */
import { Film, X } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { useFiltroUrl } from "@/components/conteudos/FiltrosConteudos";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { PlatformIcon } from "@/components/PlatformIcon";
import { HeaderCard } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
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
  type VideoResumo,
} from "@/lib/metricas";
import { formatDateTime } from "@/lib/tz";
import { FiltroContas } from "./FiltroContas";

const col = dataTableColumns<VideoResumo>();
const ORDENS = Object.keys(ordemLabel) as OrdemRanking[];
const RANKING_PARAMS = ["perfil", "conta", "origem", "de", "ate", "ordem", "direcao"] as const;

export function rankingFilters(params: URLSearchParams): MetricasVideosFilters {
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
  f.ordem = ordem && ORDENS.includes(ordem) ? ordem : "views7d";
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

export function RankingTable() {
  const [params, set] = useFiltroUrl();
  const filtros = useMemo(() => rankingFilters(params), [params]);
  const lista = useRanking(filtros);
  const rows = useMemo(() => lista.data?.pages.flatMap((p) => p.items) ?? [], [lista.data]);
  const total = lista.data?.pages[0]?.total;
  const de = params.get("de") ?? "";
  const ate = params.get("ate") ?? "";
  const algum = RANKING_PARAMS.some((k) => params.has(k));

  const columns = useMemo(
    () =>
      col.columns([
        col.display({
          id: "pos",
          header: "#",
          cell: (c) => <span className="text-xs text-muted-foreground tabular-nums">{c.row.index + 1}</span>,
          meta: { className: "w-8" },
        }),
        col.display({
          id: "miniatura",
          header: "",
          cell: (c) =>
            c.row.original.miniaturaUrl ? (
              <img src={c.row.original.miniaturaUrl} alt="" loading="lazy" className="h-16 w-9 rounded bg-muted object-cover" />
            ) : (
              <span className="flex h-16 w-9 items-center justify-center rounded bg-muted">
                {c.row.original.origem === "fora" || c.row.original.origem === "anonima" ? (
                  <PlatformIcon platform="tiktok" className="size-4 text-muted-foreground" />
                ) : (
                  <Film className="size-4 text-muted-foreground" aria-hidden="true" />
                )}
              </span>
            ),
          meta: { className: "w-12 py-2" },
        }),
        col.display({
          id: "video",
          header: "Vídeo",
          cell: (c) => {
            const v = c.row.original;
            return (
              <div className="min-w-48">
                <Link to={linkDoVideo(v)} className="line-clamp-2 font-semibold hover:underline">
                  {v.legenda || (v.origem === "anonima" ? "Vídeo anônimo" : "Sem legenda")}
                </Link>
                <span className="mt-0.5 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                  {nomeDaConta(v)}
                  {v.perfil && ` · ${v.perfil.name}`}
                  {` · ${formatDateTime(v.publicadoEm)}`}
                  <Badge variant="outline" className="text-[0.65rem]">
                    {origemMetricasLabel[v.origem]}
                  </Badge>
                  {!v.disponivel && <Badge className="bg-destructive text-[0.65rem] text-destructive-foreground">Indisponível</Badge>}
                </span>
              </div>
            );
          },
        }),
        col.display({ id: "views24h", header: "Views 24 h", cell: (c) => <Marco m={c.row.original.views24h} />, meta: numero }),
        col.display({ id: "views7d", header: "Views 7 d", cell: (c) => <Marco m={c.row.original.views7d} />, meta: numero }),
        col.display({
          id: "total",
          header: "Views (total)",
          cell: (c) => <span className="tabular-nums">{formatCompacto(c.row.original.ultima?.views)}</span>,
          meta: { className: "hidden text-right md:table-cell", headerClassName: "hidden text-right md:table-cell" },
        }),
        col.display({
          id: "engajamento",
          header: "Engajamento",
          cell: (c) => <span className="tabular-nums">{formatEngajamento(c.row.original.engajamento)}</span>,
          meta: numero,
        }),
        col.display({
          id: "velocidade",
          header: "Velocidade",
          cell: (c) => <span className="tabular-nums">{formatVelocidade(c.row.original.velocidade)}</span>,
          meta: { className: "hidden text-right sm:table-cell", headerClassName: "hidden text-right sm:table-cell" },
        }),
      ]),
    [],
  );

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <FiltroContas perfilId={params.get("perfil") ?? ""} contaId={params.get("conta") ?? ""} set={set} />
          <Field label="Origem" className="w-full sm:w-44">
            {({ id }) => (
              <NativeSelect id={id} value={params.get("origem") ?? ""} onChange={(e) => set({ origem: e.target.value })}>
                <option value="">Todas</option>
                {(Object.keys(origemMetricasLabel) as OrigemMetricas[]).map((o) => (
                  <option key={o} value={o}>
                    {origemMetricasLabel[o]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Publicado</legend>
            <div className="flex items-center gap-1.5">
              <Input type="date" aria-label="Publicado de" value={de} onChange={(e) => set({ de: e.target.value })} className="w-auto" />
              <span className="text-sm text-muted-foreground">a</span>
              <Input type="date" aria-label="Publicado até" value={ate} aria-invalid={Boolean(de && ate && de > ate)} onChange={(e) => set({ ate: e.target.value })} className="w-auto" />
            </div>
            {de && ate && de > ate && (
              <p role="alert" className="text-xs text-destructive">
                O início é depois do fim; o período foi ignorado.
              </p>
            )}
          </fieldset>
          <Field label="Ordenar por" className="w-full sm:w-56">
            {({ id }) => (
              <NativeSelect id={id} value={filtros.ordem} onChange={(e) => set({ ordem: e.target.value === "views7d" ? null : e.target.value })}>
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
              <NativeSelect id={id} value={filtros.direcao} onChange={(e) => set({ direcao: e.target.value === "desc" ? null : e.target.value })}>
                <option value="desc">Maior primeiro</option>
                <option value="asc">Menor primeiro</option>
              </NativeSelect>
            )}
          </Field>
          {algum && (
            <Button type="button" variant="ghost" size="sm" className="h-9" onClick={() => set(Object.fromEntries(RANKING_PARAMS.map((k) => [k, null])))}>
              <X aria-hidden="true" />
              Limpar filtros
            </Button>
          )}
        </div>
      </div>

      <HeaderCard
        title="Ranking"
        description={total === undefined ? ordemLabel[filtros.ordem ?? "views7d"] : `${total.toLocaleString("pt-BR")} ${total === 1 ? "vídeo" : "vídeos"} · ${ordemLabel[filtros.ordem ?? "views7d"]}`}
      >
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
            pagination={{ total, hasMore: Boolean(lista.hasNextPage), onLoadMore: () => void lista.fetchNextPage(), loadingMore: lista.isFetchingNextPage }}
          />
        )}
        <p className="pt-2 text-xs text-muted-foreground">
          * estimado: interpolado entre fotos distantes do marco. Engajamento = (curtidas + comentários + compartilhamentos) ÷ visualizações na última foto. Velocidade =
          visualizações por hora nas últimas 24 h de idade.
        </p>
      </HeaderCard>
    </div>
  );
}
