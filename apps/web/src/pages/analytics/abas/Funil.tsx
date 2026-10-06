/*
 * Aba "Funil" do analytics (spec 019, US6; FR-028/FR-029; research R7).
 *
 * - Funil de produção: as 5 etapas (enviados → cortes → aprovados → publicados → acima do patamar) em
 *   barras de uma cor só (categorias ordenadas), com a contagem e a % sobre a etapa anterior; o tooltip
 *   e a tabela listam o que caiu em cada etapa.
 * - Para onde vai o material: sankey das passagens (cor da série) e das perdas (cinza).
 * - Tempos medianos e, só para o dono, o custo de IA (o servidor manda `null` para o membro e a tela
 *   nem mostra o card).
 * O patamar de views em 24 h (padrão 100) fica acima dos cards, porque muda a última etapa.
 * Tudo é leitura.
 */
import { useEffect, useMemo, useState } from "react";
import { CardAnalytics } from "@/components/analytics/CardAnalytics";
import type { OpcoesGrafico } from "@/components/analytics/echarts";
import { Grafico } from "@/components/analytics/Grafico";
import type { DadosTabela } from "@/components/analytics/TabelaAlternativa";
import { useTemaGraficos, type TemaGraficos } from "@/components/analytics/tema";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { formatIdadeHoras, formatNumero, useAnalytics, type AnalyticsEtapaFunil, type AnalyticsFunil, type EstadoFiltroAnalytics } from "@/lib/analytics";
import { useEhDono } from "@/lib/conteudos";

const PATAMAR_PADRAO = 100;

const ETAPA: Record<AnalyticsEtapaFunil["chave"], string> = {
  enviados: "Vídeos-fonte enviados",
  cortes: "Cortes gerados",
  aprovados: "Cortes aprovados",
  publicados: "Posts publicados",
  acima_patamar: "Acima do patamar",
};

const PERDA: Record<string, string> = {
  sem_clipes: "sem clipes",
  falhou: "falhou",
  em_andamento: "em andamento",
  arquivado: "arquivado",
  recusado: "recusado",
  em_revisao: "parado em revisão",
  sem_aprovacao: "sem aprovação",
  aguardando_publicacao: "aguardando publicação",
  sem_video: "sem vídeo ligado",
  aguardando_24h: "aguardando 24 h",
  sem_dado: "sem dado",
  abaixo_do_patamar: "abaixo do patamar",
};
const perdaLabel = (m: string) => PERDA[m] ?? m.replace(/_/g, " ");

const pct = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 1 });
const usd = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", maximumFractionDigits: 4 });
const formatPct = (n: number | null | undefined) => (n === null || n === undefined ? "—" : pct.format(n));
const textoPerdas = (e: AnalyticsEtapaFunil) => e.perdas.map((p) => `${perdaLabel(p.motivo)}: ${formatNumero(p.n)}`).join("; ");

