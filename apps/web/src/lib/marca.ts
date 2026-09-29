import { ApiError, type Cor, type CorteStatus, type EntityVersion, type FontOption, type Gancho, type Kit, type KitIn, type Legenda, type MarcaDagua } from "@sociman/contract";

// Tipos e utilitários do kit de marca (specs/004-kit-de-marca, data-model.md e
// contracts/http-api.md). Os tipos do kit vêm do contrato gerado; os tokens usam os nomes em pt-BR
// do data-model (`cor_texto`, `posicao`…), que são os mesmos do JSON.
export type {
  Armazenamento,
  CardFinal,
  Cor,
  Corte,
  CorteStatus,
  Fonte,
  FontePadrao,
  FontOption,
  Gancho,
  Kit,
  Legenda,
  MarcaDagua,
  MidiaKind,
  MidiaLink,
  UserRef,
} from "@sociman/contract";

// "#RRGGBB" ou "paleta:<chave>".
export type CorRef = string;
// "padrao:<chave>" | "perfil:<uuid>".
export type FonteRef = string;
export type PosicaoMarca = MarcaDagua["posicao"];

// O corpo do PUT sem a versão; bordões e séries sempre presentes no rascunho.
export type KitTokens = Omit<KitIn, "version" | "catchphrases" | "series"> & { catchphrases: string[]; series: string[] };

export type Version = EntityVersion;

// ---------------------------------------------------------------------------------------------
// Rótulos (na ordem dos <select>)

export const legendaEstiloLabel: Record<Legenda["estilo"], string> = { classico: "Clássico", karaoke: "Karaokê" };
export const legendaEfeitoLabel: Record<Legenda["efeito"], string> = {
  nenhum: "Nenhum",
  brilho: "Brilho",
  pop: "Pop",
  caixa: "Caixa",
};
export const legendaPosicaoLabel: Record<Legenda["posicao"], string> = { topo: "Topo", meio: "Meio", base: "Base" };
export const ganchoPosicaoLabel: Record<Gancho["posicao"], string> = { topo: "Topo", centro: "Centro", base: "Base" };
export const ganchoTamanhoLabel: Record<Gancho["tamanho"], string> = { P: "Pequeno", M: "Médio", G: "Grande" };
export const fundoTipoLabel: Record<Gancho["fundo_tipo"], string> = { cor: "Cor", imagem: "Imagem" };
export const marcaTipoLabel: Record<MarcaDagua["tipo"], string> = {
  logo: "Logo do perfil",
  imagem: "Imagem própria",
  texto: "Texto (@ da conta)",
};
export const marcaPosicaoLabel: Record<PosicaoMarca, string> = {
  sup_esq: "Superior esquerdo",
  sup_dir: "Superior direito",
  inf_esq: "Inferior esquerdo",
  inf_dir: "Inferior direito",
  centro_sup: "Centro superior",
  centro_inf: "Centro inferior",
};
export const corteStatusLabel: Record<CorteStatus, string> = {
  na_fila: "Na fila",
  processando: "Processando",
  pronto: "Pronto",
  falhou: "Falhou",
};

// ---------------------------------------------------------------------------------------------
// Cores

export const HEX_RE = /^#[0-9A-Fa-f]{6}$/;
export const PALETTE_PREFIX = "paleta:";
export const MAX_PALETTE = 12;

// Resolve uma CorRef para hex; referência a uma chave que não existe mais cai no cinza.
export function resolveColor(ref: CorRef, palette: Cor[]): string {
  if (ref.startsWith(PALETTE_PREFIX)) {
    const key = ref.slice(PALETTE_PREFIX.length);
    return palette.find((c) => c.chave === key)?.valor ?? "#808080";
  }
  return HEX_RE.test(ref) ? ref.toUpperCase() : "#808080";
}

