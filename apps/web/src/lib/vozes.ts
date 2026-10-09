import type { GeracaoStatus, Voz, VozFilters, VozOrigem, VozStatus } from "@sociman/contract";
import { useInfiniteQuery, useQuery, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { buscarTodas, ordenarPorPerfil } from "./estudio";

export type { Voz, VozAnalise, VozOrigem, VozResumo, VozStatus } from "@sociman/contract";

// Vozes do perfil (spec 025, US2/US3): rótulos pt-BR, chaves e hooks. Uma voz nasce em rascunho; a
// gravação (com consentimento) ou a descrição sintética vira até 3 candidatos de referência (geração
// `voz.gravacao`/`voz.design` da 021); a escolhida aprova a voz, que o SociMan envia ao shop-tts
// (sincronização). "Testar" é a geração `voz.teste`. Polling de 2 s enquanto algo anda sozinho.

export const statusVozLabel: Record<VozStatus, string> = {
  rascunho: "Rascunho",
  gerando: "Gerando",
  revisao: "Em revisão",
  aprovada: "Aprovada",
};

export const statusVozTone: Record<VozStatus, string> = {
  rascunho: "bg-secondary text-secondary-foreground",
  gerando: "bg-info text-info-foreground",
  revisao: "bg-warning text-warning-foreground",
  aprovada: "bg-success text-success-foreground",
};

export const origemVozLabel: Record<VozOrigem, string> = { gravacao: "Gravação", sintetica: "Sintética" };

export const sincronizacaoLabel: Record<Voz["sincronizacao"], string> = {
  ok: "Sincronizada",
  pendente: "Não sincronizada",
  removendo: "Removendo do serviço de voz",
  nao_se_aplica: "Sem referência",
};

export const STATUS_VOZ: VozStatus[] = ["rascunho", "gerando", "revisao", "aprovada"];
export const LIM_VOZ = { nome: 80, tom: 120, descricao: 1000, texto: 500 } as const;
export const AUDIO_ACCEPT = "audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/x-m4a,audio/ogg,.wav,.mp3,.m4a,.ogg";
export const AUDIO_MAX_BYTES = 25 * 1024 * 1024;

// Rótulos do histórico (snapshot de `entity_versions` da voz).
export const vozFieldLabel: Record<string, string> = {
  name: "Nome",
  origem: "Origem",
  descricao: "Descrição (inglês)",
  tom: "Tom",
  gravacao_audio_id: "Gravação",
  ref_audio_id: "Referência",
  ref_texto: "Transcrição da referência",
  consentimento: "Consentimento",
  status: "Estado",
  archived: "Arquivada",
};

export function formatVozValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (field === "status" && typeof value === "string") return statusVozLabel[value as VozStatus] ?? value;
  if (field === "origem" && typeof value === "string") return origemVozLabel[value as VozOrigem] ?? value;
  if (field === "consentimento" && typeof value === "object") return consentimentoTexto(value);
  if (field.endsWith("_id") && typeof value === "string") return `${value.slice(0, 8)}…`;
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}

// O consentimento no snapshot: `{nome, data, observacao, revogado_em…}` (sem expor a prova).
export function consentimentoTexto(value: object): string {
  const c = value as { nome?: unknown; data?: unknown; revogado_em?: unknown };
  const partes = [typeof c.nome === "string" ? c.nome : null, typeof c.data === "string" ? c.data.split("-").reverse().join("/") : null].filter(Boolean);
  return `${partes.join(", ") || "Registrado"}${c.revogado_em ? " (revogado)" : ""}`;
}

// ---------------------------------------------------------------------------------------------
// Chaves e hooks

export const vozesKey = (perfilId: string) => ["vozes", perfilId] as const;
export const vozesListKey = (perfilId: string, filtros: VozFiltros) => [...vozesKey(perfilId), "lista", filtros] as const;
export const vozKey = (id: string) => ["voz", id] as const;
export const vozVersoesKey = (id: string) => ["voz-versoes", id] as const;

