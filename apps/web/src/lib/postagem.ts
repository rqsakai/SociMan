import { ApiError, type DestinoEstado, type Modo, type Previa } from "@sociman/contract";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export type { CalendarioItem, CalendarioSemData, Destino, DestinoEstado, Modo, ModoInfo } from "@sociman/contract";

// Destino e agendamento (spec 014; evolução da postagem da 006): um destino por conteúdo e conta,
// com textos, aprovação (só dono aprova e recusa) e agendamento com modo. Na 014 só o lembrete
// executa: o SociMan avisa no sino e o humano posta (princípio I).

export const destinoEstadoLabel: Record<DestinoEstado, string> = {
  pendente: "Pendente",
  aprovacao_pedida: "Aguardando aprovação",
  aprovado: "Aprovado",
  agendado: "Agendado",
  enviando: "Enviando",
  postado: "Postado",
  rascunho_criado: "Rascunho criado",
  publicado: "Publicado",
  falhou: "Falhou",
};

export const modoLabel: Record<Modo, string> = {
  lembrete: "Lembrete manual",
  criar_rascunho: "Criar rascunho no horário",
  publicar: "Publicar no horário",
  rascunho_e_publicar: "Rascunho antes, publicar no horário",
};

export const modoDescricao: Record<Modo, string> = {
  lembrete: "Na hora, o SociMan avisa \"Hora de postar\" e você posta.",
  criar_rascunho: "Na hora, o SociMan cria o rascunho na conta; você finaliza no app da rede.",
  publicar: "Na hora, o SociMan publica o post aprovado.",
  rascunho_e_publicar: "O rascunho é criado antes e publicado no horário.",
};

export const MODOS: Modo[] = ["lembrete", "criar_rascunho", "publicar", "rascunho_e_publicar"];

export const TITULO_MAX = 100;
export const DESCRICAO_MAX = 2000;
export const HASHTAGS_MIN = 3;
export const HASHTAGS_MAX = 8;
export const HASHTAG_RE = /^#[\p{L}0-9_]{1,50}$/u;
export const MOTIVO_MAX = 500;
export const INTERVALO_MAX = 1440;

// "Receita Fácil!" → "#receitafácil": minúsculas, sem espaço nem pontuação (acentos ficam).
export function normalizeHashtag(raw: string): string | null {
  const body = raw
    .trim()
    .replace(/^#+/, "")
    .toLowerCase()
    .replace(/[^\p{L}0-9_]/gu, "");
  if (!body) return null;
  const tag = `#${body.slice(0, 50)}`;
  return HASHTAG_RE.test(tag) ? tag : null;
}

// Texto colado ("#a #b, c") → hashtags normalizadas, sem repetir.
export function parseHashtags(text: string): string[] {
  const out: string[] = [];
  for (const part of text.split(/[\s,;]+/)) {
    const tag = normalizeHashtag(part);
    if (tag && !out.includes(tag)) out.push(tag);
  }
  return out;
}

// Rótulos do snapshot do destino no histórico (data-model).
export const destinoFieldLabel: Record<string, string> = {
  conta_id: "Conta",
  titulo: "Título",
  descricao: "Descrição",
  hashtags: "Hashtags",
  estado: "Estado",
  modo: "Modo",
  antecedencia_min: "Antecedência (min)",
  planned_at: "Data e hora",
  posted_url: "Link do post",
  aprovado_por: "Aprovado por",
  aprovado_em: "Aprovado em",
  pedido_nota: "Nota do pedido",
  recusa_motivo: "Motivo da recusa",
  archived: "Arquivado",
};

// Texto pronto para colar na rede: título, descrição e hashtags.
export function textoCompleto(p: { titulo: string; descricao: string; hashtags: string[] }): string {
  return [p.titulo, p.descricao, p.hashtags.join(" ")].filter((s) => s.trim()).join("\n\n");
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // sem Clipboard API (HTTP sem certificado, permissão): cai no textarea escondido
    try {
      const el = document.createElement("textarea");
      el.value = text;
      el.setAttribute("readonly", "");
      el.style.position = "fixed";
      el.style.opacity = "0";
      document.body.appendChild(el);
      el.select();
      const ok = document.execCommand("copy");
      el.remove();
      return ok;
    } catch {
      return false;
    }
  }
}

// Modos da conta (R4): os quatro, na ordem da spec; os indisponíveis vêm com o motivo em pt-BR.
export const modosKey = (contaId: string) => ["conta-modos", contaId] as const;
export function useModos(contaId: string | null | undefined) {
  return useQuery({
    queryKey: modosKey(contaId ?? ""),
    queryFn: () => api.contas.modos(contaId!),
    enabled: Boolean(contaId),
    staleTime: 5 * 60_000,
  });
}

// 409 `intervalo_conflito` (Q3): os posts próximos da mesma conta e o intervalo mínimo dela.
export interface ConflitoIntervalo {
  destinoId: string;
  conteudoId: string;
  titulo: string;
  plannedAt: string;
}

export function conflitoIntervalo(err: unknown): { intervaloMin: number; conflitos: ConflitoIntervalo[] } | null {
  if (!(err instanceof ApiError) || err.code !== "intervalo_conflito") return null;
  const conflitos = Array.isArray(err.details.conflitos) ? (err.details.conflitos as ConflitoIntervalo[]) : [];
  const intervaloMin = typeof err.details.intervaloMin === "number" ? err.details.intervaloMin : 30;
  return { intervaloMin, conflitos };
}

// 409 `previa_desatualizada` (R7): a prévia nova vem em `details.previa`.
export function previaNova(err: unknown): Previa | null {
  if (!(err instanceof ApiError) || err.code !== "previa_desatualizada") return null;
  const p = err.details.previa;
  return p && typeof p === "object" ? (p as Previa) : null;
}

export const calendarioKey = (params: object) => ["calendario", params] as const;

// Legenda da TikTok (spec 015, T102): a TikTok não tem título; a legenda é a descrição + linha em
// branco + hashtags, até 2.200 caracteres, e é obrigatória para agendar, aprovar e agendar ou enviar.
export const LEGENDA_TIKTOK_MAX = 2200;
export const LEGENDA_OBRIGATORIA = "Descreva o post: na TikTok a legenda (descrição + hashtags) é obrigatória";
export const usaLegenda = (platform: string) => platform === "tiktok";

export function legendaTiktok(p: { descricao: string; hashtags: string[] }): string {
  return [p.descricao.trim(), p.hashtags.join(" ").trim()].filter(Boolean).join("\n\n");
}

// A legenda que a API compôs (`legendaFinal`, quando exposta) ou a mesma conta feita aqui.
export function legendaDoDestino(d: { descricao: string; hashtags: string[] }): string {
  const final = (d as { legendaFinal?: unknown }).legendaFinal;
  return typeof final === "string" ? final : legendaTiktok(d);
}