// "#FF5FA2" + 0,5 → "rgba(255, 95, 162, 0.5)".
export function withAlpha(hex: string, alpha: number): string {
  const n = Number.parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

// "Rosa Queridinhos" → "rosa-queridinhos" (a chave é estável: só nasce do nome na criação).
export function colorKey(name: string, taken: string[]): string {
  const base =
    name
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 36) || "cor";
  let key = base;
  for (let i = 2; taken.includes(key); i++) key = `${base}-${i}`;
  return key;
}

// Campos do kit (fora da própria paleta) que apontam para `paleta:<chave>`, no formato do `field`
// da API ("hook.cor_fundo"). Serve para avisar antes de tirar da paleta uma cor em uso.
export function paletteUsage(tokens: KitTokens, key: string): string[] {
  const ref = `${PALETTE_PREFIX}${key}`;
  const sections = { caption: tokens.caption, hook: tokens.hook, watermark: tokens.watermark, endCard: tokens.endCard };
  const used: string[] = [];
  for (const [section, values] of Object.entries(sections)) {
    for (const [name, value] of Object.entries(values)) {
      if (value === ref) used.push(`${section}.${name}`);
    }
  }
  return used;
}

// ---------------------------------------------------------------------------------------------
// Fontes

// Família CSS de cada fonte do kit na prévia (FontFace com o nome interno, R7).
export function fontFamilyName(ref: FonteRef): string {
  return `sociman-${ref.replace(/[^a-zA-Z0-9-]/g, "-")}`;
}

export function fontLabel(ref: FonteRef, options: FontOption[]): string {
  return options.find((o) => o.ref === ref)?.name ?? ref;
}

// ---------------------------------------------------------------------------------------------
// Histórico do kit (snapshot por seção, data-model.md)

export const kitFieldLabel: Record<string, string> = {
  palette: "Paleta",
  caption: "Legenda",
  hook: "Gancho",
  watermark: "Marca d'água",
  end_card: "Card final",
  endCard: "Card final",
  catchphrases: "Bordões",
  series: "Séries",
};

const tokenLabel: Record<string, string> = {
  fonte: "fonte",
  tamanho: "tamanho",
  cor_texto: "cor do texto",
  cor_contorno: "cor do contorno",
  espessura_contorno: "contorno",
  cor_fundo: "cor do fundo",
  opacidade_fundo: "opacidade do fundo",
  estilo: "estilo",
  cor_destaque: "destaque",
  efeito: "efeito",
  posicao: "posição",
  maiusculas: "maiúsculas",
  ligado: "ligado",
  duracao_s: "duração (s)",
  tipo: "tipo",
  imagem_id: "imagem",
  conta_id: "conta",
  escala_pct: "escala (%)",
  opacidade_pct: "opacidade (%)",
  margem_pct: "margem (%)",
  cta: "CTA",
  mostrar_logo: "mostrar logo",
  fundo_tipo: "tipo de fundo",
  fundo_imagem_id: "imagem de fundo",
};

function tokenValue(value: unknown): string {
  if (typeof value === "boolean") return value ? "sim" : "não";
  if (value === null || value === undefined) return "—";
  return String(value);
}

// Antes/depois de uma seção: uma linha "rótulo: valor" por token.
export function formatKitValue(field: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (field === "palette" && Array.isArray(value)) {
    return (value as Cor[]).map((c) => `${c.nome} ${c.valor}`).join("\n") || "—";
  }
  if (Array.isArray(value)) return value.map(String).join("\n") || "—";
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => `${tokenLabel[k] ?? k}: ${tokenValue(v)}`)
      .join("\n");
  }
  return tokenValue(value);
}

// "hook.cor_fundo" → "Gancho: cor do fundo" (o `field` do 400 `invalid_kit`).
export function kitFieldText(field: string): string {
  const [section = "", name] = field.split(".");
  const sectionText = kitFieldLabel[section] ?? section;
  return name ? `${sectionText}: ${tokenLabel[name] ?? name}` : sectionText;
}

// ---------------------------------------------------------------------------------------------
// Formatação