function montar(dados: AnalyticsFunil | undefined, tema: TemaGraficos) {
  const etapas = dados?.etapas ?? [];
  const cor = tema.categorica[0]!;

  const opcoesFunil: OpcoesGrafico = {
    grid: { left: 8, right: 72, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: "value", axisLabel: { formatter: (v: number) => formatNumero(v) } },
    yAxis: { type: "category", inverse: true, data: etapas.map((e) => ETAPA[e.chave]) },
    series: [
      {
        type: "bar",
        name: "Quantidade",
        barMaxWidth: 24,
        color: cor,
        itemStyle: { borderRadius: [0, 4, 4, 0] },
        label: {
          show: true,
          position: "right",
          color: tema.texto,
          formatter: (p: { dataIndex: number }) => {
            const e = etapas[p.dataIndex];
            return e ? `${formatNumero(e.n)}${e.conversaoPct !== null && e.conversaoPct !== undefined ? ` (${formatPct(e.conversaoPct)})` : ""}` : "";
          },
        },
        data: etapas.map((e) => e.n),
      },
    ],
  };

  const tabela: DadosTabela = {
    colunas: [
      { titulo: "Etapa" },
      { titulo: "Quantidade", numerica: true },
      { titulo: "% da etapa anterior", numerica: true, formatar: (v) => formatPct(typeof v === "number" ? v : null) },
      { titulo: "O que caiu", secundaria: true },
      { titulo: "Tempo mediano (h)", numerica: true, secundaria: true, formatar: (v) => (typeof v === "number" ? formatIdadeHoras(v) : "—") },
    ],
    linhas: etapas.map((e) => [ETAPA[e.chave], e.n, e.conversaoPct ?? null, textoPerdas(e) || null, e.tempoMedianoH ?? null]),
  };

  // sankey: etapa → etapa seguinte (o n da seguinte) e etapa → perda (cinza). Nomes únicos por etapa.
  const nos: { name: string; itemStyle: { color: string } }[] = [];
  const links: { source: string; target: string; value: number }[] = [];
  etapas.forEach((e, i) => {
    nos.push({ name: ETAPA[e.chave], itemStyle: { color: cor } });
    const prox = etapas[i + 1];
    if (prox && prox.n > 0) links.push({ source: ETAPA[e.chave], target: ETAPA[prox.chave], value: prox.n });
    for (const p of e.perdas) {
      if (p.n <= 0) continue;
      const nome = `${ETAPA[e.chave]}: ${perdaLabel(p.motivo)}`;
      nos.push({ name: nome, itemStyle: { color: tema.textoFraco } });
      links.push({ source: ETAPA[e.chave], target: nome, value: p.n });
    }
  });
  const opcoesSankey: OpcoesGrafico = {
    series: [
      {
        type: "sankey",
        left: 8,
        right: 120,
        top: 8,
        bottom: 8,
        nodeGap: 10,
        nodeWidth: 12,
        draggable: false,
        emphasis: { focus: "adjacency" },
        label: { color: tema.texto, fontSize: 11 },
        lineStyle: { color: "source", opacity: 0.25, curveness: 0.5 },
        data: nos,
        links,
      },
    ],
  };
  const tabelaPerdas: DadosTabela = {
    colunas: [{ titulo: "Etapa" }, { titulo: "Motivo" }, { titulo: "Quantidade", numerica: true }],
    linhas: etapas.flatMap((e) => e.perdas.map((p) => [ETAPA[e.chave], perdaLabel(p.motivo), p.n])),
  };

  return { etapas, opcoesFunil, tabela, opcoesSankey, tabelaPerdas, temLinks: links.length > 0 };
}

function Numero({ rotulo, valor, dica }: { rotulo: string; valor: string; dica?: string }) {
  return (
    <div className="min-w-0 rounded-lg border p-3" data-numero={rotulo}>
      <p className="truncate text-sm text-muted-foreground">{rotulo}</p>
      <p className="text-xl font-semibold">{valor}</p>
      {dica && <p className="mt-0.5 text-xs text-muted-foreground">{dica}</p>}
    </div>
  );
}

