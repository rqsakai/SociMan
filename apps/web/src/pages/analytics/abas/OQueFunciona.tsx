/*
 * Aba "O que funciona" do analytics (spec 019, US3; FR-019 a FR-022). A medida do post é a do
 * seletor global; posts aguardando o marco ficam fora.
 *
 * - 3 dispersões (duração, gancho, score) só com posts vinculados a um corte do SociMan: um ponto
 *   por vídeo, no máximo 3 contas com cor (a cor fixa da conta) e o resto em "Outros"; ponto vazado
 *   = valor estimado; clicar abre o detalhe do vídeo. A frase da correlação (Spearman) só aparece
 *   com amostra suficiente.
 * - Canais-fonte: barras da mediana, com o selo de direito e o link para o canal (FR-020).
 * - Hashtags: barras do lift com a linha de referência em 1,0× (só hashtags com n ≥ mínimo).
 * - Modo de envio e padrão de corte: mediana, com o engajamento no tooltip e na tabela (FR-022).
 */
import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CardAnalytics } from "@/components/analytics/CardAnalytics";
import { corDoSlot, ROTULO_OUTROS, useOrdemContas, type OrdemContas } from "@/components/analytics/coresContas";
import type { OpcoesGrafico } from "@/components/analytics/echarts";
import { Grafico, type ItemTooltip } from "@/components/analytics/Grafico";
import type { DadosTabela } from "@/components/analytics/TabelaAlternativa";
import { useTemaGraficos, type TemaGraficos } from "@/components/analytics/tema";
import { Page } from "@/components/shell";
import { notaSemVideo } from "@/components/studio/fonteAnalytics";
import { DireitoBadge } from "@/components/canais/DireitoBadge";
import {
  formatCompacto,
  formatEngajamento,
  formatNumero,
  medidaLabel,
  truncar,
  useAnalytics,
  type AnalyticsDispersao,
  type AnalyticsLinhaRanking,
  type EstadoFiltroAnalytics,
  type Medida,
} from "@/lib/analytics";
import { aprendizadoPath } from "@/lib/aprendizado";
import { direitoLabel } from "@/lib/canais";

const MAX_SERIES_DISPERSAO = 3;
const MAX_BARRAS = 15;
const linkVideo = (id: string) => `/app/metricas/videos/${id}`;
const linkCanal = (id: string) => `/app/fontes/${id}`;
const decimal = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 2 });
const formatLift = (n: number | null | undefined) => (n === null || n === undefined ? "—" : `${decimal.format(n)}×`);
const formatRho = (n: number) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2, minimumFractionDigits: 2 }).format(n).replace("-", "−");
const inteiro = (v: number | null | undefined) => formatCompacto(v === null || v === undefined ? v : Math.round(v));

// ---------------------------------------------------------------------------------------------
// Dispersões

interface PontoDado {
  value: [number, number];
  videoId: string;
  titulo: string;
  conta: string;
  estimado: boolean;
}

