import type { AssetTipo, Perfil } from "@sociman/contract";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { useFiltroUrl } from "./filtros";

// AI Studio (spec 029, R10): a biblioteca da agência. Os itens (avatares, cenários, assets, vozes,
// produtos e cenas) podem ter um perfil base ou nenhum, e as listas mostram todos, com o filtro
// "Perfil base" na URL (`perfil=<id>|sem`; sem o parâmetro, "Todos").

export type PerfilFiltro = "todos" | "sem" | string;
export type TipoEstudio = "avatares" | "cenarios" | "vozes" | "produtos" | "cenas" | "assets";

export const SEM_PERFIL = "Sem perfil";
export const SEM_PERFIL_BASE_TEXTO = "Sem perfil base: só as regras do tipo, sem guia";

// Os tipos do item "Assets" do menu (Clarification 2): avatares e cenários têm item próprio.
export const TIPOS_ASSETS: AssetTipo[] = ["imagem", "sticker", "marca_dagua", "fundo"];

export const rotaEstudio = (tipo: TipoEstudio, perfil?: string | null) =>
  `/app/estudio/${tipo}${perfil ? `?perfil=${encodeURIComponent(perfil)}` : ""}`;

export const rotuloTipo: Record<TipoEstudio, string> = {
  avatares: "Avatares",
  cenarios: "Cenários",
  vozes: "Vozes",
  produtos: "Produtos",
  cenas: "Cenas",
  assets: "Assets",
};

// O item do menu e a lista de um asset pelo tipo (o detalhe /app/assets/:id serve aos três).
export const tipoEstudioDoAsset = (tipo: AssetTipo): TipoEstudio => (tipo === "avatar" ? "avatares" : tipo === "cenario" ? "cenarios" : "assets");

// Trilha e item ativo dos detalhes: AI Studio › <tipo> (com o perfil base no filtro, quando houver).
export function metaDetalhe(tipo: TipoEstudio, perfilBaseId?: string | null) {
  return {
    breadcrumbs: [{ label: "AI Studio" }, { label: rotuloTipo[tipo], to: rotaEstudio(tipo, perfilBaseId) }],
    ativo: rotaEstudio(tipo),
  };
}

// O filtro "Perfil base" da lista, na URL.
export function usePerfilFiltro() {
  const [params, set] = useFiltroUrl();
  const valor = params.get("perfil");
  const filtro: PerfilFiltro = !valor ? "todos" : valor;
  return [filtro, (v: PerfilFiltro) => set({ perfil: v === "todos" ? null : v })] as const;
}

// O perfil concreto do filtro (o padrão do "Novo …"), ou null em "Todos" e "Sem perfil".
export const perfilDoFiltro = (f: PerfilFiltro): string | null => (f === "todos" || f === "sem" ? null : f);

// Todos os perfis, inclusive os arquivados (o filtro aceita arquivado; o item mostra "arquivado").
// (a lista da API traz ativos ou arquivados; aqui as duas juntas, em ordem alfabética)
export function usePerfisTodos() {
  return useQuery({
    queryKey: ["perfis", { arquivados: "todos" }],
    queryFn: async () => {
      const [ativos, arquivados] = await Promise.all([api.perfis.list(), api.perfis.list({ archived: true })]);
      return [...ativos.items, ...arquivados.items].sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));
    },
    staleTime: 60_000,
  });
}

export function nomePerfil(perfis: Perfil[] | undefined, id: string | null | undefined): string {
  if (!id) return SEM_PERFIL;
  const p = perfis?.find((x) => x.id === id);
  if (!p) return "Perfil";
  return p.archived ? `${p.name} (arquivado)` : p.name;
}

// O nome do perfil base que a API manda nas listas (`perfilNome`), com o nome local de reserva.
export function perfilNomeDe(item: { perfilId?: string | null; perfilNome?: string | null }, perfis: Perfil[] | undefined): string {
  if (!item.perfilId) return SEM_PERFIL;
  return item.perfilNome ?? nomePerfil(perfis, item.perfilId);
}

