/*
 * Mercado do TikTok Shop (spec 026): o filtro do cockpit na URL, as queries de leitura e os
 * formatadores. Tudo é leitura: o SPA nunca grava no lago; acompanhar, pausar e adotar são ações
 * humanas das US4/US6, por rotas próprias.
 *
 * URL de /app/mercado: `aba` (cockpit padrão), `de`/`ate` (padrão 30 d, fora da URL), `perfil`,
 * `categoria`, `loja`, `origem`, `acompanhados`, `q`, `ordenar`, `pagina`, `tamanho`.
 */
import type { MercadoAvaliacoesFiltros, MercadoCartaoProduto, MercadoFiltros, MercadoInteresse, MercadoNumero, MercadoRankingsFiltros } from "@sociman/contract";
import { keepPreviousData, useQuery, type QueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { api } from "./api";
import { useFiltroUrl } from "./filtros";
import { addDays, localDateKey } from "./tz";

export type {
  ColetaEstado,
  MercadoAvaliacao,
  MercadoCartaoLoja,
  MercadoCartaoProduto,
  MercadoCategoria,
  MercadoLojaDetalhe,
  MercadoRankingItem,
  MercadoRankingsListar,
  MercadoRankingsProduto,
  MercadoVideo,
  MercadoInteresse,
  MercadoInteresseCriarIn,
  MercadoPerfilConfig,
  MercadoContexto,
  MercadoFicha,
  MercadoFiltros,
  MercadoImagem,
  MercadoListaProdutos,
  MercadoNumero,
  MercadoProdutoDetalhe,
  MercadoResumo,
  MercadoSerie,
} from "@sociman/contract";

export const ABAS_MERCADO = ["cockpit", "produtos", "rankings", "lojas", "acompanhamentos"] as const;
export type AbaMercado = (typeof ABAS_MERCADO)[number];
export const abaMercadoLabel: Record<AbaMercado, string> = {
  cockpit: "Cockpit",
  produtos: "Produtos",
  rankings: "Rankings",
  lojas: "Lojas",
  acompanhamentos: "Acompanhamentos",
};

export const ORDENS_MERCADO = [
  { id: "vendasPeriodo", label: "Vendas no período" },
  { id: "gmvPeriodo", label: "GMV no período" },
  { id: "crescimento", label: "Crescimento" },
  { id: "vendasTotais", label: "Vendas totais" },
  { id: "gmvTotal", label: "GMV total" },
  { id: "preco", label: "Preço" },
  { id: "comissaoBp", label: "Comissão %" },
  { id: "comissaoPorVenda", label: "Comissão por venda" },
  { id: "retornoAfiliado", label: "Retorno por afiliado" },
  { id: "nCriadores", label: "Criadores" },
  { id: "primeiraVezEm", label: "Visto pela 1ª vez" },
  { id: "ultimaFotoEm", label: "Última foto" },
  { id: "titulo", label: "Título" },
] as const;
export type OrdemMercado = (typeof ORDENS_MERCADO)[number]["id"];

export const ORIGENS_MERCADO = ["manual", "vitrine", "ranking", "video", "loja", "categoria"] as const;
export const origemMercadoLabel: Record<(typeof ORIGENS_MERCADO)[number], string> = {
  manual: "Manual (link)",
  vitrine: "Vitrine do dono",
  ranking: "Ranking",
  video: "Vídeo viral",
  loja: "Loja seguida",
  categoria: "Categoria do nicho",
};

export const PERIODO_PADRAO_DIAS = 30;
export const MAX_DIAS_MERCADO = 400;
export const ATALHOS_MERCADO = [
  { id: "7d", label: "7 d", dias: 7 },
  { id: "30d", label: "30 d", dias: 30 },
  { id: "90d", label: "90 d", dias: 90 },
] as const;
export const TAMANHO_PADRAO_MERCADO = 25;

export interface FiltroMercado {
  de: string;
  ate: string;
  perfilId?: string;
  categoriaId?: string;
  lojaId?: string;
  origem?: string;
  soAcompanhados: boolean;
  q?: string;
  ordenar: string;
  pagina: number;
  tamanho: number;
}

export interface EstadoFiltroMercado {
  aba: AbaMercado;
  filtro: FiltroMercado;
  periodoPadrao: boolean;
  setAba: (aba: AbaMercado) => void;
  set: (patch: Record<string, string | null>, opts?: { replace?: boolean }) => void;
  setPeriodo: (de: string, ate: string) => void;
}

function diasEntre(de: string, ate: string): number {
  return Math.round((Date.parse(`${ate}T00:00:00Z`) - Date.parse(`${de}T00:00:00Z`)) / 86_400_000) + 1;
}

export function useFiltroMercado(): EstadoFiltroMercado {
  const [params, set] = useFiltroUrl();
  const hoje = localDateKey(new Date());
  return useMemo(() => {
    const pedida = params.get("aba") as AbaMercado | null;
    const aba: AbaMercado = pedida && ABAS_MERCADO.includes(pedida) ? pedida : "cockpit";
    const padraoDe = addDays(hoje, -(PERIODO_PADRAO_DIAS - 1));
    let de = params.get("de") ?? padraoDe;
    let ate = params.get("ate") ?? hoje;
    if (de > ate || diasEntre(de, ate) > MAX_DIAS_MERCADO) {
      de = padraoDe;
      ate = hoje;
    }
    const ordenarUrl = params.get("ordenar");
    const filtro: FiltroMercado = {
      de,
      ate,
      soAcompanhados: params.get("acompanhados") === "1",
      ordenar: ordenarUrl && ORDENS_MERCADO.some((o) => ordenarUrl.startsWith(o.id)) ? ordenarUrl : "vendasPeriodo",
      pagina: Math.max(1, Number(params.get("pagina") ?? "1") || 1),
      tamanho: [10, 25, 50].includes(Number(params.get("tamanho"))) ? Number(params.get("tamanho")) : TAMANHO_PADRAO_MERCADO,
    };
    for (const [k, chave] of [
      ["perfil", "perfilId"],
      ["categoria", "categoriaId"],
      ["loja", "lojaId"],
      ["origem", "origem"],
      ["q", "q"],
    ] as const) {
      const v = params.get(k);
      if (v) (filtro as unknown as Record<string, unknown>)[chave] = v;
    }
    const setPeriodo = (novoDe: string, novoAte: string) => {
      const padrao = novoAte === hoje && diasEntre(novoDe, novoAte) === PERIODO_PADRAO_DIAS;
      set({ de: padrao ? null : novoDe, ate: padrao ? null : novoAte, pagina: null });
    };
    return {
      aba,
      filtro,
      periodoPadrao: ate === hoje && diasEntre(de, ate) === PERIODO_PADRAO_DIAS,
      set,
      setAba: (a) => {
        const naUrl = new URLSearchParams(window.location.search).get("aba") ?? "cockpit";
        if (a !== naUrl) set({ aba: a === "cockpit" ? null : a });
      },
      setPeriodo,
    };
  }, [params, set, hoje]);
}

// O cursor do servidor é opaco; para a paginação numerada o SPA monta a posição (base64url "o:<offset>").
export function cursorDe(pagina: number, tamanho: number): string | undefined {
  const offset = (pagina - 1) * tamanho;
  if (offset <= 0) return undefined;
  return btoa(`o:${offset}`).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function paraQueryMercado(f: FiltroMercado, extra: Partial<MercadoFiltros> = {}): MercadoFiltros {
  const q: MercadoFiltros = { de: f.de, ate: f.ate, ...extra };
  if (f.perfilId) q.perfilId = f.perfilId;
  if (f.categoriaId) q.categoriaId = f.categoriaId;
  if (f.lojaId) q.lojaId = f.lojaId;
  if (f.origem) q.origem = [f.origem as MercadoFiltros["origem"] extends (infer T)[] | undefined ? T : never];
  if (f.soAcompanhados) q.soAcompanhados = true;
  if (f.q) q.q = f.q;
  return q;
}

export const mercadoKey = (parte: string, filtro: object) => ["mercado", parte, filtro] as const;

export function useMercadoResumo(f: FiltroMercado) {
  const query = paraQueryMercado(f);
  return useQuery({ queryKey: mercadoKey("resumo", query), queryFn: () => api.mercado.resumo(query), placeholderData: keepPreviousData });
}

export function useMercadoProdutos(f: FiltroMercado) {
  const query = paraQueryMercado(f, { ordenar: f.ordenar, limite: f.tamanho, cursor: cursorDe(f.pagina, f.tamanho) });
  return useQuery({ queryKey: mercadoKey("produtos", query), queryFn: () => api.mercado.produtos(query), placeholderData: keepPreviousData });
}

export function useMercadoProduto(id: string, f: Pick<FiltroMercado, "de" | "ate">) {
  const query: MercadoFiltros = { de: f.de, ate: f.ate };
  return useQuery({ queryKey: mercadoKey(`produto:${id}`, query), queryFn: () => api.mercado.produto(id, query), enabled: Boolean(id) });
}

export function useMercadoSerie(id: string, f: Pick<FiltroMercado, "de" | "ate">) {
  const query = { de: f.de, ate: f.ate };
  return useQuery({ queryKey: mercadoKey(`serie:${id}`, query), queryFn: () => api.mercado.serie(id, query), enabled: Boolean(id) });
}

export function useColetaEstado() {
  return useQuery({ queryKey: ["coleta", "estado"], queryFn: () => api.coleta.estado(), staleTime: 15_000 });
}

// ---- formatadores ----

const moeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const inteiro = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const umaCasa = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const pct = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 1, signDisplay: "exceptZero" });
const pctSimples = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 1 });

