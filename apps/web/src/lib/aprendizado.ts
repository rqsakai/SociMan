import type {
  AprendizadoAnaliseIa,
  AprendizadoClassificacoesFiltros,
  AprendizadoEfeito,
  AprendizadoSinal,
} from "@sociman/contract";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { useFiltroUrl } from "@/components/conteudos/FiltrosConteudos";
import { api } from "./api";

export type {
  AprendizadoAnalise,
  AprendizadoAnaliseIa,
  AprendizadoClassificacao,
  AprendizadoConferencia,
  AprendizadoDecisao,
  AprendizadoEfeito,
  AprendizadoEstimativa,
  AprendizadoHipotese,
  AprendizadoItemChecklist,
  AprendizadoPreferencias,
  AprendizadoPreferenciasOut,
  AprendizadoRecomendacao,
  AprendizadoSinal,
  AprendizadoTema,
  AprendizadoTemaIn,
} from "@sociman/contract";

// Aprendizado (spec 023): a área /app/perfis/:id/aprendizado, com 5 abas. Abas, conta, medida e
// período moram na URL (os padrões somem dela). A estatística é calculada na leitura pela API; a
// SPA só formata, nunca recalcula efeito nem confiança (princípio IV). Toda escrita é do dono
// humano; para membro o servidor manda os custos `null`.

export const ABAS_APRENDIZADO = ["analise", "temas", "recomendacoes", "diagnostico", "ia"] as const;
export type AbaAprendizado = (typeof ABAS_APRENDIZADO)[number];

export const abaAprendizadoLabel: Record<AbaAprendizado, string> = {
  analise: "Por que deu certo",
  temas: "Temas",
  recomendacoes: "Recomendações",
  diagnostico: "Diagnóstico",
  ia: "Análises da IA",
};

export const MEDIDAS_APRENDIZADO = ["h1", "h24", "d7"] as const;
export type MedidaAprendizado = (typeof MEDIDAS_APRENDIZADO)[number];
export const medidaAprendizadoLabel: Record<MedidaAprendizado, string> = { h1: "Views em 1 h", h24: "Views em 24 h", d7: "Views em 7 dias" };

export const aprendizadoPath = (perfilId: string, aba?: AbaAprendizado, extra: Record<string, string> = {}) => {
  const q = new URLSearchParams({ ...(aba && aba !== "analise" ? { aba } : {}), ...extra }).toString();
  return `/app/perfis/${perfilId}/aprendizado${q ? `?${q}` : ""}`;
};

export interface FiltroAprendizado {
  contaId?: string;
  medida: MedidaAprendizado;
  de?: string;
  ate?: string;
}

export function useFiltroAprendizado() {
  const [params, set] = useFiltroUrl();
  return useMemo(() => {
    const pedida = params.get("aba") as AbaAprendizado | null;
    const aba: AbaAprendizado = pedida && ABAS_APRENDIZADO.includes(pedida) ? pedida : "analise";
    const m = params.get("medida") as MedidaAprendizado | null;
    const filtro: FiltroAprendizado = { medida: m && MEDIDAS_APRENDIZADO.includes(m) ? m : "h24" };
    const conta = params.get("conta");
    const de = params.get("de");
    const ate = params.get("ate");
    if (conta) filtro.contaId = conta;
    if (de && ate && de <= ate) {
      filtro.de = de;
      filtro.ate = ate;
    }
    return {
      aba,
      filtro,
      set,
      setAba: (a: AbaAprendizado) => {
        const naUrl = new URLSearchParams(window.location.search).get("aba") ?? "analise";
        if (a !== naUrl) set({ aba: a === "analise" ? null : a });
      },
    };
  }, [params, set]);
}
export type EstadoFiltroAprendizado = ReturnType<typeof useFiltroAprendizado>;

// ---------------------------------------------------------------------------------------------
// Rótulos

export const ESTILOS_GANCHO = ["pergunta", "revelacao", "numero_lista", "polemica", "humor", "voce_sabia", "ordem_direta", "outro"] as const;
export type EstiloGancho = (typeof ESTILOS_GANCHO)[number];
export const estiloGanchoLabel: Record<EstiloGancho, string> = {
  pergunta: "Pergunta",
  revelacao: "Revelação",
  numero_lista: "Número ou lista",
  polemica: "Polêmica",
  humor: "Humor",
  voce_sabia: "Você sabia",
  ordem_direta: "Ordem direta",
  outro: "Outro",
};

