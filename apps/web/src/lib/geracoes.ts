import type {
  AudioPerfil,
  CandidatoGeracao,
  GeracaoAlvo as GeracaoAlvoContrato,
  GeracaoDetalhe,
  GeracaoEscolhida as GeracaoEscolhidaContrato,
  GeracaoFilters,
  GeracaoInRequest,
  GeracaoResumo as GeracaoResumoContrato,
  GeracaoStatus as GeracaoStatusContrato,
  ImagemCandidato as ImagemCandidatoContrato,
} from "@sociman/contract";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { assetKey, assetVersionsKey } from "./assets";
import { uploadMultipart } from "./marcaApi";
import { produtoKey, produtoVersoesKey } from "./produtos";
import { vozKey, vozVersoesKey } from "./vozes";

// Geração local (spec 021): pedidos ao ComfyUI e ao shop-tts que a API enfileira e o gerador roda.
// A tela pede, acompanha (polling de 2 s enquanto não termina), compara as opções e escolhe uma;
// o resultado vai para o alvo (na 021, o arquivo novo do cenário).

export type Geracao = GeracaoDetalhe;
export type GeracaoResumo = GeracaoResumoContrato;
export type GeracaoEscolhida = GeracaoEscolhidaContrato;
export type GeracaoIn = GeracaoInRequest;
export type GeracaoStatus = GeracaoStatusContrato;
export type GeracaoAlvo = GeracaoAlvoContrato;
export type Candidato = CandidatoGeracao;
export type ImagemCandidato = ImagemCandidatoContrato;
export type Audio = AudioPerfil;
export type GeracaoListaQuery = GeracaoFilters;

export const geracoesApi = {
  ...api.geracoes,
  // 029: pela rota da agência (`POST /api/audios`), com o perfil base opcional
  enviarAudio: (perfilId: string | null, arquivo: File, onProgress: (fraction: number) => void = () => {}, signal?: AbortSignal) =>
    uploadMultipart<Audio>(
      "/api/audios",
      () => {
        const form = new FormData();
        if (perfilId) form.append("perfilId", perfilId);
        form.append("arquivo", arquivo);
        return form;
      },
      onProgress,
      signal,
    ),
};

// ---------------------------------------------------------------------------------------------
// Estados

export const statusGeracaoLabel: Record<GeracaoStatus, string> = {
  na_fila: "Na fila",
  rodando: "Gerando",
  revisao: "Em revisão",
  escolhido: "Escolhida",
  descartada: "Descartada",
  cancelada: "Cancelada",
  entregue: "Entregue",
  falhou: "Falhou",
};

export const statusGeracaoTone: Record<GeracaoStatus, string> = {
  na_fila: "bg-secondary text-secondary-foreground",
  rodando: "bg-info text-info-foreground",
  revisao: "bg-warning text-warning-foreground",
  escolhido: "bg-success text-success-foreground",
  descartada: "bg-dark text-dark-foreground",
  cancelada: "bg-dark text-dark-foreground",
  entregue: "bg-success text-success-foreground",
  falhou: "bg-destructive text-destructive-foreground",
};

// Finais para o polling (o `falhou` também para: só volta com "Tentar de novo").
const PARADOS: ReadonlySet<GeracaoStatus> = new Set(["escolhido", "descartada", "cancelada", "entregue", "falhou"]);
export const geracaoParada = (s: GeracaoStatus) => PARADOS.has(s);
export const podeCancelar = (s: GeracaoStatus) => s === "na_fila" || s === "rodando" || s === "revisao" || s === "falhou";
export const emAndamento = (s: GeracaoStatus) => s === "na_fila" || s === "rodando";

export const POLL_MS = 2000;

// Rótulos do histórico (snapshot de `entity_versions` da geração).
export const geracaoFieldLabel: Record<string, string> = {
  status: "Estado",
  escolhido_id: "Opção escolhida",
  error_code: "Código do erro",
  error_message: "Erro",
};

export function formatGeracaoValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (field === "status" && typeof value === "string") return statusGeracaoLabel[value as GeracaoStatus] ?? value;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

const dataHora = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });
export const fmtDataHora = (iso: string) => dataHora.format(new Date(iso));

// ---------------------------------------------------------------------------------------------
// Chaves e hooks

// 029: as gerações são da agência (o perfil base é só o guia da geração): as listas ficam sob ["geracoes"].
export const geracoesKey = ["geracoes"] as const;
export const geracoesListaKey = (filtros: GeracaoListaQuery) => [...geracoesKey, "lista", filtros] as const;
export const geracaoKey = (id: string) => ["geracao", id] as const;
export const geracaoVersoesKey = (id: string) => ["geracao-versoes", id] as const;

export function useGeracao(id: string, opts: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: geracaoKey(id),
    queryFn: () => geracoesApi.detalhe(id),
    enabled: id !== "" && (opts.enabled ?? true),
    refetchInterval: (q) => (q.state.data && geracaoParada(q.state.data.status) ? false : POLL_MS),
  });
}