export const formatCentavos = (c: number | null | undefined) => (c === null || c === undefined ? "—" : moeda.format(c / 100));
export const formatInteiro = (n: number | null | undefined) => (n === null || n === undefined ? "—" : inteiro.format(n));
export const formatUmaCasa = (n: number | null | undefined) => (n === null || n === undefined ? "—" : umaCasa.format(n));
export const formatCrescimento = (n: number | null | undefined) => (n === null || n === undefined ? "—" : pct.format(n));
export const formatBp = (bp: number | null | undefined) => (bp === null || bp === undefined ? "—" : pctSimples.format(bp / 10000));

export const motivoLabel: Record<string, string> = {
  estimado: "estimado",
  incerteza: "a página mostra uma faixa (\"1,2 mil\"); usado o ponto médio",
  inconsistente: "o contador de vendidos diminuiu entre fotos; a diferença virou zero",
  grosseiro: "vendas totais × preço atual: aproximação grosseira",
  cupons_nao_descontados: "a rede desconta cupons da comissão; aqui não",
  sem_dado_afiliado: "sem foto do Affiliate Center para este produto",
  fonte_affiliate: "fonte: Affiliate Center",
  fonte_pagina_publica: "fonte: página pública do produto",
  interpolado: "sem foto na véspera do período; a base é a 1ª foto do período",
  coletando: "ainda coletando: menos de duas fotos",
  base_pequena: "base menor que 3 vendas/dia: crescimento sem sentido",
  sem_vendas: "sem vendas no período",
};

