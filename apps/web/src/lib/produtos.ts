import type {
  GeracaoStatus,
  Produto,
  ProdutoEstado,
  ProdutoFicha,
  ProdutoFichaIn,
  ProdutoFichaPor,
  ProdutoFilters,
  ProdutoPasso,
  ProdutoPendencia,
  ProdutoStatus,
  ProdutoVariante,
} from "@sociman/contract";
import { useInfiniteQuery, useQuery, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { uploadMultipart } from "./marcaApi";

export type {
  Produto,
  ProdutoEstado,
  ProdutoFicha,
  ProdutoFichaIn,
  ProdutoFichaPor,
  ProdutoImagem,
  ProdutoPasso,
  ProdutoPendencia,
  ProdutoResumo,
  ProdutoStatus,
  ProdutoUso,
  ProdutoVariante,
} from "@sociman/contract";

// Produtos do TikTok Shop (spec 012): rótulos pt-BR, limites, chaves e hooks. O produto nasce com
// 1 a 6 fotos (uma por variante); a API pede a ficha ao Claude e, depois, o recorte e o flat lay de
// cada variante (gerações da 021). A tela acompanha por polling de 2 s enquanto houver passo aberto,
// mostra a folha e a ficha para revisar e aprova. Nada aqui publica nem fala com a loja.

// ---------------------------------------------------------------------------------------------
// Rótulos

export const estadoProdutoLabel: Record<ProdutoEstado, string> = {
  rascunho: "Rascunho",
  gerando: "Gerando",
  revisao: "Em revisão",
  aprovado: "Aprovado",
  arquivado: "Arquivado",
};

export const estadoProdutoTone: Record<ProdutoEstado, string> = {
  rascunho: "bg-secondary text-secondary-foreground",
  gerando: "bg-info text-info-foreground",
  revisao: "bg-warning text-warning-foreground",
  aprovado: "bg-success text-success-foreground",
  arquivado: "bg-dark text-dark-foreground",
};

// O filtro de estado da lista (o `arquivado` é o "Ver arquivados").
export const STATUS_PRODUTO: ProdutoStatus[] = ["rascunho", "gerando", "revisao", "aprovado"];

export const fichaPorLabel: Record<ProdutoFichaPor, string> = {
  ia: "Feita pela IA",
  ia_editada: "IA editada",
  humano: "Preenchida à mão",
};

export const passoLabel: Record<string, string> = {
  "produto.ficha": "Ficha técnica",
  "produto.recorte": "Recorte",
  "produto.flat": "Flat lay",
};

export const avisoVarianteLabel: Record<ProdutoVariante["avisos"][number], string> = {
  flat_desatualizado: "Flat feito com a ficha anterior: refaça o flat se a cor, o material ou o corte mudaram.",
  sem_cor: "Sem cor: preencha a cor em inglês e em português na ficha.",
};

const motivoLabel: Record<ProdutoPendencia["motivo"], string> = {
  ficha_incompleta: "Complete a ficha técnica",
  sem_variante: "Envie pelo menos uma foto",
  sem_recorte: "Falta o recorte",
  sem_flat: "Falta escolher o flat lay",
  sem_cor: "Falta a cor (inglês e português)",
  geracao_em_andamento: "Há uma geração em andamento",
};

// "Variante 2: Falta o recorte". O número é a ordem da variante ativa (1 a 6).
export function pendenciaTexto(p: ProdutoPendencia, numeroDe: (varianteId: string) => number | null): string {
  const n = p.varianteId ? numeroDe(p.varianteId) : null;
  return n !== null ? `Variante ${n}: ${motivoLabel[p.motivo].toLowerCase()}` : motivoLabel[p.motivo];
}

// Pendências que o 409 `produto_incompleto` manda em `details.pendencias`.
export function pendenciasDoErro(err: unknown): ProdutoPendencia[] {
  const det = (err as { details?: Record<string, unknown> } | null)?.details;
  const lista = det?.pendencias;
  if (!Array.isArray(lista)) return [];
  return lista.filter((p): p is ProdutoPendencia => typeof p === "object" && p !== null && typeof (p as { motivo?: unknown }).motivo === "string");
}

// ---------------------------------------------------------------------------------------------
// Ficha: campos, limites (produtos/ficha.py) e os que vão literais para os prompts (CAMPOS_EN).

export type CampoTexto =
  | "nomeComercial"
  | "categoria"
  | "materialEn"
  | "materialPt"
  | "formatoCorte"
  | "tamanhoRelativo"
  | "descricaoPrompt"
  | "descricaoVenda";
export type CampoLista = "detalhesVisiveis" | "cuidados";

export const LIM_TEXTO: Record<CampoTexto, number> = {
  nomeComercial: 120,
  categoria: 120,
  materialEn: 60,
  materialPt: 60,
  formatoCorte: 300,
  tamanhoRelativo: 300,
  descricaoPrompt: 500,
  descricaoVenda: 600,
};
export const LIM_LISTA = { itens: 12, item: 200 } as const;
export const COR_MAX = 40;
export const MATERIAL_PALAVRAS = [2, 5] as const;
export const LIM = { nome: 80, obs: 2000, urlLoja: 500 } as const;

export const campoFichaLabel: Record<CampoTexto | CampoLista | "precisaFlat", string> = {
  nomeComercial: "Nome comercial",
  categoria: "Categoria",
  materialEn: "Material para prompts (inglês)",
  materialPt: "Material em português",
  formatoCorte: "Formato e corte",
  detalhesVisiveis: "Detalhes visíveis",
  tamanhoRelativo: "Tamanho relativo",
  descricaoPrompt: "Descrição para prompts",
  cuidados: "Cuidados",
  descricaoVenda: "Descrição de venda",
  precisaFlat: "Precisa da versão deitada (flat lay)",
};

// Vão literais para os prompts: em inglês, sem tradução nem ajuste.
export const CAMPOS_LITERAIS: ReadonlySet<string> = new Set(["materialEn", "formatoCorte", "detalhesVisiveis", "tamanhoRelativo", "descricaoPrompt", "corEn"]);

// O formulário guarda tudo como texto ("" = não preenchido, como a API entende).
export function fichaParaForm(f: ProdutoFicha | null | undefined): ProdutoFichaIn {
  return {
    nomeComercial: f?.nomeComercial ?? "",
    categoria: f?.categoria ?? "",
    materialEn: f?.materialEn ?? "",
    materialPt: f?.materialPt ?? "",
    formatoCorte: f?.formatoCorte ?? "",
    detalhesVisiveis: f?.detalhesVisiveis ?? [],
    tamanhoRelativo: f?.tamanhoRelativo ?? "",
    descricaoPrompt: f?.descricaoPrompt ?? "",
    cuidados: f?.cuidados ?? [],
    descricaoVenda: f?.descricaoVenda ?? "",
    precisaFlat: f?.precisaFlat ?? false,
  };
}

export const contarPalavras = (s: string) => s.trim().split(/\s+/).filter(Boolean).length;

// ---------------------------------------------------------------------------------------------
// Variantes e passos

export const variantesAtivas = (p: Produto) => p.variantes.filter((v) => !v.archivedAt).sort((a, b) => a.position - b.position);
export const variantesArquivadas = (p: Produto) => p.variantes.filter((v) => v.archivedAt);

// Número de exibição (1..N) de cada variante ativa.
export function numeracao(p: Produto): (varianteId: string) => number | null {
  const mapa = new Map(variantesAtivas(p).map((v, i) => [v.id, i + 1]));
  return (id) => mapa.get(id) ?? null;
}

const ABERTOS: ReadonlySet<GeracaoStatus> = new Set(["na_fila", "rodando"]);
export const passoAberto = (s: GeracaoStatus) => ABERTOS.has(s);

// A geração mais recente de um passo (e variante): `passos` vem da mais nova para a mais antiga.
export function ultimoPasso(p: Produto, passo: string, varianteId: string | null = null): ProdutoPasso | undefined {
  return p.passos.find((g) => g.passo === passo && (g.varianteId ?? null) === varianteId);
}

export const POLL_MS = 2000;

// ---------------------------------------------------------------------------------------------
// Chaves e hooks

export const produtosKey = (perfilId: string) => ["produtos", perfilId] as const;
export const produtosListKey = (perfilId: string, filtros: ProdutoFiltros) => [...produtosKey(perfilId), "lista", filtros] as const;
export const produtoKey = (id: string) => ["produto", id] as const;
export const produtoVersoesKey = (id: string) => ["produto-versoes", id] as const;

export interface ProdutoFiltros {
  q?: string;
  status?: ProdutoStatus;
  arquivados?: ProdutoFilters["arquivados"];
}

const PAGE = 25;

export function useProdutos(perfilId: string, filtros: ProdutoFiltros) {
  return useInfiniteQuery({
    queryKey: produtosListKey(perfilId, filtros),
    queryFn: ({ pageParam }) =>
      api.produtos.listar(perfilId, {
        q: filtros.q || undefined,
        status: filtros.status ? [filtros.status] : undefined,
        arquivados: filtros.arquivados ?? "false",
        limit: PAGE,
        cursor: pageParam,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.proximoCursor ?? undefined,
    enabled: perfilId !== "",
  });
}

export function useProduto(id: string) {
  return useQuery({
    queryKey: produtoKey(id),
    queryFn: () => api.produtos.ver(id),
    enabled: id !== "",
    refetchInterval: (q) => (q.state.data?.passos.some((g) => passoAberto(g.status)) ? POLL_MS : false),
  });
}

export function useProdutoVersoes(id: string) {
  return useQuery({ queryKey: produtoVersoesKey(id), queryFn: () => api.produtos.versoes(id), enabled: id !== "" });
}

export async function invalidarProduto(qc: QueryClient, id: string, perfilId?: string) {
  await Promise.all([
    qc.invalidateQueries({ queryKey: produtoKey(id) }),
    qc.invalidateQueries({ queryKey: produtoVersoesKey(id) }),
    perfilId ? qc.invalidateQueries({ queryKey: produtosKey(perfilId) }) : null,
  ]);
}

// ---------------------------------------------------------------------------------------------
// Envio (multipart por XHR, com progresso)

export const FOTOS_MAX = 6;
export const FOTO_MAX_BYTES = 20 * 1024 * 1024;
export const FOTO_MIN_LADO = 512;
export const FOTO_ACCEPT = "image/png,image/jpeg,image/webp";

export function criarProduto(
  perfilId: string,
  dados: { name: string; obs: string; urlLoja: string; fotos: File[] },
  onProgress: (fraction: number) => void = () => {},
) {
  return uploadMultipart<Produto>(
    `/api/perfis/${encodeURIComponent(perfilId)}/produtos`,
    () => {
      const form = new FormData();
      form.append("name", dados.name.trim());
      if (dados.obs.trim()) form.append("obs", dados.obs.trim());
      if (dados.urlLoja.trim()) form.append("urlLoja", dados.urlLoja.trim());
      for (const f of dados.fotos) form.append("fotos", f);
      return form;
    },
    onProgress,
  );
}

export function adicionarVariante(produtoId: string, version: number, foto: File, onProgress: (fraction: number) => void = () => {}) {
  return uploadMultipart<Produto>(
    `/api/produtos/${encodeURIComponent(produtoId)}/variantes`,
    () => {
      const form = new FormData();
      form.append("version", String(version));
      form.append("foto", foto);
      return form;
    },
    onProgress,
  );
}

// Índice da foto recusada no 400 `invalid_image` (`field = "fotos[N]"`).
export function fotoDoErro(err: unknown): number | null {
  const field = (err as { field?: unknown } | null)?.field;
  const m = typeof field === "string" ? /^fotos\[(\d+)\]$/.exec(field) : null;
  return m ? Number(m[1]) : null;
}

// ---------------------------------------------------------------------------------------------
// Histórico (snapshot de `entity_versions` do produto)

export const produtoFieldLabel: Record<string, string> = {
  name: "Nome interno",
  nome_comercial: "Nome comercial",
  categoria: "Categoria",
  material_en: "Material (inglês)",
  material_pt: "Material (português)",
  formato_corte: "Formato e corte",
  detalhes_visiveis: "Detalhes visíveis",
  tamanho_relativo: "Tamanho relativo",
  descricao_prompt: "Descrição para prompts",
  cuidados: "Cuidados",
  descricao_venda: "Descrição de venda",
  precisa_flat: "Precisa de flat lay",
  obs: "Observação",
  url_loja: "Link da loja",
  status: "Estado",
  ficha_por: "Origem da ficha",
  archived: "Arquivado",
  variantes: "Variantes",
};

function variantesTexto(value: unknown[]): string {
  return value
    .map((v, i) => {
      const r = v as { cor_pt?: unknown; cor_en?: unknown; archived?: unknown; recorte_image_id?: unknown; flat_image_id?: unknown };
      const cor = [r.cor_pt, r.cor_en].filter((c) => typeof c === "string" && c).join(" / ") || "sem cor";
      const partes = [r.recorte_image_id ? "recorte" : null, r.flat_image_id ? "flat" : null].filter(Boolean).join(", ");
      return `${i + 1}. ${cor}${partes ? ` (${partes})` : ""}${r.archived ? " — arquivada" : ""}`;
    })
    .join("\n");
}

export function formatProdutoValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (field === "status" && typeof value === "string") return estadoProdutoLabel[value as ProdutoEstado] ?? value;
  if (field === "ficha_por" && typeof value === "string") return fichaPorLabel[value as ProdutoFichaPor] ?? value;
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (field === "variantes" && Array.isArray(value)) return value.length ? variantesTexto(value) : "—";
  if (Array.isArray(value)) return value.length ? value.map((v) => `• ${String(v)}`).join("\n") : "—";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}
