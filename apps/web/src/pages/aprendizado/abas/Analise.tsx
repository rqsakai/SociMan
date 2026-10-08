/*
 * Aba "Por que deu certo" (spec 023, US2; FR-010 a FR-028; R1–R4). Só leitura: a API calcula na
 * leitura e nada é gravado.
 *
 * - Contexto: período e medida, posts aguardando o marco, "Sem tema" e pendentes, e o rótulo
 *   "exploratório" com o número de comparações (FR-028).
 * - Distribuição travada (FR-027): aviso por conta, com o link para o Diagnóstico; a parte de
 *   rendimento dessa conta vale só como indício.
 * - Duas partes, nesta ordem: entrega (a rede mostrou?) e rendimento (quanto rendeu quando mostrou),
 *   cada uma com o gráfico (intervalo + ponto) e a lista por fator, com n, confiança e avisos.
 * - Hashtags sempre juntas (blocos) e a matriz hashtag × tema.
 * Cada card tem a leitura, a tabela alternativa e o CSV (FR-005/FR-006 da 019).
 */
import { Info, Stethoscope, TriangleAlert } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { EfeitoLinha, textoAviso } from "@/components/aprendizado/EfeitoLinha";
import { GraficoEfeitos } from "@/components/aprendizado/GraficoEfeitos";
import { MatrizHashtagTema, tabelaMatriz } from "@/components/aprendizado/MatrizHashtagTema";
import { CardAnalytics } from "@/components/analytics/CardAnalytics";
import type { DadosTabela } from "@/components/analytics/TabelaAlternativa";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Page } from "@/components/shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  aprendizadoPath,
  confiancaLabel,
  formatEfeito,
  medidaAprendizadoLabel,
  rotuloFator,
  useAnaliseAprendizado,
  type AprendizadoAnalise,
  type AprendizadoEfeito,
} from "@/lib/aprendizado";
import { formatNumero } from "@/lib/metricas";
import type { AbaProps } from "../Aprendizado";

const ORDEM_FATORES = ["tema", "estilo_gancho", "tamanho_gancho", "duracao", "faixa_horario", "dia_semana", "canal_fonte", "hashtag", "modo_envio"];

function tabelaEfeitos(efeitos: AprendizadoEfeito[]): DadosTabela {
  return {
    colunas: [
      { titulo: "Fator" },
      { titulo: "Valor" },
      { titulo: "Efeito" },
      { titulo: "Intervalo (baixo)", secundaria: true },
      { titulo: "Intervalo (alto)", secundaria: true },
      { titulo: "Posts", numerica: true },
      { titulo: "Dias", numerica: true, secundaria: true },
      { titulo: "Confiança" },
      { titulo: "Avisos", secundaria: true },
    ],
    linhas: efeitos.map((e) => [
      rotuloFator(e.fator),
      e.rotulo,
      e.confianca === "amostra_pequena" ? "—" : formatEfeito(e.parte, e.efeito),
      e.intervalo ? formatEfeito(e.parte, e.intervalo[0]) : null,
      e.intervalo ? formatEfeito(e.parte, e.intervalo[1]) : null,
      e.nPosts,
      e.nDias,
      confiancaLabel[e.confianca],
      e.avisos.map((a) => textoAviso(a, e.parte)).join("; ") || null,
    ]),
  };
}

function agrupar(efeitos: AprendizadoEfeito[]) {
  const grupos = new Map<string, AprendizadoEfeito[]>();
  for (const e of efeitos) {
    if (!grupos.has(e.fator)) grupos.set(e.fator, []);
    grupos.get(e.fator)!.push(e);
  }
  return [...grupos.entries()].sort((a, b) => ORDEM_FATORES.indexOf(a[0]) - ORDEM_FATORES.indexOf(b[0]));
}

