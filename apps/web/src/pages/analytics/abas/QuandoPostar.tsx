/*
 * Aba "Quando postar" do analytics (spec 019, US2; FR-016 a FR-018), tudo no horário de Brasília.
 *
 * - Desempenho por horário de publicação: mediana da medida do post (seletor global) por dia ×
 *   hora, com o n de posts em cada célula; célula abaixo do mínimo esmaecida.
 * - Audiência por hora: views ganhas em cada hora (fotos com intervalo de até 3 h); o que veio de
 *   intervalos maiores fica "sem hora atribuída", na frase de leitura.
 * - Calendário do período: views ganhas (cor) e posts publicados (número) por dia.
 */
import { useMemo } from "react";
import { CardAnalytics } from "@/components/analytics/CardAnalytics";
import type { OpcoesGrafico } from "@/components/analytics/echarts";
import { Grafico, type ItemTooltip } from "@/components/analytics/Grafico";
import { MapaSemana, mapaTabela } from "@/components/analytics/MapaSemana";
import type { DadosTabela } from "@/components/analytics/TabelaAlternativa";
import { useTemaGraficos, type TemaGraficos } from "@/components/analytics/tema";
import { diasEntre, formatCompacto, formatNumero, medidaLabel, useAnalytics, type AnalyticsQuandoPostar, type EstadoFiltroAnalytics, type Medida } from "@/lib/analytics";
import { parseDateKey } from "@/lib/tz";

const compactoInteiro = (v: number) => formatCompacto(Math.round(v));
const NOTA_FUSO = "Horário de Brasília (São Paulo).";
const dataBr = (dia: string) => dia.split("-").reverse().join("/");
// 0 = domingo (o `getUTCDay`), só para contar as semanas do calendário
const diaDaSemana = (dia: string) => {
  const d = parseDateKey(dia);
  return new Date(Date.UTC(d.year, d.month - 1, d.day)).getUTCDay();
};

function calendario(dados: AnalyticsQuandoPostar | undefined, tema: TemaGraficos, de: string, ate: string) {
  const dias = dados?.calendario ?? [];
  const n = diasEntre(de, ate);
  const semanas = Math.ceil((n + ((diaDaSemana(de) + 6) % 7)) / 7);
  const vertical = n <= 63;
  const max = Math.max(1, ...dias.map((d) => d.views));
  const cel = vertical ? 30 : 16;
  const altura = vertical ? semanas * cel + 56 : 7 * cel + 72;
  const largura = vertical ? 0 : semanas * cel + 64;
  const opcoes: OpcoesGrafico = {
    calendar: {
      range: [de, ate],
      orient: vertical ? "vertical" : "horizontal",
      cellSize: vertical ? ["auto", cel] : [cel, cel],
      top: vertical ? 32 : 24,
      left: vertical ? 36 : 40,
      right: 8,
      bottom: 40,
      dayLabel: { firstDay: 1, nameMap: ["D", "S", "T", "Q", "Q", "S", "S"] },
      monthLabel: { show: true },
      splitLine: { show: false },
      itemStyle: { color: tema.superficie, borderColor: tema.superficie, borderWidth: 2 },
    },
    visualMap: {
      type: "continuous",
      min: 0,
      max,
      calculable: false,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      itemHeight: 140,
      itemWidth: 10,
      inRange: { color: tema.sequencial },
      formatter: (v: unknown) => formatCompacto(Math.round(Number(v))),
      text: ["mais views", "menos"],
      dimension: 1,
    },
    series: [
      {
        type: "heatmap",
        coordinateSystem: "calendar",
        data: dias.map((d) => {
          const forte = d.views / max > 0.55;
          return {
            value: [d.dia, d.views, d.posts],
            label: {
              show: vertical && d.posts > 0,
              formatter: String(d.posts),
              fontSize: 10,
              color: forte ? (tema.escuro ? "#0b1220" : "#ffffff") : tema.texto,
            },
          };
        }),
      },
    ],
  } as OpcoesGrafico;
  const tabela: DadosTabela = {
    colunas: [{ titulo: "Dia", formatar: (v) => dataBr(String(v)) }, { titulo: "Posts publicados", numerica: true }, { titulo: "Views ganhas", numerica: true }],
    linhas: dias.map((d) => [d.dia, d.posts, d.views]),
  };
  const posts = dias.reduce((t, d) => t + d.posts, 0);
  const views = dias.reduce((t, d) => t + d.views, 0);
  return { opcoes, tabela, altura, largura, vazio: posts === 0 && views === 0, vertical, descricao: `Calendário de ${dataBr(de)} a ${dataBr(ate)}: ${formatNumero(posts)} posts e ${formatNumero(views)} views ganhas.` };
}

