/*
 * Aba "Curvas" do analytics (spec 019, US4; FR-023/FR-024).
 *
 * - Curvas de crescimento: views por idade (horas desde a publicação) dos até 50 vídeos mais recentes,
 *   todas no mesmo eixo; um vídeo em destaque (cor da conta) e o resto em cinza (dataviz: ênfase).
 *   O destaque se escolhe na lista acima dos cards ou clicando numa linha.
 * - Pequenos múltiplos por conta (com duas ou mais contas): uma grade com as curvas de cada conta.
 * - Meia-vida: horas até 50% das views de 7 dias; vídeo com menos de 7 dias → "ainda não calculável".
 * - Distribuição por conta: caixa (mínimo, quartis, máximo) da medida do post.
 * Tudo é leitura.
 */
import { useMemo, useState } from "react";
import { textoAmostra } from "@/components/analytics/Amostra";
import { CardAnalytics } from "@/components/analytics/CardAnalytics";
import { corDoSlot, useOrdemContas, type OrdemContas } from "@/components/analytics/coresContas";
import type { OpcoesGrafico } from "@/components/analytics/echarts";
import { Grafico } from "@/components/analytics/Grafico";
import type { DadosTabela } from "@/components/analytics/TabelaAlternativa";
import { useTemaGraficos, type TemaGraficos } from "@/components/analytics/tema";
import { Field, NativeSelect } from "@/components/ui/field";
import {
  formatCompacto,
  formatIdadeHoras,
  formatNumero,
  medidaLabel,
  useAnalytics,
  type AnalyticsCurva,
  type AnalyticsCurvas,
  type EstadoFiltroAnalytics,
} from "@/lib/analytics";

const NAO_CALCULAVEL = "ainda não calculável";

const ultimoPonto = (c: AnalyticsCurva) => c.pontos[c.pontos.length - 1];

// `cinzaTodas`: as outras curvas em cinza (gráfico geral) ou na cor da conta, mais claras (pequenos múltiplos).
function linhas(curvas: AnalyticsCurva[], destaque: string | undefined, ordem: OrdemContas, tema: TemaGraficos, cinzaTodas = true) {
  // o destaque vai por último (desenhado por cima das cinzas)
  const ordenadas = [...curvas].sort((a, b) => Number(a.videoId === destaque) - Number(b.videoId === destaque));
  return ordenadas.map((c) => {
    const emDestaque = c.videoId === destaque;
    const cor = emDestaque || !cinzaTodas ? corDoSlot(tema, ordem.slot(c.contaId)) : tema.textoFraco;
    return {
      type: "line" as const,
      id: c.videoId,
      name: c.tituloCurto,
      data: c.pontos.map((p) => [p.idadeH, p.views]),
      showSymbol: emDestaque,
      symbolSize: 8,
      triggerLineEvent: true,
      z: emDestaque ? 3 : 2,
      color: cor,
      lineStyle: { color: cor, width: emDestaque ? 2 : 1, opacity: emDestaque ? 1 : cinzaTodas ? 0.4 : 0.5 },
      itemStyle: { color: cor },
      emphasis: { focus: "series" as const },
    };
  });
}

function eixos(): Pick<OpcoesGrafico, "xAxis" | "yAxis"> {
  return {
    xAxis: { type: "value", name: "idade (h)", nameLocation: "middle", nameGap: 26, min: 0, axisLabel: { formatter: (v: number) => formatIdadeHoras(v) } },
    yAxis: { type: "value", axisLabel: { formatter: (v: number) => formatCompacto(v) } },
  };
}

