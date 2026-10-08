/*
 * Aba "Mercado" do analytics (spec 019, US7; FR-030/FR-031; research R8): o YouTube de origem.
 *
 * - Dois mapas 7 × 24 (dia da semana × hora, São Paulo) em rampa de um só tom: quantos vídeos os
 *   canais-fonte publicaram no período e a velocidade mediana (views/h) por horário de publicação.
 * - Oportunidades: os vídeos-fonte mais rápidos ainda sem envio, com o selo de direito do canal à vista
 *   e "Gerar cortes", que abre a seleção de sempre (/app/descobrir, com o vídeo em destaque). Selecionar,
 *   gerar e o aviso de direito continuam lá, iguais (princípio II): o analytics não pula nada.
 * - Canais: a mediana da velocidade por canal, com o direito.
 * Tudo é leitura.
 */
import { Scissors } from "lucide-react";
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CardAnalytics } from "@/components/analytics/CardAnalytics";
import type { OpcoesGrafico } from "@/components/analytics/echarts";
import { Grafico } from "@/components/analytics/Grafico";
import type { DadosTabela } from "@/components/analytics/TabelaAlternativa";
import { useTemaGraficos, type TemaGraficos } from "@/components/analytics/tema";
import { DireitoBadge } from "@/components/canais/DireitoBadge";
import { Page } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  formatCompacto,
  formatIdadeHoras,
  formatNumero,
  formatVelocidade,
  useAnalytics,
  type AnalyticsCelulaMapa,
  type AnalyticsMercado,
  type EstadoFiltroAnalytics,
} from "@/lib/analytics";
import { direitoLabel } from "@/lib/canais";

const DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
const DIAS_LONGOS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"];
const HORAS = Array.from({ length: 24 }, (_, h) => `${h}h`);

function mapa(celulas: AnalyticsCelulaMapa[], tema: TemaGraficos, formatar: (n: number) => string): OpcoesGrafico {
  const comValor = celulas.filter((c) => c.valor !== null && c.valor !== undefined);
  const max = Math.max(1, ...comValor.map((c) => c.valor!));
  return {
    grid: { left: 8, right: 8, top: 8, bottom: 56, containLabel: true },
    xAxis: { type: "category", data: HORAS, splitArea: { show: false }, axisLabel: { interval: 2 } },
    yAxis: { type: "category", data: DIAS, inverse: true, splitArea: { show: false } },
    visualMap: {
      min: 0,
      max,
      calculable: false,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      itemHeight: 120,
      text: [formatar(max), "0"],
      inRange: { color: tema.sequencial },
    },
    series: [
      {
        type: "heatmap",
        data: comValor.map((c) => [c.hora, c.dia, c.valor!]),
        itemStyle: { borderColor: tema.superficie, borderWidth: 2, borderRadius: 2 },
        emphasis: { itemStyle: { borderColor: tema.texto, borderWidth: 1 } },
      },
    ],
  };
}

function tabelaMapa(celulas: AnalyticsCelulaMapa[], titulo: string, formatar: (n: number) => string): DadosTabela {
  return {
    colunas: [{ titulo: "Dia" }, { titulo: "Hora" }, { titulo, numerica: true, formatar: (v) => (typeof v === "number" ? formatar(v) : "—") }, { titulo: "n", numerica: true }, { titulo: "Amostra pequena", secundaria: true }],
    linhas: celulas.filter((c) => c.n > 0).map((c) => [DIAS_LONGOS[c.dia] ?? String(c.dia), `${c.hora}h`, c.valor ?? null, c.n, c.amostraPequena]),
  };
}

function tooltipMapa(celulas: AnalyticsCelulaMapa[], rotulo: string, formatar: (n: number) => string) {
  return (itens: { value?: unknown }[]) => {
    const [hora, dia] = (Array.isArray(itens[0]?.value) ? itens[0]!.value : []) as number[];
    const c = celulas.find((x) => x.dia === dia && x.hora === hora);
    if (!c) return null;
    return {
      titulo: `${DIAS_LONGOS[c.dia]}, ${c.hora}h`,
      linhas: [
        { rotulo, valor: c.valor === null || c.valor === undefined ? "—" : formatar(c.valor) },
        { rotulo: "vídeos", valor: formatNumero(c.n) },
      ],
      nota: c.amostraPequena ? "amostra pequena" : undefined,
    };
  };
}