function dispersao(d: AnalyticsDispersao | undefined, ordem: OrdemContas, tema: TemaGraficos, eixoX: string, eixoY: string, formatarX: (v: number) => string) {
  const pontos = d?.pontos ?? [];
  // cor pela conta: o id (cor fixa); só sem id (anônima) tenta o rótulo "@handle"
  const slotDe = (p: (typeof pontos)[number]) => (p.contaId ? ordem.slot(p.contaId) : ordem.slotDoRotulo(p.conta));
  // contas com cor, da que tem mais pontos para a que tem menos; só 3 séries (R11), o resto é "Outros"
  const porSlot = new Map<number, { nome: string; n: number }>();
  for (const p of pontos) {
    const slot = slotDe(p);
    if (slot === null) continue;
    const g = porSlot.get(slot) ?? { nome: p.conta ?? ROTULO_OUTROS, n: 0 };
    g.n += 1;
    porSlot.set(slot, g);
  }
  const comCor = [...porSlot.entries()]
    .sort((a, b) => b[1].n - a[1].n || a[0] - b[0])
    .slice(0, MAX_SERIES_DISPERSAO)
    .map(([slot]) => slot)
    .sort((a, b) => a - b);
  const grupos = new Map<number | null, PontoDado[]>(comCor.map((slot) => [slot, []]));
  for (const p of pontos) {
    const slot = slotDe(p);
    const chave = slot !== null && grupos.has(slot) ? slot : null;
    if (!grupos.has(chave)) grupos.set(chave, []);
    grupos.get(chave)!.push({ value: [p.x, p.y], videoId: p.videoId, titulo: p.tituloCurto, conta: p.conta ?? ROTULO_OUTROS, estimado: p.estimado });
  }
  const series = [...grupos.entries()].filter(([, ps]) => ps.length > 0);
  const opcoes: OpcoesGrafico = {
    grid: { left: 8, right: 16, top: series.length > 1 ? 52 : 28, bottom: 32, containLabel: true },
    legend: series.length > 1 ? { top: 0, type: "scroll", icon: "circle", itemWidth: 10, itemHeight: 10 } : undefined,
    xAxis: { type: "value", name: eixoX, nameLocation: "middle", nameGap: 28, scale: true, axisLabel: { formatter: (v: number) => formatarX(v) }, splitLine: { show: false } },
    yAxis: { type: "value", name: eixoY, nameTextStyle: { align: "left" }, axisLabel: { formatter: (v: number) => formatCompacto(v) } },
    series: series.map(([slot, ps]) => {
      const cor = corDoSlot(tema, slot);
      const nome = slot === null ? ROTULO_OUTROS : porSlot.get(slot)!.nome;
      return {
        type: "scatter",
        name: nome,
        symbolSize: 11,
        cursor: "pointer",
        itemStyle: { color: cor, borderColor: tema.superficie, borderWidth: 2 },
        emphasis: { scale: 1.4 },
        data: ps.map((p) => (p.estimado ? { ...p, itemStyle: { color: tema.superficie, borderColor: cor, borderWidth: 2 } } : p)),
      };
    }),
  };
  const tabela: DadosTabela = {
    colunas: [
      { titulo: "Vídeo", formatar: (v, l) => <Link to={linkVideo(String(l[5]))} className="underline-offset-2 hover:underline">{String(v ?? "")}</Link> },
      { titulo: "Conta", secundaria: true },
      { titulo: eixoX, numerica: true },
      { titulo: eixoY, numerica: true },
      { titulo: "Estimado", secundaria: true },
      { titulo: "ID do vídeo", secundaria: true },
    ],
    linhas: pontos.map((p) => [p.tituloCurto, p.conta, p.x, Math.round(p.y), p.estimado, p.videoId]),
  };
  const tooltip = (itens: ItemTooltip[]) => {
    const p = itens[0]?.data as PontoDado | undefined;
    if (!p) return null;
    return {
      titulo: p.titulo || "(sem legenda)",
      linhas: [
        { rotulo: "Conta", valor: p.conta },
        { rotulo: eixoX, valor: formatarX(p.value[0]) },
        { rotulo: eixoY, valor: `${formatNumero(Math.round(p.value[1]))}${p.estimado ? " (estimado)" : ""}` },
      ],
      nota: "Clique para abrir o vídeo",
    };
  };
  return { pontos, opcoes, tabela, tooltip };
}

function FraseCorrelacao({ d, eixoX }: { d: AnalyticsDispersao; eixoX: string }) {
  const c = d.correlacao;
  if (c.rho === null || c.rho === undefined || !c.amostra.suficiente) {
    return (
      <p className="text-sm text-muted-foreground" data-correlacao="sem">
        Correlação só com {c.amostra.minimo} vídeos ou mais (faltam {formatNumero(c.amostra.faltam)}). Os pontos continuam visíveis.
      </p>
    );
  }
  return (
    <p className="text-sm" data-correlacao={formatRho(c.rho)}>
      <span className="font-medium">ρ = {formatRho(c.rho)}</span>: correlação {c.leitura} entre {eixoX.toLowerCase()} e a medida do post (n = {formatNumero(c.amostra.n)}).
    </p>
  );
}

// ---------------------------------------------------------------------------------------------
// Barras horizontais (canais, hashtags, modos, padrões): uma série, uma cor; a maior no topo

