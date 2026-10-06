/*
 * Aba "Alertas" do analytics (spec 019, US8; FR-032/FR-033; research R9).
 *
 * Os alertas são calculados na hora pela API e nunca gravados: somem sozinhos quando a condição deixa
 * de valer. A lista vem por severidade (atenção → informação → destaque positivo), cada um com ícone e
 * texto (as cores de status são reservadas e nunca andam sozinhas), o motivo, os números, o que
 * conferir e o link para o item. `ContadorAlertas` é o "(N)" no rótulo da aba: atenção + informação
 * (o destaque positivo não pede ação).
 * Tudo é leitura.
 */
import { ArrowRight, Info, TrendingUp, TriangleAlert, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { CardAnalytics } from "@/components/analytics/CardAnalytics";
import type { DadosTabela } from "@/components/analytics/TabelaAlternativa";
import { Button } from "@/components/ui/button";
import { formatIdadeHoras, formatNumero, useAnalytics, type AnalyticsAlerta, type EstadoFiltroAnalytics, type FiltroAnalytics } from "@/lib/analytics";
import { cn } from "@/lib/utils";

type Severidade = AnalyticsAlerta["severidade"];

const SEVERIDADE: Record<Severidade, { rotulo: string; plural: string; icone: LucideIcon; tom: string }> = {
  atencao: { rotulo: "Atenção", plural: "Atenção", icone: TriangleAlert, tom: "border-l-warning [&_[data-icone]]:text-warning" },
  info: { rotulo: "Informação", plural: "Informação", icone: Info, tom: "border-l-info [&_[data-icone]]:text-info" },
  positivo: { rotulo: "Destaque positivo", plural: "Destaques positivos", icone: TrendingUp, tom: "border-l-success [&_[data-icone]]:text-success" },
};
const ORDEM: Severidade[] = ["atencao", "info", "positivo"];

const TIPO: Record<AnalyticsAlerta["tipo"], string> = {
  estagnado: "Post estagnado",
  destaque: "Acima do esperado",
  sem_coleta: "Conta sem coleta",
  vinculo_a_confirmar: "Vínculo a confirmar",
};

const ABRIR: Record<AnalyticsAlerta["tipo"], string> = {
  estagnado: "Abrir o vídeo",
  destaque: "Abrir o vídeo",
  sem_coleta: "Ver a conta",
  vinculo_a_confirmar: "Escolher o post",
};

// Números conhecidos (camelCase da API) → rótulo e formato; o resto aparece cru.
const NUMEROS: Record<string, { rotulo: string; formatar: (n: number) => string }> = {
  idadeH: { rotulo: "idade", formatar: formatIdadeHoras },
  views: { rotulo: "views", formatar: formatNumero },
  medianaReferencia: { rotulo: "mediana da conta na mesma idade", formatar: (n) => formatNumero(Math.round(n)) },
  referencias: { rotulo: "vídeos de referência", formatar: formatNumero },
  horasSemColeta: { rotulo: "sem coleta há", formatar: formatIdadeHoras },
  candidatos: { rotulo: "candidatos", formatar: formatNumero },
};

function numeros(a: AnalyticsAlerta): { rotulo: string; valor: string }[] {
  return Object.entries(a.numeros)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => ({ rotulo: NUMEROS[k]?.rotulo ?? k, valor: NUMEROS[k] ? NUMEROS[k].formatar(v!) : formatNumero(v) }));
}

/** O "(N)" do rótulo da aba: alertas de atenção e informação do filtro atual. Nada com zero. */
export function ContadorAlertas({ filtro }: { filtro: FiltroAnalytics }) {
  const dados = useAnalytics("alertas", filtro);
  const c = dados.data?.contagem;
  const n = c ? c.atencao + c.info : 0;
  if (n === 0) return null;
  return (
    <span className="tabular-nums" title={`${n} ${n === 1 ? "alerta pede" : "alertas pedem"} atenção`}>
      {" "}
      ({n})
    </span>
  );
}

