/*
 * Aba "Visão geral" do analytics (spec 019, US1; FR-012 a FR-015).
 *
 * - 6 indicadores do período, cada um com o anterior de mesma duração e a variação (▲/▼, ou
 *   "sem base de comparação").
 * - Views ganhas por dia, uma linha por conta, com a cor fixa da conta (coresContas) e "Outros"
 *   para a 9ª conta em diante e para as anônimas.
 * - Insights das regras fixas (sem IA): frase, n e, abaixo do mínimo, o que falta.
 * - Principais vídeos (top 10 por views ganhas) → detalhe do vídeo.
 * - Ranking da 016 (FR-001), inteiro (ordem por select e cabeçalho, "Carregar mais"), dentro de um
 *   card: o período, o perfil e a conta vêm do filtro global (`escopo`), inclusive o padrão de 7 d
 *   sem período na URL. A tabela alternativa e o CSV usam as linhas já carregadas (mesma query).
 */
import { Film, Hourglass, Lightbulb } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Amostra } from "@/components/analytics/Amostra";
import { CardAnalytics } from "@/components/analytics/CardAnalytics";
import { corDoSlot, ROTULO_OUTROS, useOrdemContas, type OrdemContas } from "@/components/analytics/coresContas";
import type { OpcoesGrafico } from "@/components/analytics/echarts";
import { Grafico, type ItemTooltip, type LinhaTooltip } from "@/components/analytics/Grafico";
import { Indicador } from "@/components/analytics/Indicador";
import type { DadosTabela } from "@/components/analytics/TabelaAlternativa";
import { useTemaGraficos, type TemaGraficos } from "@/components/analytics/tema";
import { RankingTable, rankingFilters, type EscopoRanking } from "@/components/metricas/RankingTable";
import {
  comparacaoDe,
  diasStudioDe,
  fonteDe,
  fonteLabel,
  NOTA_FUSO_STUDIO,
  studioDoContexto,
  visitasDe,
  type FonteCalendario,
} from "@/components/studio/fonteAnalytics";
import { Page } from "@/components/shell";
import { Button } from "@/components/ui/button";
import {
  formatCompacto,
  formatEngajamento,
  formatNumero,
  medidaLabel,
  truncar,
  useAnalytics,
  type AnalyticsIndicador,
  type AnalyticsInsight,
  type AnalyticsPostResumo,
  type AnalyticsVisaoGeral,
  type EstadoFiltroAnalytics,
  type Medida,
} from "@/lib/analytics";
import { useFiltroUrl } from "@/lib/filtros";
import { linkDoVideo, nomeDaConta, origemMetricasLabel, useRanking, type MarcoValor } from "@/lib/metricas";
import { useAuth } from "@/lib/authStore";
import { studioContaPath, useCoberturaStudio } from "@/lib/studio";
import { formatDateKey, formatDateTime } from "@/lib/tz";
import { cn } from "@/lib/utils";

const diaCurto = (dia: string) => `${dia.slice(8, 10)}/${dia.slice(5, 7)}`;
const linkVideo = (id: string) => `/app/metricas/videos/${id}`;

type Chave = AnalyticsIndicador["chave"];
const ORDEM_INDICADORES: Chave[] = ["views", "likes", "engajamento", "seguidores", "posts", "mediana_post"];

function rotuloIndicador(chave: Chave, medida: Medida): string {
  switch (chave) {
    case "views":
      return "Views ganhas";
    case "likes":
      return "Curtidas ganhas";
    case "engajamento":
      return "Engajamento";
    case "seguidores":
      return "Seguidores ganhos";
    case "posts":
      return "Posts publicados";
    case "mediana_post":
      return `Mediana por post (${medidaLabel[medida].replace(/^Views em /, "")})`;
  }
}

const formatoIndicador = (chave: Chave) => (chave === "engajamento" ? formatEngajamento : chave === "posts" || chave === "seguidores" ? formatNumero : (n: number | null | undefined) => formatCompacto(n === null || n === undefined ? n : Math.round(n)));

// ---------------------------------------------------------------------------------------------
// Série diária: uma linha por conta com cor (slot 0..7); o resto (9ª em diante, anônimas) soma em "Outros".
// Spec 020 (FR-019, R12): uma conta com dias importados do Studio vira duas séries com a mesma cor,
// "— coletado" (contínua) e "— Studio" (tracejada, opacidade 0,6), com null nos dias da outra fonte.
// Sem Studio, a série é a mesma da 019. O tooltip traz a fonte e o valor da outra (comparação).