function montar(dados: AnalyticsCurvas | undefined, destaque: string | undefined, tema: TemaGraficos, ordem: OrdemContas, medida: keyof typeof medidaLabel) {
  const curvas = dados?.curvas ?? [];
  const dist = dados?.distribuicao ?? [];
  const atual = curvas.find((c) => c.videoId === destaque);

  const tabelaCurvas: DadosTabela = {
    colunas: [
      { titulo: "Vídeo" },
      { titulo: "Conta", secundaria: true },
      { titulo: "Em destaque", secundaria: true },
      { titulo: "Idade da última foto (h)", numerica: true, secundaria: true, formatar: (v) => (typeof v === "number" ? formatIdadeHoras(v) : "—") },
      { titulo: "Views", numerica: true },
      { titulo: "Meia-vida (h)", numerica: true, formatar: (v) => (typeof v === "number" ? formatIdadeHoras(v) : NAO_CALCULAVEL) },
    ],
    linhas: curvas.map((c) => [c.tituloCurto, c.conta, c.videoId === destaque, ultimoPonto(c)?.idadeH ?? null, ultimoPonto(c)?.views ?? null, c.meiaVidaH ?? null]),
  };

  const opcoesCurvas: OpcoesGrafico = {
    grid: { left: 56, right: 16, top: 16, bottom: 44 },
    ...eixos(),
    series: linhas(curvas, destaque, ordem, tema),
  };

  // pequenos múltiplos: uma grade por conta, na ordem em que as contas aparecem
  const porConta = new Map<string, { rotulo: string; contaId: string | null; curvas: AnalyticsCurva[] }>();
  for (const c of curvas) {
    const chave = c.contaId ?? c.conta;
    if (!porConta.has(chave)) porConta.set(chave, { rotulo: c.conta, contaId: c.contaId ?? null, curvas: [] });
    porConta.get(chave)!.curvas.push(c);
  }
  const multiplos = [...porConta.values()].map((g) => ({
    ...g,
    opcoes: {
      grid: { left: 48, right: 8, top: 8, bottom: 40 },
      ...eixos(),
      series: linhas(g.curvas, destaque, ordem, tema, false),
    } satisfies OpcoesGrafico,
  }));

  const comMeiaVida = curvas.filter((c) => c.meiaVidaH !== null && c.meiaVidaH !== undefined).sort((a, b) => a.meiaVidaH! - b.meiaVidaH!);
  const opcoesMeiaVida: OpcoesGrafico = {
    grid: { left: 8, right: 24, top: 8, bottom: 24, containLabel: true },
    xAxis: { type: "value", axisLabel: { formatter: (v: number) => formatIdadeHoras(v) } },
    yAxis: { type: "category", inverse: true, data: comMeiaVida.map((c) => c.tituloCurto), axisLabel: { width: 140, overflow: "truncate" } },
    series: [
      {
        type: "bar",
        name: "Meia-vida",
        barMaxWidth: 24,
        itemStyle: { borderRadius: [0, 4, 4, 0] },
        data: comMeiaVida.map((c) => ({ value: c.meiaVidaH!, itemStyle: { color: corDoSlot(tema, ordem.slot(c.contaId)) } })),
      },
    ],
  };

  const opcoesDist: OpcoesGrafico = {
    grid: { left: 8, right: 16, top: 16, bottom: 24, containLabel: true },
    xAxis: { type: "category", data: dist.map((d) => d.rotulo) },
    yAxis: { type: "value", axisLabel: { formatter: (v: number) => formatCompacto(v) } },
    series: [
      {
        type: "boxplot",
        name: medidaLabel[medida],
        boxWidth: [8, 24],
        data: dist.map((d) => {
          const cor = corDoSlot(tema, ordem.slot(d.contaId));
          return { value: [d.min ?? 0, d.q1 ?? 0, d.mediana ?? 0, d.q3 ?? 0, d.max ?? 0], itemStyle: { borderColor: cor, color: "transparent" } };
        }),
      },
    ],
  };
  const tabelaDist: DadosTabela = {
    colunas: [
      { titulo: "Conta" },
      { titulo: "Mínimo", numerica: true, secundaria: true },
      { titulo: "1º quartil", numerica: true, secundaria: true },
      { titulo: "Mediana", numerica: true },
      { titulo: "3º quartil", numerica: true, secundaria: true },
      { titulo: "Máximo", numerica: true, secundaria: true },
      { titulo: "Amostra" },
    ],
    linhas: dist.map((d) => [d.rotulo, d.min ?? null, d.q1 ?? null, d.mediana ?? null, d.q3 ?? null, d.max ?? null, textoAmostra(d.amostra)]),
  };

  return { curvas, atual, tabelaCurvas, opcoesCurvas, multiplos, comMeiaVida, opcoesMeiaVida, dist, opcoesDist, tabelaDist };
}