export function estadoLabel(estado: MercadoCartaoProduto["estado"]): string {
  return estado === "coletando" ? "coletando" : estado === "amostra_pequena" ? "amostra pequena" : "ok";
}

/** Texto de um Numero para tabela e CSV: o valor formatado (ou "—") e, com faixa, "min–max". */
export function textoNumero(n: MercadoNumero | undefined, formatar: (v: number | null | undefined) => string): string {
  if (!n || n.valor === null || n.valor === undefined) return "—";
  const base = formatar(n.valor);
  return n.min !== null && n.min !== undefined && n.max !== null && n.max !== undefined && n.min !== n.max ? `${base} (${formatar(n.min)}–${formatar(n.max)})` : base;
}

export function projecao(comissaoPorVendaCentavos: MercadoNumero, vendas: number): number | null {
  return comissaoPorVendaCentavos.valor === null || comissaoPorVendaCentavos.valor === undefined ? null : comissaoPorVendaCentavos.valor * vendas;
}

export const produtoMercadoPath = (id: string) => `/app/mercado/produtos/${id}`;

// ---- interesses (US4) ----

export const situacaoInteresseLabel: Record<MercadoInteresse["situacao"], string> = {
  ativo: "Ativo",
  pausado: "Pausado",
  encerrado: "Encerrado",
};
export const situacaoInteresseTone: Record<MercadoInteresse["situacao"], string> = {
  ativo: "bg-success text-success-foreground",
  pausado: "bg-warning text-warning-foreground",
  encerrado: "bg-secondary text-secondary-foreground",
};

export const interessesPerfilKey = (perfilId: string) => ["mercado", "interesses", perfilId] as const;
export const interessesTodosKey = (filtro: object) => ["mercado", "interesses-todos", filtro] as const;
export const perfilConfigKey = (perfilId: string) => ["mercado", "perfil-config", perfilId] as const;
export const categoriasKey = ["mercado", "categorias"] as const;

