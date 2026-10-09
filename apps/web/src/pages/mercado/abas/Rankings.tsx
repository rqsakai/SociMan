/*
 * Aba "Rankings" (spec 026, US5): seletor categoria × tipo × janela (na URL, prefixo `rk`), a
 * foto atual com a variação de posição contra a anterior (setas) e quem saiu; sem categoria,
 * a lista das fotos coletadas no período. CSV da tabela visível.
 */
import { Download } from "lucide-react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { baixarCsv } from "@/components/analytics/csv";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { Estimado } from "@/components/mercado/Estimado";
import { Variacao } from "@/components/mercado/SecoesProduto";
import { EmptyState, HeaderCard } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { Link } from "react-router-dom";
import { useFiltroUrl } from "@/lib/filtros";
import {
  formatCentavos,
  formatInteiro,
  produtoMercadoPath,
  RANKING_JANELAS,
  RANKING_TIPOS,
  rankingTipoLabel,
  useCategoriasMercado,
  useRankings,
  type EstadoFiltroMercado,
  type MercadoRankingItem,
} from "@/lib/mercado";
import { formatDateKey } from "@/lib/tz";

const col = dataTableColumns<MercadoRankingItem>();
const columns = col.columns([
  col.accessor("posicao", { header: () => <span className="block text-right">#</span>, cell: (c) => <span className="block text-right tabular-nums">{c.getValue()}</span> }),
  col.display({
    id: "produto",
    header: "Produto",
    cell: (c) => {
      const p = c.row.original.produto;
      return (
        <div className="min-w-0">
          <Link to={produtoMercadoPath(p.id)} className="block truncate font-medium hover:underline">
            {p.titulo ?? p.redeProdutoId}
          </Link>
          <p className="truncate text-xs text-muted-foreground">
            {p.loja?.nome ?? "—"}
            {p.novoEmAlta ? " · novo em alta" : ""}
          </p>
        </div>
      );
    },
  }),
  col.display({ id: "variacao", header: "Variação", cell: (c) => <Variacao delta={c.row.original.delta ?? null} variacao={c.row.original.variacao} /> }),
  col.accessor("valorExibido", { header: "Valor no ranking", cell: (c) => c.getValue() ?? "—" }),
  col.display({ id: "vendas", header: () => <span className="block text-right">Vendas no período</span>, cell: (c) => <span className="block text-right"><Estimado numero={c.row.original.produto.vendasPeriodo} formatar={formatInteiro} /></span> }),
  col.display({ id: "gmv", header: () => <span className="block text-right">GMV no período</span>, cell: (c) => <span className="block text-right"><Estimado numero={c.row.original.produto.gmvPeriodoCentavos} formatar={formatCentavos} /></span> }),
]);

export function Rankings({ estado }: { estado: EstadoFiltroMercado }) {
  const [params, set] = useFiltroUrl("rk");
  const categoriaId = params.get("categoria") ?? "";
  const tipo = (params.get("tipo") ?? "mais_vendidos") as (typeof RANKING_TIPOS)[number];
  const janela = params.get("janela") ?? "7d";
  const categorias = useCategoriasMercado();
  const q = useRankings(estado.filtro, { ...(categoriaId ? { categoriaId } : {}), tipo, janela });
  const atual = q.data?.atual;

  return (
    <HeaderCard
      title="Rankings"
      description={atual ? `${rankingTipoLabel[tipo]} · ${janela} · foto de ${formatDateKey(atual.dataLocal)}${atual.anteriorDataLocal ? ` (variação contra ${formatDateKey(atual.anteriorDataLocal)})` : ""}` : "Escolha a categoria para ver o ranking atual com a variação de posição."}
      actions={
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Categoria" className="w-56">
            {({ id }) => (
              <NativeSelect id={id} value={categoriaId} onChange={(e) => set({ categoria: e.target.value || null })}>
                <option value="">Todas (só as fotos)</option>
                {categorias.data?.itens.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.caminho}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Tipo" className="w-40">
            {({ id }) => (
              <NativeSelect id={id} value={tipo} onChange={(e) => set({ tipo: e.target.value === "mais_vendidos" ? null : e.target.value })}>
                {RANKING_TIPOS.map((t) => (
                  <option key={t} value={t}>
                    {rankingTipoLabel[t]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Janela" className="w-28">
            {({ id }) => (
              <NativeSelect id={id} value={janela} onChange={(e) => set({ janela: e.target.value === "7d" ? null : e.target.value })}>
                {RANKING_JANELAS.map((j) => (
                  <option key={j} value={j}>
                    {j}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          {atual && atual.itens.length > 0 && (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() =>
                baixarCsv(
                  `ranking-${tipo}-${janela}`,
                  ["Posição", "Produto", "Loja", "Variação", "Delta", "Valor no ranking", "Vendas no período", "GMV no período (centavos)"],
                  atual.itens.map((i) => [i.posicao, i.produto.titulo ?? i.produto.redeProdutoId, i.produto.loja?.nome ?? null, i.variacao, i.delta ?? null, i.valorExibido ?? null, i.produto.vendasPeriodo.valor ?? null, i.produto.gmvPeriodoCentavos.valor ?? null]),
                )
              }
            >
              <Download aria-hidden="true" />
              CSV
            </Button>
          )}
        </div>
      }
    >
      {q.isPending && <Skeleton className="h-24 w-full" />}
      {q.isError && <ApiErrorAlert error={q.error} />}
      {q.data && !categoriaId && (
        <>
          {q.data.fotos.length === 0 ? (
            <EmptyState titulo="Nenhum ranking coletado no período" descricao="Escolha as categorias do nicho nos perfis; os rankings delas entram na fila de hoje." />
          ) : (
            <ul className="divide-y text-sm" aria-label="Fotos de ranking">
              {q.data.fotos.map((f) => (
                <li key={f.id} className="flex flex-wrap items-center gap-2 py-2">
                  <span className="tabular-nums">{formatDateKey(f.dataLocal)}</span>
                  <span>{f.categoria?.caminho ?? "geral"}</span>
                  <Badge variant="outline">{rankingTipoLabel[f.tipo]}</Badge>
                  <Badge variant="outline">{f.janela}</Badge>
                  <span className="text-muted-foreground">{f.nItens} itens</span>
                  {f.categoria && (
                    <button type="button" className="ml-auto text-xs underline" onClick={() => set({ categoria: f.categoria!.id, tipo: f.tipo === "mais_vendidos" ? null : f.tipo, janela: f.janela === "7d" ? null : f.janela })}>
                      ver ranking
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {q.data && categoriaId && !atual && <EmptyState titulo="Sem foto deste ranking no período" descricao="Troque o tipo, a janela ou o período." />}
      {atual && (
        <>
          <DataTable columns={columns} data={atual.itens} getRowId={(r) => `${r.posicao}-${r.produto.id}`} label="Ranking atual" empty={<p className="text-sm text-muted-foreground">Ranking vazio.</p>} />
          {atual.sairam.length > 0 && (
            <div className="mt-3 text-sm">
              <p className="font-medium">Saíram desde a foto anterior</p>
              <ul className="list-disc pl-5">
                {atual.sairam.map((s) => (
                  <li key={s.produto.id}>
                    <Link to={produtoMercadoPath(s.produto.id)} className="hover:underline">
                      {s.produto.titulo ?? s.produto.redeProdutoId}
                    </Link>{" "}
                    <span className="text-muted-foreground">(estava em {s.ultimaPosicao})</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </HeaderCard>
  );
}
