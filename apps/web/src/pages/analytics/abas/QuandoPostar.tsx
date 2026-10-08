/*
 * Aba "Quando postar" do analytics (spec 019, US2; FR-016 a FR-018), tudo no horário de Brasília.
 *
 * - Desempenho por horário de publicação: mediana da medida do post (seletor global) por dia ×
 *   hora, com o n de posts em cada célula; célula abaixo do mínimo esmaecida.
 * - Audiência por hora: views ganhas em cada hora (fotos com intervalo de até 3 h); o que veio de
 *   intervalos maiores fica "sem hora atribuída", na frase de leitura.
 * - Calendário do período: views ganhas (cor) e posts publicados (número) por dia.
 * - Seguidores on-line (spec 022, FR-023): o 3º mapa, a média de seguidores ativos do TikTok Studio,
 *   o mesmo cálculo da aba Público (horas conforme a TikTok), uma conta por vez.
 */
import { useMemo } from "react";
import { CardAnalytics } from "@/components/analytics/CardAnalytics";
import type { OpcoesGrafico } from "@/components/analytics/echarts";
import { Grafico, type ItemTooltip } from "@/components/analytics/Grafico";
import { MapaSemana, mapaTabela } from "@/components/analytics/MapaSemana";
import type { DadosTabela } from "@/components/analytics/TabelaAlternativa";
import { useTemaGraficos, type TemaGraficos } from "@/components/analytics/tema";
import {
  atividadeSeguidoresDe,
  diasEntre,
  formatCompacto,
  formatNumero,
  medidaLabel,
  useAnalytics,
  type AnalyticsQuandoPostar,
  type EstadoFiltroAnalytics,
  type Medida,
} from "@/lib/analytics";
import { Page } from "@/components/shell";
import { contasStudioDe, fonteDe, fonteLabel, NOTA_FUSO_STUDIO, notaSemVideo } from "@/components/studio/fonteAnalytics";
import { formatDateKey, parseDateKey } from "@/lib/tz";
import { CardAtividade } from "./Publico";

const compactoInteiro = (v: number) => formatCompacto(Math.round(v));
const NOTA_FUSO = "Horário de Brasília (São Paulo).";
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
          // spec 020: dia com dado importado do Studio (só ele ou misturado) ganha contorno tracejado
          const fonte = fonteDe(d);
          return {
            value: [d.dia, d.views, d.posts],
            fonte,
            contasStudio: contasStudioDe(d),
            ...(fonte !== "coletado" ? { itemStyle: { borderType: "dashed", borderColor: tema.texto, borderWidth: 1.5 } } : {}),
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
  const temStudio = dias.some((d) => fonteDe(d) !== "coletado");
  const tabela: DadosTabela = {
    colunas: [
      { titulo: "Dia", formatar: (v) => formatDateKey(String(v)) },
      { titulo: "Posts publicados", numerica: true },
      { titulo: "Views ganhas", numerica: true },
      ...(temStudio ? [{ titulo: "Fonte" }] : []),
    ],
    linhas: dias.map((d) => [d.dia, d.posts, d.views, ...(temStudio ? [fonteDe(d)] : [])]),
  };
  const posts = dias.reduce((t, d) => t + d.posts, 0);
  const views = dias.reduce((t, d) => t + d.views, 0);
  return { opcoes, tabela, altura, largura, vazio: posts === 0 && views === 0, vertical, temStudio, descricao: `Calendário de ${formatDateKey(de)} a ${formatDateKey(ate)}: ${formatNumero(posts)} posts e ${formatNumero(views)} views ganhas.` };
}

const tooltipCalendario = (itens: ItemTooltip[]) => {
  const item = itens[0]?.data as { value: [string, number, number]; fonte?: ReturnType<typeof fonteDe>; contasStudio?: number } | undefined;
  const v = item?.value;
  if (!v) return null;
  const fonte = item.fonte ?? "coletado";
  return {
    titulo: formatDateKey(v[0]),
    linhas: [
      { rotulo: "Views ganhas", valor: formatNumero(v[1]) },
      { rotulo: "Posts publicados", valor: formatNumero(v[2]) },
      ...(fonte !== "coletado" ? [{ rotulo: "Fonte", valor: fonte === "misto" ? `${fonteLabel.misto} (${formatNumero(item.contasStudio ?? 0)} do Studio)` : fonteLabel.studio }] : []),
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
    <Page>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {notaSemVideo(d?.contexto) && (
          <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground lg:col-span-2" data-nota-studio>
            {notaSemVideo(d?.contexto)}
          </p>
        )}
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
        {d && "atividadeSeguidores" in d && (
          <CardAtividade titulo="Seguidores on-line (TikTok Studio)" contas={atividadeSeguidoresDe(d)} carregando={carregando} erro={dados.error} estado={estado} />
        )}
        <CardAnalytics
          titulo="Calendário"
          comoLer={
            <>
              {cal.vertical ? "um quadrado por dia: a cor são as views ganhas no dia e o número, os posts publicados." : "um quadrado por dia: a cor são as views ganhas no dia; os posts estão no tooltip e na tabela."}
              {cal.temStudio && ` Contorno tracejado: views importadas do Studio. ${NOTA_FUSO_STUDIO}`}
            </>
          }
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
    </Page>
  );
}
