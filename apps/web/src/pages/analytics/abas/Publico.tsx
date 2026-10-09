/*
 * Aba "Público" do analytics (spec 022, US3; FR-020 a FR-027), tudo importado do TikTok Studio.
 *
 * - Gênero e Territórios: a foto válida para o período (FR-016), em barras de um tom com a % em texto
 *   e a mudança em p.p.; com várias contas, um gráfico por conta (pequenos múltiplos, nunca somados).
 * - Atividade dos seguidores: o mapa 7 × 24 da 019 com a média de seguidores ativos e o n de dias
 *   (FR-017); as horas são as do arquivo ("horas conforme a TikTok", R13). Uma conta por vez
 *   (seletor local quando há mais de uma).
 * - Espectadores: indicadores do período (novos somados, médias diárias de total e de recorrentes) e a
 *   série diária, total em linha com a cor fixa da conta e novos × recorrentes em barras; "sem dado" é
 *   buraco, nunca zero.
 * - Estado vazio por motivo (sem importação, veio vazia, sem dado no período), com o atalho para o
 *   "Histórico do Studio" (só dono) e, no mapa, "ver os últimos dias com dado".
 * Tudo é leitura (FR-027).
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CardAnalytics } from "@/components/analytics/CardAnalytics";
import { corDoSlot, useOrdemContas, type OrdemContas } from "@/components/analytics/coresContas";
import { distribuicaoTabela, Distribuicao } from "@/components/analytics/Distribuicao";
import type { OpcoesGrafico } from "@/components/analytics/echarts";
import { Grafico, type ItemTooltip, type LinhaTooltip } from "@/components/analytics/Grafico";
import { Indicador } from "@/components/analytics/Indicador";
import { faixaHora, MapaSemana, DIAS_SEMANA } from "@/components/analytics/MapaSemana";
import type { DadosTabela } from "@/components/analytics/TabelaAlternativa";
import { useTemaGraficos, type TemaGraficos } from "@/components/analytics/tema";
import { Page } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import {
  chaveConta,
  FONTE_STUDIO,
  formatCompacto,
  formatNumero,
  MIN_DIAS_CELULA,
  motivoPublicoLabel,
  NOTA_HORAS_TIKTOK,
  usePublico,
  type AtividadeSeguidoresConta,
  type EstadoFiltroAnalytics,
  type MotivoPublico,
  type PublicoConta,
  type PublicoContaRef,
} from "@/lib/analytics";
import { useEhDono } from "@/lib/conteudos";
import { studioContaPath } from "@/lib/studio";
import { addDays, formatDateKey } from "@/lib/tz";

const decimal = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const formatMedia = (v: number | null | undefined) => (v === null || v === undefined ? "—" : decimal.format(v));
const formatInteiro = (v: number | null | undefined) => (v === null || v === undefined ? "—" : formatNumero(v));
const diaCurto = (dia: string) => dia.slice(8, 10) + "/" + dia.slice(5, 7);

type Card = "genero" | "territorios" | "atividade" | "espectadores";

// O motivo do card quando nenhuma conta tem dado: o mesmo para todas, ou um por conta.
function motivoDoCard(contas: PublicoConta[], card: Card): string {
  if (contas.length === 0) return motivoPublicoLabel.sem_importacao;
  const motivos = contas.map((c) => c.motivos[card] ?? "sem_dado_no_periodo");
  if (motivos.every((m) => m === motivos[0])) return motivoPublicoLabel[motivos[0]!];
  return contas.map((c, i) => `${c.conta.rotulo}: ${motivoPublicoLabel[motivos[i]!]}`).join(" ");
}

// Atalhos do estado vazio: o "Histórico do Studio" de cada conta (só dono; o membro vê o motivo).
export function AtalhosStudio({ contas }: { contas: PublicoContaRef[] }) {
  const dono = useEhDono();
  const comId = contas.filter((c) => c.contaId);
  if (!dono || comId.length === 0) return null;
  return (
    <>
      {comId.map((c) => (
        <Button key={chaveConta(c)} asChild size="sm" variant="outline">
          <Link to={studioContaPath(c.contaId!)}>{comId.length > 1 ? `Histórico do Studio de ${c.rotulo}` : "Histórico do Studio"}</Link>
        </Button>
      ))}
    </>
  );
}

// Seletor local de conta (FR-022): o mapa e a série de uma conta por vez, na ordem de contas.
export function SeletorConta({ contas, valor, onChange, rotulo = "Conta" }: { contas: PublicoContaRef[]; valor: string; onChange: (serieId: string) => void; rotulo?: string }) {
  if (contas.length < 2) return null;
  return (
    <Field label={rotulo} className="w-full sm:w-56">
      {({ id }) => (
        <NativeSelect id={id} value={valor} onChange={(e) => onChange(e.target.value)}>
          {contas.map((c) => (
            <option key={chaveConta(c)} value={chaveConta(c)}>
              {c.rotulo}
            </option>
          ))}
        </NativeSelect>
      )}
    </Field>
  );
}

// ---------------------------------------------------------------------------------------------
// Atividade (também o 3º mapa de "Quando postar")

export function atividadeTabela(a: AtividadeSeguidoresConta["atividade"]): DadosTabela {
  return {
    colunas: [
      { titulo: "fonte", secundaria: true },
      { titulo: "dia" },
      { titulo: "hora" },
      { titulo: "media_ativos", numerica: true },
      { titulo: "n_dias", numerica: true },
      { titulo: "amostra_pequena", secundaria: true },
    ],
    linhas: (a?.celulas ?? []).filter((c) => c.n > 0).map((c) => ["studio", DIAS_SEMANA[c.dia] ?? String(c.dia), faixaHora(c.hora), c.valor === null ? null : Math.round(c.valor * 10) / 10, c.n, c.amostraPequena]),
  };
}

/** O card do mapa de atividade, usado na aba Público e como 3º mapa de "Quando postar". */
export function CardAtividade({
  titulo,
  contas,
  carregando,
  erro,
  estado,
}: {
  titulo: string;
  contas: AtividadeSeguidoresConta[];
  carregando: boolean;
  erro: unknown;
  estado: EstadoFiltroAnalytics;
}) {
  const [escolhida, setEscolhida] = useState<string | null>(null);
  const atual = contas.find((c) => chaveConta(c.conta) === escolhida) ?? contas.find((c) => c.atividade && c.atividade.diasComDado > 0) ?? contas[0];
  const a = atual?.atividade ?? null;
  const temDado = Boolean(a && a.diasComDado > 0);
  const motivo: MotivoPublico = atual?.motivo ?? (a?.ultimoDiaComDado ? "sem_dado_no_periodo" : "sem_importacao");
  const ultimo = a?.ultimoDiaComDado ?? null;
  return (
    <CardAnalytics
      titulo={titulo}
      comoLer={
        <>
          cada célula é a média de seguidores ativos naquele dia da semana e hora, sobre os dias com dado no período; o número é a quantidade de dias. Célula esmaecida:
          menos de {MIN_DIAS_CELULA} dias.{" "}
          {temDado && (
            <span data-dias-cobertos>
              {formatNumero(a!.diasComDado)} {a!.diasComDado === 1 ? "dia" : "dias"} com dado.{" "}
            </span>
          )}
          <span data-nota-horas>{NOTA_HORAS_TIKTOK}</span>
        </>
      }
      carregando={carregando}
      erro={erro}
      vazio={temDado ? null : atual ? motivoPublicoLabel[motivo] : motivoPublicoLabel.sem_importacao}
      acoesVazio={
        <>
          {ultimo && (
            <Button type="button" size="sm" variant="outline" onClick={() => estado.setPeriodo(addDays(ultimo, -6), ultimo)}>
              Ver os últimos dias com dado
            </Button>
          )}
          {atual && motivo !== "sem_dado_no_periodo" && <AtalhosStudio contas={[atual.conta]} />}
        </>
      }
      acoes={<SeletorConta contas={contas.map((c) => c.conta)} valor={atual ? chaveConta(atual.conta) : ""} onChange={setEscolhida} />}
      tabela={temDado ? atividadeTabela(a) : null}
      largo
    >
      {a && (
        <MapaSemana
          celulas={a.celulas}
          rotuloValor="Média de seguidores ativos"
          rotuloN="dias"
          minimo={MIN_DIAS_CELULA}
          formatar={(v) => formatMedia(v)}
          notaHora="horas conforme a TikTok"
          descricao={`Mapa de calor da média de seguidores ativos de ${atual!.conta.rotulo} por dia da semana e hora, com as horas conforme a TikTok.`}
        />
      )}
    </CardAnalytics>
  );
}