const tooltipCalendario = (itens: ItemTooltip[]) => {
  const v = (itens[0]?.data as { value: [string, number, number] } | undefined)?.value;
  if (!v) return null;
  return {
    titulo: dataBr(v[0]),
    linhas: [
      { rotulo: "Views ganhas", valor: formatNumero(v[1]) },
      { rotulo: "Posts publicados", valor: formatNumero(v[2]) },
    ],
  };
};

export function QuandoPostar({ estado }: { estado: EstadoFiltroAnalytics }) {
  const { filtro } = estado;
  const dados = useAnalytics("quando-postar", filtro);
  const tema = useTemaGraficos();
  const d = dados.data;
  const carregando = dados.isPending;
  const minimo = d?.contexto.minimos.grupo ?? 5;
  const medida = (d?.contexto.medida ?? filtro.medida) as Medida;
  const rotuloMedida = `Mediana de ${medidaLabel[medida].toLowerCase()}`;
  const publicacao = d?.porPublicacao.celulas ?? [];
  const audiencia = d?.audiencia.celulas ?? [];
  const semHora = d?.audiencia.semHora ?? 0;
  const cal = useMemo(() => calendario(d, tema, filtro.de, filtro.ate), [d, tema, filtro.de, filtro.ate]);
  const aguardando = d?.contexto.aguardando ?? 0;

  const temPublicacao = publicacao.some((c) => c.n > 0);
  const temAudiencia = audiencia.some((c) => (c.valor ?? 0) > 0);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <CardAnalytics
        titulo="Desempenho por horário de publicação"
        comoLer={
          <>
            cada célula é a {rotuloMedida.toLowerCase()} dos posts publicados naquele dia da semana e hora; o número é a quantidade de posts. Quanto mais forte a cor, melhor.
            Célula esmaecida: menos de {minimo} posts. {NOTA_FUSO}
            {aguardando > 0 && ` Aguardando o marco (fora do mapa): ${formatNumero(aguardando)}.`}
          </>
        }
        carregando={carregando}
        erro={dados.error}
        vazio={temPublicacao ? null : aguardando > 0 ? `Nenhum post do período chegou ao marco (${formatNumero(aguardando)} aguardando).` : "Nenhum post publicado neste período."}
        onAmpliarPeriodo={estado.ampliarPeriodo}
        tabela={mapaTabela(publicacao, rotuloMedida, "posts")}
        largo
      >
        <MapaSemana
          celulas={publicacao}
          rotuloValor={rotuloMedida}
          rotuloN="posts"
          minimo={minimo}
          formatar={compactoInteiro}
          descricao={`Mapa de calor da ${rotuloMedida.toLowerCase()} por dia da semana e hora de publicação, horário de Brasília.`}
        />
      </CardAnalytics>
      <CardAnalytics
        titulo="Audiência por hora"
        comoLer={
          <>
            views ganhas em cada hora do dia, somando todos os vídeos: mostra quando o público assiste; o número é a quantidade de vídeos com ganho na célula.{" "}
            {semHora > 0 && (
              <span data-sem-hora>
                {formatNumero(semHora)} views vieram de intervalos de mais de 3 h entre fotos e ficaram sem hora atribuída.{" "}
              </span>
            )}
            {NOTA_FUSO}
          </>
        }
        carregando={carregando}
        erro={dados.error}
        vazio={temAudiencia ? null : semHora > 0 ? `Nenhuma view com hora atribuída neste período (${formatNumero(semHora)} sem hora).` : "Nenhuma view ganha neste período."}
        onAmpliarPeriodo={estado.ampliarPeriodo}
        tabela={mapaTabela(audiencia, "Views ganhas", "vídeos")}
        largo
      >
        <MapaSemana
          celulas={audiencia}
          rotuloValor="Views ganhas"
          rotuloN="vídeos"
          minimo={minimo}
          formatar={compactoInteiro}
          descricao="Mapa de calor das views ganhas por dia da semana e hora do dia, horário de Brasília."
        />
      </CardAnalytics>
      <CardAnalytics
        titulo="Calendário"
        comoLer={cal.vertical ? "um quadrado por dia: a cor são as views ganhas no dia e o número, os posts publicados." : "um quadrado por dia: a cor são as views ganhas no dia; os posts estão no tooltip e na tabela."}
        carregando={carregando}
        erro={dados.error}
        vazio={cal.vazio ? "Nenhum post nem view neste período." : null}
        onAmpliarPeriodo={estado.ampliarPeriodo}
        tabela={cal.tabela}
        largo={!cal.vertical}
      >
        <div className="-mx-1 overflow-x-auto px-1">
          <div style={{ minWidth: cal.largura || undefined }}>
            <Grafico opcoes={cal.opcoes} descricao={cal.descricao} altura={cal.altura} tooltip={tooltipCalendario} />
          </div>
        </div>
      </CardAnalytics>
    </div>
  );
}
