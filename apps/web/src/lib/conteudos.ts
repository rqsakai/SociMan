import type { Atalhos, Conteudo, ConteudoFilters, EstadoEfetivo, Origem, PropostaOpenshorts, Situacao } from "@sociman/contract";
import { useInfiniteQuery, useQuery, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { useAuth } from "./authStore";

export type {
  Atalhos,
  Conteudo,
  ConteudoFilters,
  ConteudoItem,
  Destino,
  DestinoEstado,
  DestinoResumo,
  EstadoEfetivo,
  LoteResultado,
  Modo,
  ModoInfo,
  Origem,
  Previa,
  PropostaOpenshorts,
  Situacao,
  SlotSequencia,
} from "@sociman/contract";

// Central de conteúdos (spec 014): queries, chaves e rótulos em pt-BR. Os filtros moram na URL
// (R10): a lista usa os parâmetros como chave do TanStack e pagina por cursor no servidor.

export const conteudosKey = (filters: object) => ["conteudos", filters] as const;
export const resumoKey = (filters: object) => ["conteudos-resumo", filters] as const;
export const conteudoKey = (id: string) => ["conteudo", id] as const;
export const conteudoVersionsKey = (id: string) => ["conteudo-versions", id] as const;
export const destinoVersionsKey = (id: string) => ["destino-versions", id] as const;

export const PAGE_LIMIT = 50;

// ---------------------------------------------------------------------------------------------
// Rótulos

export const situacaoLabel: Record<Situacao, string> = {
  em_revisao: "Em revisão",
  processando: "Processando",
  pronto: "Pronto",
  erro_marca: "Erro na marca",
};

export const origemLabel: Record<Origem, string> = {
  corte: "Corte",
  video_proprio: "Vídeo próprio",
};

// Estado efetivo por conta (R3), na ordem da esteira (é a ordem do filtro).
export const estadoEfetivoLabel: Record<EstadoEfetivo, string> = {
  em_revisao: "Em revisão",
  pronto: "Pronto",
  aprovacao_pedida: "Aguardando aprovação",
  aprovado: "Aprovado",
  agendado: "Agendado",
  a_postar: "A postar",
  atrasado: "Atrasado",
  atencao: "Atenção",
  // spec 015
  pausado: "Pausado",
  vencido: "Vencido",
  aguardando_vaga: "Aguardando vaga",
  enviando: "Enviando",
  postado: "Postado",
  rascunho_criado: "Rascunho criado",
  publicado: "Publicado",
  falhou: "Falhou",
  arquivado: "Arquivado",
};

export const estadoEfetivoTone: Record<EstadoEfetivo, string> = {
  em_revisao: "bg-secondary text-secondary-foreground",
  pronto: "bg-muted text-foreground ring-1 ring-border",
  aprovacao_pedida: "bg-warning text-warning-foreground",
  aprovado: "bg-primary/15 text-primary ring-1 ring-primary/30",
  agendado: "bg-info text-info-foreground",
  a_postar: "bg-primary text-primary-foreground",
  atrasado: "bg-destructive text-white",
  atencao: "bg-warning text-warning-foreground",
  pausado: "bg-secondary text-secondary-foreground ring-1 ring-border",
  vencido: "bg-warning text-warning-foreground",
  aguardando_vaga: "bg-warning text-warning-foreground",
  enviando: "bg-info text-info-foreground",
  postado: "bg-success text-success-foreground",
  rascunho_criado: "bg-info text-info-foreground",
  publicado: "bg-success text-success-foreground",
  falhou: "bg-destructive text-white",
  arquivado: "bg-dark text-dark-foreground",
};

// Atalhos do topo (R10): chave da URL → campo do `resumo`.
export const atalhos = [
  { id: "prontos_sem_agendamento", label: "Prontos sem agendamento", campo: "prontosSemAgendamento" },
  { id: "aprovacao_pedida", label: "Aguardando aprovação", campo: "aprovacaoPedida" },
  { id: "aprovados_sem_data", label: "Aprovados sem data", campo: "aprovadosSemData" },
  { id: "agendados_hoje", label: "Agendados hoje", campo: "agendadosHoje" },
  { id: "esta_semana", label: "Esta semana", campo: "estaSemana" },
  { id: "a_postar", label: "A postar", campo: "aPostar" },
  { id: "atrasados", label: "Atrasados", campo: "atrasados" },
  { id: "falharam", label: "Falharam", campo: "falharam" },
  // spec 015
  { id: "vencidos", label: "Vencidos", campo: "vencidos" },
  { id: "enviando", label: "Enviando", campo: "enviando" },
  { id: "rascunhos_criados", label: "Rascunhos criados", campo: "rascunhosCriados" },
] as const satisfies readonly { id: string; label: string; campo: keyof Atalhos }[];

export type AtalhoId = (typeof atalhos)[number]["id"];

// "1:05" / "12:30".
export function formatDuracao(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------------------------
// Filtros na URL. Nomes curtos na URL (como o calendário), nomes do contrato na query.

export const filtroParams = ["perfil", "conta", "plataforma", "estado", "origem", "agendadoDe", "agendadoAte", "criadoDe", "criadoAte", "q", "atalho", "ordem", "arquivados"] as const;

export function filtersFromParams(params: URLSearchParams): ConteudoFilters {
  const f: Record<string, unknown> = {};
  const perfis = params.getAll("perfil").filter(Boolean);
  if (perfis.length) f.perfilId = perfis;
  const estados = params.getAll("estado").filter(Boolean);
  if (estados.length) f.estado = estados;
  const simples: Record<string, string> = {
    conta: "contaId",
    plataforma: "plataforma",
    origem: "origem",
    agendadoDe: "agendadoDe",
    agendadoAte: "agendadoAte",
    criadoDe: "criadoDe",
    criadoAte: "criadoAte",
    q: "q",
    atalho: "atalho",
    ordem: "ordem",
  };
  for (const [url, api] of Object.entries(simples)) {
    const v = params.get(url)?.trim();
    if (v) f[api] = v;
  }
  // Período invertido: o filtro mostra o aviso e a lista ignora o período (a API daria 400).
  for (const [de, ate] of [["agendadoDe", "agendadoAte"], ["criadoDe", "criadoAte"]] as const) {
    if (typeof f[de] === "string" && typeof f[ate] === "string" && (f[de] as string) > (f[ate] as string)) {
      delete f[de];
      delete f[ate];
    }
  }
  if (params.get("arquivados") === "1") f.archived = true;
  return f as ConteudoFilters;
}

export function useConteudos(filters: ConteudoFilters) {
  return useInfiniteQuery({
    queryKey: conteudosKey(filters),
    queryFn: ({ pageParam }) => api.conteudos.list({ ...filters, limit: PAGE_LIMIT, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });
}

export function useResumo(filters: { perfilId?: string[]; contaId?: string }) {
  return useQuery({ queryKey: resumoKey(filters), queryFn: () => api.conteudos.resumo(filters) });
}

export function useConteudo(id: string) {
  return useQuery({ queryKey: conteudoKey(id), queryFn: () => api.conteudos.get(id), enabled: Boolean(id) });
}

// Depois de qualquer mudança num conteúdo ou destino: lista, atalhos, detalhe, corte e calendário.
export async function invalidarConteudos(queryClient: QueryClient, conteudoId?: string) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ["conteudos"] }),
    queryClient.invalidateQueries({ queryKey: ["conteudos-resumo"] }),
    queryClient.invalidateQueries({ queryKey: ["calendario"] }),
    ...(conteudoId
      ? [
          queryClient.invalidateQueries({ queryKey: conteudoKey(conteudoId) }),
          queryClient.invalidateQueries({ queryKey: conteudoVersionsKey(conteudoId) }),
          queryClient.invalidateQueries({ queryKey: ["corte", conteudoId] }),
        ]
      : [queryClient.invalidateQueries({ queryKey: ["conteudo"] })]),
    queryClient.invalidateQueries({ queryKey: ["destino-versions"] }),
  ]);
}

export const conteudoFieldLabel: Record<string, string> = { titulo: "Título", archived: "Arquivado" };

// Aprovar, recusar, aprovar em lote e reverter são só do dono (a API responde 403 aos membros);
// a tela só evita mostrar o que não funcionaria.
export const useEhDono = () => useAuth((s) => s.user?.role === "dono");

// Proposta do OpenShorts (T074/T075): título, descrição, gancho e nota sugeridos para o corte (null no
// vídeo próprio e no corte enviado à mão). O operador confere e usa nos textos do destino.
export function propostaDe(conteudo: Pick<Conteudo, "propostaOpenshorts">): PropostaOpenshorts | null {
  const p = conteudo.propostaOpenshorts;
  return p && (p.titulo || p.descricao || p.gancho) ? p : null;
}