function montar(dados: AnalyticsMercado | undefined, tema: TemaGraficos) {
  const pub = dados?.publicacao.celulas ?? [];
  const vel = dados?.velocidadePorHorario.celulas ?? [];
  const oportunidades = dados?.oportunidades ?? [];
  const canais = dados?.canais ?? [];
  const contagem = (n: number) => formatNumero(Math.round(n));

  const tabelaOport: DadosTabela = {
    colunas: [
      { titulo: "Vídeo" },
      { titulo: "Canal", secundaria: true },
      { titulo: "Direito", secundaria: true },
      { titulo: "Idade", numerica: true, secundaria: true, formatar: (v) => (typeof v === "number" ? formatIdadeHoras(v) : "—") },
      { titulo: "Views", numerica: true },
      { titulo: "Views/h", numerica: true, formatar: (v) => formatVelocidade(typeof v === "number" ? v : null) },
    ],
    linhas: oportunidades.map((o) => [o.tituloCurto, o.canal.titulo, direitoLabel[o.canal.direito], o.idadeH, o.views ?? null, o.velocidade ?? null]),
  };

  const comVel = canais.filter((c) => c.medianaVelocidade !== null && c.medianaVelocidade !== undefined).sort((a, b) => b.medianaVelocidade! - a.medianaVelocidade!);
  const opcoesCanais: OpcoesGrafico = {
    grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: "value", axisLabel: { formatter: (v: number) => formatCompacto(v) } },
    yAxis: { type: "category", inverse: true, data: comVel.map((c) => c.titulo), axisLabel: { width: 140, overflow: "truncate" } },
    series: [
      {
        type: "bar",
        name: "Velocidade mediana",
        barMaxWidth: 24,
        color: tema.categorica[0],
        itemStyle: { borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: "right", color: tema.texto, formatter: (p: { value?: unknown }) => formatVelocidade(Number(p.value ?? 0)) },
        data: comVel.map((c) => c.medianaVelocidade!),
      },
    ],
  };
  const tabelaCanais: DadosTabela = {
    colunas: [
      { titulo: "Canal" },
      { titulo: "Direito" },
      { titulo: "Vídeos no período", numerica: true },
      { titulo: "Velocidade mediana", numerica: true, formatar: (v) => formatVelocidade(typeof v === "number" ? v : null) },
    ],
    linhas: canais.map((c) => [c.titulo, direitoLabel[c.direito], c.videos, c.medianaVelocidade ?? null]),
  };

  return {
    pub,
    vel,
    oportunidades,
    canais,
    comVel,
    opcoesPub: mapa(pub, tema, contagem),
    opcoesVel: mapa(vel, tema, (n) => formatVelocidade(n)),
    tabelaPub: tabelaMapa(pub, "Vídeos publicados", contagem),
    tabelaVel: tabelaMapa(vel, "Velocidade mediana (views/h)", (n) => formatVelocidade(n)),
    tooltipPub: tooltipMapa(pub, "publicados", contagem),
    tooltipVel: tooltipMapa(vel, "velocidade mediana", (n) => formatVelocidade(n)),
    tabelaOport,
    opcoesCanais,
    tabelaCanais,
  };
}

