/*
 * Gráfico dos efeitos de uma parte (entrega ou rendimento) (spec 023, R12): uma linha por efeito,
 * o intervalo plausível como barra empilhada (base transparente + faixa) e o efeito como ponto
 * (Scatter). Linha de referência no típico da conta (0 p.p. na entrega, 1× no rendimento). Só Bar e Scatter, já registrados pela
 * 019. O eixo sempre inclui o 0. Os efeitos de amostra pequena e os "não separáveis" ficam fora do gráfico (só na lista e na
 * tabela). Os valores vêm da API na unidade de exibição (p.p. e fator ×).
 */
import { useMemo } from "react";
import type { OpcoesGrafico } from "@/components/analytics/echarts";
import { Grafico, type ItemTooltip } from "@/components/analytics/Grafico";
import { useTemaGraficos } from "@/components/analytics/tema";
import { confiancaLabel, formatEfeito, formatIntervalo, REFERENCIA_PARTE, rotuloFator, type AprendizadoEfeito } from "@/lib/aprendizado";
import { formatNumero, truncar } from "@/lib/metricas";

export const noGrafico = (e: AprendizadoEfeito) =>
  e.confianca !== "amostra_pequena" && e.efeito !== null && e.efeito !== undefined && !!e.intervalo && !e.avisos.some((a) => a.tipo === "nao_separavel" || a.tipo === "quase_so_com");

export function GraficoEfeitos({ efeitos, parte, descricao }: { efeitos: AprendizadoEfeito[]; parte: AprendizadoEfeito["parte"]; descricao: string }) {
  const tema = useTemaGraficos();
  const linhas = useMemo(() => efeitos.filter(noGrafico).sort((a, b) => (b.efeito ?? 0) - (a.efeito ?? 0)), [efeitos]);

  const opcoes = useMemo<OpcoesGrafico>(() => {
    const cor = tema.categorica[0]!;
    const rot = linhas.map((e) => truncar(`${rotuloFator(e.fator)}: ${e.rotulo}`, 28));
    const baixo = linhas.map((e) => e.intervalo![0]!);
    const largura = linhas.map((e) => e.intervalo![1]! - e.intervalo![0]!);
    return {
      grid: { left: 8, right: 24, top: 8, bottom: 28, containLabel: true },
      xAxis: { type: "value", axisLabel: { formatter: (v: number) => formatEfeito(parte, v).replace("≈ ", "") } },
      yAxis: { type: "category", inverse: true, data: rot, axisTick: { show: false } },
      series: [
        // base invisível do intervalo (stack "ic"): começa no limite de baixo
        { type: "bar", name: "base", stack: "ic", silent: true, itemStyle: { color: "transparent" }, data: baixo, barMaxWidth: 14 },
        {
          type: "bar",
          name: "Intervalo plausível",
          stack: "ic",
          barMaxWidth: 14,
          itemStyle: { color: cor, opacity: 0.25, borderRadius: 4 },
          data: largura.map((v, i) => ({ value: v, efeito: linhas[i] })),
          markLine: {
            silent: true,
            symbol: "none",
            data: [{ xAxis: REFERENCIA_PARTE[parte] }],
            lineStyle: { color: tema.textoFraco, type: "solid", width: 1 },
            label: { formatter: parte === "entrega" ? "0 = a conta" : "1× = o típico", position: "start", color: tema.textoFraco },
          },
        },
        {
          type: "scatter",
          name: "Efeito",
          symbolSize: 12,
          itemStyle: { color: cor, borderColor: tema.superficie, borderWidth: 2 },
          data: linhas.map((e, i) => ({ value: [e.efeito!, i], efeito: e })),
        },
      ],
    } as OpcoesGrafico;
  }, [linhas, parte, tema]);

  const tooltip = (itens: ItemTooltip[]) => {
    const e = (itens.find((i) => (i.data as { efeito?: AprendizadoEfeito })?.efeito)?.data as { efeito?: AprendizadoEfeito } | undefined)?.efeito;
    if (!e) return null;
    return {
      titulo: `${rotuloFator(e.fator)}: ${e.rotulo}`,
      linhas: [
        { rotulo: "Efeito", valor: formatEfeito(e.parte, e.efeito) },
        { rotulo: "Intervalo", valor: formatIntervalo(e) },
        { rotulo: "Posts distintos", valor: formatNumero(e.nPosts) },
        { rotulo: "Confiança", valor: confiancaLabel[e.confianca] },
      ],
    };
  };

  if (linhas.length === 0) return <p className="text-sm text-muted-foreground">Nenhum efeito com amostra mínima e separável para desenhar. A lista abaixo mostra os números brutos.</p>;
  return <Grafico opcoes={opcoes} descricao={descricao} altura={Math.max(140, linhas.length * 30 + 48)} tooltip={tooltip} />;
}