export type Confianca = AprendizadoEfeito["confianca"];
export const confiancaLabel: Record<Confianca, string> = {
  forte: "forte",
  moderada: "moderada",
  fraca: "fraca",
  indicio: "indício",
  amostra_pequena: "amostra pequena",
};
export const confiancaTom: Record<Confianca, string> = {
  forte: "bg-success/15 ring-success/50",
  moderada: "bg-info/15 ring-info/50",
  fraca: "bg-muted ring-border",
  indicio: "bg-muted ring-border",
  amostra_pequena: "bg-warning/15 ring-warning/50",
};

export const fatorLabel: Record<string, string> = {
  tema: "Tema",
  estilo_gancho: "Estilo do gancho",
  tamanho_gancho: "Tamanho do gancho",
  duracao: "Duração",
  faixa_horario: "Faixa de horário",
  dia_semana: "Dia da semana",
  canal_fonte: "Canal-fonte",
  hashtag: "Hashtag",
  modo_envio: "Modo de envio",
};
export const rotuloFator = (f: string) => fatorLabel[f] ?? f;

export const parteLabel: Record<AprendizadoEfeito["parte"], string> = {
  entrega: "Entrega (a rede mostrou?)",
  rendimento: "Rendimento (quanto rendeu quando mostrou)",
};

export const tipoRecomendacaoLabel: Record<string, string> = {
  tema_ampliar: "Ampliar tema",
  tema_cortar: "Cortar tema",
  hashtag_fixar: "Fixar hashtag",
  hashtag_evitar: "Evitar hashtag",
  padrao_gancho: "Padrão de gancho",
  padrao_duracao: "Padrão de duração",
  padrao_horario: "Janela de horário",
};

export const TIPOS_PADRAO = ["padrao_gancho", "padrao_duracao", "padrao_horario"] as const;
export type TipoPadrao = (typeof TIPOS_PADRAO)[number];

export const sinalLabel: Record<string, string> = {
  conta_nova: "Conta nova",
  muitos_no_dia: "Muitos posts no mesmo dia",
  intervalo_curto: "Intervalo curto entre posts",
  fora_da_audiencia: "Fora do horário da audiência",
  repostagem: "Possível repostagem",
  curto: "Vídeo muito curto",
  legenda_vazia: "Legenda vazia",
  hashtags_demais: "Hashtags demais",
  travada: "Distribuição travada",
};
export const rotuloSinal = (s: Pick<AprendizadoSinal, "tipo">) => sinalLabel[s.tipo] ?? s.tipo;

export const resultadoConferenciaLabel = { ok: "Conferi: está ok", problema: "Conferi: tem problema", nao_sei: "Não consegui conferir" } as const;
export type ResultadoConferencia = keyof typeof resultadoConferenciaLabel;

export const estadoAnaliseLabel: Record<AprendizadoAnaliseIa["estado"], string> = {
  pendente: "Na fila",
  processando: "Analisando",
  pronta: "Pronta",
  erro: "Erro",
};
export const analiseEmCurso = (a: Pick<AprendizadoAnaliseIa, "estado"> | null | undefined) => a?.estado === "pendente" || a?.estado === "processando";

// ---------------------------------------------------------------------------------------------
// Formatação do efeito: a API já manda na unidade de exibição (entrega em pontos percentuais,
// ex. 35.0; rendimento como fator, ex. 2.4 = "≈ 2,4×"), inclusive o intervalo e o "sem o maior".

const decimal = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4 });
const menos = (s: string) => s.replace("-", "−");

/** a referência "igual ao típico da conta" de cada parte */
export const REFERENCIA_PARTE: Record<AprendizadoEfeito["parte"], number> = { entrega: 0, rendimento: 1 };

export function formatEfeito(parte: AprendizadoEfeito["parte"], v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  if (parte === "entrega") return `${v > 0 ? "+" : ""}${menos(decimal.format(v))} p.p.`;
  return `≈ ${decimal.format(v)}×`;
}

export function fraseEfeito(e: Pick<AprendizadoEfeito, "parte" | "efeito">): string {
  if (e.efeito === null || e.efeito === undefined) return "sem efeito calculado";
  return e.parte === "entrega" ? `${formatEfeito("entrega", e.efeito)} de chance de sair do zero` : `${formatEfeito("rendimento", e.efeito)} o típico da conta`;
}

export const formatIntervalo = (e: Pick<AprendizadoEfeito, "parte" | "intervalo">) =>
  e.intervalo ? `${formatEfeito(e.parte, e.intervalo[0])} a ${formatEfeito(e.parte, e.intervalo[1])}` : "—";

export const formatUsd = (v: number | null | undefined) => (v === null || v === undefined ? "—" : usd.format(v));

// ---------------------------------------------------------------------------------------------
// Queries. Tudo sob ["aprendizado", perfilId, …]: qualquer escrita invalida o perfil inteiro.