export function Funil({ estado }: { estado: EstadoFiltroAnalytics }) {
  const dono = useEhDono();
  const [texto, setTexto] = useState(String(PATAMAR_PADRAO));
  const [patamar, setPatamar] = useState(PATAMAR_PADRAO);
  useEffect(() => {
    const t = setTimeout(() => {
      const n = Number.parseInt(texto, 10);
      if (Number.isFinite(n) && n >= 1) setPatamar(n);
    }, 400);
    return () => clearTimeout(t);
  }, [texto]);
  const dados = useAnalytics("funil", estado.filtro, { patamar });
  const tema = useTemaGraficos();
  const v = useMemo(() => montar(dados.data, tema), [dados.data, tema]);
  const comum = { carregando: dados.isPending, erro: dados.error, onAmpliarPeriodo: estado.ampliarPeriodo };
  const vazio = v.etapas.length === 0 ? "Nenhum vídeo-fonte enviado para corte neste período." : null;
  const tempo = (chave: AnalyticsEtapaFunil["chave"]) => {
    const h = v.etapas.find((e) => e.chave === chave)?.tempoMedianoH;
    return h === null || h === undefined ? "—" : formatIdadeHoras(h);
  };
  const custo = dados.data?.custoIaUsd;
  const porMil = dados.data?.custoPorMilViewsUsd;
  const verCusto = dono && custo !== null && custo !== undefined;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Patamar de views em 24 h" className="w-full sm:w-56">
          {({ id }) => (
            <Input
              id={id}
              type="number"
              min={1}
              step={1}
              inputMode="numeric"
              value={texto}
              aria-invalid={!(Number.parseInt(texto, 10) >= 1)}
              onChange={(e) => setTexto(e.target.value)}
            />
          )}
        </Field>
        <p className="pb-2 text-xs text-muted-foreground">A última etapa conta os posts com pelo menos {formatNumero(patamar)} views em 24 h.</p>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CardAnalytics
          titulo="Funil de produção"
          comoLer="quantos itens chegam a cada etapa, do vídeo-fonte enviado ao post acima do patamar, e entre parênteses a % sobre a etapa anterior (um envio gera vários cortes, então pode passar de 100%)."
          vazio={vazio}
          tabela={v.tabela}
          {...comum}
        >
          <Grafico
            opcoes={v.opcoesFunil}
            altura={240}
            descricao={`Funil do período: ${v.etapas.map((e) => `${ETAPA[e.chave]} ${formatNumero(e.n)}`).join(", ")}.`}
            tooltip={(itens) => {
              const e = v.etapas[itens[0]?.dataIndex ?? -1];
              if (!e) return null;
              return {
                titulo: ETAPA[e.chave],
                linhas: [
                  { rotulo: "quantidade", valor: formatNumero(e.n) },
                  { rotulo: "da etapa anterior", valor: formatPct(e.conversaoPct) },
                  ...e.perdas.map((p) => ({ rotulo: `caiu: ${perdaLabel(p.motivo)}`, valor: formatNumero(p.n) })),
                ],
              };
            }}
          />
        </CardAnalytics>
        <CardAnalytics
          titulo="Para onde vai o material"
          comoLer="a largura de cada faixa é a quantidade; as faixas azuis seguem para a etapa seguinte e as cinzas são o que caiu (sem clipes, arquivado, recusado…). A 1ª passagem pode alargar: um envio gera vários cortes, então ela conta cortes, não envios."
          vazio={vazio ?? (v.temLinks ? null : "Nada passou de etapa nem caiu neste período.")}
          tabela={v.tabelaPerdas}
          {...comum}
        >
          <Grafico
            opcoes={v.opcoesSankey}
            altura={300}
            descricao={`Fluxo do material entre as etapas e as perdas: ${v.tabelaPerdas.linhas.map((l) => `${l[0]}, ${l[1]}: ${l[2]}`).join("; ") || "sem perdas"}.`}
            tooltip={(itens) => {
              const d = itens[0]?.data as { source?: string; target?: string; value?: number; name?: string } | undefined;
              if (!d) return null;
              if (d.source) return { titulo: `${d.source} → ${d.target}`, linhas: [{ rotulo: "quantidade", valor: formatNumero(d.value) }] };
              return { titulo: d.name ?? "", linhas: [] };
            }}
          />
        </CardAnalytics>
        <CardAnalytics titulo="Tempos de cada etapa" comoLer="a mediana do tempo para chegar a cada etapa; metade dos itens levou menos que isso." vazio={vazio} {...comum}>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Numero rotulo="Processamento do envio" valor={tempo("cortes")} dica="do início ao fim no SociShorts" />
            <Numero rotulo="Corte até a aprovação" valor={tempo("aprovados")} />
            <Numero rotulo="Aprovação até a publicação" valor={tempo("publicados")} />
          </div>
        </CardAnalytics>
        {verCusto && (
          <CardAnalytics titulo="Custo de IA" comoLer="o custo aproximado do assistente de IA nos conteúdos do período, no total e por mil views dos vídeos ligados a eles. Só o dono vê." {...comum}>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Numero rotulo="Custo total" valor={usd.format(custo)} />
              <Numero rotulo="Custo por mil views" valor={porMil === null || porMil === undefined ? "—" : usd.format(porMil)} dica={porMil === null || porMil === undefined ? "sem views nos vídeos ligados" : undefined} />
            </div>
          </CardAnalytics>
        )}
      </div>
    </div>
  );
}
