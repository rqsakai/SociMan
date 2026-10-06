/*
 * Mapa de calor dia da semana × hora (spec 019, FR-007/FR-016/FR-017): 7 linhas (segunda no topo)
 * × 24 colunas, no fuso de São Paulo.
 *
 * - Rampa sequencial de um tom (`--chart-seq-*`, via visualMap do tema) com a escala visível; a
 *   célula sem dado fica neutra (fora da faixa), para não sumir no fundo nem parecer um zero.
 * - O n de cada célula vai escrito nela (FR-016); a célula com amostra pequena fica esmaecida (sem a
 *   intensidade cheia) e o tooltip diz "amostra pequena (n = X de Y)".
 * - No celular o mapa tem largura mínima e rola na horizontal DENTRO do card, nunca a página.
 * `mapaTabela` dá a tabela alternativa (e o CSV) com as mesmas células.
 */
import { useMemo } from "react";
import type { AnalyticsCelulaMapa } from "@/lib/analytics";
import type { OpcoesGrafico } from "./echarts";
import { Grafico, type ItemTooltip } from "./Grafico";
import type { DadosTabela } from "./TabelaAlternativa";
import { useTemaGraficos } from "./tema";

export const DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"] as const;
const DIAS_CURTOS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
const HORAS = Array.from({ length: 24 }, (_, h) => `${h}h`);
const numero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });

export const faixaHora = (h: number) => `${String(h).padStart(2, "0")}h–${String((h + 1) % 24).padStart(2, "0")}h`;

export interface MapaSemanaProps {
  celulas: AnalyticsCelulaMapa[];
  /** o que é o valor da célula, ex.: "Mediana de views em 24 h" */
  rotuloValor: string;
  /** o que é o n, ex.: "posts" */
  rotuloN: string;
  minimo: number;
  descricao: string;
  formatar?: (v: number) => string;
}

export function mapaTabela(celulas: AnalyticsCelulaMapa[], rotuloValor: string, rotuloN: string): DadosTabela {
  return {
    colunas: [{ titulo: "Dia" }, { titulo: "Hora" }, { titulo: rotuloValor, numerica: true }, { titulo: `n (${rotuloN})`, numerica: true }, { titulo: "Amostra pequena", secundaria: true }],
    linhas: celulas
      .filter((c) => c.n > 0 || (c.valor !== null && c.valor !== 0))
      .map((c) => [DIAS_SEMANA[c.dia] ?? String(c.dia), faixaHora(c.hora), c.valor === null ? null : Math.round(c.valor), c.n, c.amostraPequena]),
  };
}

export function MapaSemana({ celulas, rotuloValor, rotuloN, minimo, descricao, formatar = (v) => numero.format(v) }: MapaSemanaProps) {
  const tema = useTemaGraficos();
  const opcoes = useMemo<OpcoesGrafico>(() => {
    const comValor = celulas.filter((c) => c.valor !== null);
    const max = Math.max(1, ...comValor.map((c) => c.valor!));
    const data = comValor.map((c) => {
      // texto do n: contraste pela posição na rampa (no claro o alto é escuro; no escuro, claro)
      const t = c.valor! / max;
      const forte = t > 0.55;
      const corTexto = forte ? (tema.escuro ? "#0b1220" : "#ffffff") : tema.texto;
      return {
        value: [c.hora, c.dia, c.valor!],
        n: c.n,
        pequena: c.amostraPequena,
        itemStyle: c.amostraPequena ? { opacity: 0.4 } : undefined,
        label: { show: c.n > 0, formatter: String(c.n), color: c.amostraPequena ? tema.texto : corTexto, fontSize: 10 },
      };
    });
    const vazias = celulas.filter((c) => c.valor === null).map((c) => ({ value: [c.hora, c.dia, -1], vazia: true, label: { show: false } }));
    return {
      grid: { left: 40, right: 8, top: 4, bottom: 64 },
      xAxis: { type: "category", data: HORAS, splitArea: { show: false }, axisLabel: { interval: 1 }, axisLine: { show: false } },
      yAxis: { type: "category", data: DIAS_CURTOS, inverse: true, axisLine: { show: false } },
      visualMap: {
        type: "continuous",
        min: 0,
        max,
        calculable: false,
        orient: "horizontal",
        left: "center",
        bottom: 0,
        itemHeight: 160,
        itemWidth: 10,
        inRange: { color: tema.sequencial },
        // a célula sem dado vem com -1: fica fora da faixa e aparece neutra, sem parecer um zero
        outOfRange: { color: tema.borda, opacity: 0.35 },
        formatter: (v: unknown) => formatar(Number(v)),
        text: ["mais", "menos"],
      },
      series: [
        {
          type: "heatmap",
          data: [...vazias, ...data],
          itemStyle: { borderColor: tema.superficie, borderWidth: 2, borderRadius: 3 },
          emphasis: { itemStyle: { borderColor: tema.texto, borderWidth: 1 } },
        },
      ],
    } as OpcoesGrafico;
  }, [celulas, tema, formatar]);

  const tooltip = (itens: ItemTooltip[]) => {
    const d = itens[0]?.data as { value: [number, number, number]; n: number; pequena: boolean; vazia?: boolean } | undefined;
    if (!d || d.vazia) return null;
    const [hora, dia, valor] = d.value;
    return {
      titulo: `${DIAS_SEMANA[dia]}, ${faixaHora(hora)}`,
      linhas: [
        { rotulo: rotuloValor, valor: formatar(valor) },
        { rotulo: rotuloN, valor: numero.format(d.n) },
      ],
      nota: d.pequena ? `amostra pequena (n = ${d.n} de ${minimo})` : "horário de Brasília",
    };
  };

  return (
    <div className="-mx-1 overflow-x-auto px-1" data-mapa-semana>
      <div className="min-w-[640px]">
        <Grafico opcoes={opcoes} descricao={descricao} altura={300} tooltip={tooltip} />
      </div>
    </div>
  );
}
