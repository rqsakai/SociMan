/*
 * Tema do ECharts lido dos tokens do app (spec 019, R11; ADR 0002).
 *
 * - Categórica: `--chart-1..8`, em ordem fixa (a cor segue a entidade, nunca a posição).
 * - Sequencial (mapas de calor): `--chart-seq-*`. No claro, "perto de zero" é o passo mais claro e
 *   o valor alto o mais escuro. No escuro, a âncora inverte: o zero recua para a superfície do card
 *   (`--card`) e o valor alto sobe para os passos claros, que são os de mais contraste ali.
 * - Grade, eixos e textos recessivos (`--border`, `--muted-foreground`); linhas de 2 px e
 *   marcadores de 8 px.
 *
 * Os tokens podem ser `oklch(...)`, que o ECharts não interpola (visualMap, decal). Cada cor é
 * resolvida para rgba pintando 1 pixel num canvas: o navegador converte, o tema recebe sRGB.
 * `useTemaGraficos()` relê tudo quando a classe `dark` do <html> muda (MutationObserver).
 */
import { useEffect, useState } from "react";

export interface TemaGraficos {
  escuro: boolean;
  categorica: string[];
  /** do "perto de zero" ao valor mais alto, já na ordem do tema atual */
  sequencial: string[];
  texto: string;
  textoFraco: string;
  borda: string;
  superficie: string;
  /** objeto passado a `echarts.init`/`setTheme` */
  echarts: Record<string, unknown>;
}

let ctx: CanvasRenderingContext2D | null | undefined;

// "oklch(0.25 0.03 263)" → "rgba(30, 38, 56, 1)"; sem canvas (teste/SSR), devolve o valor lido.
function resolverCor(valor: string): string {
  const v = valor.trim();
  if (!v) return v;
  if (ctx === undefined) ctx = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  if (!ctx) return v;
  ctx.clearRect(0, 0, 1, 1);
  ctx.fillStyle = "#000";
  ctx.fillStyle = v;
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
  return `rgba(${r}, ${g}, ${b}, ${Math.round(((a ?? 255) / 255) * 100) / 100})`;
}

const PASSOS_SEQ = [100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700] as const;
// Passos usados na rampa contínua: 5 marcos bastam para o visualMap interpolar.
const RAMPA_CLARO = [100, 250, 400, 550, 700] as const;
const RAMPA_ESCURO = [700, 550, 400, 250, 100] as const;

export function lerTemaGraficos(): TemaGraficos {
  const html = document.documentElement;
  const escuro = html.classList.contains("dark");
  const css = getComputedStyle(html);
  const token = (nome: string) => resolverCor(css.getPropertyValue(nome));

  const categorica = Array.from({ length: 8 }, (_, i) => token(`--chart-${i + 1}`));
  const seq = Object.fromEntries(PASSOS_SEQ.map((p) => [p, token(`--chart-seq-${p}`)])) as Record<number, string>;
  const superficie = token("--card");
  const sequencial = escuro ? [superficie, ...RAMPA_ESCURO.map((p) => seq[p]!)] : RAMPA_CLARO.map((p) => seq[p]!);
  const texto = token("--foreground");
  const textoFraco = token("--muted-foreground");
  const borda = token("--border");
  const popover = token("--popover");

  const eixo = {
    axisLine: { show: true, lineStyle: { color: borda } },
    axisTick: { show: false },
    axisLabel: { color: textoFraco },
    splitLine: { show: true, lineStyle: { color: borda, width: 1 } },
    splitArea: { show: false },
    nameTextStyle: { color: textoFraco },
  };

  return {
    escuro,
    categorica,
    sequencial,
    texto,
    textoFraco,
    borda,
    superficie,
    echarts: {
      color: categorica,
      backgroundColor: "transparent",
      textStyle: { color: texto, fontFamily: "Roboto Variable, ui-sans-serif, system-ui, sans-serif" },
      title: { textStyle: { color: texto }, subtextStyle: { color: textoFraco } },
      legend: { textStyle: { color: textoFraco }, inactiveColor: borda },
      tooltip: {
        backgroundColor: popover,
        borderColor: borda,
        borderWidth: 1,
        textStyle: { color: texto },
        axisPointer: { lineStyle: { color: textoFraco }, crossStyle: { color: textoFraco } },
      },
      categoryAxis: { ...eixo, splitLine: { show: false } },
      valueAxis: { ...eixo, axisLine: { show: false } },
      timeAxis: { ...eixo, splitLine: { show: false } },
      logAxis: { ...eixo, axisLine: { show: false } },
      line: { lineStyle: { width: 2 }, symbolSize: 8, symbol: "circle" },
      scatter: { symbolSize: 8, itemStyle: { borderColor: superficie, borderWidth: 2 } },
      bar: { itemStyle: { borderRadius: [4, 4, 0, 0] } },
      radar: {
        axisName: { color: textoFraco },
        axisLine: { lineStyle: { color: borda } },
        splitLine: { lineStyle: { color: borda } },
        splitArea: { show: false },
        symbolSize: 8,
        lineStyle: { width: 2 },
      },
      boxplot: { itemStyle: { borderWidth: 2 } },
      visualMap: { color: [...sequencial].reverse(), textStyle: { color: textoFraco } },
      calendar: {
        itemStyle: { color: superficie, borderColor: borda, borderWidth: 1 },
        splitLine: { lineStyle: { color: borda } },
        dayLabel: { color: textoFraco },
        monthLabel: { color: textoFraco },
        yearLabel: { show: false },
      },
      markLine: { lineStyle: { color: textoFraco, type: "dashed" }, label: { color: textoFraco } },
    },
  };
}

export function useTemaGraficos(): TemaGraficos {
  const [tema, setTema] = useState(lerTemaGraficos);
  useEffect(() => {
    const html = document.documentElement;
    let escuro = html.classList.contains("dark");
    const obs = new MutationObserver(() => {
      const agora = html.classList.contains("dark");
      if (agora === escuro) return;
      escuro = agora;
      setTema(lerTemaGraficos());
    });
    obs.observe(html, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return tema;
}