function barras(
  linhas: AnalyticsLinhaRanking[],
  tema: TemaGraficos,
  valor: (l: AnalyticsLinhaRanking) => number | null,
  formatar: (n: number | null | undefined) => string,
  opts: { referencia?: number; nomeValor: string },
) {
  const top = linhas.filter((l) => valor(l) !== null).slice(0, MAX_BARRAS);
  const cor = tema.categorica[0]!;
  const opcoes: OpcoesGrafico = {
    grid: { left: 8, right: 56, top: opts.referencia ? 24 : 8, bottom: 8, containLabel: true },
    xAxis: { type: "value", axisLabel: { formatter: (v: number) => (opts.referencia ? `${decimal.format(v)}×` : formatCompacto(v)) } },
    yAxis: { type: "category", inverse: true, data: top.map((l) => truncar(l.rotulo, 24)), axisTick: { show: false } },
    series: [
      {
        type: "bar",
        name: opts.nomeValor,
        barMaxWidth: 24,
        cursor: "pointer",
        itemStyle: { color: cor, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: "right", color: tema.texto, formatter: (p: { value: unknown }) => formatar(Number(p.value)) },
        data: top.map((l) => ({ value: valor(l)!, linha: l, itemStyle: l.amostra.suficiente ? undefined : { opacity: 0.45 } })),
        markLine: opts.referencia
          ? {
              silent: true,
              symbol: "none",
              data: [{ xAxis: opts.referencia }],
              lineStyle: { color: tema.textoFraco, type: "solid", width: 1 },
              // o eixo das categorias é invertido: "start" é o topo
              label: { formatter: "1,0× = mediana geral", position: "start", color: tema.textoFraco },
            }
          : undefined,
      },
    ],
  } as OpcoesGrafico;
  return { top, opcoes, altura: Math.max(120, top.length * 34 + 40) };
}

function tooltipLinha(nomeValor: string, formatar: (n: number | null | undefined) => string, comEngajamento = false) {
  return (itens: ItemTooltip[]) => {
    const l = (itens[0]?.data as { linha: AnalyticsLinhaRanking } | undefined)?.linha;
    if (!l) return null;
    const linhas = [
      { rotulo: nomeValor, valor: formatar(nomeValor === "Lift" ? l.lift : l.mediana) },
      { rotulo: "Posts", valor: formatNumero(l.n) },
    ];
    if (nomeValor !== "Lift") linhas.push({ rotulo: "Lift", valor: formatLift(l.lift) });
    if (comEngajamento) linhas.push({ rotulo: "Engajamento (mediana)", valor: formatEngajamento(l.engajamento) });
    if (l.direito) linhas.push({ rotulo: "Direito", valor: direitoLabel[l.direito] });
    return { titulo: l.rotulo, linhas, nota: l.amostra.suficiente ? undefined : `amostra pequena (n = ${l.n} de ${l.amostra.minimo})` };
  };
}

function tabelaLinhas(linhas: AnalyticsLinhaRanking[], rotulo: string, extra: { direito?: boolean; engajamento?: boolean; link?: (l: string) => string } = {}): DadosTabela {
  return {
    colunas: [
      { titulo: rotulo, formatar: extra.link ? (v, l) => <Link to={extra.link!(String(l[l.length - 1]))} className="underline-offset-2 hover:underline">{String(v)}</Link> : undefined },
      ...(extra.direito ? [{ titulo: "Direito", formatar: (v: unknown) => (v ? <DireitoBadge direito={v as AnalyticsLinhaRanking["direito"] & string} /> : "—") }] : []),
      { titulo: "Posts", numerica: true },
      { titulo: "Mediana", numerica: true },
      { titulo: "Lift", numerica: true, formatar: (v) => formatLift(v as number | null) },
      ...(extra.engajamento ? [{ titulo: "Engajamento (mediana)", numerica: true, formatar: (v: unknown) => formatEngajamento(v as number | null) }] : []),
      { titulo: "Amostra pequena", secundaria: true },
      ...(extra.link ? [{ titulo: "ID", secundaria: true }] : []),
    ],
    linhas: linhas.map((l) => [
      l.rotulo,
      ...(extra.direito ? [l.direito ?? null] : []),
      l.n,
      l.mediana === null ? null : Math.round(l.mediana),
      l.lift === null ? null : Math.round(l.lift * 100) / 100,
      ...(extra.engajamento ? [l.engajamento ?? null] : []),
      !l.amostra.suficiente,
      ...(extra.link ? [l.chave] : []),
    ]),
  };
}

// ---------------------------------------------------------------------------------------------

const EIXOS = [
  { chave: "duracao", titulo: "Duração × desempenho", eixo: "Duração (s)", formatar: (v: number) => `${Math.round(v)} s`, leitura: "duração do clipe" },
  { chave: "gancho", titulo: "Gancho × desempenho", eixo: "Gancho (caracteres)", formatar: (v: number) => formatNumero(Math.round(v)), leitura: "tamanho do gancho" },
  { chave: "score", titulo: "Score × desempenho", eixo: "Score do SociShorts", formatar: (v: number) => formatNumero(Math.round(v)), leitura: "score do SociShorts" },
] as const;

