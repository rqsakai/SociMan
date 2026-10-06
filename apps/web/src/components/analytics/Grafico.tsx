/*
 * Gráfico do analytics (spec 019, R1; ADR 0002): um ECharts por elemento, sem echarts-for-react.
 *
 * <Grafico opcoes descricao altura? onClickItem? tooltip? />
 *   opcoes       OpcoesGrafico (sem cores fixas: o tema dá a paleta; `tooltip.formatter` é sempre o daqui)
 *   descricao    texto da leitura acessível (role="img" + aria-label e `aria.label.description`)
 *   altura       px (padrão 280)
 *   onClickItem  clique num ponto, barra ou célula (ex.: abrir o detalhe do vídeo)
 *   tooltip      monta o conteúdo do tooltip como TEXTO; o componente escapa tudo
 *   textura      liga o decal (opt-in; padrão desligado)
 *
 * Ciclo de vida: `init` (SVG, PT-br) no efeito e `dispose` no cleanup (idempotente no StrictMode),
 * `setOption` a cada `opcoes`, `ResizeObserver` → `resize()`, `setTheme` quando o tema muda.
 * Tooltip: o ECharts monta o HTML com innerHTML e os títulos vêm da rede, então TODO texto passa
 * por `echarts.format.encodeHTML` (R1, cuidado 1). Com `prefers-reduced-motion`, sem animação.
 * O ECharts não navega por teclado: a "Ver tabela" do CardAnalytics é o caminho acessível.
 * Textura (decal) DESLIGADA por padrão (dataviz: textura ligada é ruído e risco vestibular); a
 * acessibilidade fica com a tabela alternativa e os rótulos. `textura` liga por opção, e mesmo assim
 * nunca nos mapas de calor (neles a magnitude já é a luminosidade da rampa de um só tom).
 */
import { useEffect, useRef } from "react";
import { echarts, LOCALE, type OpcoesGrafico } from "./echarts";
import { useTemaGraficos } from "./tema";

export interface LinhaTooltip {
  rotulo: string;
  valor: string;
  cor?: string;
}

export interface ConteudoTooltip {
  titulo?: string;
  linhas: LinhaTooltip[];
  nota?: string;
}

/** O que o ECharts passa ao formatter (um item, ou a lista no trigger "axis"). */
export interface ItemTooltip {
  seriesName?: string;
  seriesIndex?: number;
  name?: string;
  value?: unknown;
  data?: unknown;
  color?: unknown;
  dataIndex?: number;
}

export interface ItemClicado {
  seriesIndex?: number;
  seriesName?: string;
  dataIndex: number;
  name: string;
  value: unknown;
  data: unknown;
}

export interface GraficoProps {
  opcoes: OpcoesGrafico;
  descricao: string;
  altura?: number;
  onClickItem?: (item: ItemClicado) => void;
  tooltip?: (itens: ItemTooltip[]) => ConteudoTooltip | null;
  className?: string;
  textura?: boolean;
}

const esc = (s: unknown) => echarts.format.encodeHTML(String(s ?? ""));
const numero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });

function valorTexto(v: unknown): string {
  if (typeof v === "number") return Number.isFinite(v) ? numero.format(v) : "—";
  if (Array.isArray(v)) return valorTexto(v[v.length - 1]);
  if (v === null || v === undefined) return "—";
  return String(v);
}

// Conteúdo padrão: o nome da categoria e uma linha por série ("série: valor").
export function tooltipPadrao(itens: ItemTooltip[]): ConteudoTooltip {
  return {
    titulo: itens[0]?.name,
    linhas: itens.map((p) => ({ rotulo: p.seriesName ?? "", valor: valorTexto(p.value), cor: typeof p.color === "string" ? p.color : undefined })),
  };
}

// Só cores simples entram no style (o resto vira cinza): nada de texto livre num atributo.
const corSegura = (c: string | undefined) => (c && /^(#[0-9a-f]{3,8}|rgba?\([\d\s.,%]+\))$/i.test(c) ? c : "currentColor");

export function htmlTooltip(c: ConteudoTooltip): string {
  const partes: string[] = [];
  if (c.titulo) partes.push(`<div style="font-weight:600;margin-bottom:4px">${esc(c.titulo)}</div>`);
  for (const l of c.linhas) {
    const marca = l.cor ? `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:${corSegura(l.cor)}"></span>` : "";
    const rotulo = l.rotulo ? `${esc(l.rotulo)}: ` : "";
    partes.push(`<div>${marca}${rotulo}<strong style="font-variant-numeric:tabular-nums">${esc(l.valor)}</strong></div>`);
  }
  if (c.nota) partes.push(`<div style="opacity:.75;margin-top:4px;font-size:11px">${esc(c.nota)}</div>`);
  return partes.join("");
}

type Serie = { type?: string; itemStyle?: Record<string, unknown> };
function semDecalNoMapa(series: OpcoesGrafico["series"]): OpcoesGrafico["series"] {
  if (!series) return series;
  const lista = (Array.isArray(series) ? series : [series]) as Serie[];
  return lista.map((s) => (s.type === "heatmap" ? { ...s, itemStyle: { decal: { symbol: "none" }, ...s.itemStyle } } : s)) as OpcoesGrafico["series"];
}

const reduzMovimento = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function Grafico({ opcoes, descricao, altura = 280, onClickItem, tooltip, className, textura = false }: GraficoProps) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<ReturnType<typeof echarts.init> | null>(null);
  const tema = useTemaGraficos();
  const temaInicial = useRef(tema);
  const clique = useRef(onClickItem);
  const montarTooltip = useRef(tooltip);
  clique.current = onClickItem;
  montarTooltip.current = tooltip;

  // init/dispose: no StrictMode o efeito roda duas vezes; o dispose do cleanup e o
  // getInstanceByDom deixam um só ECharts por elemento.
  useEffect(() => {
    const dom = el.current;
    if (!dom) return;
    echarts.getInstanceByDom(dom)?.dispose();
    const c = echarts.init(dom, temaInicial.current.echarts, { renderer: "svg", locale: LOCALE });
    chart.current = c;
    c.on("click", (p) => {
      const ev = p as unknown as ItemClicado;
      clique.current?.({ seriesIndex: ev.seriesIndex, seriesName: ev.seriesName, dataIndex: ev.dataIndex, name: ev.name, value: ev.value, data: ev.data });
    });
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(dom);
    return () => {
      ro.disconnect();
      c.dispose();
      if (chart.current === c) chart.current = null;
    };
  }, []);

  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    if (temaInicial.current !== tema) c.setTheme(tema.echarts);
  }, [tema]);

  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    const base = (opcoes.tooltip && !Array.isArray(opcoes.tooltip) ? opcoes.tooltip : {}) as Record<string, unknown>;
    c.setOption(
      {
        ...opcoes,
        series: semDecalNoMapa(opcoes.series),
        animation: reduzMovimento() ? false : (opcoes.animation ?? true),
        aria: { enabled: true, decal: { show: textura }, label: { enabled: true, description: descricao } },
        tooltip: {
          trigger: "item",
          confine: true,
          ...base,
          formatter: (p: unknown) => {
            const itens = (Array.isArray(p) ? p : [p]) as ItemTooltip[];
            const conteudo = (montarTooltip.current ?? tooltipPadrao)(itens);
            return conteudo ? htmlTooltip(conteudo) : "";
          },
        },
      } as OpcoesGrafico,
      { notMerge: true },
    );
  }, [opcoes, descricao, tema, textura]);

  return <div ref={el} role="img" aria-label={descricao} className={className} style={{ width: "100%", height: altura }} />;
}