export function useInteressesPerfil(perfilId: string, query: { origem?: MercadoInteresse["origem"]; situacao?: MercadoInteresse["situacao"] } = {}) {
  return useQuery({ queryKey: [...interessesPerfilKey(perfilId), query], queryFn: () => api.mercado.perfilInteresses(perfilId, query), enabled: Boolean(perfilId) });
}
export function useInteressesTodos(query: { perfilId?: string; origem?: MercadoInteresse["origem"]; situacao?: MercadoInteresse["situacao"] } = {}) {
  return useQuery({ queryKey: interessesTodosKey(query), queryFn: () => api.mercado.interesses(query), placeholderData: keepPreviousData });
}
export function usePerfilConfigMercado(perfilId: string) {
  return useQuery({ queryKey: perfilConfigKey(perfilId), queryFn: () => api.mercado.perfilConfig(perfilId), enabled: Boolean(perfilId) });
}
export function useCategoriasMercado(query: { nivel?: number; q?: string } = {}) {
  return useQuery({ queryKey: [...categoriasKey, query], queryFn: () => api.mercado.categorias(query), staleTime: 60_000 });
}
export async function invalidarInteresses(queryClient: QueryClient): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: ["mercado"] });
}

// ---- detalhe (US5) ----

export const RANKING_TIPOS = ["mais_vendidos", "em_alta", "novos", "alta_comissao"] as const;
export const rankingTipoLabel: Record<(typeof RANKING_TIPOS)[number], string> = {
  mais_vendidos: "Mais vendidos",
  em_alta: "Em alta",
  novos: "Novos",
  alta_comissao: "Alta comissão",
};
export const RANKING_JANELAS = ["1d", "7d", "30d", "total"] as const;

export function useFichas(id: string) {
  return useQuery({ queryKey: mercadoKey(`fichas:${id}`, {}), queryFn: () => api.mercado.fichas(id), enabled: Boolean(id) });
}
export function useRankingsProduto(id: string, f: Pick<FiltroMercado, "de" | "ate">) {
  const query = { de: f.de, ate: f.ate };
  return useQuery({ queryKey: mercadoKey(`rankings:${id}`, query), queryFn: () => api.mercado.rankingsProduto(id, query), enabled: Boolean(id) });
}
export function useVideos(id: string, f: Pick<FiltroMercado, "de" | "ate">) {
  const query = { de: f.de, ate: f.ate, limite: 50 };
  return useQuery({ queryKey: mercadoKey(`videos:${id}`, query), queryFn: () => api.mercado.videos(id, query), enabled: Boolean(id) });
}
export function useAvaliacoes(id: string, extra: Pick<MercadoAvaliacoesFiltros, "nota" | "comFotos" | "cursor"> = {}) {
  const query: MercadoAvaliacoesFiltros = { limite: 20, ...extra };
  return useQuery({ queryKey: mercadoKey(`avaliacoes:${id}`, query), queryFn: () => api.mercado.avaliacoes(id, query), enabled: Boolean(id), placeholderData: keepPreviousData });
}
export function useRankings(f: FiltroMercado, extra: Pick<MercadoRankingsFiltros, "tipo" | "janela" | "categoriaId"> = {}) {
  const query: MercadoRankingsFiltros = { de: f.de, ate: f.ate, ...(f.perfilId ? { perfilId: f.perfilId } : {}), ...extra };
  return useQuery({ queryKey: mercadoKey("rankings", query), queryFn: () => api.mercado.rankings(query), placeholderData: keepPreviousData });
}
export function useLojas(f: FiltroMercado, extra: { oficial?: boolean; seguidaPor?: string; ordenarLoja?: string } = {}) {
  const query = { de: f.de, ate: f.ate, ...(f.q ? { q: f.q } : {}), limite: f.tamanho, cursor: cursorDe(f.pagina, f.tamanho), ...extra };
  return useQuery({ queryKey: mercadoKey("lojas", query), queryFn: () => api.mercado.lojas(query), placeholderData: keepPreviousData });
}
export function useLoja(id: string, f: Pick<FiltroMercado, "de" | "ate">) {
  const query = { de: f.de, ate: f.ate };
  return useQuery({ queryKey: mercadoKey(`loja:${id}`, query), queryFn: () => api.mercado.loja(id, query), enabled: Boolean(id) });
}
export const lojaMercadoPath = (id: string) => `/app/mercado?aba=lojas&loja=${id}`;
