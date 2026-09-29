import type { EstadoPostagem } from "@sociman/contract";

export type { CalendarioItem, CalendarioSemData, EstadoPostagem, Postagem, Sugestao } from "@sociman/contract";

// Preparação da postagem (spec 006, US5): uma postagem por conta de destino (Q2 = A), com textos,
// data e hora planejadas e "Postado" marcado à mão. O SociMan NÃO publica (princípio I).

export const estadoLabel: Record<EstadoPostagem, string> = {
  rascunho: "Rascunho",
  agendado: "Agendado",
  postado: "Postado",
};

export const estadoTone: Record<EstadoPostagem, string> = {
  rascunho: "bg-secondary text-secondary-foreground",
  agendado: "bg-info text-info-foreground",
  postado: "bg-success text-success-foreground",
};

export const TITULO_MAX = 100;
export const DESCRICAO_MAX = 2000;
export const HASHTAGS_MIN = 3;
export const HASHTAGS_MAX = 8;
export const HASHTAG_RE = /^#[\p{L}0-9_]{1,50}$/u;

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

export const postagemFieldLabel: Record<string, string> = {
  conta_id: "Conta",
  titulo: "Título",
  descricao: "Descrição",
  hashtags: "Hashtags",
  estado: "Estado",
  planned_at: "Data e hora",
  posted_url: "Link do post",
  archived: "Arquivada",
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

export const postagensKey = (corteId: string) => ["postagens", corteId] as const;
export const sugestoesKey = (corteId: string) => ["sugestoes", corteId] as const;
export const postagemVersionsKey = (id: string) => ["postagem-versions", id] as const;
export const calendarioKey = (params: object) => ["calendario", params] as const;