// Lista por alvo (mais nova primeiro), pela rota da agência. Enquanto houver item em andamento,
// recarrega a cada 2 s.
export function useGeracoesDoAlvo(alvoTipo: GeracaoAlvo, alvoId: string, limite = 10) {
  const filtros: GeracaoListaQuery = { alvoTipo, alvoId, limite };
  return useInfiniteQuery({
    queryKey: geracoesListaKey(filtros),
    queryFn: ({ pageParam }) => geracoesApi.listarAgencia({ alvoTipo, alvoId, limite, cursor: pageParam ?? undefined }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.proximo,
    enabled: alvoId !== "",
    refetchInterval: (q) =>
      q.state.data?.pages.some((p) => p.itens.some((g) => !geracaoParada(g.status))) ? POLL_MS : false,
  });
}

export function useGeracaoVersoes(id: string, enabled: boolean) {
  return useQuery({ queryKey: geracaoVersoesKey(id), queryFn: () => geracoesApi.versoes(id), enabled: enabled && id !== "" });
}

async function invalidarGeracao(qc: QueryClient, g: { id: string }) {
  await Promise.all([
    qc.invalidateQueries({ queryKey: geracaoKey(g.id) }),
    qc.invalidateQueries({ queryKey: geracaoVersoesKey(g.id) }),
    qc.invalidateQueries({ queryKey: geracoesKey }),
  ]);
}

// O resultado escolhido vai para o alvo: no asset, no produto (012) e na voz (025), o detalhe, a lista
// e o histórico. Pedir, cancelar e tentar de novo também mudam o alvo (passos do kit, estado da voz).
// As listas (do perfil e da agência, 029) ficam sob ["assets"], ["produtos"] e ["vozes"].
export async function invalidarAlvo(qc: QueryClient, _perfilId: string | null, alvo: { tipo: GeracaoAlvo; id: string }) {
  if (alvo.tipo === "voz") {
    await Promise.all([
      qc.invalidateQueries({ queryKey: vozKey(alvo.id) }),
      qc.invalidateQueries({ queryKey: vozVersoesKey(alvo.id) }),
      qc.invalidateQueries({ queryKey: ["vozes"] }),
    ]);
    return;
  }
  if (alvo.tipo === "produto") {
    await Promise.all([
      qc.invalidateQueries({ queryKey: produtoKey(alvo.id) }),
      qc.invalidateQueries({ queryKey: produtoVersoesKey(alvo.id) }),
      qc.invalidateQueries({ queryKey: ["produtos"] }),
    ]);
    return;
  }
  if (alvo.tipo !== "asset") return;
  await Promise.all([
    qc.invalidateQueries({ queryKey: assetKey(alvo.id) }),
    qc.invalidateQueries({ queryKey: assetVersionsKey(alvo.id) }),
    qc.invalidateQueries({ queryKey: ["assets"] }),
  ]);
}

// 029 (FR-008): o pedido vai pela rota da agência; o corpo leva o `perfilBaseId` da geração (o guia e
// as proibidas desse perfil; null = só as regras do tipo; ausente = o perfil base do item).
export function useCriarGeracao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: GeracaoIn) => geracoesApi.pedirAgencia(body),
    onSuccess: async (g) => {
      qc.setQueryData(geracaoKey(g.id), g);
      await Promise.all([qc.invalidateQueries({ queryKey: geracoesKey }), invalidarAlvo(qc, g.perfilId, { tipo: g.alvoTipo, id: g.alvoId })]);
    },
  });
}

export function useEscolherGeracao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { geracao: Geracao; candidatoId: string; alvoVersion: number }) =>
      geracoesApi.escolher(v.geracao.id, { candidatoId: v.candidatoId, version: v.geracao.version, alvoVersion: v.alvoVersion }),
    onSuccess: async (g) => {
      await Promise.all([invalidarGeracao(qc, g), invalidarAlvo(qc, g.perfilId, g.alvo)]);
    },
  });
}

type Acao = "cancelar" | "tentarDeNovo" | "gerarOutras";
export function useAcaoGeracao(acao: Acao) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (g: Geracao) => geracoesApi[acao](g.id, g.version),
    onSuccess: async (nova, antiga) => {
      qc.setQueryData(geracaoKey(nova.id), nova);
      // cancelar, tentar de novo e gerar outras mudam o alvo (passos do produto e do kit, estado da voz)
      const alvo = invalidarAlvo(qc, antiga.perfilId, { tipo: antiga.alvoTipo, id: antiga.alvoId });
      await Promise.all([invalidarGeracao(qc, antiga), nova.id !== antiga.id ? invalidarGeracao(qc, nova) : null, alvo]);
    },
  });
}

// Métricas de um candidato de áudio (voz): só as chaves que a tela mostra.
export function metricasAudio(m: Record<string, unknown>): { segundos: number | null; similaridade: number | null; transcricao: string | null } {
  const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  return {
    segundos: num(m.segundos),
    similaridade: num(m.similaridade),
    transcricao: typeof m.transcricao === "string" && m.transcricao ? m.transcricao : null,
  };
}
