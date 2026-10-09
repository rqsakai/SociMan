/*
 * Coleta de mercado (spec 026, US3): chaves, hooks e rótulos da tela /app/configuracoes/coleta e do
 * bloco de estado. A gestão (aceite de risco, interruptor, janela e tetos, pausar/continuar,
 * clientes `scol_`) é só do dono humano: a API recusa o membro e o MCP com 403 `somente_humano`.
 * O token aparece uma vez (criar e rotacionar) e nunca entra no cache do TanStack Query.
 */
import type { ColetaCliente, ColetaConfig, ColetaEstado, ColetaEvento, ColetaResumoRodada } from "@sociman/contract";
import { useQuery, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";

export type { ColetaCliente, ColetaConfig, ColetaConfigIn, ColetaEstado, ColetaEvento, ColetaResumoRodada } from "@sociman/contract";

export const coletaConfigKey = ["coleta", "config"] as const;
export const coletaConfigVersionsKey = ["coleta", "config-versions"] as const;
export const coletaClientesKey = ["coleta", "clientes"] as const;
export const coletaEstadoKey = ["coleta", "estado"] as const;
export const coletaColetasKey = ["coleta", "coletas"] as const;
export const coletaEventosKey = ["coleta", "eventos"] as const;

export function useColetaConfig(enabled = true) {
  return useQuery({ queryKey: coletaConfigKey, queryFn: () => api.coleta.config(), enabled });
}
export function useColetaClientes(enabled = true) {
  return useQuery({ queryKey: coletaClientesKey, queryFn: () => api.coleta.clientes(), enabled });
}
export function useColetaEstado() {
  return useQuery({ queryKey: coletaEstadoKey, queryFn: () => api.coleta.estado(), refetchInterval: 30_000 });
}
export function useColetaColetas() {
  return useQuery({ queryKey: coletaColetasKey, queryFn: () => api.coleta.coletas({ limite: 20 }) });
}
export function useColetaEventos() {
  return useQuery({ queryKey: coletaEventosKey, queryFn: () => api.coleta.eventos({ limite: 20 }) });
}

export async function invalidarColeta(queryClient: QueryClient): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: ["coleta"] });
}

export const situacaoColetaLabel: Record<ColetaEstado["situacao"], string> = {
  desligada_no_servidor: "Desligada no servidor",
  desligada: "Desligada",
  aceite_pendente: "Aceite de risco pendente",
  pausada: "Pausada",
  aguardando_continuar: "Aguardando Continuar",
  fora_da_janela: "Fora da janela",
  ociosa: "Ociosa",
  coletando: "Coletando",
  pausada_captcha: "Pausada: verificação na tela",
  pausada_login: "Pausada: login perdido",
  sem_cliente: "Sem coletor cadastrado",
  parada: "Parada há mais de 48 h",
};

export const situacaoColetaTone: Record<ColetaEstado["situacao"], string> = {
  desligada_no_servidor: "bg-secondary text-secondary-foreground",
  desligada: "bg-secondary text-secondary-foreground",
  aceite_pendente: "bg-warning text-warning-foreground",
  pausada: "bg-warning text-warning-foreground",
  aguardando_continuar: "bg-warning text-warning-foreground",
  fora_da_janela: "bg-secondary text-secondary-foreground",
  ociosa: "bg-info text-info-foreground",
  coletando: "bg-success text-success-foreground",
  pausada_captcha: "bg-warning text-warning-foreground",
  pausada_login: "bg-destructive text-destructive-foreground",
  sem_cliente: "bg-warning text-warning-foreground",
  parada: "bg-destructive text-destructive-foreground",
};

export const clienteSituacaoLabel: Record<ColetaCliente["situacao"], string> = {
  ativo: "Ativo",
  suspenso: "Suspenso",
  revogado: "Revogado",
};
export const clienteSituacaoTone: Record<ColetaCliente["situacao"], string> = {
  ativo: "bg-success text-success-foreground",
  suspenso: "bg-warning text-warning-foreground",
  revogado: "bg-secondary text-secondary-foreground",
};

export const rodadaEstadoLabel: Record<ColetaResumoRodada["estado"], string> = {
  ativa: "ativa",
  pausada_captcha: "pausada (verificação)",
  pausada_login: "pausada (login)",
  interrompida: "interrompida",
  encerrada: "encerrada",
  abortada: "abortada",
};

export const eventoTipoLabel: Record<ColetaEvento["tipo"], string> = {
  captcha: "Verificação na tela",
  login_perdido: "Login perdido",
  bloqueio_suspeito: "Bloqueio suspeito",
  layout_mudou: "A página mudou",
  parar_local: "Parado no desktop",
  retomou: "Retomou",
  iniciado: "Coletor iniciado",
  parado: "Coletor parado",
};

export const coletaConfigFieldLabel: Record<string, string> = {
  habilitada: "Coleta ligada",
  risco_aceito_em: "Risco aceito em",
  risco_aceito_por_id: "Risco aceito por",
  risco_texto_versao: "Versão do texto de risco",
  janela_inicio: "Janela: início (h)",
  janela_fim: "Janela: fim (h)",
  paginas_dia: "Páginas por dia",
  imagens_dia: "Imagens por dia",
  imagens_por_produto: "Imagens por produto",
  itens_por_coleta: "Itens por rodada",
  pausa_min_s: "Pausa mínima (s)",
  pausa_max_s: "Pausa máxima (s)",
  pausada_ate: "Pausada até",
  continuar_em: "Continuar em",
};

export const HORAS = Array.from({ length: 24 }, (_, h) => h);
export const horaLabel = (h: number) => `${String(h).padStart(2, "0")}h`;
