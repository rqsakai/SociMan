/*
 * Aba "Contas" do analytics (spec 019, US5; FR-025 a FR-027).
 *
 * - Comparação entre contas e entre perfis: views do período em barras (uma cor fixa por conta) e, na
 *   tabela, os indicadores da visão geral. "Ver @conta" (e o clique na barra) aplica o filtro global
 *   `conta` (com o perfil dela) e mostra a trilha "Contas → @conta"; o perfil aplica `perfil`.
 * - Radar contra a média: 6 eixos com o índice (valor ÷ média × 100, cortado em 200), a conta escolhida
 *   contra a média em 100 (tracejada) e a tabela eixo / conta / média / índice. Com menos de 2 contas, o
 *   motivo da API e só a tabela de valores.
 * - Com uma conta filtrada, a evolução da conta da 016 (ContaMetricas, FR-001).
 * Tudo é leitura.
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CardAnalytics } from "@/components/analytics/CardAnalytics";
import { corDoSlot, useOrdemContas, type OrdemContas } from "@/components/analytics/coresContas";
import type { OpcoesGrafico } from "@/components/analytics/echarts";
import { Grafico } from "@/components/analytics/Grafico";
import { TabelaAlternativa, type DadosTabela } from "@/components/analytics/TabelaAlternativa";
import { useTemaGraficos, type TemaGraficos } from "@/components/analytics/tema";
import { ContaMetricas } from "@/components/metricas/ContaMetricas";
import { EmptyState, Page } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import {
  formatCompacto,
  formatEngajamento,
  formatNumero,
  useAnalytics,
  type AnalyticsContas,
  type AnalyticsIndicador,
  type AnalyticsRadarConta,
  type EstadoFiltroAnalytics,
} from "@/lib/analytics";
import { platformLabel } from "@/lib/perfis";
import { studioContaPath } from "@/lib/studio";

type ChaveIndicador = AnalyticsIndicador["chave"];
type ChaveEixo = AnalyticsRadarConta["eixos"][number]["chave"];

const INDICADORES: { chave: ChaveIndicador; titulo: string; formatar: (n: number | null | undefined) => string }[] = [
  { chave: "views", titulo: "Views", formatar: formatNumero },
  { chave: "likes", titulo: "Curtidas", formatar: formatNumero },
  { chave: "engajamento", titulo: "Engajamento", formatar: formatEngajamento },
  { chave: "seguidores", titulo: "Seguidores ganhos", formatar: formatNumero },
  { chave: "posts", titulo: "Posts", formatar: formatNumero },
  { chave: "mediana_post", titulo: "Mediana do post", formatar: formatNumero },
];

const fracao = (n: number | null | undefined) => formatEngajamento(n);
const EIXOS: Record<ChaveEixo, { nome: string; formatar: (n: number | null | undefined) => string }> = {
  views_por_post: { nome: "Views por post", formatar: formatNumero },
  engajamento: { nome: "Engajamento", formatar: formatEngajamento },
  frequencia: { nome: "Frequência (posts/dia)", formatar: (n) => (n === null || n === undefined ? "—" : n.toLocaleString("pt-BR", { maximumFractionDigits: 2 })) },
  crescimento: { nome: "Crescimento de seguidores", formatar: fracao },
  velocidade_1h: { nome: "Views na 1ª hora", formatar: formatNumero },
  acima_mediana: { nome: "% acima da mediana", formatar: fracao },
};

const valorDe = (indicadores: AnalyticsIndicador[], chave: ChaveIndicador) => indicadores.find((i) => i.chave === chave)?.valor ?? null;

function barras(rotulos: string[], valores: (number | null)[], cores: string[]): OpcoesGrafico {
  return {
    grid: { left: 8, right: 24, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: "value", axisLabel: { formatter: (v: number) => formatCompacto(v) } },
    yAxis: { type: "category", inverse: true, data: rotulos, axisLabel: { width: 140, overflow: "truncate" } },
    series: [
      {
        type: "bar",
        name: "Views no período",
        barMaxWidth: 24,
        itemStyle: { borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: "right", formatter: (p: { value?: unknown }) => formatCompacto(Number(p.value ?? 0)) },
        data: valores.map((v, i) => ({ value: v ?? 0, itemStyle: { color: cores[i] } })),
      },
    ],
  };
}

function montar(dados: AnalyticsContas | undefined, radarConta: string | undefined, tema: TemaGraficos, ordem: OrdemContas) {
  const contas = dados?.contas ?? [];
  const perfis = dados?.perfis ?? [];
  const radar = dados?.radar ?? null;

  const tabelaContas: DadosTabela = {
    colunas: [
      { titulo: "Conta" },
      { titulo: "Perfil", secundaria: true },
      { titulo: "Rede", secundaria: true },
      ...INDICADORES.map((i) => ({ titulo: i.titulo, numerica: true, secundaria: i.chave !== "views", formatar: (v: unknown) => i.formatar(typeof v === "number" ? v : null) })),
    ],
    linhas: contas.map((c) => [c.rotulo, c.perfil.name, platformLabel[c.rede], ...INDICADORES.map((i) => valorDe(c.indicadores, i.chave))]),
  };
  const opcoesContas = barras(
    contas.map((c) => c.rotulo),
    contas.map((c) => valorDe(c.indicadores, "views")),
    contas.map((c) => corDoSlot(tema, ordem.slot(c.contaId))),
  );

  const tabelaPerfis: DadosTabela = {
    colunas: [{ titulo: "Perfil" }, ...INDICADORES.map((i) => ({ titulo: i.titulo, numerica: true, secundaria: i.chave !== "views", formatar: (v: unknown) => i.formatar(typeof v === "number" ? v : null) }))],
    linhas: perfis.map((p) => [p.perfil.name, ...INDICADORES.map((i) => valorDe(p.indicadores, i.chave))]),
  };
  // perfis não têm cor de entidade da paleta de contas: uma série só, no slot 1
  const opcoesPerfis = barras(
    perfis.map((p) => p.perfil.name),
    perfis.map((p) => valorDe(p.indicadores, "views")),
    perfis.map(() => tema.categorica[0]!),
  );

  const atual = radar?.find((r) => r.contaId === radarConta) ?? radar?.[0];
  const corAtual = corDoSlot(tema, ordem.slot(atual?.contaId));
  const opcoesRadar: OpcoesGrafico | null = atual
    ? {
        legend: { bottom: 0, data: [atual.rotulo, "Média das contas"] },
        radar: {
          indicator: atual.eixos.map((e) => ({ name: EIXOS[e.chave].nome, min: 0, max: 200 })),
          radius: "62%",
          center: ["50%", "48%"],
          axisName: { color: tema.textoFraco },
        },
        series: [
          {
            type: "radar",
            data: [
              {
                name: "Média das contas",
                value: atual.eixos.map(() => 100),
                symbol: "none",
                lineStyle: { color: tema.textoFraco, type: "dashed", width: 1 },
                itemStyle: { color: tema.textoFraco },
              },
              {
                name: atual.rotulo,
                value: atual.eixos.map((e) => e.indice ?? 0),
                lineStyle: { color: corAtual, width: 2 },
                itemStyle: { color: corAtual },
                areaStyle: { color: corAtual, opacity: 0.1 },
              },
            ],
          },
        ],
      }
    : null;
  const tabelaRadar: DadosTabela = {
    colunas: [
      { titulo: "Eixo" },
      { titulo: "Conta", numerica: true },
      { titulo: "Média", numerica: true },
      { titulo: "Índice", numerica: true, formatar: (v, l) => (typeof v === "number" ? `${formatNumero(Math.round(v))}${l[4] ? "+ (acima)" : ""}` : "—") },
      { titulo: "Acima de 200", secundaria: true },
    ],
    linhas: (atual?.eixos ?? []).map((e) => [EIXOS[e.chave].nome, EIXOS[e.chave].formatar(e.valor), EIXOS[e.chave].formatar(e.media), e.indice ?? null, e.acima]),
  };

  return { contas, perfis, radar, atual, tabelaContas, opcoesContas, tabelaPerfis, opcoesPerfis, opcoesRadar, tabelaRadar };
}

export function Contas({ estado }: { estado: EstadoFiltroAnalytics }) {
  const dados = useAnalytics("contas", estado.filtro);
  const tema = useTemaGraficos();
  const ordem = useOrdemContas();
  const [radarConta, setRadarConta] = useState<string>();
  const v = useMemo(() => montar(dados.data, radarConta ?? estado.filtro.contaId, tema, ordem), [dados.data, radarConta, estado.filtro.contaId, tema, ordem]);
  const comum = { carregando: dados.isPending || !ordem.pronto, erro: dados.error, onAmpliarPeriodo: estado.ampliarPeriodo };

  // drill-down (FR-027): a conta leva o perfil dela, para a trilha e o filtro de conta funcionarem
  const abrirConta = (contaId: string) => {
    const c = v.contas.find((x) => x.contaId === contaId);
    if (c) estado.set({ perfil: c.perfil.id, conta: c.contaId });
  };
  const abrirPerfil = (perfilId: string) => estado.set({ perfil: perfilId, conta: null });

  return (
    <Page>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CardAnalytics
          titulo="Comparação entre contas"
          comoLer="views ganhas no período por conta, cada uma com a sua cor; a tabela traz os outros indicadores. Clique numa conta para ver todas as abas filtradas por ela."
          vazio={v.contas.length === 0 ? "Nenhuma conta com post ou views no período." : null}
          tabela={v.tabelaContas}
          {...comum}
        >
          <Grafico
            opcoes={v.opcoesContas}
            altura={Math.max(140, v.contas.length * 36 + 40)}
            descricao={`Views no período de ${v.contas.length} contas: ${v.contas.map((c) => `${c.rotulo} ${formatNumero(valorDe(c.indicadores, "views"))}`).join(", ")}.`}
            onClickItem={(item) => {
              const c = v.contas[item.dataIndex];
              if (c) abrirConta(c.contaId);
            }}
          />
          <div className="mt-2 flex flex-wrap gap-1.5" aria-label="Abrir conta">
            {v.contas.map((c) => (
              <Button key={c.contaId} type="button" size="sm" variant="outline" onClick={() => abrirConta(c.contaId)} aria-current={c.contaId === estado.filtro.contaId ? "true" : undefined}>
                Ver {c.rotulo}
              </Button>
            ))}
          </div>
          {/* spec 020 (FR-022): o histórico importado do Studio de cada conta TikTok */}
          {v.contas.some((c) => c.rede === "tiktok") && (
            <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-sm" aria-label="Histórico do Studio">
              {v.contas
                .filter((c) => c.rede === "tiktok")
                .map((c) => (
                  <Link key={c.contaId} to={studioContaPath(c.contaId)} className="text-primary underline-offset-2 hover:underline">
                    Histórico do Studio de {c.rotulo}
                  </Link>
                ))}
            </p>
          )}
        </CardAnalytics>

        <CardAnalytics
          titulo="Radar contra a média"
          comoLer="cada eixo compara a conta com a média das contas com post no período; a linha tracejada é a média (100). Fora dela é melhor; o eixo vai até 200."
          tabela={v.radar ? v.tabelaRadar : null}
          acoes={
            v.radar && v.radar.length > 1 ? (
              <Field label="Conta no radar" className="w-44">
                {({ id }) => (
                  <NativeSelect id={id} value={v.atual?.contaId ?? ""} onChange={(e) => setRadarConta(e.target.value)}>
                    {v.radar!.map((r) => (
                      <option key={r.contaId} value={r.contaId}>
                        {r.rotulo}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
            ) : undefined
          }
          vazio={!v.radar && v.contas.length === 0 ? "Nenhuma conta com post no período." : null}
          {...comum}
        >
          {v.opcoesRadar && v.atual ? (
            <Grafico
              opcoes={v.opcoesRadar}
              altura={320}
              descricao={`Radar de ${v.atual.rotulo} contra a média das contas (100): ${v.atual.eixos.map((e) => `${EIXOS[e.chave].nome} ${e.indice === null || e.indice === undefined ? "sem dado" : Math.round(e.indice)}${e.acima ? " ou mais" : ""}`).join("; ")}.`}
              onClickItem={() => v.atual && abrirConta(v.atual.contaId)}
              tooltip={() => ({
                titulo: v.atual!.rotulo,
                linhas: v.atual!.eixos.map((e) => ({ rotulo: EIXOS[e.chave].nome, valor: `${e.indice === null || e.indice === undefined ? "—" : Math.round(e.indice)}${e.acima ? "+" : ""} (${EIXOS[e.chave].formatar(e.valor)})` })),
                nota: "índice: 100 = média das contas",
              })}
            />
          ) : (
            <div className="flex flex-col gap-3">
              <EmptyState
                className="rounded-lg border border-dashed py-6"
                titulo={dados.data?.radarMotivo ?? "O radar precisa de pelo menos duas contas com post no período."}
              />
              <TabelaAlternativa titulo="Valores da conta" dados={v.tabelaContas} />
            </div>
          )}
        </CardAnalytics>

        <CardAnalytics
          titulo="Comparação entre perfis"
          comoLer="views ganhas no período por perfil, somando as contas dele; a tabela traz os outros indicadores."
          vazio={v.perfis.length === 0 ? "Nenhum perfil com post ou views no período." : null}
          tabela={v.tabelaPerfis}
          largo
          {...comum}
        >
          <Grafico
            opcoes={v.opcoesPerfis}
            altura={Math.max(120, v.perfis.length * 36 + 40)}
            descricao={`Views no período de ${v.perfis.length} perfis.`}
            onClickItem={(item) => {
              const p = v.perfis[item.dataIndex];
              if (p) abrirPerfil(p.perfil.id);
            }}
          />
          <div className="mt-2 flex flex-wrap gap-1.5">
            {v.perfis.map((p) => (
              <Button key={p.perfil.id} type="button" size="sm" variant="outline" onClick={() => abrirPerfil(p.perfil.id)}>
                Ver perfil {p.perfil.name}
              </Button>
            ))}
          </div>
        </CardAnalytics>
      </div>
      {estado.filtro.contaId ? (
        <ContaMetricas semFiltroContas />
      ) : (
        <p className="text-sm text-muted-foreground">Escolha uma conta (acima ou nos filtros) para ver a evolução dela.</p>
      )}
    </Page>
  );
}
