/*
 * Distribuição de uma foto de público (spec 022, FR-016/FR-021/FR-024; R12): gênero ou territórios
 * dos seguidores de UMA conta, como barras horizontais de um tom só (a cor de magnitude da rampa
 * sequencial da 019, nunca uma cor por rótulo).
 *
 * - O rótulo e a % vão escritos ao lado da barra, com a mudança em p.p. (▲/▼ e texto) contra a foto de
 *   comparação; "novo" e "saiu" quando o rótulo só aparece numa das duas fotos. Nada depende de cor.
 * - Acima do gráfico: a data da foto ("anterior ao período" em destaque), a de comparação e os
 *   seguidores na data (a referência de FR-025; a TikTok não diz sobre quantos calculou).
 * - Territórios: "Outros" = 100 − a soma, em tom esmaecido.
 * - Tooltip pelo <Grafico>, que escapa o texto (o território vem como veio no arquivo; ADR 0002).
 * `distribuicaoTabela` dá a tabela alternativa e o CSV (fonte, data_foto, rotulo, pct, pct_comparacao, dif_pp).
 */
import { useMemo } from "react";
import { formatNumero, FONTE_STUDIO, type PublicoConta, type PublicoDistribuicao } from "@/lib/analytics";
import { cn } from "@/lib/utils";
import type { OpcoesGrafico } from "./echarts";
import { Grafico, type ItemTooltip } from "./Grafico";
import type { DadosTabela } from "./TabelaAlternativa";
import { useTemaGraficos } from "./tema";

const pct1 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 1 });
export const formatPct = (v: number | null | undefined) => (v === null || v === undefined ? "sem dado" : `${pct1.format(v)}%`);
export const dataBr = (dia: string) => dia.split("-").reverse().join("/");

export function formatPp(dif: number | null | undefined): string | null {
  if (dif === null || dif === undefined) return null;
  if (Math.abs(dif) < 0.05) return "= 0 p.p.";
  return `${dif > 0 ? "▲" : "▼"} ${pct1.format(Math.abs(dif))} p.p.`;
}

type Item = PublicoDistribuicao["itens"][number];

// texto ao lado da barra: "61% · ▲ 3 p.p.", "4% · novo", "saiu (antes 2%)"
function textoItem(i: Item): string {
  if (i.marca === "saiu") return `saiu (antes ${formatPct(i.pctComparacao)})`;
  const partes = [formatPct(i.pct)];
  if (i.marca === "novo") partes.push("novo");
  else {
    const pp = formatPp(i.difPp);
    if (pp) partes.push(pp);
  }
  return partes.join(" · ");
}

export function distribuicaoTabela(contas: PublicoConta[], tipo: "genero" | "territorios"): DadosTabela {
  const varias = contas.length > 1;
  const linhas: DadosTabela["linhas"] = [];
  for (const c of contas) {
    const d = c[tipo];
    if (!d) continue;
    const base = (rotulo: string, pct: number | null, comp: number | null, dif: number | null) => [
      ...(varias ? [c.conta.rotulo] : []),
      "studio",
      d.dataFoto,
      rotulo,
      pct,
      comp,
      dif,
    ];
    for (const i of d.itens) linhas.push(base(i.rotuloExibicao, i.pct, i.pctComparacao, i.difPp));
    if (tipo === "territorios" && d.outrosPct !== null) linhas.push(base("Outros", d.outrosPct, null, null));
  }
  return {
    colunas: [
      ...(varias ? [{ titulo: "conta" }] : []),
      { titulo: "fonte", secundaria: true },
      { titulo: "data_foto", formatar: (v) => dataBr(String(v)) },
      { titulo: "rotulo" },
      { titulo: "pct", numerica: true },
      { titulo: "pct_comparacao", numerica: true, secundaria: true },
      { titulo: "dif_pp", numerica: true },
    ],
    linhas,
  };
}

