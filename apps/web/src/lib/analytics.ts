import type {
  AnalyticsFiltros,
  AnalyticsPublico as ContractPublico,
  AnalyticsPublicoAtividade,
  AnalyticsPublicoAtividadeConta,
  AnalyticsPublicoConta,
  AnalyticsPublicoContaRef,
  AnalyticsPublicoDistribuicao,
  AnalyticsQuandoPostar,
} from "@sociman/contract";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api } from "./api";
import { useFiltroUrl } from "./filtros";
import { addDays, localDateKey, parseDateKey } from "./tz";

// Analytics de decisão (spec 019): filtros globais na URL e as queries das 8 abas. Tudo é leitura.
// Padrões somem da URL (contrato §SPA): aba "visao-geral", últimos 7 dias (hoje − 6 … hoje, fuso da
// casa) e medida "h24". Os formatadores vêm de lib/metricas.

export type {
  AnalyticsAlerta,
  AnalyticsAlertas,
  AnalyticsAmostra,
  AnalyticsCelulaMapa,
  AnalyticsContas,
  AnalyticsContexto,
  AnalyticsCurva,
  AnalyticsCurvas,
  AnalyticsDispersao,
  AnalyticsDistribuicaoConta,
  AnalyticsEtapaFunil,
  AnalyticsFiltros,
  AnalyticsFunil,
  AnalyticsIndicador,
  AnalyticsInsight,
  AnalyticsLinhaRanking,
  AnalyticsMedida,
  AnalyticsMercado,
  AnalyticsOportunidade,
  AnalyticsOQueFunciona,
  AnalyticsPostResumo,
  AnalyticsQuandoPostar,
  AnalyticsRadarConta,
  AnalyticsVisaoGeral,
} from "@sociman/contract";

export {
  formatCompacto,
  formatDuracaoS,
  formatEngajamento,
  formatIdadeHoras,
  formatNumero,
  formatVelocidade,
  linkDoVideo,
  truncar,
} from "./metricas";

// ---------------------------------------------------------------------------------------------
// Abas, medidas e períodos

export const ABAS_ANALYTICS = ["visao-geral", "quando-postar", "publico", "o-que-funciona", "curvas", "contas", "funil", "mercado", "alertas"] as const;
export type AbaAnalytics = (typeof ABAS_ANALYTICS)[number];

export const abaLabel: Record<AbaAnalytics, string> = {
  "visao-geral": "Visão geral",
  "quando-postar": "Quando postar",
  publico: "Público",
  "o-que-funciona": "O que funciona",
  curvas: "Curvas",
  contas: "Contas",
  funil: "Funil",
  mercado: "Fontes", // spec 026: o YouTube de origem; "Mercado de produtos" é o TikTok Shop
  alertas: "Alertas",
};

export const MEDIDAS = ["h1", "h24", "d7"] as const;
export type Medida = (typeof MEDIDAS)[number];
export const medidaLabel: Record<Medida, string> = { h1: "Views em 1 h", h24: "Views em 24 h", d7: "Views em 7 dias" };

export const REDES = ["tiktok", "youtube", "instagram", "kwai", "facebook", "x"] as const;

// Atalhos de período: a URL guarda só `de`/`ate` (contrato); o atalho ativo é reconhecido quando
// `ate` é hoje e a duração bate. "24 h" é ontem e hoje (a API trabalha com dias); "Tudo" é o
// máximo que a API aceita (400 dias).
export const MAX_DIAS = 400;
export const ATALHOS = [
  { id: "24h", label: "24 h", dias: 2 },
  { id: "7d", label: "7 d", dias: 7 },
  { id: "14d", label: "14 d", dias: 14 },
  { id: "30d", label: "30 d", dias: 30 },
  { id: "90d", label: "90 d", dias: 90 },
  { id: "tudo", label: "Tudo", dias: MAX_DIAS },
] as const;
export type AtalhoPeriodo = (typeof ATALHOS)[number]["id"] | "personalizado";
const PADRAO_DIAS = 7;

