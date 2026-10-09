import { ApiError, type Anotacao, type AnotacaoCamposCena, type AnotacaoCamposTexto, type AnotacaoCreateRequest, type AnotacaoFilters } from "@sociman/contract";
import { useInfiniteQuery, useQuery, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";

export type { Anotacao, AnotacaoCreateRequest, AnotacaoFilters } from "@sociman/contract";

// Anotações e propostas dos agentes (spec 009, US4). Os agentes gravam pelo MCP; aqui o humano lê,
// aplica (pelo save do destino, com `propostaId`), descarta, arquiva as próprias e anota também.

export type AlvoTipo = Anotacao["alvo"]["tipo"];
export type AnotacaoSituacao = Anotacao["situacao"];
export type AnotacaoTipo = Anotacao["tipo"];

export const anotacoesKey = (filtros: AnotacaoFilters) => ["anotacoes", filtros] as const;
export const anotacoesResumoKey = ["anotacoes-resumo"] as const;

export const situacaoAnotacaoLabel: Record<AnotacaoSituacao, string> = {
  aberta: "Aberta",
  aplicada: "Aplicada",
  descartada: "Descartada",
  arquivada: "Arquivada",
};

export const situacaoAnotacaoTone: Record<AnotacaoSituacao, string> = {
  aberta: "bg-info text-info-foreground",
  aplicada: "bg-success text-success-foreground",
  descartada: "bg-secondary text-secondary-foreground",
  arquivada: "bg-secondary text-secondary-foreground",
};

export const tipoAnotacaoLabel: Record<AnotacaoTipo, string> = {
  observacao: "Observação",
  proposta_texto: "Proposta de texto",
  // spec 010
  proposta_cena: "Proposta de cena",
};

export const alvoTipoLabel: Record<AlvoTipo, string> = {
  perfil: "Perfil",
  conta: "Conta",
  canal: "Canal-fonte",
  video_fonte: "Vídeo-fonte",
  corte: "Corte",
  conteudo: "Conteúdo",
  destino: "Destino",
  // spec 010
  cena: "Cena",
  // spec 012
  produto: "Produto",
};

// `campos` é uma união pelo `tipo` (spec 010): texto do destino ou campos de uma cena.
export type CamposTexto = AnotacaoCamposTexto;
export type CamposCenaProposta = AnotacaoCamposCena;

export function camposTexto(a: Anotacao): CamposTexto | null {
  return a.tipo === "proposta_texto" && a.campos ? (a.campos as CamposTexto) : null;
}

export function camposCena(a: Anotacao): CamposCenaProposta | null {
  return a.tipo === "proposta_cena" && a.campos ? (a.campos as CamposCenaProposta) : null;
}

// "Aceitar" de uma proposta de cena: o formulário da cena nova (alvo perfil) ou da cena (alvo cena).
export function aceitarCenaHref(a: Anotacao): string | null {
  if (a.tipo !== "proposta_cena" || a.situacao !== "aberta") return null;
  if (a.alvo.tipo === "cena") return `/app/cenas/${a.alvo.id}?proposta=${a.id}`;
  // 029: a nova cena vive no AI Studio, com o perfil da proposta como perfil base
  if (a.alvo.tipo === "perfil") return `/app/estudio/cenas/nova?perfil=${a.alvo.id}&proposta=${a.id}`;
  return null;
}

// Sem retry em 404 (rota ausente numa API antiga): não fica em loop no console.
const semRetry404 = (falhas: number, err: unknown) => !(err instanceof ApiError && err.status === 404) && falhas < 1;

// A API tem as rotas de anotações? Uma sondagem só, pelo contador (`anotacoes_resumo`): 404 = API
// sem a spec 009, e nenhuma outra query de anotações dispara. Nunca refaz a sondagem sozinha.
const disponivelKey = ["anotacoes-disponivel"] as const;
export function useAnotacoesDisponiveis(): boolean {
  const q = useQuery({
    queryKey: disponivelKey,
    queryFn: async () => {
      try {
        await api.anotacoes.resumo();
        return true;
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return false;
        throw err;
      }
    },
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
  return q.data === true;
}

export const TEXTO_MAX = 4000;
export const MOTIVO_DESCARTE_MAX = 300;

// Anotações de um item (detalhe do destino, conteúdo, corte, canal, vídeo-fonte), as abertas primeiro.
export function useAnotacoesDoItem(alvoTipo: AlvoTipo, alvoId: string | null | undefined) {
  const disponivel = useAnotacoesDisponiveis();
  const filtros: AnotacaoFilters = { alvoTipo, alvoId: alvoId ?? undefined, limit: 100 };
  return useQuery({
    queryKey: anotacoesKey(filtros),
    queryFn: () => api.anotacoes.list(filtros),
    enabled: disponivel && Boolean(alvoId),
    retry: semRetry404,
    select: (r) => [...r.anotacoes].sort((a, b) => Number(b.situacao === "aberta") - Number(a.situacao === "aberta")),
  });
}

// Caixa "Propostas dos agentes": filtros no servidor e "Carregar mais" por cursor.
export function useAnotacoes(filtros: AnotacaoFilters) {
  const disponivel = useAnotacoesDisponiveis();
  return useInfiniteQuery({
    enabled: disponivel,
    retry: semRetry404,
    queryKey: anotacoesKey(filtros),
    queryFn: ({ pageParam }) => api.anotacoes.list({ ...filtros, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });
}

// Contador do menu: propostas abertas.
export function useAnotacoesResumo(enabled = true) {
  const disponivel = useAnotacoesDisponiveis();
  return useQuery({
    queryKey: anotacoesResumoKey,
    queryFn: () => api.anotacoes.resumo(),
    enabled: enabled && disponivel,
    retry: semRetry404,
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

export async function invalidarAnotacoes(queryClient: QueryClient): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ["anotacoes"] }),
    queryClient.invalidateQueries({ queryKey: anotacoesResumoKey }),
  ]);
}

export function criarAnotacao(body: AnotacaoCreateRequest) {
  return api.anotacoes.create(body);
}

export function arquivarAnotacao(a: Pick<Anotacao, "id" | "version">) {
  return api.anotacoes.archive(a.id, a.version);
}

export function descartarAnotacao(a: Pick<Anotacao, "id" | "version">, motivo: string) {
  return api.anotacoes.descartar(a.id, { version: a.version, motivo: motivo.trim() || null });
}

// "Agente: Caçador" / "Raul" / "Sistema".
export function autorTexto(autor: Anotacao["autor"]): string {
  if (autor.tipo === "mcp_client") return `Agente: ${autor.nome}`;
  return autor.nome ?? "—";
}
