import {
  ApiError,
  type Cena,
  type CenaFilters,
  type CenaModo,
  type CenaMovimento,
  type CenaPlano,
  type CenaStatus,
  type CenaTomada,
  type IaAplicacao,
} from "@sociman/contract";
import { useInfiniteQuery, useQuery, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { uploadMultipart } from "./marcaApi";

export type {
  Cena,
  CenaAviso as Aviso,
  CenaFilters,
  CenaIngrediente as Ingrediente,
  CenaModo,
  CenaMovimento,
  CenaPadroes,
  CenaPlano,
  CenaPrompt,
  CenaResumo,
  CenaStatus,
  CenaTomada as Tomada,
} from "@sociman/contract";

// Cenas para o Flow/Veo (spec 010): rótulos pt-BR, limites, chaves e hooks. Uma cena é a TOMADA (até
// 8 s no Flow); o ambiente reutilizável é o cenário da 007. O prompt é montado pela API (ao vivo em
// rascunho, congelado em pronta/usada); a tela só mostra.

type Tomada = CenaTomada;
export type IngredientePapel = Cena["ingredientes"][number]["papel"];
export type CenaAssetRef = NonNullable<Cena["avatar"]>;
export type CenaProdutoRef = NonNullable<Cena["produto"]>;

// Campos editáveis (CenaIn / CenaPatch), como o formulário os guarda.
export type Duracao = 4 | 6 | 8;
export type CenaCampos = { duracaoS: Duracao } & Pick<
  Cena,
  | "nome"
  | "avatarId"
  | "avatarArquivoId"
  | "cenarioId"
  | "cenarioArquivoId"
  | "plano"
  | "movimento"
  | "camera"
  | "acao"
  | "fala"
  | "textoTela"
  | "estilo"
  | "audio"
  | "modo"
  | "quadroInicial"
  | "quadroFinal"
  | "produtoNome"
  | "produtoImagemId"
  | "produtoId"
  | "produtoVarianteId"
  | "negative"
  | "tags"
  | "notas"
>;

// Filtros da aba (a lista aceita status repetido e arquivadas false|true|all).
export interface CenaFiltros {
  q?: string;
  status?: CenaStatus;
  avatarId?: string;
  cenarioId?: string;
  produtoImagemId?: string;
  produtoId?: string;
  tag?: string;
  arquivadas?: boolean;
}

export type IaAplicacaoCena = IaAplicacao;

// ---------------------------------------------------------------------------------------------
// Rótulos e limites (data-model)

export const statusCenaLabel: Record<CenaStatus, string> = { rascunho: "Rascunho", pronta: "Pronta", usada: "Usada" };
export const statusCenaTone: Record<CenaStatus, string> = {
  rascunho: "bg-secondary text-secondary-foreground",
  pronta: "bg-info text-info-foreground",
  usada: "bg-success text-success-foreground",
};

export const modoCenaLabel: Record<CenaModo, string> = {
  ingredientes: "Ingredients to Video",
  quadros: "Frames to Video",
  estender: "Extend",
};

export const planoLabel: Record<CenaPlano, string> = {
  close: "Close",
  busto: "Busto",
  medio: "Plano médio",
  americano: "Plano americano",
  aberto: "Plano aberto",
  detalhe_produto: "Detalhe do produto",
};

export const movimentoLabel: Record<CenaMovimento, string> = {
  parada: "Câmera parada",
  aproximacao: "Aproximação",
  afastamento: "Afastamento",
  panoramica: "Panorâmica",
  camera_na_mao: "Câmera na mão",
};

export const papelLabel: Record<IngredientePapel, string> = { avatar: "Avatar", produto: "Produto", cenario: "Cenário" };

export const parteLabel: Record<string, string> = {
  quadro_inicial: "Quadro inicial",
  quadro_final: "Quadro final",
  avatar: "Avatar",
  regras: "Regras de imagem",
  acao: "Ação",
  cenario: "Cenário",
  camera: "Câmera",
  estilo: "Iluminação e estilo",
  fala: "Fala",
  audio: "Áudio",
};

export const DURACOES = [4, 6, 8] as const;
export const LIM = {
  nome: 120,
  camera: 500,
  acao: 1000,
  fala: 300,
  textoTela: 300,
  estilo: 500,
  audio: 300,
  quadro: 500,
  produtoNome: 120,
  negative: 500,
  tags: 20,
  notas: 2000,
  nota: 300,
} as const;
export const TOMADA_MAX_BYTES = 200 * 1024 * 1024;
export const TOMADA_ACCEPTED = ["video/mp4", "video/quicktime", "video/webm"];

// Campos que mudam o prompt: editar numa cena `pronta` volta a rascunho; numa `usada`, a API recusa.
export const CAMPOS_PROMPT: (keyof CenaCampos)[] = [
  "avatarId",
  "avatarArquivoId",
  "cenarioId",
  "cenarioArquivoId",
  "plano",
  "movimento",
  "camera",
  "acao",
  "fala",
  "estilo",
  "audio",
  "duracaoS",
  "modo",
  "quadroInicial",
  "quadroFinal",
  "produtoNome",
  "produtoImagemId",
  "produtoId",
  "produtoVarianteId",
  "negative",
];

// Palavras que cabem na fala para a duração (research R4: 15 em 8 s, proporcional).
export const falaMaxPalavras = (duracaoS: number) => Math.ceil((15 * duracaoS) / 8);
export const contarPalavras = (texto: string | null | undefined) => (texto ?? "").trim().split(/\s+/).filter(Boolean).length;

export const camposVazios = (): CenaCampos => ({
  nome: "",
  avatarId: null,
  avatarArquivoId: null,
  cenarioId: null,
  cenarioArquivoId: null,
  plano: null,
  movimento: null,
  camera: null,
  acao: "",
  fala: null,
  textoTela: null,
  estilo: null,
  audio: null,
  duracaoS: 8,
  modo: "ingredientes",
  quadroInicial: null,
  quadroFinal: null,
  produtoNome: null,
  produtoImagemId: null,
  produtoId: null,
  produtoVarianteId: null,
  negative: null,
  tags: [],
  notas: "",
});

export function camposDe(c: Cena | CenaCampos): CenaCampos {
  const base = camposVazios();
  for (const k of Object.keys(base) as (keyof CenaCampos)[]) (base as unknown as Record<string, unknown>)[k] = (c as unknown as Record<string, unknown>)[k] ?? base[k];
  return base;
}

// Só o que mudou (o PATCH aceita subconjunto).
export function diferencas(antes: CenaCampos, depois: CenaCampos): Partial<CenaCampos> {
  const out: Partial<CenaCampos> = {};
  for (const k of Object.keys(depois) as (keyof CenaCampos)[]) {
    if (JSON.stringify(antes[k] ?? null) !== JSON.stringify(depois[k] ?? null)) (out as Record<string, unknown>)[k] = depois[k];
  }
  return out;
}

// Campos em camelCase (o `faltando` do 422 cena_incompleta).
export const campoCenaLabel: Record<string, string> = {
  nome: "Nome",
  acao: "Ação",
  duracaoS: "Duração",
  modo: "Modo do Flow",
  quadroInicial: "Quadro inicial (modo Frames to Video)",
  quadroFinal: "Quadro final (modo Frames to Video)",
  avatarId: "Avatar ativo (o escolhido está arquivado)",
  avatarArquivoId: "Look ou pose ativo",
  cenarioId: "Cenário ativo (o escolhido está arquivado)",
  cenarioArquivoId: "Imagem do cenário ativa",
  produtoImagemId: "Foto do produto ativa",
  // spec 012
  produtoId: "Produto aprovado do catálogo",
  produtoVarianteId: "Variante ativa, com recorte",
};

// Histórico (snapshot em snake_case).
export const cenaFieldLabel: Record<string, string> = {
  nome: "Nome",
  avatar_id: "Avatar",
  avatar_arquivo_id: "Look ou pose",
  cenario_id: "Cenário",
  cenario_arquivo_id: "Imagem do cenário",
  plano: "Plano",
  movimento: "Movimento",
  camera: "Detalhe de câmera",
  acao: "Ação",
  fala: "Fala",
  texto_tela: "Texto na tela",
  estilo: "Iluminação e estilo",
  audio: "Áudio",
  duracao_s: "Duração",
  modo: "Modo do Flow",
  quadro_inicial: "Quadro inicial",
  quadro_final: "Quadro final",
  produto_nome: "Produto",
  produto_imagem_id: "Foto do produto",
  produto_id: "Produto do catálogo",
  produto_variante_id: "Variante do produto",
  negative: "Negative prompt",
  tags: "Tags",
  notas: "Notas",
  status: "Status",
  prompt_congelado: "Prompt congelado",
  negative_congelado: "Negative congelado",
  avatar_version_congelada: "Versão do avatar no prompt",
  cenario_version_congelada: "Versão do cenário no prompt",
  tomada_escolhida_id: "Tomada escolhida",
  archived_at: "Arquivada em",
  archived: "Arquivada",
};

export function formatCenaValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (field === "status" && typeof value === "string") return statusCenaLabel[value as CenaStatus] ?? value;
  if (field === "modo" && typeof value === "string") return modoCenaLabel[value as CenaModo] ?? value;
  if (field === "plano" && typeof value === "string") return planoLabel[value as CenaPlano] ?? value;
  if (field === "movimento" && typeof value === "string") return movimentoLabel[value as CenaMovimento] ?? value;
  if (field === "duracao_s") return `${String(value)} s`;
  if (field === "tags" && Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (field.endsWith("_id") && typeof value === "string") return `${value.slice(0, 8)}…`;
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

export function formatSegundos(ms: number): string {
  return `${(ms / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} s`;
}

// "Faltam: ação, quadro final" do 422 cena_incompleta.
export function faltandoDe(err: unknown): string[] {
  if (!(err instanceof ApiError) || !Array.isArray(err.details.faltando)) return [];
  return (err.details.faltando as unknown[]).filter((x): x is string => typeof x === "string");
}

// ---------------------------------------------------------------------------------------------
// Chaves

export const cenasKey = (perfilId: string) => ["cenas", perfilId] as const;
export const cenasListKey = (perfilId: string, filtros: CenaFiltros) => [...cenasKey(perfilId), "list", filtros] as const;
export const cenaKey = (id: string) => ["cena", id] as const;
export const cenaVersionsKey = (id: string) => ["cena-versions", id] as const;
export const cenaTomadasKey = (id: string, arquivadas = false) => ["cena-tomadas", id, arquivadas] as const;
export const cenaPadroesKey = (perfilId: string) => ["cena-padroes", perfilId] as const;
export const conteudoCenasKey = (conteudoId: string) => ["conteudo-cenas", conteudoId] as const;

// Sem retry em 404 (rota ausente numa API antiga, ou cena de outro perfil): nada de loop no console.
export const semRetry404 = (falhas: number, err: unknown) => !(err instanceof ApiError && err.status === 404) && falhas < 1;

// ---------------------------------------------------------------------------------------------
// Chamadas

const enc = encodeURIComponent;

const paraQuery = (f: CenaFiltros): CenaFilters => ({
  q: f.q || undefined,
  status: f.status ? [f.status] : undefined,
  avatarId: f.avatarId || undefined,
  cenarioId: f.cenarioId || undefined,
  produtoImagemId: f.produtoImagemId || undefined,
  produtoId: f.produtoId || undefined,
  tag: f.tag ? [f.tag] : undefined,
  arquivadas: f.arquivadas ? "all" : "false",
});

// Tomada (multipart, ≤ 200 MB): XHR com progresso e cancelamento, como o vídeo próprio.
export async function uploadTomada(cenaId: string, file: File, onProgress: (f: number) => void, signal?: AbortSignal): Promise<Tomada> {
  return uploadMultipart<Tomada>(
    `/api/cenas/${enc(cenaId)}/tomadas`,
    () => {
      const form = new FormData();
      form.append("file", file);
      return form;
    },
    onProgress,
    signal,
  );
}

// ---------------------------------------------------------------------------------------------
// Hooks

export const PAGE = 50;

export function useCenas(perfilId: string, filtros: CenaFiltros, enabled = true) {
  return useInfiniteQuery({
    queryKey: cenasListKey(perfilId, filtros),
    queryFn: ({ pageParam }) => api.cenas.list(perfilId, { ...paraQuery(filtros), limit: PAGE, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    retry: semRetry404,
    enabled,
  });
}

// Spec 029: a lista da agência (todos os perfis e sem perfil), com o filtro de perfil base.
export function useCenasAgencia(perfilFiltro: string, filtros: CenaFiltros) {
  return useInfiniteQuery({
    queryKey: ["cenas", "agencia", perfilFiltro, filtros] as const,
    queryFn: ({ pageParam }) =>
      api.cenas.listarAgencia({ ...paraQuery(filtros), perfilId: perfilFiltro === "todos" ? undefined : perfilFiltro, limit: PAGE, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    retry: semRetry404,
  });
}

export function useCena(id: string) {
  return useQuery({ queryKey: cenaKey(id), queryFn: () => api.cenas.get(id), enabled: Boolean(id), retry: semRetry404 });
}

export function useCenaPadroes(perfilId: string) {
  return useQuery({
    queryKey: cenaPadroesKey(perfilId),
    queryFn: () => api.cenas.padroes(perfilId),
    enabled: Boolean(perfilId),
    retry: semRetry404,
  });
}

export function useTomadas(cenaId: string, arquivadas: boolean) {
  return useQuery({ queryKey: cenaTomadasKey(cenaId, arquivadas), queryFn: () => api.cenas.tomadas(cenaId, arquivadas).then((r) => r.items), retry: semRetry404 });
}

// As listas (do perfil e da agência, 029) ficam todas sob ["cenas"].
export async function invalidarCena(queryClient: QueryClient, cenaId: string | null, _perfilId?: string | null) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ["cenas"] }),
    ...(cenaId
      ? [
          queryClient.invalidateQueries({ queryKey: cenaKey(cenaId) }),
          queryClient.invalidateQueries({ queryKey: cenaVersionsKey(cenaId) }),
          queryClient.invalidateQueries({ queryKey: ["cena-tomadas", cenaId] }),
        ]
      : []),
  ]);
}
