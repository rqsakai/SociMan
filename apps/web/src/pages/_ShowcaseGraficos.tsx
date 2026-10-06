// Vitrine dos gráficos do analytics (spec 019). SÓ EM DEV: /app/_showcase?graficos=1.
// Dados fictícios: mapa de calor 7 × 24 com a rampa sequencial do tema, barras empilhadas e
// linhas com a paleta categórica, tooltip escapado (o título com <b> aparece como texto) e o
// card com "Ver tabela", CSV e amostra pequena. Troque o tema no menu para ver o setTheme.
import { useMemo } from "react";
import { CardAnalytics } from "@/components/analytics/CardAnalytics";
import type { OpcoesGrafico } from "@/components/analytics/echarts";
import { Grafico } from "@/components/analytics/Grafico";
import { Indicador } from "@/components/analytics/Indicador";
import { useTemaGraficos } from "@/components/analytics/tema";
import { formatCompacto } from "@/lib/metricas";

const DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
const HORAS = Array.from({ length: 24 }, (_, h) => `${h}h`);
const CONTAS = ["@cortes_<b>alfa</b>", "@cortes_beta", "@cortes_gama"];
const celulas = DIAS.flatMap((_, d) => HORAS.map((_, h) => [h, d, Math.round(Math.max(0, Math.sin((h - 6) / 4) * 800 + d * 90 + ((h * 7 + d * 13) % 11) * 40))] as [number, number, number]));
const dias = Array.from({ length: 14 }, (_, i) => `${String(i + 18).padStart(2, "0")}/09`);
const serie = CONTAS.map((_, c) => dias.map((_, i) => Math.round(500 + c * 300 + Math.sin(i / 2 + c) * 250)));

export default function ShowcaseGraficos() {
  const tema = useTemaGraficos();
  const mapa = useMemo<OpcoesGrafico>(
    () => ({
      grid: { left: 40, right: 8, top: 8, bottom: 64 },
      xAxis: { type: "category", data: HORAS, splitArea: { show: false } },
      yAxis: { type: "category", data: DIAS, inverse: true },
      visualMap: { min: 0, max: 1400, calculable: false, orient: "horizontal", left: "center", bottom: 0, inRange: { color: tema.sequencial } },
      series: [{ type: "heatmap", data: celulas, itemStyle: { borderColor: tema.superficie, borderWidth: 2 } }],
    }),
    [tema],
  );
  const barras = useMemo<OpcoesGrafico>(
    () => ({
      grid: { left: 48, right: 8, top: 32, bottom: 24 },
      legend: { top: 0 },
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: dias },
      yAxis: { type: "value" },
      series: CONTAS.map((nome, c) => ({ type: "bar", name: nome, stack: "views", data: serie[c] })),
    }),
    [],
  );
  const linhas = useMemo<OpcoesGrafico>(
    () => ({
      grid: { left: 48, right: 8, top: 32, bottom: 24 },
      legend: { top: 0 },
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: dias },
      yAxis: { type: "value" },
      series: CONTAS.map((nome, c) => ({ type: "line", name: nome, data: serie[c] })),
    }),
    [],
  );
  const tabela = {
    colunas: [{ titulo: "Dia" }, ...CONTAS.map((c) => ({ titulo: c, numerica: true }))],
    linhas: dias.map((d, i) => [d, ...serie.map((s) => s[i]!)]),
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Indicador rotulo="Views ganhas" valor={18400} anterior={15200} formatar={formatCompacto} />
        <Indicador rotulo="Seguidores ganhos" valor={-12} anterior={30} formatar={formatCompacto} />
        <Indicador rotulo="Posts publicados" valor={9} anterior={null} formatar={formatCompacto} />
        <Indicador rotulo="Mediana 24 h" valor={1200} anterior={1200} formatar={formatCompacto} estimado />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CardAnalytics titulo="Mapa de calor" comoLer="mais forte = mais views; zero recua para o fundo." largo amostra={{ n: 3, minimo: 5, suficiente: false, faltam: 2 }}>
          <Grafico opcoes={mapa} descricao="Mapa de calor fictício de views por dia da semana e hora." altura={300} tooltip={(p) => ({ titulo: `${DIAS[(p[0]?.value as number[])[1]!]} ${(p[0]?.value as number[])[0]}h`, linhas: [{ rotulo: "Views", valor: String((p[0]?.value as number[])[2]) }] })} />
        </CardAnalytics>
        <CardAnalytics titulo="Views por dia (barras)" comoLer="uma cor por conta, empilhadas." tabela={tabela}>
          <Grafico opcoes={barras} descricao="Barras empilhadas fictícias de views por dia e conta." />
        </CardAnalytics>
        <CardAnalytics titulo="Views por dia (linhas)" comoLer="uma linha por conta." tabela={tabela}>
          <Grafico opcoes={linhas} descricao="Linhas fictícias de views por dia e conta." />
        </CardAnalytics>
        <CardAnalytics titulo="Card vazio" comoLer="estado vazio com atalho." vazio="Nenhum post no período." onAmpliarPeriodo={() => undefined} />
      </div>
    </div>
  );
}
