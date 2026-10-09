/*
 * Aba "Produtos" (spec 026, FR-051): a tabela do cartão mínimo com paginação no servidor (página e
 * tamanho na URL), ordenação por qualquer número (select, na URL) e CSV da página visível.
 */
import type { MercadoCartaoProduto } from "@sociman/contract";
import { Download, ImageOff } from "lucide-react";
import { useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { baixarCsv } from "@/components/analytics/csv";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { Estimado } from "@/components/mercado/Estimado";
import { EmptyState, HeaderCard } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import {
  estadoLabel,
  formatBp,
  formatCentavos,
  formatCrescimento,
  formatInteiro,
  ORDENS_MERCADO,
  produtoMercadoPath,
  useMercadoProdutos,
  type EstadoFiltroMercado,
} from "@/lib/mercado";
import { tabelaProdutos } from "./Cockpit";

const col = dataTableColumns<MercadoCartaoProduto>();

export function Produtos({ estado }: { estado: EstadoFiltroMercado }) {
  const { filtro, set } = estado;
  const lista = useMercadoProdutos(filtro);
  const rows = useMemo(() => lista.data?.itens ?? [], [lista.data]);
  const total = lista.data?.total;
  const ultima = total === undefined ? undefined : Math.max(Math.ceil(total / filtro.tamanho), 1);
  const foraDoFim = !lista.isPlaceholderData && ultima !== undefined && filtro.pagina > ultima;
  useEffect(() => {
    if (foraDoFim) set({ pagina: ultima === 1 ? null : String(ultima) }, { replace: true });
  }, [foraDoFim, ultima]); // eslint-disable-line react-hooks/exhaustive-deps

  const [ordemCampo, ordemSufixo] = filtro.ordenar.split(":");
  const columns = useMemo(
    () =>
      col.columns([
        col.display({
          id: "produto",
          header: "Produto",
          cell: (c) => {
            const p = c.row.original;
            return (
              <div className="flex min-w-0 items-center gap-2">
                <span className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded bg-muted">
                  {p.imagemUrl ? <img src={p.imagemUrl} alt="" className="size-full object-cover" loading="lazy" /> : <ImageOff className="size-4 text-muted-foreground" aria-hidden="true" />}
                </span>
                <div className="min-w-0">
                  <Link to={produtoMercadoPath(p.id)} className="block truncate font-medium hover:underline">
                    {p.titulo ?? p.redeProdutoId}
                  </Link>
                  <p className="truncate text-xs text-muted-foreground">
                    {p.loja?.nome ?? "—"}
                    {p.loja?.oficial ? " · Loja oficial" : ""}
                  </p>
                </div>
                {p.estado !== "ok" && <Badge variant="outline">{estadoLabel(p.estado)}</Badge>}
                {p.novoEmAlta && <Badge>novo em alta</Badge>}
              </div>
            );
          },
        }),
        col.display({ id: "preco", header: () => <span className="block text-right">Preço</span>, cell: (c) => <span className="block text-right tabular-nums">{formatCentavos(c.row.original.preco?.minCentavos)}</span> }),
        col.display({ id: "comissao", header: () => <span className="block text-right">Comissão</span>, cell: (c) => <span className="block text-right"><Estimado numero={c.row.original.comissaoBp} formatar={formatBp} /></span> }),
        col.display({ id: "comissaoVenda", header: () => <span className="block text-right">Por venda</span>, cell: (c) => <span className="block text-right"><Estimado numero={c.row.original.comissaoPorVendaCentavos} formatar={formatCentavos} /></span> }),
        col.display({ id: "vendas", header: () => <span className="block text-right">Vendas no período</span>, cell: (c) => <span className="block text-right"><Estimado numero={c.row.original.vendasPeriodo} formatar={formatInteiro} /></span> }),
        col.display({ id: "gmv", header: () => <span className="block text-right">GMV no período</span>, cell: (c) => <span className="block text-right"><Estimado numero={c.row.original.gmvPeriodoCentavos} formatar={formatCentavos} /></span> }),
        col.display({ id: "crescimento", header: () => <span className="block text-right">Crescimento</span>, cell: (c) => <span className="block text-right"><Estimado numero={c.row.original.crescimento} formatar={formatCrescimento} /></span> }),
        col.display({ id: "totais", header: () => <span className="block text-right">Vendas totais</span>, cell: (c) => <span className="block text-right"><Estimado numero={c.row.original.vendasTotais} formatar={formatInteiro} /></span> }),
        col.display({ id: "gmvTotal", header: () => <span className="block text-right">GMV total</span>, cell: (c) => <span className="block text-right"><Estimado numero={c.row.original.gmvTotalCentavos} formatar={formatCentavos} /></span> }),
        col.display({ id: "retorno", header: () => <span className="block text-right">Retorno/afiliado/dia</span>, cell: (c) => <span className="block text-right"><Estimado numero={c.row.original.retornoAfiliadoCentavosDia} formatar={formatCentavos} /></span> }),
      ]),
    [],
  );

  return (
    <HeaderCard
      title="Produtos"
      description={total === undefined ? "Carregando…" : `${formatInteiro(total)} produto${total === 1 ? "" : "s"} neste recorte`}
      actions={
        <Button type="button" size="sm" variant="secondary" disabled={rows.length === 0} onClick={() => { const t = tabelaProdutos(rows); baixarCsv("mercado-produtos", t.colunas.map((c) => c.titulo), t.linhas); }}>
          <Download aria-hidden="true" />
          CSV
        </Button>
      }
    >
      <DataTable
        columns={columns}
        data={rows}
        loading={lista.isPending}
        getRowId={(r) => r.id}
        label="Produtos do mercado"
        toolbar={
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Ordenar por" className="w-56">
              {({ id }) => (
                <NativeSelect id={id} value={ordemCampo} onChange={(e) => set({ ordenar: e.target.value === "vendasPeriodo" && !ordemSufixo ? null : `${e.target.value}${ordemSufixo ? `:${ordemSufixo}` : ""}`, pagina: null })}>
                  {ORDENS_MERCADO.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.label}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <Field label="Sentido" className="w-36">
              {({ id }) => (
                <NativeSelect id={id} value={ordemSufixo ?? ""} onChange={(e) => set({ ordenar: `${ordemCampo}${e.target.value ? `:${e.target.value}` : ""}`, pagina: null })}>
                  <option value="">Padrão</option>
                  <option value="desc">Maior primeiro</option>
                  <option value="asc">Menor primeiro</option>
                </NativeSelect>
              )}
            </Field>
          </div>
        }
        empty={<EmptyState titulo="Nada coletado ainda" descricao="Quando o coletor devolver as primeiras fotos, os produtos aparecem aqui. Acompanhe um produto por link na aba Mercado do perfil ou escolha as categorias do nicho." />}
        pagination={{
          modo: "servidor",
          total: total ?? 0,
          pagina: filtro.pagina,
          tamanho: filtro.tamanho,
          onPagina: (p) => set({ pagina: p === 1 ? null : String(p) }),
          onTamanho: (t) => set({ tamanho: t === 25 ? null : String(t), pagina: null }),
        }}
      />
    </HeaderCard>
  );
}
