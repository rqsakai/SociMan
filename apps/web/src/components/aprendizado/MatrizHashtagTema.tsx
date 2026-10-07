/*
 * Matriz hashtag × tema (spec 023, FR-024; R3): quantos posts de cada tema usam cada hashtag (ou
 * bloco), num Heatmap de um só tom (o da 019). É o que explica o "não separável do tema X".
 */
import { useMemo } from "react";
import type { OpcoesGrafico } from "@/components/analytics/echarts";
import { Grafico, type ItemTooltip } from "@/components/analytics/Grafico";
import type { DadosTabela } from "@/components/analytics/TabelaAlternativa";
import { useTemaGraficos } from "@/components/analytics/tema";
import type { AprendizadoAnalise } from "@/lib/aprendizado";
import { formatNumero, truncar } from "@/lib/metricas";

type Celula = AprendizadoAnalise["matriz"][number];

// As células chegam como lista (bloco × tema → n); os eixos saem delas: blocos do mais usado para o
// menos usado, temas na ordem em que aparecem.
export function eixosMatriz(celulas: Celula[]) {
  const total = new Map<string, number>();
  const temas = new Map<string, string>();
  for (const c of celulas) {
    total.set(c.bloco, (total.get(c.bloco) ?? 0) + c.n);
    if (!temas.has(c.temaId)) temas.set(c.temaId, c.temaNome);
  }
  const hashtags = [...total.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([h]) => h);
  return { hashtags, temas: [...temas.entries()].map(([id, nome]) => ({ id, nome })) };
}

export function tabelaMatriz(celulas: Celula[]): DadosTabela {
  const { hashtags, temas } = eixosMatriz(celulas);
  const n = new Map(celulas.map((c) => [`${c.bloco}|${c.temaId}`, c.n]));
  return {
    colunas: [{ titulo: "Hashtag" }, ...temas.map((t) => ({ titulo: t.nome, numerica: true }))],
    linhas: hashtags.map((h) => [h, ...temas.map((t) => n.get(`${h}|${t.id}`) ?? 0)]),
  };
}

export function MatrizHashtagTema({ matriz: celulas }: { matriz: Celula[] }) {
  const tema = useTemaGraficos();
  const m = useMemo(() => ({ ...eixosMatriz(celulas), celulas }), [celulas]);
  const opcoes = useMemo<OpcoesGrafico>(() => {
    const col = new Map(m.temas.map((t, i) => [t.id, i]));
    const lin = new Map(m.hashtags.map((h, i) => [h, i]));
    const max = Math.max(1, ...m.celulas.map((c) => c.n));
    return {
      grid: { left: 8, right: 8, top: 8, bottom: 56, containLabel: true },
      xAxis: { type: "category", data: m.temas.map((t) => truncar(t.nome, 14)), splitArea: { show: false }, axisLabel: { interval: 0, rotate: m.temas.length > 4 ? 30 : 0 } },
      yAxis: { type: "category", data: m.hashtags.map((h) => truncar(h, 22)), inverse: true, splitArea: { show: false } },
      visualMap: { min: 0, max, calculable: false, orient: "horizontal", left: "center", bottom: 0, itemHeight: 120, text: [formatNumero(max), "0"], inRange: { color: tema.sequencial } },
      series: [
        {
          type: "heatmap",
          data: m.celulas.filter((c) => c.n > 0).map((c) => [col.get(c.temaId) ?? 0, lin.get(c.bloco) ?? 0, c.n]),
          label: { show: true, color: tema.texto },
          itemStyle: { borderColor: tema.superficie, borderWidth: 2, borderRadius: 2 },
        },
      ],
    } as OpcoesGrafico;
  }, [m, tema]);

  const tooltip = (itens: ItemTooltip[]) => {
    const v = itens[0]?.value as [number, number, number] | undefined;
    if (!v) return null;
    return { titulo: m.hashtags[v[1]], linhas: [{ rotulo: m.temas[v[0]]?.nome ?? "", valor: `${formatNumero(v[2])} posts` }] };
  };

  return (
    <Grafico
      opcoes={opcoes}
      tooltip={tooltip}
      altura={Math.max(160, m.hashtags.length * 28 + 90)}
      descricao={`Matriz de ${m.hashtags.length} hashtags por ${m.temas.length} temas: quantos posts de cada tema usam cada hashtag.`}
    />
  );
}