export function OQueFunciona({ estado }: { estado: EstadoFiltroAnalytics }) {
  const { filtro } = estado;
  const dados = useAnalytics("o-que-funciona", filtro);
  const ordem = useOrdemContas();
  const tema = useTemaGraficos();
  const navigate = useNavigate();
  const d = dados.data;
  const carregando = dados.isPending;
  const medida = (d?.contexto.medida ?? filtro.medida) as Medida;
  const eixoY = medidaLabel[medida];
  const excluidos = d?.excluidosSemVinculo ?? 0;
  const aguardando = d?.contexto.aguardando ?? 0;
  const minimo = d?.contexto.minimos.grupo ?? 5;

  const disp = useMemo(
    () => EIXOS.map((e) => ({ ...e, ...dispersao(d?.dispersoes[e.chave], ordem, tema, e.eixo, eixoY, e.formatar), dados: d?.dispersoes[e.chave] })),
    [d, ordem, tema, eixoY],
  );
  const canais = useMemo(() => barras(d?.canais ?? [], tema, (l) => l.mediana, inteiro, { nomeValor: `Mediana (${eixoY.toLowerCase()})` }), [d, tema, eixoY]);
  const hashtags = useMemo(() => barras(d?.hashtags ?? [], tema, (l) => l.lift, formatLift, { referencia: 1, nomeValor: "Lift" }), [d, tema]);
  const modos = useMemo(() => barras(d?.modos ?? [], tema, (l) => l.mediana, inteiro, { nomeValor: "Mediana" }), [d, tema]);
  const padroes = useMemo(() => barras(d?.padroes ?? [], tema, (l) => l.mediana, inteiro, { nomeValor: "Mediana" }), [d, tema]);

  const abrirVideo = (item: { data: unknown }) => {
    const id = (item.data as PontoDado | undefined)?.videoId;
    if (id) navigate(linkVideo(id));
  };
  const abrirCanal = (item: { data: unknown }) => {
    const l = (item.data as { linha?: AnalyticsLinhaRanking } | undefined)?.linha;
    if (l) navigate(linkCanal(l.chave));
  };

  const semVinculo = excluidos > 0 ? ` Vídeos fora do SociMan (sem vínculo): ${formatNumero(excluidos)}.` : "";
  const vazioCorte = (n: number) => (n > 0 ? null : `Nenhum post vinculado a um corte e já medido neste período.${semVinculo}`);

  return (
    <Page>
      {/* spec 023: o "por que deu certo" do perfil (efeito encolhido, n e confiança) */}
      {estado.filtro.perfilId && (
        <p className="rounded-lg bg-muted/50 p-3 text-sm">
          Quer saber por que um post rendeu e que assunto ampliar ou cortar?{" "}
          <Link
            to={aprendizadoPath(estado.filtro.perfilId, undefined, estado.filtro.contaId ? { conta: estado.filtro.contaId } : {})}
            className="font-medium underline"
          >
            Abrir o Aprendizado do perfil
          </Link>
        </p>
      )}
      {notaSemVideo(d?.contexto) && (
        <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground" data-nota-studio>
          {notaSemVideo(d?.contexto)}
        </p>
      )}
      {d && (excluidos > 0 || aguardando > 0) && (
        <p className="text-sm text-muted-foreground" data-excluidos={excluidos}>
          {excluidos > 0 && `Vídeos publicados fora do SociMan (sem vínculo), fora das análises de corte: ${formatNumero(excluidos)}; as hashtags usam todos os posts. `}
          {aguardando > 0 && `Aguardando o marco de ${eixoY.toLowerCase().replace("views em ", "")}: ${formatNumero(aguardando)}.`}
        </p>
      )}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {disp.map((e) => (
          <CardAnalytics
            key={e.chave}
            titulo={e.titulo}
            comoLer={`cada ponto é um vídeo vinculado a um corte: ${e.leitura} no eixo horizontal, ${eixoY.toLowerCase()} no vertical. Ponto vazado = estimado. Clique num ponto para abrir o vídeo.`}
            amostra={e.dados?.correlacao.amostra}
            carregando={carregando || !ordem.pronto}
            erro={dados.error}
            vazio={vazioCorte(e.pontos.length)}
            onAmpliarPeriodo={estado.ampliarPeriodo}
            tabela={e.tabela}
          >
            <div className="flex flex-col gap-2">
              {e.dados && <FraseCorrelacao d={e.dados} eixoX={e.leitura} />}
              <Grafico opcoes={e.opcoes} descricao={`Dispersão de ${e.leitura} contra ${eixoY.toLowerCase()}, ${e.pontos.length} vídeos.`} tooltip={e.tooltip} onClickItem={abrirVideo} />
            </div>
          </CardAnalytics>
        ))}
        <CardAnalytics
          titulo="Canais-fonte"
          comoLer={`mediana de ${eixoY.toLowerCase()} dos posts cortados de cada canal; barra esmaecida = menos de ${minimo} posts. Clique para abrir o canal.`}
          carregando={carregando}
          erro={dados.error}
          vazio={vazioCorte(canais.top.length)}
          onAmpliarPeriodo={estado.ampliarPeriodo}
          tabela={tabelaLinhas(d?.canais ?? [], "Canal", { direito: true, link: linkCanal })}
        >
          <Grafico opcoes={canais.opcoes} descricao={`Mediana por canal-fonte: ${canais.top.map((l) => `${l.rotulo} ${inteiro(l.mediana)}`).join(", ")}.`} altura={canais.altura} tooltip={tooltipLinha(`Mediana`, inteiro)} onClickItem={abrirCanal} />
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5" aria-label="Canais-fonte">
            {canais.top.map((l) => (
              <li key={l.chave} className="flex items-center gap-1.5 text-sm">
                <Link to={linkCanal(l.chave)} className="underline-offset-2 hover:underline">
                  {l.rotulo}
                </Link>
                {l.direito && <DireitoBadge direito={l.direito} />}
              </li>
            ))}
          </ul>
        </CardAnalytics>
        <CardAnalytics
          titulo="Hashtags"
          comoLer={`lift = mediana dos posts com a hashtag ÷ mediana geral; acima de 1,0× a hashtag rende mais que o normal. Só hashtags usadas em ${minimo} posts ou mais.`}
          carregando={carregando}
          erro={dados.error}
          vazio={hashtags.top.length > 0 ? null : `Nenhuma hashtag usada em ${minimo} posts ou mais neste período.`}
          onAmpliarPeriodo={estado.ampliarPeriodo}
          tabela={tabelaLinhas(d?.hashtags ?? [], "Hashtag")}
        >
          <Grafico opcoes={hashtags.opcoes} descricao={`Lift das hashtags: ${hashtags.top.map((l) => `${l.rotulo} ${formatLift(l.lift)}`).join(", ")}.`} altura={hashtags.altura} tooltip={tooltipLinha("Lift", formatLift)} />
        </CardAnalytics>
        <CardAnalytics
          titulo="Modo de envio"
          comoLer={`mediana de ${eixoY.toLowerCase()} por modo (lembrete, rascunho ou publicação direta); o engajamento está no tooltip e na tabela.`}
          carregando={carregando}
          erro={dados.error}
          vazio={vazioCorte(modos.top.length)}
          onAmpliarPeriodo={estado.ampliarPeriodo}
          tabela={tabelaLinhas(d?.modos ?? [], "Modo", { engajamento: true })}
        >
          <Grafico opcoes={modos.opcoes} descricao={`Mediana por modo de envio: ${modos.top.map((l) => `${l.rotulo} ${inteiro(l.mediana)}`).join(", ")}.`} altura={modos.altura} tooltip={tooltipLinha("Mediana", inteiro, true)} />
        </CardAnalytics>
        <CardAnalytics
          titulo="Padrões de corte"
          comoLer={`mediana de ${eixoY.toLowerCase()} por padrão de corte do envio (duração mínima–máxima e layout); o engajamento está no tooltip e na tabela.`}
          carregando={carregando}
          erro={dados.error}
          vazio={vazioCorte(padroes.top.length)}
          onAmpliarPeriodo={estado.ampliarPeriodo}
          tabela={tabelaLinhas(d?.padroes ?? [], "Padrão", { engajamento: true })}
        >
          <Grafico opcoes={padroes.opcoes} descricao={`Mediana por padrão de corte: ${padroes.top.map((l) => `${l.rotulo} ${inteiro(l.mediana)}`).join(", ")}.`} altura={padroes.altura} tooltip={tooltipLinha("Mediana", inteiro, true)} />
        </CardAnalytics>
      </div>
    </Page>
  );
}
