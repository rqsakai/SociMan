import { ApiError, type McpChamada, type McpChamadaFilters, type McpCliente, type McpConfig, type McpEscopo, type McpSituacao } from "@sociman/contract";
import { useInfiniteQuery, useQuery, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";

export type { McpChamada, McpChamadaFilters, McpCliente, McpClienteCreateRequest, McpConfig, McpEscopo, McpSituacao } from "@sociman/contract";

// Clientes MCP dos agentes (spec 009, US1 e US5). Tudo aqui é só do dono humano: a API recusa o
// membro e qualquer ator MCP com 403 `somente_humano`. O token aparece uma vez (create e
// rotacionar) e nunca entra no cache do TanStack Query.

export const mcpClientesKey = ["mcp-clientes"] as const;
export const mcpClienteVersionsKey = (id: string) => ["mcp-cliente-versions", id] as const;
export const mcpConfigKey = ["mcp-config"] as const;
export const mcpConfigVersionsKey = ["mcp-config-versions"] as const;
export const mcpChamadasKey = (filtros: McpChamadaFilters) => ["mcp-chamadas", filtros] as const;

export const escopoLabel: Record<McpEscopo, string> = {
  leitura: "Só leitura",
  propostas: "Leitura e propostas",
};

export const situacaoLabel: Record<McpSituacao, string> = {
  ativo: "Ativo",
  suspenso: "Suspenso",
  revogado: "Revogado",
};

export const situacaoTone: Record<McpSituacao, string> = {
  ativo: "bg-success text-success-foreground",
  suspenso: "bg-warning text-warning-foreground",
  revogado: "bg-secondary text-secondary-foreground",
};

export const resultadoLabel: Record<McpChamada["resultado"], string> = {
  ok: "ok",
  erro: "erro",
  recusada: "recusada",
  limite: "limite",
  nao_autenticado: "não autenticado",
};

export const resultadoTone: Record<McpChamada["resultado"], string> = {
  ok: "bg-success text-success-foreground",
  erro: "bg-destructive text-destructive-foreground",
  recusada: "bg-warning text-warning-foreground",
  limite: "bg-warning text-warning-foreground",
  nao_autenticado: "bg-secondary text-secondary-foreground",
};

export const viaLabel: Record<McpChamada["via"], string> = { mcp: "MCP", api: "API direta" };

export const mcpClienteFieldLabel: Record<string, string> = {
  nome: "Nome",
  descricao: "Descrição",
  escopo: "Escopo",
  situacao: "Situação",
  expira_em: "Vence em",
  limite_por_minuto: "Chamadas por minuto",
  limite_escritas_dia: "Escritas por dia",
  token_id: "Credencial (id)",
};

export const mcpConfigFieldLabel: Record<string, string> = { habilitado: "Acesso MCP" };

// Sem retry em 404 (API sem a spec 009) nem em 403 (não é dono): a tela mostra o erro uma vez.
const semRetry = (falhas: number, err: unknown) => !(err instanceof ApiError && (err.status === 404 || err.status === 403)) && falhas < 1;

export function useMcpClientes(enabled = true) {
  return useQuery({ queryKey: mcpClientesKey, queryFn: () => api.mcp.clientes(), enabled, retry: semRetry });
}

export function useMcpConfig() {
  return useQuery({ queryKey: mcpConfigKey, queryFn: () => api.mcp.config(), retry: semRetry });
}

export function useMcpChamadas(filtros: McpChamadaFilters) {
  return useInfiniteQuery({
    queryKey: mcpChamadasKey(filtros),
    queryFn: ({ pageParam }) => api.mcp.chamadas({ ...filtros, cursor: pageParam }),
    retry: semRetry,
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });
}

// Depois de qualquer ação num cliente: a lista, o histórico dele e o registro (a ação em si não
// gera chamada, mas o "no limite" e o uso mudam com o tempo).
export async function invalidarMcp(queryClient: QueryClient, clienteId?: string): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: mcpClientesKey }),
    queryClient.invalidateQueries({ queryKey: ["mcp-chamadas"] }),
    clienteId ? queryClient.invalidateQueries({ queryKey: mcpClienteVersionsKey(clienteId) }) : Promise.resolve(),
  ]);
}

// Os dois níveis precisam estar ligados (FR-007).
export const mcpLigado = (c: McpConfig | undefined) => Boolean(c?.servidorHabilitado && c?.habilitado);

export const LIMITE_MINUTO = { min: 1, max: 600, padrao: 60 } as const;
export const LIMITE_ESCRITAS = { min: 0, max: 5000, padrao: 200 } as const;
export const NOME_MAX = 60;
export const DESCRICAO_MAX = 300;

// Situação + vencimento num texto curto para a tabela.
export function vencimentoTexto(c: Pick<McpCliente, "expiraEm" | "venceEmBreve">, formatar: (iso: string) => string): string {
  if (!c.expiraEm) return "Sem validade";
  const vencido = new Date(c.expiraEm).getTime() <= Date.now();
  if (vencido) return `Vencida em ${formatar(c.expiraEm)}`;
  return `${formatar(c.expiraEm)}${c.venceEmBreve ? " (vence em breve)" : ""}`;
}
