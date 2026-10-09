import {
  ApiError,
  type IaAlvo,
  type IaAplicacao,
  type IaChamada,
  type IaChamadaFilters,
  type IaDesfecho,
  type IaValor,
  type TipoCampo,
  type TipoCampoId,
} from "@sociman/contract";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { api } from "./api";
import { errorText } from "./perfis";

export type {
  IaAlvo,
  IaAplicacao,
  IaChamada,
  IaChamadaFilters,
  IaDesfecho,
  IaLimites,
  IaRegras,
  IaResumo,
  IaValor,
  TipoCampo,
  TipoCampoId,
} from "@sociman/contract";

// Assistente de IA (spec 008): queries, rótulos, o tipo do `onSave` que cada tela implementa, a
// sessão do painel (sobrevive à remontagem do formulário) e o `useFormRebase` (R11, risco R-9).
// Gerar nunca salva; só o clique humano em Aplicar chama o `onSave` da tela.

export const iaTiposKey = ["ia-tipos"] as const;
export const iaTipoVersionsKey = (tipo: string) => ["ia-tipo-versions", tipo] as const;
export const iaChamadasKey = (filters: object) => ["ia-chamadas", filters] as const;
export const iaResumoKey = (mes: string) => ["ia-resumo", mes] as const;

export const iaTiposQuery = {
  queryKey: iaTiposKey,
  queryFn: () => api.ia.tipos(),
  staleTime: 5 * 60_000,
};

export function useIaTipo(tipo: TipoCampoId): TipoCampo | undefined {
  const tipos = useQuery(iaTiposQuery);
  return tipos.data?.items.find((t) => t.id === tipo);
}

export const desfechoLabel: Record<IaDesfecho, string> = {
  sem_acao: "Sem ação",
  aplicada: "Aplicada",
  editada: "Editada",
  descartada: "Descartada",
  erro: "Erro",
};

export const desfechoTone: Record<IaDesfecho, string> = {
  sem_acao: "bg-secondary text-secondary-foreground",
  aplicada: "bg-success text-success-foreground",
  editada: "bg-info text-info-foreground",
  descartada: "bg-muted text-muted-foreground",
  erro: "bg-destructive text-destructive-foreground",
};

export const idiomaLabel: Record<TipoCampo["idioma"], string> = { en: "Inglês", perfil: "Idioma do perfil" };

export const formatoLabel: Record<TipoCampo["formato"], string> = {
  texto: "Texto",
  lista: "Lista",
  sugestoes: "Sugestões com seleção",
  textos_postagem: "Título, descrição e hashtags",
  // spec 017
  guia: "Guia de comunicação",
  variacoes: "3 variações de título, descrição e hashtags",
  // spec 010
  campos_cena: "Ação, câmera, estilo e áudio da cena",
  // spec 023
  taxonomia: "Temas do perfil",
  classificacao: "Tema e estilo do gancho de um post",
  analise: "Hipóteses sobre os melhores posts",
  // spec 012
  ficha_produto: "Ficha técnica do produto",
  // spec 025
  identidade: "Checagem de identidade do kit",
};

export const IA_AUSENTE_TEXTO = "IA não configurada: falta a chave do Claude (ANTHROPIC_API_KEY no .env). O campo continua editável à mão.";
export const INSTRUCAO_MAX = 1000;
export const REGRAS_MAX = 8000;

// Os três campos da postagem juntos (formato `textos_postagem`).
export interface TextosPostagem {
  titulo: string;
  descricao: string;
  hashtags: string[];
}

export type IaValorCampo = string | string[] | TextosPostagem;

// Salva só aquele campo pelo save normal da tela, com o `ia` no corpo (FR-006). Rejeita com o erro da
// API (409, 400…): o painel mostra o erro e mantém a proposta; a tela não mexe no formulário.
export type IaOnSave<V extends IaValorCampo = string> = (valor: V, ia: IaAplicacao[]) => Promise<void>;

export function valorAtual(formato: TipoCampo["formato"] | undefined, value: IaValorCampo): IaValor {
  if (typeof value === "string") return { texto: value };
  if (Array.isArray(value)) return { itens: value };
  if (formato === "textos_postagem" || !formato) return { titulo: value.titulo, descricao: value.descricao, hashtags: value.hashtags };
  return {};
}