export interface DistribuicaoProps {
  dist: PublicoDistribuicao;
  tipo: "genero" | "territorios";
  /** nome do gráfico na leitura acessível, ex.: "Gênero dos seguidores de @conta" */
  descricao: string;
  className?: string;
}

export function Distribuicao({ dist, tipo, descricao, className }: DistribuicaoProps) {
  const tema = useTemaGraficos();
  // o passo mais forte da rampa: o de mais contraste com o card, no claro e no escuro
  const cor = tema.sequencial[tema.sequencial.length - 1]!;
  const linhas = useMemo(() => {
    const l = dist.itens.map((i) => ({ rotulo: i.rotuloExibicao, pct: i.pct, texto: textoItem(i), item: i as Item | null }));
    if (tipo === "territorios" && dist.outrosPct !== null) l.push({ rotulo: "Outros", pct: dist.outrosPct, texto: formatPct(dist.outrosPct), item: null });
    return l;
  }, [dist, tipo]);

  const opcoes = useMemo<OpcoesGrafico>(
    () =>
      ({
        grid: { left: 8, right: 132, top: 4, bottom: 4, containLabel: true },
        xAxis: { type: "value", min: 0, max: 100, show: false },
        yAxis: {
          type: "category",
          inverse: true,
          data: linhas.map((l) => l.rotulo),
          axisLine: { show: false },
          axisLabel: { color: tema.texto, width: 110, overflow: "truncate" },
        },
        series: [
          {
            type: "bar",
            barMaxWidth: 22,
            data: linhas.map((l) => ({
              value: l.pct ?? 0,
              linha: l,
              itemStyle: { color: cor, opacity: l.item ? 1 : 0.45, borderRadius: [0, 4, 4, 0] },
              label: { show: true, position: "right", formatter: l.texto, color: tema.texto, fontSize: 12 },
            })),
          },
        ],
      }) as OpcoesGrafico,
    [linhas, cor, tema],
  );

  const tooltip = (itens: ItemTooltip[]) => {
    const l = (itens[0]?.data as { linha?: (typeof linhas)[number] } | undefined)?.linha;
    if (!l) return null;
    const i = l.item;
    return {
      titulo: l.rotulo,
      linhas: [
        { rotulo: `Foto de ${dataBr(dist.dataFoto)}`, valor: formatPct(l.pct) },
        ...(i && dist.dataFotoComparacao ? [{ rotulo: `Foto de ${dataBr(dist.dataFotoComparacao)}`, valor: formatPct(i.pctComparacao) }] : []),
        ...(i && formatPp(i.difPp) ? [{ rotulo: "Mudança", valor: formatPp(i.difPp)! }] : []),
      ],
      nota: l.item ? `Fonte: ${FONTE_STUDIO} (importação ${dist.importacaoId.slice(0, 8)})` : "100% menos a soma dos países listados",
    };
  };

  return (
    <div className={cn("flex min-w-0 flex-col gap-2", className)} data-distribuicao={tipo}>
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground" data-data-foto={dist.dataFoto}>
        <span>
          Foto de <span className="font-medium text-foreground">{dataBr(dist.dataFoto)}</span>
        </span>
        {dist.anteriorAoPeriodo && (
          <span className="rounded-full bg-warning/15 px-2 py-0.5 font-medium text-foreground ring-1 ring-warning/50" data-anterior-ao-periodo>
            anterior ao período
          </span>
        )}
        <span>{dist.dataFotoComparacao ? `comparada com a de ${dataBr(dist.dataFotoComparacao)}` : "sem foto anterior para comparar"}</span>
        {dist.seguidoresNaData !== null && <span>· {formatNumero(dist.seguidoresNaData)} seguidores na data</span>}
      </p>
      <Grafico opcoes={opcoes} descricao={descricao} altura={Math.max(80, linhas.length * 36 + 12)} tooltip={tooltip} />
    </div>
  );
}