export interface VozFiltros {
  q?: string;
  status?: VozStatus;
  arquivadas?: boolean;
}

const ANDANDO: ReadonlySet<GeracaoStatus> = new Set(["na_fila", "rodando"]);
export const POLL_MS = 2000;

// A voz muda sozinha: gerando, teste em andamento ou sincronização com o shop-tts.
export function vozMudando(v: Voz): boolean {
  return (
    v.status === "gerando" ||
    (v.geracaoAberta !== null && ANDANDO.has(v.geracaoAberta.status)) ||
    (v.ultimoTeste !== null && ANDANDO.has(v.ultimoTeste.status)) ||
    v.sincronizacao === "pendente" ||
    v.sincronizacao === "removendo"
  );
}

export function useVozes(perfilId: string, filtros: VozFiltros) {
  const query: VozFilters = {
    q: filtros.q || undefined,
    status: filtros.status ? [filtros.status] : undefined,
    arquivadas: filtros.arquivadas ?? false,
    limite: 50,
  };
  return useInfiniteQuery({
    queryKey: vozesListKey(perfilId, filtros),
    queryFn: ({ pageParam }) => api.vozes.listar(perfilId, { ...query, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.proximo ?? undefined,
    enabled: perfilId !== "",
  });
}

// Spec 029: a lista da agência (todos os perfis e sem perfil), com o filtro de perfil base.
export function useVozesAgencia(perfilFiltro: string, filtros: VozFiltros) {
  return useInfiniteQuery({
    queryKey: ["vozes", "agencia", perfilFiltro, filtros] as const,
    queryFn: ({ pageParam }) =>
      api.vozes.listarAgencia({
        perfilId: perfilFiltro === "todos" ? undefined : perfilFiltro,
        q: filtros.q || undefined,
        status: filtros.status ? [filtros.status] : undefined,
        arquivadas: filtros.arquivadas ?? false,
        limite: 50,
        cursor: pageParam,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.proximo ?? undefined,
  });
}

// As aprovadas e não arquivadas da agência (seletor "Voz padrão" do avatar; 029: de qualquer perfil base).
// Todas as páginas até o teto, as do perfil base do avatar primeiro.
export function useVozesAprovadas(perfilBase?: string | null) {
  const q = useQuery({
    queryKey: ["vozes", "agencia", "aprovadas"],
    queryFn: () =>
      buscarTodas(
        (cursor) => api.vozes.listarAgencia({ status: ["aprovada"], arquivadas: false, limite: 50, cursor }),
        (p) => p.itens,
        (p) => p.proximo,
      ),
  });
  const itens = q.data ? ordenarPorPerfil(q.data.itens, perfilBase, (v) => v.name) : undefined;
  return { ...q, itens, truncado: q.data?.truncado ?? false };
}

export function useVoz(id: string) {
  return useQuery({
    queryKey: vozKey(id),
    queryFn: () => api.vozes.detalhe(id),
    enabled: id !== "",
    refetchInterval: (q) => (q.state.data && vozMudando(q.state.data) ? POLL_MS : false),
  });
}

export function useVozVersoes(id: string) {
  return useQuery({ queryKey: vozVersoesKey(id), queryFn: () => api.vozes.versoes(id), enabled: id !== "" });
}

export async function invalidarVoz(qc: QueryClient, id: string, perfilId?: string) {
  await Promise.all([
    qc.invalidateQueries({ queryKey: vozKey(id) }),
    qc.invalidateQueries({ queryKey: vozVersoesKey(id) }),
    qc.invalidateQueries({ queryKey: ["vozes"] }),
  ]);
}

// Métricas da análise da gravação, formatadas.
const num1 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
export const fmtNum = (v: number | null | undefined, sufixo = "") => (v === null || v === undefined ? "—" : `${num1.format(v)}${sufixo}`);