export function Mercado({ estado }: { estado: EstadoFiltroAnalytics }) {
  // spec 023: com perfil, os vídeos de tema cortado ficam ocultos; `?cortados=1` os mostra (com o selo)
  const [params] = useSearchParams();
  const mostrarCortados = params.get("cortados") === "1";
  const dados = useAnalytics("mercado", estado.filtro, { mostrarCortados });
  const ocultos = dados.data?.ocultosPorTema ?? 0;
  const tema = useTemaGraficos();
  const v = useMemo(() => montar(dados.data, tema), [dados.data, tema]);
  const comum = { carregando: dados.isPending, erro: dados.error, onAmpliarPeriodo: estado.ampliarPeriodo };
  const totalPub = v.pub.reduce((s, c) => s + (c.valor ?? 0), 0);
  // a seleção vai para o perfil filtrado (sem filtro, o Descobrir usa o primeiro perfil, como sempre)
  const linkCortes = (link: string) => (estado.filtro.perfilId ? `${link}&perfil=${encodeURIComponent(estado.filtro.perfilId)}` : link);

  return (
    <Page>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <CardAnalytics
          titulo="Publicação dos canais-fonte"
          comoLer="quantos vídeos os canais-fonte publicaram em cada dia da semana e hora (São Paulo) no período; quanto mais escura a célula, mais vídeos."
          vazio={totalPub === 0 ? "Nenhum vídeo publicado pelos canais-fonte neste período." : null}
          tabela={v.tabelaPub}
          {...comum}
        >
          <Grafico opcoes={v.opcoesPub} altura={300} descricao={`Mapa de publicação dos canais-fonte por dia da semana e hora: ${formatNumero(totalPub)} vídeos no período.`} tooltip={v.tooltipPub} />
        </CardAnalytics>
        <CardAnalytics
          titulo="Velocidade por horário de publicação"
          comoLer="a mediana de views por hora dos vídeos-fonte com 24 h a 7 dias, pelo horário em que foram publicados; mostra quando o público do YouTube responde mais rápido. Vale sempre a janela recente, não o período."
          vazio={v.vel.every((c) => c.valor === null || c.valor === undefined) ? "Nenhum vídeo-fonte com 24 h a 7 dias de publicado." : null}
          tabela={v.tabelaVel}
          {...comum}
          onAmpliarPeriodo={undefined}
        >
          <Grafico opcoes={v.opcoesVel} altura={300} descricao="Velocidade mediana dos vídeos-fonte por dia da semana e hora de publicação." tooltip={v.tooltipVel} />
        </CardAnalytics>
        <CardAnalytics
          titulo="Oportunidades"
          comoLer={'os vídeos-fonte recentes mais rápidos (views por hora) que ainda não foram enviados para corte; o selo mostra o direito do canal. "Gerar cortes" abre a seleção de sempre, com os mesmos avisos.'}
          vazio={v.oportunidades.length === 0 ? `Nenhum vídeo-fonte recente sem envio.${ocultos > 0 ? ` ${formatNumero(ocultos)} ocultos por tema cortado.` : ""}` : null}
          tabela={v.tabelaOport}
          largo
          {...comum}
          acoes={
            estado.filtro.perfilId ? (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={mostrarCortados}
                  onChange={(e) => estado.set({ cortados: e.target.checked ? "1" : null }, { replace: true })}
                />
                Mostrar temas cortados
              </label>
            ) : undefined
          }
        >
          {!mostrarCortados && ocultos > 0 && (
            <p className="mb-2 text-xs text-muted-foreground" data-ocultos-por-tema={ocultos}>
              {formatNumero(ocultos)} {ocultos === 1 ? "oculto" : "ocultos"} por tema cortado
            </p>
          )}
          <ul className="divide-y" aria-label="Oportunidades">
            {v.oportunidades.map((o) => (
              <li key={o.videoFonteId} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-2.5" data-oportunidade={o.videoFonteId}>
                <div className="min-w-0 flex-1 basis-56">
                  <p className="truncate text-sm font-medium" title={o.tituloCurto}>
                    {o.tituloCurto}
                  </p>
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                    <span className="max-w-48 truncate">{o.canal.titulo}</span>
                    <DireitoBadge direito={o.canal.direito} />
                    <span aria-hidden="true">·</span>
                    <span>há {formatIdadeHoras(o.idadeH)}</span>
                    {o.afinidade?.cortado && <Badge variant="outline">tema cortado</Badge>}
                  </div>
                  {o.afinidade?.motivo && <p className="text-xs text-muted-foreground">{o.afinidade.motivo}</p>}
                </div>
                <dl className="flex gap-4 text-sm">
                  <div>
                    <dt className="text-xs text-muted-foreground">Views</dt>
                    <dd className="font-medium tabular-nums">{formatCompacto(o.views)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Views/h</dt>
                    <dd className="font-medium tabular-nums">{formatVelocidade(o.velocidade)}</dd>
                  </div>
                </dl>
                <Button size="sm" variant="outline" asChild>
                  <Link to={linkCortes(o.linkGerarCortes)} aria-label={`Gerar cortes: ${o.tituloCurto}`}>
                    <Scissors aria-hidden="true" />
                    Gerar cortes
                  </Link>
                </Button>
              </li>
            ))}
          </ul>
        </CardAnalytics>
        <CardAnalytics
          titulo="Canais-fonte"
          comoLer="a mediana de views por hora dos vídeos recentes de cada canal (24 h a 7 dias); a tabela traz o direito e os vídeos publicados no período."
          vazio={v.canais.length === 0 ? "Nenhum canal-fonte no escopo." : v.comVel.length === 0 ? "Nenhum canal com vídeos de 24 h a 7 dias para medir a velocidade." : null}
          tabela={v.tabelaCanais}
          largo
          {...comum}
        >
          <Grafico
            opcoes={v.opcoesCanais}
            altura={Math.max(140, v.comVel.length * 32 + 40)}
            descricao={`Velocidade mediana de ${v.comVel.length} canais-fonte.`}
            tooltip={(itens) => {
              const c = v.comVel[itens[0]?.dataIndex ?? -1];
              return c ? { titulo: c.titulo, linhas: [{ rotulo: "velocidade mediana", valor: formatVelocidade(c.medianaVelocidade) }, { rotulo: "direito", valor: direitoLabel[c.direito] }] } : null;
            }}
          />
        </CardAnalytics>
      </div>
    </Page>
  );
}