export function Curvas({ estado }: { estado: EstadoFiltroAnalytics }) {
  const dados = useAnalytics("curvas", estado.filtro);
  const tema = useTemaGraficos();
  const ordem = useOrdemContas();
  const [escolhido, setEscolhido] = useState<string>();
  const curvas = dados.data?.curvas ?? [];
  // padrão: o vídeo mais recente (a API manda os mais recentes primeiro)
  const destaque = curvas.some((c) => c.videoId === escolhido) ? escolhido : curvas[0]?.videoId;
  const v = useMemo(() => montar(dados.data, destaque, tema, ordem, estado.filtro.medida), [dados.data, destaque, tema, ordem, estado.filtro.medida]);
  const comum = { carregando: dados.isPending || !ordem.pronto, erro: dados.error, onAmpliarPeriodo: estado.ampliarPeriodo };
  const semCurvas = curvas.length === 0 ? "Nenhum vídeo publicado no período com fotos para desenhar a curva." : null;
  const nomeDestaque = v.atual ? `"${v.atual.tituloCurto}" (${v.atual.conta})` : "nenhum";
  const escolher = (item: { seriesIndex?: number }) => {
    const serie = (v.opcoesCurvas.series as { id?: string }[] | undefined)?.[item.seriesIndex ?? -1];
    if (serie?.id) setEscolhido(serie.id);
  };

  return (
    <div className="flex flex-col gap-4">
      {curvas.length > 0 && (
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Vídeo em destaque" className="w-full sm:w-96">
            {({ id }) => (
              <NativeSelect id={id} value={destaque ?? ""} onChange={(e) => setEscolhido(e.target.value)}>
                {curvas.map((c) => (
                  <option key={c.videoId} value={c.videoId}>
                    {c.tituloCurto} ({c.conta})
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CardAnalytics
          titulo="Curvas de crescimento"
          comoLer="views acumuladas de cada vídeo pela idade em horas; o vídeo em destaque tem a cor da conta e os outros ficam em cinza. Curvas que achatam cedo pararam de crescer. Clique numa linha para destacá-la."
          vazio={semCurvas}
          tabela={v.tabelaCurvas}
          largo
          {...comum}
        >
          <Grafico
            opcoes={v.opcoesCurvas}
            altura={320}
            onClickItem={escolher}
            descricao={`Views por idade de ${curvas.length} vídeos, alinhados pela hora da publicação. Em destaque: ${nomeDestaque}.`}
            tooltip={(itens) => {
              const p = itens[0];
              const [idade, views] = (Array.isArray(p?.value) ? p.value : []) as number[];
              return p ? { titulo: p.seriesName, linhas: [{ rotulo: "idade", valor: formatIdadeHoras(idade ?? 0) }, { rotulo: "views", valor: formatNumero(views) }] } : null;
            }}
          />
        </CardAnalytics>
        <CardAnalytics
          titulo="Curvas por conta"
          comoLer="as mesmas curvas separadas por conta, na escala de cada uma; compare o formato, não a altura."
          vazio={semCurvas ?? (v.multiplos.length < 2 ? "Só uma conta tem curvas no período; a separação por conta aparece com duas ou mais." : null)}
          largo
          {...comum}
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {v.multiplos.map((g) => (
              <figure key={g.contaId ?? g.rotulo} className="min-w-0">
                <figcaption className="text-sm font-medium">
                  {g.rotulo} <span className="font-normal text-muted-foreground">({g.curvas.length} vídeos)</span>
                </figcaption>
                <Grafico opcoes={g.opcoes} altura={200} descricao={`Curvas de ${g.curvas.length} vídeos de ${g.rotulo}.`} />
              </figure>
            ))}
          </div>
        </CardAnalytics>
        <CardAnalytics
          titulo="Meia-vida"
          comoLer={`horas até o vídeo alcançar metade das views de 7 dias; quanto menor, mais cedo ele "pegou". Vídeos com menos de 7 dias aparecem como "${NAO_CALCULAVEL}" na tabela.`}
          vazio={semCurvas ?? (v.comMeiaVida.length === 0 ? `Nenhum vídeo do período tem 7 dias completos: meia-vida ${NAO_CALCULAVEL}.` : null)}
          tabela={v.tabelaCurvas}
          {...comum}
        >
          <Grafico
            opcoes={v.opcoesMeiaVida}
            altura={Math.max(160, v.comMeiaVida.length * 28 + 40)}
            descricao={`Meia-vida de ${v.comMeiaVida.length} vídeos com 7 dias completos.`}
            tooltip={(itens) => ({ titulo: itens[0]?.name, linhas: [{ rotulo: "meia-vida", valor: formatIdadeHoras(Number(itens[0]?.value ?? 0)) }] })}
          />
        </CardAnalytics>
        <CardAnalytics
          titulo="Distribuição por conta"
          comoLer={`caixa de ${medidaLabel[estado.filtro.medida].toLowerCase()} em cada conta: a linha do meio é a mediana, a caixa vai do 1º ao 3º quartil e as hastes, do mínimo ao máximo.`}
          vazio={v.dist.length === 0 ? "Nenhum post medido no período." : null}
          tabela={v.tabelaDist}
          {...comum}
        >
          <Grafico
            opcoes={v.opcoesDist}
            descricao={`Distribuição de ${medidaLabel[estado.filtro.medida].toLowerCase()} por conta, ${v.dist.length} contas.`}
            tooltip={(itens) => {
              const d = v.dist[itens[0]?.dataIndex ?? -1];
              if (!d) return null;
              return {
                titulo: d.rotulo,
                linhas: [
                  { rotulo: "máximo", valor: formatNumero(d.max) },
                  { rotulo: "3º quartil", valor: formatNumero(d.q3) },
                  { rotulo: "mediana", valor: formatNumero(d.mediana) },
                  { rotulo: "1º quartil", valor: formatNumero(d.q1) },
                  { rotulo: "mínimo", valor: formatNumero(d.min) },
                ],
                nota: textoAmostra(d.amostra),
              };
            }}
          />
        </CardAnalytics>
      </div>
    </div>
  );
}