// UUID v4 sem `crypto.randomUUID` (que exige contexto seguro; o getRandomValues não).
export function novoSessaoId(): string {
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6]! & 0x0f) | 0x40;
  b[8] = (b[8]! & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

// Descartar ao fechar é melhor esforço: sem isso, o desfecho só fica `sem_acao`.
export function descartarChamadas(ids: string[]) {
  for (const id of ids) void api.ia.descartar(id).catch(() => undefined);
}

export function iaErroTexto(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === "ia_timeout") return "A IA demorou demais. Tente de novo.";
    if (err.code === "claude_unconfigured") return IA_AUSENTE_TEXTO;
    if (err.code === "ia_recusa") return "A IA recusou o pedido. Mude a instrução e tente de novo.";
    if (err.code === "ia_invalida") return "A IA devolveu uma resposta fora do formato. Tente de novo.";
  }
  return errorText(err);
}

export const iaErroRepetivel = (err: unknown) =>
  err instanceof ApiError && ["ia_timeout", "ia_invalida", "claude_error", "internal_error"].includes(err.code);

const usd = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
export function custoText(valor: number | null | undefined): string {
  if (valor === null || valor === undefined) return "—";
  return `≈ US$ ${usd.format(valor)}`;
}

// "Sem diferenciar maiúsculas e sem espaço nas pontas" (FR-012).
export const chaveItem = (s: string) => s.trim().toLocaleLowerCase("pt-BR");

// ---------------------------------------------------------------------------------------------
// Sessão do painel: fica fora do React para sobreviver à remontagem do formulário pela `key` com a
// versão (PerfilDetalhe, MarcaTab, DestinoPanel). Some ao fechar o painel; se a tela sai de cena
// (navegação), `aoAbandonar` roda (descarta as chamadas sem aplicação) e a sessão some também.

const sessoes = new Map<string, unknown>();
const ouvintes = new Map<string, Set<() => void>>();
const montados = new Map<string, number>();

function notificar(key: string) {
  for (const fn of ouvintes.get(key) ?? []) fn();
}

export function useSessaoIa<S>(key: string, inicial: () => S, aoAbandonar?: (s: S) => void) {
  if (!sessoes.has(key)) sessoes.set(key, inicial());
  const abandonar = useRef(aoAbandonar);
  abandonar.current = aoAbandonar;

  const subscribe = useCallback(
    (fn: () => void) => {
      const set = ouvintes.get(key) ?? new Set();
      set.add(fn);
      ouvintes.set(key, set);
      return () => set.delete(fn);
    },
    [key],
  );
  const estado = useSyncExternalStore(subscribe, () => sessoes.get(key) as S);

  useEffect(() => {
    montados.set(key, (montados.get(key) ?? 0) + 1);
    return () => {
      montados.set(key, (montados.get(key) ?? 1) - 1);
      // A remontagem pela `key` monta a instância nova no mesmo commit; só a saída de verdade
      // chega aqui com zero.
      setTimeout(() => {
        if ((montados.get(key) ?? 0) > 0 || !sessoes.has(key)) return;
        abandonar.current?.(sessoes.get(key) as S);
        sessoes.delete(key);
      }, 0);
    };
  }, [key]);

  const atualizar = useCallback(
    (up: (s: S) => S) => {
      sessoes.set(key, up((sessoes.get(key) as S | undefined) ?? inicial()));
      notificar(key);
    },
    // `inicial` só vale quando a sessão ainda não existe.
    [key],
  );
  return [estado, atualizar] as const;
}

// ---------------------------------------------------------------------------------------------
// useFormRebase (R11, risco R-9): o Aplicar salva só um campo e a versão muda; as telas que remontam
// o formulário pela `key` com a versão perderiam o que foi digitado nos outros campos. A tela guarda
// os campos sujos antes do `onSave` e, na montagem seguinte, os lê de volta por cima dos dados novos.

const rebases = new Map<string, unknown>();

export function useFormRebase<T>(key: string) {
  const [retomado] = useState(() => rebases.get(key) as T | undefined);
  useEffect(() => {
    rebases.delete(key);
  }, [key]);
  return {
    // O que estava sujo antes do último Aplicar (só na montagem logo depois dele).
    retomado,
    guardar: (valores: T) => rebases.set(key, valores),
    esquecer: () => rebases.delete(key),
  };
}

// Guarda os sujos, roda o save e, se ele falhar, esquece o que guardou (o formulário fica como estava).
export async function comRebase<T>(rebase: { guardar: (v: T) => void; esquecer: () => void }, sujos: T | null, save: () => Promise<void>) {
  if (sujos !== null) rebase.guardar(sujos);
  try {
    await save();
  } catch (err) {
    rebase.esquecer();
    throw err;
  }
}
