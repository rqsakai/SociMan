import type { CanalFonte, CanalSyncStatus, Direito, VideoFonte } from "@sociman/contract";

export type { CanalFonte, CanalCandidato, CanalSyncStatus, Direito, VideoFonte, VideoFonteFilters } from "@sociman/contract";

// Canais-fonte e descoberta (spec 006, US1 e US2): rótulos pt-BR, formatação e chaves do TanStack
// Query. O status de direito é só informativo (constitution 3.0.0, princípio II): nada bloqueia.

export const direitoLabel: Record<Direito, string> = {
  proprio: "Próprio",
  parceiro: "Parceiro",
  programa_de_cortes: "Programa de cortes",
  sem_acordo: "Sem acordo",
};

// Ordem do <select> do direito.
export const DIREITOS: Direito[] = ["proprio", "parceiro", "programa_de_cortes", "sem_acordo"];

export const direitoHint: Record<Direito, string> = {
  proprio: "O canal é da agência ou do dono.",
  parceiro: "Há acordo com o dono do canal.",
  programa_de_cortes: "O canal tem programa aberto de cortes.",
  sem_acordo: "Sem acordo registrado: a geração mostra o aviso de direito.",
};

export const syncLabel: Record<CanalSyncStatus, string> = {
  pendente: "Na fila da busca",
  sincronizando: "Buscando vídeos",
  ok: "Atualizado",
  pausado_cota: "Pausado pela cota do YouTube",
  erro: "Erro na busca",
};

// Texto do estado da sincronização ("Buscando vídeos: 150 de 480").
export function syncText(canal: Pick<CanalFonte, "sync">): string {
  const { status, lidos, total } = canal.sync;
  if (status === "sincronizando" && lidos !== null && lidos !== undefined) {
    return total ? `${syncLabel.sincronizando}: ${lidos} de ${total}` : `${syncLabel.sincronizando}: ${lidos}`;
  }
  return syncLabel[status];
}

const compact = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
const integer = new Intl.NumberFormat("pt-BR");

// 12345 → "12,3 mil"; null → "—".
export function formatCount(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n < 10_000 ? integer.format(n) : compact.format(n);
}

// 3725 → "1:02:05"; 125 → "2:05".
export function formatSeconds(s: number | null | undefined): string {
  if (s === null || s === undefined) return "—";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.round(s % 60);
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}

// Pontuação 0–100 → tom do selo.
export function scoreTone(score: number): string {
  if (score >= 70) return "bg-success text-success-foreground";
  if (score >= 40) return "bg-warning text-warning-foreground";
  return "bg-muted text-muted-foreground";
}

// Componentes da pontuação (R3), na ordem de peso.
export const scoreComponentLabel: Record<string, string> = {
  v: "Views por hora recentes",
  e: "Engajamento",
  r: "Idade do vídeo",
  d: "Duração para corte",
};

export const scoreWeights: Record<string, number> = { v: 0.45, e: 0.2, r: 0.15, d: 0.2 };

// Aviso de vídeo que não entra na recomendação.
export function videoWarning(v: Pick<VideoFonte, "disponivel" | "live" | "durationS">): string | null {
  if (!v.disponivel) return "Indisponível (removido ou privado)";
  if (v.live === "ao_vivo") return "Transmissão ao vivo em andamento";
  if (v.live === "agendado") return "Transmissão agendada";
  if (v.durationS !== null && v.durationS !== undefined && v.durationS > 3 * 3600) return "Mais de 3 horas";
  if (v.durationS !== null && v.durationS !== undefined && v.durationS < 45) return "Menos de 45 segundos";
  return null;
}

// Campos versionados do canal (snapshot do histórico, data-model.md).
export const canalFieldLabel: Record<string, string> = {
  title: "Nome",
  handle: "@",
  direito: "Direito",
  direito_evidencia_url: "Evidência (link)",
  direito_evidencia_nota: "Evidência (nota)",
  perfil_ids: "Perfis",
  archived: "Arquivado",
};

export function formatCanalValue(field: string, value: unknown, perfilName?: (id: string) => string): string {
  if (value === null || value === undefined || value === "") return "—";
  if (field === "direito" && typeof value === "string") return direitoLabel[value as Direito] ?? value;
  if (field === "perfil_ids" && Array.isArray(value)) {
    return value.map((id) => (perfilName ? perfilName(String(id)) : String(id).slice(0, 8))).join("\n") || "—";
  }
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  return String(value);
}

export const canaisKey = (params: object = {}) => ["canais", params] as const;
export const canalKey = (id: string) => ["canal", id] as const;
export const canalVersionsKey = (id: string) => ["canal-versions", id] as const;
export const videosKey = (params: object) => ["videos-fonte", params] as const;
export const integracoesKey = ["integracoes"] as const;