function ItemAlerta({ alerta }: { alerta: AnalyticsAlerta }) {
  const s = SEVERIDADE[alerta.severidade];
  const Icone = s.icone;
  const nums = numeros(alerta);
  return (
    <li className={cn("flex flex-col gap-1.5 rounded-lg border border-l-4 p-3 sm:flex-row sm:items-start sm:justify-between", s.tom)} data-alerta={alerta.tipo} data-severidade={alerta.severidade}>
      <div className="flex min-w-0 gap-2.5">
        <Icone data-icone="" className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <div className="min-w-0 space-y-1">
          <p className="text-sm">
            <span className="font-semibold">{s.rotulo}:</span> {TIPO[alerta.tipo]} · <span className="break-words">{alerta.alvo.rotulo}</span>
          </p>
          <p className="text-sm text-muted-foreground">{alerta.motivo}</p>
          {nums.length > 0 && (
            <dl className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs">
              {nums.map((n) => (
                <div key={n.rotulo} className="flex gap-1">
                  <dt className="text-muted-foreground">{n.rotulo}:</dt>
                  <dd className="font-medium tabular-nums">{n.valor}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </div>
      {alerta.link && (
        <Button size="sm" variant="outline" asChild className="self-start">
          <Link to={alerta.link}>
            {ABRIR[alerta.tipo]}
            <ArrowRight aria-hidden="true" />
          </Link>
        </Button>
      )}
    </li>
  );
}

export function Alertas({ estado }: { estado: EstadoFiltroAnalytics }) {
  const dados = useAnalytics("alertas", estado.filtro);
  const alertas = dados.data?.alertas ?? [];
  const contagem = dados.data?.contagem;
  const tabela: DadosTabela = {
    colunas: [
      { titulo: "Severidade" },
      { titulo: "Tipo" },
      { titulo: "Item" },
      { titulo: "Motivo", secundaria: true },
      { titulo: "Idade (h)", numerica: true, secundaria: true },
      { titulo: "Views", numerica: true, secundaria: true },
      { titulo: "Mediana de referência", numerica: true, secundaria: true },
      { titulo: "Link", secundaria: true },
    ],
    linhas: alertas.map((a) => [
      SEVERIDADE[a.severidade].rotulo,
      TIPO[a.tipo],
      a.alvo.rotulo,
      a.motivo,
      a.numeros.idadeH ?? null,
      a.numeros.views ?? null,
      a.numeros.medianaReferencia ?? null,
      a.link ?? null,
    ]),
  };

  return (
    <div className="flex flex-col gap-4">
      <CardAnalytics
        titulo="Alertas do período"
        comoLer="o que precisa de atenção agora: posts estagnados, contas sem coleta e vínculos a confirmar, além dos destaques positivos. Nada é gravado: o alerta some quando a condição deixa de valer."
        carregando={dados.isPending}
        erro={dados.error}
        vazio={alertas.length === 0 ? "Nenhum alerta: nada estagnado, nenhuma conta sem coleta e nenhum vínculo a confirmar." : null}
        tabela={tabela}
        largo
      >
        <div className="flex flex-col gap-4">
          {contagem && (
            <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm" aria-label="Resumo dos alertas">
              {ORDEM.map((s) => {
                const Icone = SEVERIDADE[s].icone;
                return (
                  <span key={s} className={cn("inline-flex items-center gap-1", SEVERIDADE[s].tom.replace(/border-l-\S+/, ""))}>
                    <Icone data-icone="" className="size-4" aria-hidden="true" />
                    {SEVERIDADE[s].plural}: <strong className="tabular-nums">{contagem[s]}</strong>
                  </span>
                );
              })}
            </p>
          )}
          {ORDEM.map((s) => {
            const lista = alertas.filter((a) => a.severidade === s);
            if (lista.length === 0) return null;
            return (
              <section key={s} aria-label={SEVERIDADE[s].plural} className="flex flex-col gap-2">
                <h4 className="text-sm font-semibold">
                  {SEVERIDADE[s].plural} ({lista.length})
                </h4>
                <ul className="flex flex-col gap-2">
                  {lista.map((a, i) => (
                    <ItemAlerta key={`${a.tipo}-${a.alvo.id ?? a.alvo.rotulo}-${i}`} alerta={a} />
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      </CardAnalytics>
    </div>
  );
}