// ---------------------------------------------------------------------------------------------
// Opções dos seletores e filtros (a agência inteira): todas as páginas do cursor até o TETO, com os
// do perfil base de referência primeiro, depois os sem perfil e depois o resto (em ordem alfabética
// dentro de cada grupo). Passou do teto: `truncado`, e a tela pede para refinar pelo Perfil base.

export const TETO_OPCOES = 1000;
export const TETO_TEXTO = `Mostrando os primeiros ${TETO_OPCOES}: refine pelo Perfil base`;

export async function buscarTodas<P, T>(
  pagina: (cursor: string | undefined) => Promise<P>,
  itens: (p: P) => T[],
  proximo: (p: P) => string | null | undefined,
): Promise<{ itens: T[]; truncado: boolean }> {
  const out: T[] = [];
  let cursor: string | undefined;
  for (;;) {
    const p = await pagina(cursor);
    out.push(...itens(p));
    const prox = proximo(p);
    if (!prox) return { itens: out.slice(0, TETO_OPCOES), truncado: out.length > TETO_OPCOES };
    if (out.length >= TETO_OPCOES) return { itens: out.slice(0, TETO_OPCOES), truncado: true };
    cursor = prox;
  }
}

export function ordenarPorPerfil<T extends { perfilId?: string | null }>(itens: T[], perfilBase: string | null | undefined, nome: (t: T) => string): T[] {
  const grupo = (t: T) => (perfilBase && t.perfilId === perfilBase ? 0 : !t.perfilId ? 1 : 2);
  return [...itens].sort((a, b) => grupo(a) - grupo(b) || nome(a).localeCompare(nome(b), "pt-BR"));
}

// Assets ativos de um tipo (seletores e filtros da cena).
export function useAssetsOpcoes(tipo: AssetTipo, perfilBase: string | null | undefined) {
  const q = useQuery({
    queryKey: ["assets", "agencia", "opcoes", tipo],
    queryFn: () =>
      buscarTodas(
        (cursor) => api.assets.listarAgencia({ tipo: [tipo], archived: "false", limit: 100, cursor }),
        (p) => p.items,
        (p) => p.nextCursor,
      ),
    staleTime: 30_000,
  });
  const itens = q.data ? ordenarPorPerfil(q.data.itens, perfilBase, (a) => a.name) : undefined;
  return { ...q, itens, truncado: q.data?.truncado ?? false };
}

// Produtos da agência (o seletor da cena só os aprovados; o filtro da lista, todos com os arquivados).
export function useProdutosOpcoes(modo: "aprovados" | "todos", perfilBase: string | null | undefined) {
  const q = useQuery({
    queryKey: ["produtos", "agencia", "opcoes", modo],
    queryFn: () =>
      buscarTodas(
        (cursor) =>
          api.produtos.listarAgencia(
            modo === "aprovados" ? { status: ["aprovado"], arquivados: "false", limit: 100, cursor } : { arquivados: "true", limit: 100, cursor },
          ),
        (p) => p.itens,
        (p) => p.proximoCursor,
      ),
    staleTime: 30_000,
  });
  const itens = q.data ? ordenarPorPerfil(q.data.itens, perfilBase, (p) => p.nomeComercial ?? p.name) : undefined;
  return { ...q, itens, truncado: q.data?.truncado ?? false };
}

// O complemento do estado vazio pelo filtro de perfil (029): o filtro de perfil sozinho não é um
// "filtro ativo"; quem chega pelo card do perfil vê o convite para criar, já com o perfil base.
export function vazioDoPerfil(filtro: PerfilFiltro, perfis: Perfil[] | undefined): { trecho: string; criarComPerfil: boolean } {
  if (filtro === "todos") return { trecho: "", criarComPerfil: false };
  if (filtro === "sem") return { trecho: " sem perfil base", criarComPerfil: false };
  return { trecho: ` com o perfil base ${nomePerfil(perfis, filtro)}`, criarComPerfil: true };
}