const bytesUnits = ["B", "KB", "MB", "GB", "TB"];
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < bytesUnits.length - 1) {
    value /= 1024;
    unit++;
  }
  return `${value.toLocaleString("pt-BR", { maximumFractionDigits: unit === 0 ? 0 : 1 })} ${bytesUnits[unit]}`;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  const total = Math.round(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export const SAMPLE_TEXT = "Os achadinhos que você queria";

// ---------------------------------------------------------------------------------------------
// Chaves do TanStack Query

export const kitKey = (perfilId: string) => ["kit", perfilId] as const;
export const kitVersionsKey = (perfilId: string) => ["kit-versions", perfilId] as const;
export const fontesKey = (perfilId: string, archived: boolean) => ["fontes", perfilId, archived] as const;
export const marcaDaguaKey = (perfilId: string) => ["marca-dagua", perfilId] as const;
export const fundosKey = (perfilId: string) => ["fundos", perfilId] as const;
export const cortesKey = (perfilId: string) => ["cortes", perfilId] as const;
export const corteKey = (corteId: string) => ["corte", corteId] as const;
export const armazenamentoKey = ["armazenamento"] as const;

// ---------------------------------------------------------------------------------------------
// Validação no navegador (as mesmas faixas do KitTokens da API; a API confere de novo e manda o
// `field` recusado, que cai no mesmo mapa de erros).

type Range = [min: number, max: number];
const ranges: Record<string, Range> = {
  "caption.tamanho": [10, 200],
  "caption.espessura_contorno": [0, 10],
  "caption.opacidade_fundo": [0, 1],
  "hook.opacidade_fundo": [0, 1],
  "hook.espessura_contorno": [0, 10],
  "hook.duracao_s": [1, 10],
  "watermark.escala_pct": [5, 40],
  "watermark.opacidade_pct": [10, 100],
  "watermark.margem_pct": [0, 10],
  "endCard.duracao_s": [1, 5],
  "endCard.opacidade_fundo": [0, 1],
};

export function validateKit(t: KitTokens): Record<string, string> {
  const errors: Record<string, string> = {};
  if (t.palette.length < 1 || t.palette.length > MAX_PALETTE) errors.palette = `A paleta precisa de 1 a ${MAX_PALETTE} cores`;
  const keys = new Set(t.palette.map((c) => c.chave));
  t.palette.forEach((c, i) => {
    const nome = c.nome.trim();
    if (nome.length < 1 || nome.length > 40) errors[`palette.${i}.nome`] = "Dê um nome de até 40 caracteres";
    if (!HEX_RE.test(c.valor)) errors[`palette.${i}.valor`] = "Use #RRGGBB";
  });

  const sections = { caption: t.caption, hook: t.hook, watermark: t.watermark, endCard: t.endCard };
  for (const [section, values] of Object.entries(sections)) {
    for (const [name, value] of Object.entries(values)) {
      const field = `${section}.${name}`;
      if (name.startsWith("cor_") && typeof value === "string") {
        const ok = value.startsWith(PALETTE_PREFIX) ? keys.has(value.slice(PALETTE_PREFIX.length)) : HEX_RE.test(value);
        if (!ok) errors[field] = "Escolha uma cor da paleta ou um hex #RRGGBB";
      }
      const range = ranges[field];
      if (range && (typeof value !== "number" || Number.isNaN(value) || value < range[0] || value > range[1])) {
        errors[field] = `Use um valor de ${range[0].toLocaleString("pt-BR")} a ${range[1].toLocaleString("pt-BR")}`;
      }
    }
  }
  for (const [field, value] of [
    ["caption.tamanho", t.caption.tamanho],
    ["caption.espessura_contorno", t.caption.espessura_contorno],
    ["hook.espessura_contorno", t.hook.espessura_contorno],
    ["watermark.escala_pct", t.watermark.escala_pct],
    ["watermark.opacidade_pct", t.watermark.opacidade_pct],
    ["watermark.margem_pct", t.watermark.margem_pct],
  ] as const) {
    if (!Number.isInteger(value)) errors[field] ??= "Use um número inteiro";
  }
  for (const field of ["hook.duracao_s", "endCard.duracao_s"] as const) {
    const value = field === "hook.duracao_s" ? t.hook.duracao_s : t.endCard.duracao_s;
    if (!errors[field] && !Number.isInteger(value * 2)) errors[field] = "Use passos de 0,5 s";
  }
  // Sem conta ou imagem só é problema com a marca ligada (o padrão nasce desligado e sem conta).
  if (t.watermark.ligado && t.watermark.tipo === "imagem" && !t.watermark.imagem_id) errors["watermark.imagem_id"] = "Escolha ou envie uma imagem";
  if (t.watermark.ligado && t.watermark.tipo === "texto" && !t.watermark.conta_id) errors["watermark.conta_id"] = "Escolha a conta do @";
  // Fundo com imagem: a imagem só é obrigatória com a seção ligada (FR-005a).
  if (t.hook.ligado && t.hook.fundo_tipo === "imagem" && !t.hook.fundo_imagem_id) errors["hook.fundo_imagem_id"] = "Escolha ou envie uma imagem de fundo";
  if (t.endCard.ligado && t.endCard.fundo_tipo === "imagem" && !t.endCard.fundo_imagem_id) errors["endCard.fundo_imagem_id"] = "Escolha ou envie uma imagem de fundo";
  const cta = t.endCard.cta.trim();
  if (cta.length < 1 || cta.length > 80) errors["endCard.cta"] = "Escreva um CTA de até 80 caracteres";
  const list = (items: string[], max: number, label: string) => {
    if (items.length > 20) return `Até 20 ${label}`;
    if (items.some((s) => s.length > max)) return `Cada item tem até ${max} caracteres`;
    if (new Set(items.map((s) => s.toLowerCase())).size !== items.length) return "Há itens repetidos";
    return undefined;
  };
  const catchError = list(t.catchphrases, 120, "bordões");
  if (catchError) errors.catchphrases = catchError;
  const seriesError = list(t.series, 60, "séries");
  if (seriesError) errors.series = seriesError;
  return errors;
}

// Campo recusado num 400 `invalid_kit`: o `field` do envelope, quando vier, ou o prefixo da
// mensagem ("hook.cor_fundo: …", o formato atual da API).
export function kitErrorField(err: unknown): { field: string; message: string } | null {
  if (!(err instanceof ApiError) || (err.code !== "invalid_kit" && err.code !== "revert_conflict")) return null;
  if (err.field) return { field: normalizeKitField(err.field), message: err.message };
  const m = /^([a-zA-Z_]+(?:\.[a-zA-Z0-9_]+|\[\d+\])*): (.+)$/.exec(err.message);
  return m?.[1] && m[2] ? { field: normalizeKitField(m[1]), message: m[2] } : null;
}

// `field` da API → chave do mapa de erros: "palette[2].valor" → "palette.2.valor",
// "end_card.cta" → "endCard.cta", "catchphrases.3" → "catchphrases".
export function normalizeKitField(field: string): string {
  const f = field.replace(/\[(\d+)\]/g, ".$1").replace(/^end_card\b/, "endCard");
  return /^(catchphrases|series)\.\d+$/.test(f) ? f.split(".")[0]! : f;
}

// Troca `paleta:<de>` por `paleta:<para>` em todas as seções (chave de cor nova que acompanha o nome).
export function replaceColorKey(t: KitTokens, from: string, to: string): KitTokens {
  const fromRef = `${PALETTE_PREFIX}${from}`;
  const swap = <T extends object>(section: T): T =>
    Object.fromEntries(Object.entries(section).map(([k, v]) => [k, v === fromRef ? `${PALETTE_PREFIX}${to}` : v])) as T;
  return { ...t, caption: swap(t.caption), hook: swap(t.hook), watermark: swap(t.watermark), endCard: swap(t.endCard) };
}

export function kitTokens(kit: Kit): KitTokens {
  const { palette, caption, hook, watermark, endCard, catchphrases, series } = kit;
  return { palette, caption, hook, watermark, endCard, catchphrases: catchphrases ?? [], series: series ?? [] };
}