export const aprendizadoKey = (perfilId: string, ...resto: unknown[]) => ["aprendizado", perfilId, ...resto] as const;

const paraFiltro = (f: FiltroAprendizado) => ({
  medida: f.medida,
  ...(f.contaId ? { contaId: f.contaId } : {}),
  ...(f.de && f.ate ? { de: f.de, ate: f.ate } : {}),
});

export function useTemas(perfilId: string, arquivados = false) {
  return useQuery({
    queryKey: aprendizadoKey(perfilId, "temas", arquivados),
    queryFn: () => api.aprendizado.temas.list(perfilId, { arquivados }),
    enabled: Boolean(perfilId),
  });
}

export function useTemaVersions(temaId: string | null) {
  return useQuery({
    queryKey: ["aprendizado-tema-versions", temaId],
    queryFn: () => api.aprendizado.temas.versions(temaId!),
    enabled: Boolean(temaId),
  });
}

export function useClassificacoes(perfilId: string, filtros: AprendizadoClassificacoesFiltros) {
  return useQuery({
    queryKey: aprendizadoKey(perfilId, "classificacoes", filtros),
    queryFn: () => api.aprendizado.classificacoes.list(perfilId, filtros),
    enabled: Boolean(perfilId),
    placeholderData: keepPreviousData,
  });
}

export function useClassificacaoVersions(videoId: string | null) {
  return useQuery({
    queryKey: ["aprendizado-classificacao-versions", videoId],
    queryFn: () => api.aprendizado.classificacoes.versions(videoId!),
    enabled: Boolean(videoId),
  });
}

export function useAnaliseAprendizado(perfilId: string, f: FiltroAprendizado) {
  const q = paraFiltro(f);
  return useQuery({
    queryKey: aprendizadoKey(perfilId, "analise", q),
    queryFn: () => api.aprendizado.analise(perfilId, q),
    enabled: Boolean(perfilId),
    placeholderData: keepPreviousData,
  });
}

export function useRecomendacoes(perfilId: string, f: FiltroAprendizado) {
  const q = { medida: f.medida, ...(f.contaId ? { contaId: f.contaId } : {}) };
  return useQuery({
    queryKey: aprendizadoKey(perfilId, "recomendacoes", q),
    queryFn: () => api.aprendizado.recomendacoes(perfilId, q),
    enabled: Boolean(perfilId),
    placeholderData: keepPreviousData,
  });
}

export function usePreferencias(perfilId: string, contaId?: string) {
  return useQuery({
    queryKey: aprendizadoKey(perfilId, "preferencias", contaId ?? null),
    queryFn: () => api.aprendizado.preferencias.get(perfilId, contaId),
    enabled: Boolean(perfilId),
  });
}

export function usePreferenciasVersions(perfilId: string, contaId?: string) {
  return useQuery({
    queryKey: aprendizadoKey(perfilId, "preferencias-versions", contaId ?? null),
    queryFn: () => api.aprendizado.preferencias.versions(perfilId, contaId),
    enabled: Boolean(perfilId),
  });
}

export function useAnalisesIa(perfilId: string) {
  return useQuery({
    queryKey: aprendizadoKey(perfilId, "analises"),
    queryFn: () => api.aprendizado.analises.list(perfilId),
    enabled: Boolean(perfilId),
    // polling de 5 s só enquanto alguma análise está na fila ou em curso (R12)
    refetchInterval: (q) => (q.state.data?.items.some(analiseEmCurso) ? 5_000 : false),
  });
}

export function useDiagnostico(perfilId: string, f: FiltroAprendizado) {
  const q = { ...(f.contaId ? { contaId: f.contaId } : {}), ...(f.de && f.ate ? { de: f.de, ate: f.ate } : {}) };
  return useQuery({
    queryKey: aprendizadoKey(perfilId, "diagnostico", q),
    queryFn: () => api.aprendizado.diagnostico(perfilId, q),
    enabled: Boolean(perfilId),
    placeholderData: keepPreviousData,
  });
}

export function usePostDiagnostico(videoId: string, enabled = true) {
  return useQuery({
    queryKey: ["aprendizado-post-diagnostico", videoId],
    queryFn: () => api.aprendizado.postDiagnostico(videoId),
    enabled: Boolean(videoId) && enabled,
  });
}

export function useInvalidarAprendizado() {
  const qc = useQueryClient();
  return (perfilId: string) =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["aprendizado", perfilId] }),
      qc.invalidateQueries({ queryKey: ["aprendizado-tema-versions"] }),
      qc.invalidateQueries({ queryKey: ["aprendizado-classificacao-versions"] }),
      qc.invalidateQueries({ queryKey: ["aprendizado-post-diagnostico"] }),
    ]);
}