export function diasEntre(de: string, ate: string): number {
  const a = parseDateKey(de);
  const b = parseDateKey(ate);
  return Math.round((Date.UTC(b.year, b.month - 1, b.day) - Date.UTC(a.year, a.month - 1, a.day)) / 86_400_000) + 1;
}

// ---------------------------------------------------------------------------------------------
// Filtro global

export interface FiltroAnalytics {
  de: string;
  ate: string;
  perfilId?: string;
  contaId?: string;
  rede?: string;
  medida: Medida;
}

export interface EstadoFiltroAnalytics {
  aba: AbaAnalytics;
  filtro: FiltroAnalytics;
  atalho: AtalhoPeriodo;
  /** `de` > `ate` ou mais de 400 dias: o período da URL foi ignorado (vale o padrão) */
  periodoInvalido: boolean;
  setAba: (aba: AbaAnalytics) => void;
  setAtalho: (id: Exclude<AtalhoPeriodo, "personalizado">) => void;
  setPeriodo: (de: string, ate: string) => void;
  /** um patch dos parâmetros (perfil, conta, rede, medida…); null apaga */
  set: (patch: Record<string, string | null>, opts?: { replace?: boolean }) => void;
  /** dobra o período (até 400 dias), para o "Ampliar período" dos estados vazios */
  ampliarPeriodo: () => void;
}

export function useFiltroAnalytics(): EstadoFiltroAnalytics {
  const [params, set] = useFiltroUrl();
  const hoje = localDateKey(new Date());

  return useMemo(() => {
    const pedida = params.get("aba") as AbaAnalytics | null;
    const aba: AbaAnalytics = pedida && ABAS_ANALYTICS.includes(pedida) ? pedida : "visao-geral";
    const medidaUrl = params.get("medida") as Medida | null;
    const medida: Medida = medidaUrl && MEDIDAS.includes(medidaUrl) ? medidaUrl : "h24";

    const padraoDe = addDays(hoje, -(PADRAO_DIAS - 1));
    const deUrl = params.get("de");
    const ateUrl = params.get("ate");
    let de = deUrl ?? (ateUrl ? addDays(ateUrl, -(PADRAO_DIAS - 1)) : padraoDe);
    let ate = ateUrl ?? (deUrl && deUrl > hoje ? deUrl : hoje);
    const periodoInvalido = de > ate || diasEntre(de, ate) > MAX_DIAS;
    if (periodoInvalido) {
      de = padraoDe;
      ate = hoje;
    }
    const n = diasEntre(de, ate);
    const atalho: AtalhoPeriodo = ate === hoje ? (ATALHOS.find((a) => a.dias === n)?.id ?? "personalizado") : "personalizado";

    const filtro: FiltroAnalytics = { de, ate, medida };
    const perfil = params.get("perfil");
    const conta = params.get("conta");
    const rede = params.get("rede");
    if (perfil) filtro.perfilId = perfil;
    if (conta) filtro.contaId = conta;
    if (rede && (REDES as readonly string[]).includes(rede)) filtro.rede = rede;

    const setPeriodo = (novoDe: string, novoAte: string) => {
      const padrao = novoAte === hoje && diasEntre(novoDe, novoAte) === PADRAO_DIAS;
      set({ de: padrao ? null : novoDe, ate: padrao ? null : novoAte });
    };

    return {
      aba,
      filtro,
      atalho,
      periodoInvalido,
      set,
      // o Radix chama onValueChange no mousedown e de novo no foco, antes do novo render: a guarda
      // lê a URL do momento (não a do render) para a mesma aba não entrar duas vezes no histórico
      setAba: (a) => {
        const naUrl = new URLSearchParams(window.location.search).get("aba") ?? "visao-geral";
        if (a !== naUrl) set({ aba: a === "visao-geral" ? null : a });
      },
      setAtalho: (id) => {
        const dias = ATALHOS.find((a) => a.id === id)!.dias;
        setPeriodo(addDays(hoje, -(dias - 1)), hoje);
      },
      setPeriodo,
      ampliarPeriodo: () => setPeriodo(addDays(ate, -(Math.min(n * 2, MAX_DIAS) - 1)), ate),
    };
  }, [params, set, hoje]);
}

