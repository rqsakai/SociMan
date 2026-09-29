import { ApiError, type Conta, type ContaStatus, type PerfilStatus, type Platform } from "@sociman/contract";

// Rótulos de perfis e contas (specs/003-contas-sociais, data-model.md), na ordem dos <select>.
export const perfilStatusLabel: Record<PerfilStatus, string> = {
  em_preparacao: "Em preparação",
  ativo: "Ativo",
  pausado: "Pausado",
};

export const contaStatusLabel: Record<ContaStatus, string> = {
  planejada: "Planejada",
  ativa: "Ativa",
  pausada: "Pausada",
  encerrada: "Encerrada",
};

export const platformLabel: Record<Platform, string> = {
  tiktok: "TikTok",
  youtube: "YouTube",
  instagram: "Instagram",
  kwai: "Kwai",
  facebook: "Facebook",
  x: "X",
  outra: "Outra",
};

// Idiomas oferecidos no formulário; um valor fora da lista (ex.: gravado pela CLI) entra como opção extra.
export const languageLabel: Record<string, string> = {
  "pt-BR": "Português (Brasil)",
  en: "Inglês",
  es: "Espanhol",
};

export function contaPlatformText(conta: Pick<Conta, "platform" | "platformName">): string {
  return conta.platform === "outra" ? conta.platformName || platformLabel.outra : platformLabel[conta.platform];
}

// "A Taverna Nerd" → "AT": o avatar sem logo (US3, cenário 4).
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? [words[0], words[words.length - 1]] : words;
  return letters.map((w) => w?.[0]?.toUpperCase() ?? "").join("") || "?";
}

// Mensagens da API já vêm em pt-BR (inclusive o 409 de versão: "Este perfil foi alterado por
// outra pessoa; recarregue"); mostramos o texto dela como veio.
export function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === "forbidden") return "Sem permissão.";
    return err.message;
  }
  return "Não foi possível concluir a operação. Tente de novo.";
}

export function isVersionConflict(err: unknown): boolean {
  return err instanceof ApiError && err.code === "version_conflict";
}

// Rótulos dos campos versionados (snapshot do histórico, data-model.md).
export const perfilFieldLabel: Record<string, string> = {
  name: "Nome",
  slug: "Identificador",
  niche: "Nicho",
  bio: "Descrição",
  language: "Idioma",
  status: "Status",
  logo_image_id: "Logo",
  banner_image_id: "Banner",
  archived: "Arquivado",
};

export const contaFieldLabel: Record<string, string> = {
  platform: "Plataforma",
  platform_name: "Nome da plataforma",
  handle: "@",
  url: "Link",
  status: "Status",
  notes: "Observação",
  archived: "Arquivada",
};

export function formatPerfilValue(field: string, value: unknown): string {
  if (field === "status" && typeof value === "string") {
    return perfilStatusLabel[value as PerfilStatus] ?? value;
  }
  if (field === "language" && typeof value === "string") return languageLabel[value] ?? value;
  if (field === "logo_image_id" || field === "banner_image_id") {
    return typeof value === "string" ? `Imagem ${value.slice(0, 8)}` : "Sem imagem";
  }
  return formatValue(value);
}

export function formatContaValue(field: string, value: unknown): string {
  if (field === "status" && typeof value === "string") {
    return contaStatusLabel[value as ContaStatus] ?? value;
  }
  if (field === "platform" && typeof value === "string") return platformLabel[value as Platform] ?? value;
  if (field === "handle" && typeof value === "string") return `@${value}`;
  return formatValue(value);
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

export const perfilKey = (id: string) => ["perfil", id] as const;
export const perfilVersionsKey = (id: string) => ["perfil-versions", id] as const;
export const contaVersionsKey = (id: string) => ["conta-versions", id] as const;