// Os valores com amostra pequena (só números brutos) ficam recolhidos: a lista abre com o que tem
// efeito, e "Mais N com amostra pequena" mostra o resto.
function ListaFator({ lista }: { lista: AprendizadoEfeito[] }) {
  const comEfeito = lista.filter((e) => e.confianca !== "amostra_pequena");
  const pequenos = lista.filter((e) => e.confianca === "amostra_pequena");
  return (
    <>
      <ul className="divide-y">
        {comEfeito.map((e) => (
          <EfeitoLinha key={`${e.fator}:${e.valor}`} efeito={e} />
        ))}
      </ul>
      {pequenos.length > 0 && (
        <details className="group text-sm" open={comEfeito.length === 0 && pequenos.length <= 3}>
          <summary className="cursor-pointer py-1.5 text-muted-foreground">
            {comEfeito.length > 0 ? "Mais " : ""}
            {formatNumero(pequenos.length)} {pequenos.length === 1 ? "valor" : "valores"} com amostra pequena
          </summary>
          <ul className="divide-y">
            {pequenos.map((e) => (
              <EfeitoLinha key={`${e.fator}:${e.valor}`} efeito={e} />
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

function Parte({ parte, efeitos, travadas }: { parte: AprendizadoEfeito["parte"]; efeitos: AprendizadoEfeito[]; travadas: boolean }) {
  const titulo = parte === "entrega" ? "Entrega: a rede mostrou?" : "Rendimento: quanto rendeu quando mostrou";
  const comoLer =
    parte === "entrega"
      ? "a diferença, em pontos percentuais, na chance de o post sair do zero (sair da estagnação) em relação à conta. O ponto é o efeito; a faixa é o intervalo plausível."
      : `só entre os posts que saíram do zero: quantas vezes o típico da conta (escala logarítmica, sem deixar um viral dominar). O ponto é o efeito encolhido; a faixa é o intervalo plausível.${travadas ? " Há conta com distribuição travada: leia como indício." : ""}`;
  const tabela = useMemo(() => tabelaEfeitos(efeitos), [efeitos]);
  return (
    <CardAnalytics titulo={titulo} comoLer={comoLer} tabela={tabela} vazio={efeitos.length === 0 ? "Nenhum post medido neste recorte." : null} largo>
      <div className="flex flex-col gap-4">
        <GraficoEfeitos efeitos={efeitos} parte={parte} descricao={`${titulo}: efeito e intervalo por fator.`} />
        <div className="grid gap-x-8 gap-y-2 lg:grid-cols-2">
          {agrupar(efeitos).map(([fator, lista]) => (
            <section key={fator} aria-label={`${rotuloFator(fator)} (${parte})`} className="min-w-0">
              <h4 className="text-sm font-semibold">{rotuloFator(fator)}</h4>
              <ListaFator lista={lista} />
            </section>
          ))}
        </div>
      </div>
    </CardAnalytics>
  );
}

function Contexto({ d, perfilId }: { d: AprendizadoAnalise; perfilId: string }) {
  const c = d.contexto;
  const k = c.constantes;
  const travadas = c.contas.filter((x) => x.travada);
  return (
    <div className="flex flex-col gap-3">
      {travadas.map((t) => (
        <Alert key={t.contaId} data-travada={t.rotulo}>
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>Distribuição travada em {t.rotulo}</AlertTitle>
          <AlertDescription>
            <p>
              {formatNumero(t.estagnados)} de {formatNumero(t.medidos)} posts medidos ficaram estagnados (0 a 1 view). Enquanto a rede não entrega, o assunto não explica o
              resultado: as conclusões de rendimento desta conta ficam suspensas e aparecem só como indício.
            </p>
            <Button asChild size="sm" variant="outline" className="mt-1">
              <Link to={aprendizadoPath(perfilId, "diagnostico", { conta: t.contaId })}>
                <Stethoscope aria-hidden="true" />
                Ver o diagnóstico
              </Link>
            </Button>
          </AlertDescription>
        </Alert>
      ))}
      <p className="flex items-start gap-2 rounded-lg bg-muted/50 p-3 text-sm" data-exploratorio={c.comparacoes}>
        <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <span>
          <strong>Exploratório:</strong> {formatNumero(c.comparacoes)} comparações neste recorte; espere cerca de {formatNumero(c.falsosEsperados)} achados fracos por
          acaso. Só confiança moderada ou forte vira recomendação. {medidaAprendizadoLabel[c.medida as keyof typeof medidaAprendizadoLabel] ?? c.medida}
          {c.aguardando > 0 ? `; ${formatNumero(c.aguardando)} posts aguardando o marco ficaram fora` : ""}
          {d.semTema > 0 ? `; ${formatNumero(d.semTema)} "Sem tema"` : ""}
          {d.pendentesClassificacao > 0 ? (
            <>
              {"; "}
              <Link to={aprendizadoPath(perfilId, "temas")} className="underline">
                {formatNumero(d.pendentesClassificacao)} aguardando classificação
              </Link>
            </>
          ) : null}
          .
        </span>
      </p>
      {k && (
        <p className="text-xs text-muted-foreground">
          Regras fixas: efeito encolhido com {k.kEncolhimento} posts &quot;típicos&quot;; mínimo de {k.minGrupo} posts distintos em {k.minDias} dias por grupo e {k.minConta} posts
          medidos por conta; meia-vida de {k.meiaVidaDias} dias numa janela de {k.janelaDias} dias; conta travada com mais de {Math.round(k.travada * 100)}% dos posts estagnados.
        </p>
      )}
    </div>
  );
}

export function Analise({ perfil, estado }: AbaProps) {
  const analise = useAnaliseAprendizado(perfil.id, estado.filtro);
  const d = analise.data;
  const entrega = useMemo(() => d?.efeitos.filter((e) => e.parte === "entrega") ?? [], [d]);
  const rendimento = useMemo(() => d?.efeitos.filter((e) => e.parte === "rendimento") ?? [], [d]);
  const tabelaM = useMemo(() => (d ? tabelaMatriz(d.matriz) : null), [d]);
  // bloco de uma hashtag só não é "sempre juntas"
  const blocos = useMemo(() => d?.blocos.filter((b) => b.hashtags.length > 1) ?? [], [d]);

  if (analise.isError) return <ApiErrorAlert error={analise.error} />;
  if (analise.isPending || !d) return <Skeleton className="h-96 w-full" />;

  return (
    <Page>
      <Contexto d={d} perfilId={perfil.id} />
      <div className="grid min-w-0 gap-6 lg:grid-cols-2">
        <Parte parte="entrega" efeitos={entrega} travadas={d.contexto.contas.some((c) => c.travada)} />
        <Parte parte="rendimento" efeitos={rendimento} travadas={d.contexto.contas.some((c) => c.travada)} />
        <CardAnalytics
          titulo="Hashtags sempre juntas"
          comoLer="hashtags usadas exatamente nos mesmos posts viram um bloco e contam uma vez só: não dá para saber qual delas fez efeito."
          tabela={{ colunas: [{ titulo: "Bloco" }, { titulo: "Posts", numerica: true }], linhas: blocos.map((b) => [b.hashtags.map((h) => `#${h}`).join(" + "), b.nPosts]) }}
          vazio={blocos.length === 0 ? "Nenhum grupo de hashtags que aparece sempre junto." : null}
        >
          <ul className="divide-y" aria-label="Blocos de hashtags">
            {blocos.map((b) => (
              <li key={b.valor} className="py-2 text-sm" data-bloco={b.valor}>
                <span className="font-medium">{b.hashtags.map((h) => `#${h}`).join(" + ")}</span>
                <span className="text-muted-foreground">: sempre juntas em {formatNumero(b.nPosts)} posts</span>
                {b.quaseSempreCom.length > 0 && <span className="block text-xs text-muted-foreground">quase sempre com {b.quaseSempreCom.join(", ")}</span>}
              </li>
            ))}
          </ul>
        </CardAnalytics>
        <CardAnalytics
          titulo="Hashtag × tema"
          comoLer="quantos posts de cada tema usam cada hashtag. Hashtag que só aparece num tema não se separa dele: o efeito pode ser do assunto."
          tabela={tabelaM}
          vazio={d.matriz.length === 0 ? "Sem hashtags ou sem temas classificados neste recorte." : null}
        >
          <MatrizHashtagTema matriz={d.matriz} />
        </CardAnalytics>
      </div>
    </Page>
  );
}