interface SerieConta {
  conta: string;
  nome: string;
  slot: number | null;
  studio: boolean;
  valores: (number | null)[];
  comparacao: (number | null)[];
}

const nomeDaSerie = (s: SerieConta, comStudio: Set<string>) => (s.studio ? `${s.nome} — Studio` : comStudio.has(s.conta) ? `${s.nome} — coletado` : s.nome);

function serieDiaria(dados: AnalyticsVisaoGeral | undefined, ordem: OrdemContas, tema: TemaGraficos, de: string, ate: string, comVisitas: boolean) {
  const serie = dados?.serieDiaria ?? [];
  const chaveConta = (c: { contaId?: string | null }) => {
    const slot = ordem.slot(c.contaId);
    return slot === null ? ROTULO_OUTROS : (c.contaId as string);
  };
  const comStudio = new Set<string>();
  for (const d of serie) for (const c of d.porConta) if (fonteDe(c) === "studio") comStudio.add(chaveConta(c));

  const contas = new Map<string, SerieConta>();
  const porConta = new Map<string, { nome: string; slot: number | null; valores: number[] }>();
  const fontes: string[] = [];
  const visitas: (number | null)[] = [];
  serie.forEach((d, i) => {
    const doDia = new Set<string>();
    let visitasDia: number | null = null;
    for (const c of d.porConta) {
      const slot = ordem.slot(c.contaId);
      const conta = chaveConta(c);
      const nome = slot === null ? ROTULO_OUTROS : c.rotulo;
      const studio = fonteDe(c) === "studio";
      const chave = studio ? `${conta}|studio` : conta;
      let s = contas.get(chave);
      if (!s) {
        // sem Studio na conta, a linha fica em 0 nos dias sem dado (como na 019)
        const vazio = comStudio.has(conta) ? null : 0;
        s = { conta, nome, slot, studio, valores: serie.map(() => vazio), comparacao: serie.map(() => null) };
        contas.set(chave, s);
      }
      s.valores[i] = (s.valores[i] ?? 0) + c.views;
      if (slot !== null) s.comparacao[i] = comparacaoDe(c);
      let t = porConta.get(conta);
      if (!t) {
        t = { nome, slot, valores: serie.map(() => 0) };
        porConta.set(conta, t);
      }
      t.valores[i]! += c.views;
      doDia.add(fonteDe(c));
      const v = visitasDe(c);
      if (v !== null) visitasDia = (visitasDia ?? 0) + v;
    }
    fontes.push(doDia.size > 1 ? "misto" : (doDia.values().next().value ?? "coletado"));
    visitas.push(visitasDia);
  });
  // ordem da legenda: pelo slot (estável), "Outros" por último; o coletado antes do Studio
  const series = [...contas.values()].sort((a, b) => (a.slot ?? 99) - (b.slot ?? 99) || Number(a.studio) - Number(b.studio));
  const colunas = [...porConta.values()].sort((a, b) => (a.slot ?? 99) - (b.slot ?? 99));
  const total = colunas.reduce((t, s) => t + s.valores.reduce((x, y) => x + y, 0), 0);
  const temStudio = comStudio.size > 0;
  const temVisitas = visitas.some((v) => v !== null);
  const tabela: DadosTabela = {
    colunas: [
      { titulo: "Dia" },
      ...colunas.map((s) => ({ titulo: s.nome, numerica: true })),
      ...(temStudio ? [{ titulo: "Fonte" }] : []),
      ...(temVisitas ? [{ titulo: "Visitas ao perfil", numerica: true, secundaria: true }] : []),
    ],
    linhas: serie.map((d, i) => [d.dia, ...colunas.map((s) => s.valores[i]!), ...(temStudio ? [fontes[i]!] : []), ...(temVisitas ? [visitas[i] ?? null] : [])]),
  };
  const linhasVisiveis = series.length + (comVisitas && temVisitas ? 1 : 0);
  const varios = linhasVisiveis > 1;
  const opcoes: OpcoesGrafico = {
    grid: { left: 8, right: 16, top: varios ? 36 : 12, bottom: 8, containLabel: true },
    legend: varios ? { top: 0, type: "scroll", icon: "roundRect", itemWidth: 14, itemHeight: 3 } : undefined,
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", boundaryGap: false, data: serie.map((d) => diaCurto(d.dia)) },
    yAxis: { type: "value", axisLabel: { formatter: (v: number) => formatCompacto(v) } },
    series: [
      ...series.map((s) => {
        const cor = corDoSlot(tema, s.slot);
        return {
          type: "line" as const,
          name: nomeDaSerie(s, comStudio),
          data: s.valores,
          showSymbol: serie.length <= 31,
          symbolSize: 8,
          lineStyle: { width: 2, color: cor, type: s.studio ? ("dashed" as const) : ("solid" as const), opacity: s.studio ? 0.6 : 1 },
          itemStyle: { color: cor, borderColor: tema.superficie, borderWidth: 2, opacity: s.studio ? 0.6 : 1 },
          emphasis: { focus: "series" as const },
        };
      }),
      ...(comVisitas && temVisitas
        ? [
            {
              type: "line" as const,
              name: "Visitas ao perfil",
              data: visitas,
              showSymbol: false,
              lineStyle: { width: 1.5, color: tema.textoFraco, type: "dotted" as const },
              itemStyle: { color: tema.textoFraco },
            },
          ]
        : []),
    ],
  };
  // tooltip: o valor de cada série no dia, com a fonte e a outra fonte para comparar
  const tooltip = (itens: ItemTooltip[]) => {
    const i = itens[0]?.dataIndex;
    if (i === undefined) return null;
    const linhas: LinhaTooltip[] = [];
    for (const p of itens) {
      if (p.value === null || p.value === undefined) continue;
      const s = series[p.seriesIndex ?? -1];
      linhas.push({ rotulo: p.seriesName ?? "", valor: formatNumero(p.value as number), cor: typeof p.color === "string" ? p.color : undefined });
      const comp = s?.comparacao[i];
      if (s && comp !== null && comp !== undefined) linhas.push({ rotulo: `  ${s.studio ? "coletado" : "Studio"} (comparação)`, valor: formatNumero(comp) });
    }
    const f = fontes[i];
    return { titulo: serie[i] ? formatDateKey(serie[i].dia) : undefined, linhas, nota: temStudio ? `Fonte: ${fonteLabel[(f ?? "coletado") as FonteCalendario]}` : undefined };
  };
  const nomesContas = colunas.map((s) => s.nome).join(", ");
  return {
    vazia: serie.length === 0 || series.length === 0 || total === 0,
    tabela,
    opcoes,
    tooltip,
    temStudio,
    temVisitas,
    descricao: `Views ganhas por dia, de ${de} a ${ate}, uma linha por conta (${nomesContas}). Total: ${formatNumero(total)}.${temStudio ? " Linhas tracejadas: dias importados do Studio." : ""}`,
  };
}

