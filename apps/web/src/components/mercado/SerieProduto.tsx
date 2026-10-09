/*
 * A série de um produto (spec 026, US1/US5): vendidos acumulado, vendas/dia, preço mínimo e nº de
 * criadores ao longo dos dias com foto, no ECharts modular (chunk `graficos`), com o tooltip em
 * TEXTO (o <Grafico> escapa tudo) e a tabela alternativa/CSV pelo <CardAnalytics>.
 */
import type { MercadoSerie } from "@sociman/contract";
import { useMemo } from "react";
import { CardAnalytics } from "@/components/analytics/CardAnalytics";
import type { OpcoesGrafico } from "@/components/analytics/echarts";
import { Grafico, type ItemTooltip } from "@/components/analytics/Grafico";
import type { DadosTabela } from "@/components/analytics/TabelaAlternativa";
import { useTemaGraficos } from "@/components/analytics/tema";
import { formatCentavos, formatInteiro, formatUmaCasa } from "@/lib/mercado";
import { formatDateKey } from "@/lib/tz";

export function SerieProduto({ serie, carregando, erro }: { serie: MercadoSerie | undefined; carregando?: boolean; erro?: unknown }) {
  const tema = useTemaGraficos();
  const diaria = useMemo(() => serie?.diaria ?? [], [serie]);
  const dias = diaria.map((d) => d.dataLocal);

  const opcoes: OpcoesGrafico = useMemo(
    () => ({
      grid: { left: 8, right: 8, top: 32, bottom: 8, containLabel: true },
      legend: { top: 0 },
      xAxis: { type: "category", data: dias.map((d) => formatDateKey(d).slice(0, 5)) },
      yAxis: [
        { type: "value", name: "vendidos", axisLabel: { formatter: (v: number) => formatInteiro(v) } },
        { type: "value", name: "vendas/dia", axisLabel: { formatter: (v: number) => formatUmaCasa(v) } },
      ],
      series: [
        { type: "line", name: "Vendidos (acumulado)", data: diaria.map((d) => d.vendidos.valor ?? null), smooth: false, showSymbol: true, color: tema.categorica[0] },
        { type: "bar", name: "Vendas/dia", yAxisIndex: 1, data: diaria.map((d) => d.vendasDia.valor ?? null), barMaxWidth: 18, color: tema.categorica[1] },
        { type: "line", name: "Criadores", yAxisIndex: 1, data: diaria.map((d) => d.nCriadores.valor ?? null), lineStyle: { type: "dashed" }, color: tema.categorica[2] },
      ],
    }),
    [diaria, dias, tema],
  );

  const tabela: DadosTabela = {
    colunas: [
      { titulo: "Dia" },
      { titulo: "Vendidos", numerica: true },
      { titulo: "Vendas/dia", numerica: true, formatar: (v) => (typeof v === "number" ? formatUmaCasa(v) : "—") },
      { titulo: "Preço mínimo", numerica: true, formatar: (v) => (typeof v === "number" ? formatCentavos(v) : "—") },
      { titulo: "Criadores", numerica: true, secundaria: true },
      { titulo: "Comissão (bp)", numerica: true, secundaria: true },
    ],
    linhas: diaria.map((d) => [formatDateKey(d.dataLocal), d.vendidos.valor ?? null, d.vendasDia.valor ?? null, d.precoMinCentavos ?? null, d.nCriadores.valor ?? null, d.comissaoBp.valor ?? null]),
  };

  const tooltip = (itens: ItemTooltip[]) => {
    const i = itens[0]?.dataIndex ?? 0;
    const d = diaria[i];
    if (!d) return null;
    return {
      titulo: formatDateKey(d.dataLocal),
      linhas: [
        { rotulo: "vendidos", valor: formatInteiro(d.vendidos.valor) },
        { rotulo: "vendas/dia", valor: formatUmaCasa(d.vendasDia.valor) },
        { rotulo: "preço mínimo", valor: formatCentavos(d.precoMinCentavos) },
        { rotulo: "criadores", valor: formatInteiro(d.nCriadores.valor) },
      ],
      nota: "valores estimados a partir das fotos diárias",
    };
  };

  return (
    <CardAnalytics
      titulo="Série do produto"
      comoLer="A linha é o contador de vendidos da página (acumulado); as barras, a média de vendas por dia nos 7 dias anteriores; a linha tracejada, os criadores promovendo. Dias sem foto não aparecem."
      tabela={tabela}
      carregando={carregando}
      erro={erro}
      vazio={!carregando && !erro && diaria.length === 0 ? "Ainda sem fotos no período." : null}
      largo
    >
      <Grafico opcoes={opcoes} descricao="Série de vendidos, vendas por dia e criadores do produto" altura={300} tooltip={tooltip} />
    </CardAnalytics>
  );
}