// ---------------------------------------------------------------------------------------------
// Queries: uma por aba, chave ['analytics', aba, filtro]. O dado anterior fica na tela enquanto
// o novo filtro carrega (sem piscar o card).

export const analyticsKey = (aba: AbaAnalytics, filtro: object) => ["analytics", aba, filtro] as const;

export function paraQuery(f: FiltroAnalytics): AnalyticsFiltros {
  const q: AnalyticsFiltros = { de: f.de, ate: f.ate, medida: f.medida };
  if (f.perfilId) q.perfilId = f.perfilId;
  if (f.contaId) q.contaId = f.contaId;
  if (f.rede) q.rede = f.rede as AnalyticsFiltros["rede"];
  return q;
}

const BUSCAR = {
  "visao-geral": api.analytics.visaoGeral,
  "quando-postar": api.analytics.quandoPostar,
  publico: api.analytics.publico,
  "o-que-funciona": api.analytics.oQueFunciona,
  curvas: api.analytics.curvas,
  contas: api.analytics.contas,
  funil: api.analytics.funil,
  mercado: api.analytics.mercado,
  alertas: api.analytics.alertas,
} satisfies Record<AbaAnalytics, (q: AnalyticsFiltros) => Promise<unknown>>;

type Resposta = { [A in AbaAnalytics]: Awaited<ReturnType<(typeof BUSCAR)[A]>> };

export function useAnalytics<A extends AbaAnalytics>(aba: A, filtro: FiltroAnalytics, extra: { patamar?: number; mostrarCortados?: boolean } = {}) {
  const query = {
    ...paraQuery(filtro),
    ...(aba === "funil" && extra.patamar ? { patamar: extra.patamar } : {}),
    // spec 023: no Mercado, os vídeos de tema cortado só voltam com o filtro ligado
    ...(aba === "mercado" && extra.mostrarCortados ? { mostrarCortados: true } : {}),
  };
  return useQuery({
    queryKey: analyticsKey(aba, query),
    queryFn: () => (BUSCAR[aba] as (q: AnalyticsFiltros) => Promise<Resposta[A]>)(query),
    placeholderData: keepPreviousData,
  });
}

// ---------------------------------------------------------------------------------------------
// Público (spec 022): a aba "publico" e o 3º mapa de "Quando postar", com dados importados do
// TikTok Studio. A forma segue contracts/http-api.md da 022 (PublicoOut).

export type AnalyticsPublico = ContractPublico;
export type PublicoConta = AnalyticsPublicoConta;
export type PublicoContaRef = AnalyticsPublicoContaRef;
export type PublicoDistribuicao = AnalyticsPublicoDistribuicao;
export type PublicoAtividade = AnalyticsPublicoAtividade;
export type AtividadeSeguidoresConta = AnalyticsPublicoAtividadeConta;
export type MotivoPublico = NonNullable<PublicoConta["motivos"]["genero"]>;

// chave estável de uma conta da resposta (a série; a anônima pode vir sem ela)
export const chaveConta = (c: PublicoContaRef) => c.serieId ?? c.rotulo;

// `QuandoPostarOut.atividadeSeguidores` (aditivo na 022)
export const atividadeSeguidoresDe = (d: AnalyticsQuandoPostar | undefined): AtividadeSeguidoresConta[] => d?.atividadeSeguidores?.contas ?? [];

export const MIN_DIAS_CELULA = 2;
export const FONTE_STUDIO = "importado do TikTok Studio";
export const NOTA_HORAS_TIKTOK = "Horas conforme a TikTok (o arquivo não diz o fuso) · fonte: TikTok Studio.";

export const motivoPublicoLabel: Record<MotivoPublico, string> = {
  sem_importacao: "Nenhuma importação de público ainda.",
  veio_vazia: "Ainda sem dados de público: a TikTok libera esses dados quando a conta tem mais seguidores (cerca de 100). Reimporte quando a conta crescer.",
  sem_dado_no_periodo: "Sem dado no período.",
};

export const usePublico = (filtro: FiltroAnalytics) => useAnalytics("publico", filtro);