// ---------------------------------------------------------------------------------------------

function Insights({ insights }: { insights: AnalyticsInsight[] }) {
  return (
    <ul className="flex flex-col gap-2" aria-label="Insights do período">
      {insights.map((i) => (
        <li key={i.regra} data-insight={i.regra} className={cn("flex gap-3 rounded-lg border p-3", i.pendente && "border-dashed")}>
          {i.pendente ? <Hourglass className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" /> : <Lightbulb className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />}
          <div className="min-w-0 flex-1">
            <p className={cn("text-sm", i.pendente ? "text-muted-foreground" : "font-medium")}>{i.frase}</p>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              {i.pendente && <span>sem conclusão</span>}
              <Amostra amostra={i.amostra} />
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function Principais({ posts, ordem, tema }: { posts: AnalyticsPostResumo[]; ordem: OrdemContas; tema: TemaGraficos }) {
  return (
    <ol className="flex flex-col divide-y" aria-label="Principais vídeos do período">
      {posts.map((p, i) => (
        <li key={p.videoId} className="flex items-center gap-3 py-2">
          <span className="w-5 shrink-0 text-right text-sm text-muted-foreground tabular-nums">{i + 1}</span>
          {p.thumbUrl ? (
            <img src={p.thumbUrl} alt="" className="size-10 shrink-0 rounded object-cover" loading="lazy" />
          ) : (
            <span className="flex size-10 shrink-0 items-center justify-center rounded bg-muted text-muted-foreground">
              <Film className="size-4" aria-hidden="true" />
            </span>
          )}
          <div className="min-w-0 flex-1">
            <Link to={linkVideo(p.videoId)} className="block truncate text-sm font-medium underline-offset-2 hover:underline" title={p.tituloCurto}>
              {p.tituloCurto || "(sem legenda)"}
            </Link>
            <p className="flex items-center gap-1.5 truncate text-xs text-muted-foreground">
              <span aria-hidden="true" className="inline-block size-2 shrink-0 rounded-full" style={{ background: corDoSlot(tema, ordem.slot(p.contaId)) }} />
              {p.rotuloConta} · {formatDateTime(p.publicadoEm)}
            </p>
          </div>
          <div className="shrink-0 text-right">
            <p className="text-sm font-semibold tabular-nums">{formatCompacto(p.viewsPeriodo)}</p>
            <p className="hidden text-xs text-muted-foreground tabular-nums sm:block">{formatEngajamento(p.engajamento)} eng.</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

const marcoNum = (m: MarcoValor) => (m.valor === null ? null : Math.round(m.valor));

export function VisaoGeral({ estado }: { estado: EstadoFiltroAnalytics }) {
  const { filtro } = estado;
  const dados = useAnalytics("visao-geral", filtro);
  const ordem = useOrdemContas();
  const tema = useTemaGraficos();
  const d = dados.data;
  const carregando = dados.isPending;
  const [comVisitas, setComVisitas] = useState(false);
  const serie = useMemo(() => serieDiaria(d, ordem, tema, filtro.de, filtro.ate, comVisitas), [d, ordem, tema, filtro.de, filtro.ate, comVisitas]);
  const medida = (d?.contexto.medida ?? filtro.medida) as Medida;
  const porChave = new Map((d?.indicadores ?? []).map((i) => [i.chave, i]));
  const ctx = d?.contexto;
  const studio = studioDoContexto(ctx);
  // spec 020 (R12): com uma conta filtrada e o período começando antes da 1ª coleta, o atalho para
  // importar o histórico do Studio (só dono; a página fica fora do analytics, que é só leitura)
  const ehDono = useAuth((s) => s.user?.role === "dono");
  const cobertura = useCoberturaStudio(ehDono ? filtro.contaId : undefined);
  const primeiraColeta = cobertura.data?.coleta?.primeiroDia;
  const atalhoStudio = ehDono && filtro.contaId && cobertura.data && (!primeiraColeta || filtro.de < primeiraColeta);

  const insights = d?.insights ?? [];
  const tabelaInsights: DadosTabela = {
    colunas: [{ titulo: "Regra" }, { titulo: "Frase" }, { titulo: "Grupo", secundaria: true }, { titulo: "Razão", numerica: true }, { titulo: "n", numerica: true }, { titulo: "Conclusão" }],
    linhas: insights.map((i) => [i.regra, i.frase, i.grupo, i.valor === null ? null : Math.round(i.valor * 100) / 100, i.amostra.n, i.pendente ? "pendente" : "sim"]),
  };

  const principais = d?.principais ?? [];
  const tabelaPrincipais: DadosTabela = {
    colunas: [
      { titulo: "Vídeo", formatar: (v, l) => <Link to={linkVideo(String(l[6]))} className="underline-offset-2 hover:underline">{String(v ?? "")}</Link> },
      { titulo: "Conta", secundaria: true },
      { titulo: "Publicado em", secundaria: true },
      { titulo: "Views no período", numerica: true },
      { titulo: medidaLabel[medida], numerica: true, secundaria: true },
      { titulo: "Engajamento", numerica: true, secundaria: true, formatar: (v) => formatEngajamento(v as number | null) },
      { titulo: "ID do vídeo", secundaria: true },
    ],
    linhas: principais.map((p) => [p.tituloCurto, p.rotuloConta, p.publicadoEm, p.viewsPeriodo, p.medida.valor === null ? null : Math.round(p.medida.valor), p.engajamento, p.videoId]),
  };

  const [params] = useFiltroUrl();
  const escopo = useMemo<EscopoRanking>(
    () => ({ de: filtro.de, ate: filtro.ate, perfilId: filtro.perfilId, contaId: filtro.contaId }),
    [filtro.de, filtro.ate, filtro.perfilId, filtro.contaId],
  );
  // a mesma chave do RankingTable: o TanStack Query devolve as linhas já carregadas, sem buscar de novo
  const rankingQuery = useRanking(useMemo(() => rankingFilters(params, escopo), [params, escopo]));
  const ranking = rankingQuery.data?.pages.flatMap((p) => p.items) ?? [];
  const tabelaRanking: DadosTabela = {
    colunas: [
      { titulo: "Vídeo", formatar: (v, l) => <Link to={String(l[8])} className="underline-offset-2 hover:underline">{truncar(String(v ?? ""))}</Link> },
      { titulo: "Conta", secundaria: true },
      { titulo: "Publicado em", secundaria: true },
      { titulo: "Origem", secundaria: true },
      { titulo: "Views", numerica: true },
      { titulo: "Views em 24 h", numerica: true, secundaria: true },
      { titulo: "Views em 7 dias", numerica: true, secundaria: true },
      { titulo: "Engajamento", numerica: true, secundaria: true, formatar: (v) => formatEngajamento(v as number | null) },
      { titulo: "Link", secundaria: true },
    ],
    linhas: ranking.map((v) => [v.legenda ?? "", nomeDaConta(v), v.publicadoEm, origemMetricasLabel[v.origem], v.ultima?.views ?? null, marcoNum(v.views24h), marcoNum(v.views7d), v.engajamento, linkDoVideo(v)]),
  };

  return (
    <Page>
      <section aria-label="Indicadores do período" className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        {ORDEM_INDICADORES.map((chave) => {
          const ind = porChave.get(chave);
          return (
            <Indicador
              key={chave}
              rotulo={rotuloIndicador(chave, medida)}
              valor={ind?.valor}
              anterior={ind?.anterior}
              formatar={formatoIndicador(chave)}
              carregando={carregando}
              dica={
                chave === "mediana_post" && ctx && ctx.aguardando > 0
                  ? `${formatNumero(ctx.aguardando)} aguardando o marco`
                  : diasStudioDe(ind) > 0
                    ? `inclui ${formatNumero(diasStudioDe(ind))} ${diasStudioDe(ind) === 1 ? "dia importado" : "dias importados"} do Studio`
                    : undefined
              }
            />
          );
        })}
      </section>
      {dados.error ? null : ctx && (
        <p className="text-xs text-muted-foreground" data-contexto>
          Período de {formatDateKey(ctx.de)} a {formatDateKey(ctx.ate)}, comparado com {formatDateKey(ctx.anteriorDe)} a {formatDateKey(ctx.anteriorAte)}.{" "}
          {ctx.aguardando > 0 && `Aguardando o marco de ${medidaLabel[medida].replace(/^Views em /, "")}: ${formatNumero(ctx.aguardando)}.`}
          {studio.dias > 0 && ` ${formatNumero(studio.dias)} ${studio.dias === 1 ? "dia veio" : "dias vieram"} do histórico importado do Studio. ${NOTA_FUSO_STUDIO}`}
        </p>
      )}
      {atalhoStudio && (
        <p className="text-sm" data-atalho-studio>
          O período começa antes da coleta desta conta.{" "}
          <Link to={studioContaPath(filtro.contaId!)} className="font-medium text-primary underline-offset-2 hover:underline">
            Importar histórico do Studio
          </Link>
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CardAnalytics
          titulo="Views por dia"
          comoLer={
            serie.temStudio
              ? "views ganhas em cada dia do período, uma linha por conta (cada conta tem sempre a mesma cor). Linha tracejada: importado do Studio; contínua: coletado pela API."
              : "views ganhas em cada dia do período, uma linha por conta (cada conta tem sempre a mesma cor)."
          }
          acoes={
            serie.temVisitas && (
              <Button type="button" size="sm" variant="outline" aria-pressed={comVisitas} onClick={() => setComVisitas(!comVisitas)}>
                Visitas ao perfil
              </Button>
            )
          }
          carregando={carregando || !ordem.pronto}
          erro={dados.error}
          vazio={serie.vazia ? "Nenhuma view ganha neste período." : null}
          onAmpliarPeriodo={estado.ampliarPeriodo}
          tabela={serie.tabela}
          largo
        >
          <Grafico opcoes={serie.opcoes} descricao={serie.descricao} tooltip={serie.tooltip} />
        </CardAnalytics>
        <CardAnalytics
          titulo="Insights"
          comoLer="frases calculadas por regras fixas sobre a medida do post; cada uma com o tamanho da amostra. Abaixo do mínimo, a frase diz quanto falta."
          carregando={carregando}
          erro={dados.error}
          vazio={insights.length === 0 ? "Nenhum post medido neste período para tirar conclusões." : null}
          onAmpliarPeriodo={estado.ampliarPeriodo}
          tabela={tabelaInsights}
        >
          <Insights insights={insights} />
        </CardAnalytics>
        <CardAnalytics
          titulo="Principais vídeos"
          comoLer="os 10 vídeos com mais views ganhas no período; clique para ver o vídeo."
          carregando={carregando}
          erro={dados.error}
          vazio={principais.length === 0 ? "Nenhum vídeo ganhou views neste período." : null}
          onAmpliarPeriodo={estado.ampliarPeriodo}
          tabela={tabelaPrincipais}
        >
          <Principais posts={principais} ordem={ordem} tema={tema} />
        </CardAnalytics>
      </div>
      <CardAnalytics
        titulo="Ranking"
        comoLer="os vídeos publicados no período, na ordem escolhida (padrão: views totais, a última foto); clique no cabeçalho de uma coluna para reordenar. * = estimado."
        tabela={tabelaRanking}
        largo
      >
        <RankingTable semFiltroContas semMoldura escopo={escopo} />
      </CardAnalytics>
    </Page>
  );
}