// ---------------------------------------------------------------------------------------------
// Espectadores

function espectadores(contas: PublicoConta[], ordem: OrdemContas, tema: TemaGraficos) {
  const comSerie = contas.filter((c) => c.espectadores && c.espectadores.serie.length > 0);
  const dias = [...new Set(comSerie.flatMap((c) => c.espectadores!.serie.map((p) => p.dia)))].sort();
  const varias = comSerie.length > 1;
  const sufixo = (c: PublicoConta) => (varias ? ` ${c.conta.rotulo}` : "");
  const porDia = comSerie.map((c) => new Map(c.espectadores!.serie.map((p) => [p.dia, p])));
  const series = comSerie.flatMap((c, i) => {
    const cor = corDoSlot(tema, ordem.slot(c.conta.contaId));
    const m = porDia[i]!;
    const pilha = chaveConta(c.conta);
    return [
      {
        type: "bar" as const,
        name: `Novos${sufixo(c)}`,
        stack: pilha,
        data: dias.map((d) => m.get(d)?.novos ?? null),
        itemStyle: { color: cor, opacity: 0.85, borderRadius: 0 },
        barMaxWidth: 18,
      },
      {
        type: "bar" as const,
        name: `Recorrentes${sufixo(c)}`,
        stack: pilha,
        data: dias.map((d) => m.get(d)?.recorrentes ?? null),
        itemStyle: { color: cor, opacity: 0.4, borderRadius: [3, 3, 0, 0] },
        barMaxWidth: 18,
      },
      {
        type: "line" as const,
        name: `Total${sufixo(c)}`,
        // null = "sem dado": buraco na linha, nunca zero (FR-007)
        data: dias.map((d) => m.get(d)?.total ?? null),
        connectNulls: false,
        showSymbol: true,
        symbolSize: 7,
        lineStyle: { width: 2, color: cor },
        itemStyle: { color: cor, borderColor: tema.superficie, borderWidth: 2 },
      },
    ];
  });
  const opcoes: OpcoesGrafico = {
    grid: { left: 8, right: 16, top: 40, bottom: 8, containLabel: true },
    legend: { top: 0, type: "scroll", icon: "roundRect", itemWidth: 14, itemHeight: 8 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: dias.map(diaCurto) },
    yAxis: { type: "value", axisLabel: { formatter: (v: number) => formatCompacto(v) } },
    series,
  } as OpcoesGrafico;
  const tooltip = (itens: ItemTooltip[]) => {
    const i = itens[0]?.dataIndex;
    if (i === undefined || !dias[i]) return null;
    const linhas: LinhaTooltip[] = itens.map((p) => ({
      rotulo: p.seriesName ?? "",
      valor: p.value === null || p.value === undefined ? "sem dado" : formatNumero(p.value as number),
      cor: typeof p.color === "string" ? p.color : undefined,
    }));
    const semDado = linhas.some((l) => l.valor === "sem dado");
    return { titulo: formatDateKey(dias[i]), linhas, nota: semDado ? `"sem dado": a TikTok não informou o número neste dia. Fonte: ${FONTE_STUDIO}.` : `Fonte: ${FONTE_STUDIO}.` };
  };
  const tabela: DadosTabela = {
    colunas: [
      ...(varias ? [{ titulo: "conta" }] : []),
      { titulo: "fonte", secundaria: true },
      { titulo: "dia", formatar: (v) => formatDateKey(String(v)) },
      { titulo: "total", numerica: true },
      { titulo: "novos", numerica: true },
      { titulo: "recorrentes", numerica: true },
    ],
    linhas: comSerie.flatMap((c) => c.espectadores!.serie.map((p) => [...(varias ? [c.conta.rotulo] : []), "studio", p.dia, p.total, p.novos, p.recorrentes])),
  };
  return { comSerie, dias, opcoes, tooltip, tabela };
}

function IndicadoresEspectadores({ c, varias }: { c: PublicoConta; varias: boolean }) {
  const e = c.espectadores!;
  const dica = (n: number) => `${formatNumero(n)} ${n === 1 ? "dia" : "dias"} com dado`;
  return (
    <div className="flex flex-col gap-2" data-espectadores-conta={c.conta.rotulo}>
      {varias && <p className="text-sm font-medium">{c.conta.rotulo}</p>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Indicador rotulo="Novos espectadores (soma)" valor={e.novos.valor} anterior={e.novos.anterior} formatar={formatInteiro} dica={dica(e.novos.n)} className="bg-muted/40 shadow-none" />
        <Indicador rotulo="Espectadores por dia (média)" valor={e.mediaTotal.valor} anterior={e.mediaTotal.anterior} formatar={formatMedia} dica={dica(e.mediaTotal.n)} className="bg-muted/40 shadow-none" />
        <Indicador
          rotulo="Recorrentes por dia (média)"
          valor={e.mediaRecorrentes.valor}
          anterior={e.mediaRecorrentes.anterior}
          formatar={formatMedia}
          dica={dica(e.mediaRecorrentes.n)}
          className="bg-muted/40 shadow-none"
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------

function CardDistribuicao({ tipo, contas, carregando, erro }: { tipo: "genero" | "territorios"; contas: PublicoConta[]; carregando: boolean; erro: unknown }) {
  const tema = useTemaGraficos();
  const ordem = useOrdemContas();
  const comFoto = contas.filter((c) => c[tipo]);
  const varias = contas.length > 1;
  const titulo = tipo === "genero" ? "Gênero dos seguidores" : "Territórios dos seguidores";
  const fotos = [...new Set(comFoto.map((c) => c[tipo]!.dataFoto))];
  return (
    <CardAnalytics
      titulo={titulo}
      comoLer={
        <>
          {tipo === "genero"
            ? "a % dos seguidores por gênero na foto mais recente até o fim do período"
            : "os países com mais seguidores (até 5) na foto mais recente até o fim do período; \"Outros\" é o resto"}
          , com a mudança em pontos percentuais (p.p.) contra a foto anterior ao período. As fotos são do dia da exportação, não diárias; a TikTok não diz sobre quantos
          seguidores calculou. Fonte: {FONTE_STUDIO}
          {fotos.length > 0 && ` (foto de ${fotos.map(formatDateKey).join(", ")})`}.
        </>
      }
      carregando={carregando}
      erro={erro}
      vazio={comFoto.length === 0 ? motivoDoCard(contas, tipo) : null}
      acoesVazio={<AtalhosStudio contas={contas.filter((c) => c.motivos[tipo] !== "sem_dado_no_periodo").map((c) => c.conta)} />}
      tabela={distribuicaoTabela(contas, tipo)}
    >
      <div className={varias ? "grid grid-cols-1 gap-4" : undefined}>
        {contas.map((c) => {
          const d = c[tipo];
          if (!varias && !d) return null;
          return (
            <div key={chaveConta(c.conta)} className="min-w-0" data-distribuicao-conta={c.conta.rotulo}>
              {varias && (
                <p className="mb-1 flex items-center gap-1.5 text-sm font-medium">
                  <span aria-hidden="true" className="inline-block size-2 shrink-0 rounded-full" style={{ background: corDoSlot(tema, ordem.slot(c.conta.contaId)) }} />
                  {c.conta.rotulo}
                </p>
              )}
              {d ? (
                <Distribuicao dist={d} tipo={tipo} descricao={`${titulo} de ${c.conta.rotulo}, foto de ${formatDateKey(d.dataFoto)}.`} />
              ) : (
                <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">{motivoPublicoLabel[c.motivos[tipo] ?? "sem_importacao"]}</p>
              )}
            </div>
          );
        })}
      </div>
    </CardAnalytics>
  );
}

export function Publico({ estado }: { estado: EstadoFiltroAnalytics }) {
  const dados = usePublico(estado.filtro);
  const tema = useTemaGraficos();
  const ordem = useOrdemContas();
  const contas = useMemo(() => dados.data?.contas ?? [], [dados.data]);
  const carregando = dados.isPending;
  const esp = useMemo(() => espectadores(contas, ordem, tema), [contas, ordem, tema]);
  const atividades = useMemo<AtividadeSeguidoresConta[]>(() => contas.map((c) => ({ conta: c.conta, atividade: c.atividade, motivo: c.motivos.atividade })), [contas]);
  const diasSemDado = esp.comSerie.reduce((t, c) => t + c.espectadores!.diasSemDado, 0);

  return (
    <Page>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <CardDistribuicao tipo="genero" contas={contas} carregando={carregando} erro={dados.error} />
        <CardDistribuicao tipo="territorios" contas={contas} carregando={carregando} erro={dados.error} />
        <CardAtividade titulo="Atividade dos seguidores" contas={atividades} carregando={carregando} erro={dados.error} estado={estado} />
        <CardAnalytics
          titulo="Espectadores"
          comoLer={
            <>
              espectadores únicos de cada dia: as barras dividem os novos e os recorrentes, e a linha é o total. Os novos são somados no período; o total e os recorrentes viram média
              diária (o mesmo recorrente volta em vários dias, então não se somam).{" "}
              {esp.dias.length > 0 && (
                <span data-dias-cobertos>
                  {formatNumero(esp.dias.length)} dias cobertos{diasSemDado > 0 && `, ${formatNumero(diasSemDado)} "sem dado" (buraco na linha)`}.{" "}
                </span>
              )}
              Fonte: {FONTE_STUDIO}.
            </>
          }
          carregando={carregando}
          erro={dados.error}
          vazio={esp.comSerie.length === 0 ? motivoDoCard(contas, "espectadores") : null}
          acoesVazio={<AtalhosStudio contas={contas.filter((c) => c.motivos.espectadores !== "sem_dado_no_periodo").map((c) => c.conta)} />}
          onAmpliarPeriodo={contas.some((c) => c.motivos.espectadores === "sem_dado_no_periodo") ? estado.ampliarPeriodo : undefined}
          tabela={esp.tabela}
          largo
        >
          <div className="flex flex-col gap-4">
            {esp.comSerie.map((c) => (
              <IndicadoresEspectadores key={chaveConta(c.conta)} c={c} varias={esp.comSerie.length > 1} />
            ))}
            <Grafico opcoes={esp.opcoes} descricao={`Espectadores por dia de ${esp.comSerie.map((c) => c.conta.rotulo).join(", ")}: novos e recorrentes em barras e o total em linha.`} altura={300} tooltip={esp.tooltip} />
          </div>
        </CardAnalytics>
      </div>
    </Page>
  );
}
