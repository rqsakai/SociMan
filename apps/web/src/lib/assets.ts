import {
  ApiError,
  toApiError,
  type Asset,
  type AssetFile,
  type AssetFileEnviado,
  type AssetTipo,
  type FileRole,
  type Uso,
} from "@sociman/contract";
import { refreshSession } from "./api";
import { useAuth } from "./authStore";

export type { Asset, AssetFile, AssetSummary, AssetTipo, FileRole, LibraryImage, TagCount, Uso } from "@sociman/contract";

// Biblioteca de assets do perfil (spec 007): rótulos pt-BR, regras de arquivo por tipo (data-model,
// "Classe técnica por tipo do asset"), query keys e o envio por XHR (progresso do upload).

export const tipoLabel: Record<AssetTipo, string> = {
  avatar: "Avatar",
  cenario: "Cenário",
  fundo: "Fundo",
  sticker: "Sticker",
  marca_dagua: "Marca d'água",
  imagem: "Imagem",
};

// Ordem do menu "Novo asset" e dos chips de tipo.
export const TIPOS: AssetTipo[] = ["avatar", "cenario", "fundo", "sticker", "marca_dagua", "imagem"];

// Tipos de um arquivo só: o envio cria um asset por arquivo (POST …/assets/arquivo).
export const SINGLE_FILE_TIPOS: AssetTipo[] = ["fundo", "sticker", "marca_dagua", "imagem"];
export const isSingleFile = (tipo: AssetTipo) => SINGLE_FILE_TIPOS.includes(tipo);

export const roleLabel: Record<FileRole, string> = {
  referencia: "Referência",
  pose: "Pose",
  arquivo: "Arquivo",
  // spec 025
  kit: "Kit padrão",
  variacao: "Variação",
};

export const MAX_BYTES = 20 * 1024 * 1024;
const RASTER = ["image/png", "image/jpeg", "image/webp"];
const ALPHA = ["image/png", "image/webp"];

export interface FileRule {
  accepted: string[];
  minSize: number;
  transparent: boolean;
  hint: string;
}

export const fileRule: Record<AssetTipo, FileRule> = {
  avatar: { accepted: RASTER, minSize: 256, transparent: false, hint: "PNG, JPG ou WebP, até 20 MB, mínimo 256×256 px." },
  cenario: { accepted: RASTER, minSize: 540, transparent: false, hint: "PNG, JPG ou WebP, até 20 MB, mínimo 540×540 px." },
  fundo: { accepted: RASTER, minSize: 540, transparent: false, hint: "PNG, JPG ou WebP, até 20 MB, mínimo 540×540 px." },
  sticker: {
    accepted: ALPHA,
    minSize: 64,
    transparent: true,
    hint: "PNG ou WebP com fundo transparente, até 20 MB, mínimo 64×64 px.",
  },
  marca_dagua: {
    accepted: ALPHA,
    minSize: 64,
    transparent: true,
    hint: "PNG ou WebP com fundo transparente, até 20 MB, mínimo 64×64 px.",
  },
  imagem: { accepted: RASTER, minSize: 64, transparent: false, hint: "PNG, JPG ou WebP, até 20 MB, mínimo 64×64 px." },
};

// Tipos cuja miniatura vai sobre xadrez (imagem com transparência).
export const isTransparentTipo = (tipo: AssetTipo) => fileRule[tipo].transparent;

export const checkerClass = "bg-[repeating-conic-gradient(#ddd_0_25%,#fff_0_50%)] bg-[length:12px_12px]";

// createImageBitmap decodifica sem <img>: uma URL blob: seria bloqueada pela CSP (img-src 'self'
// data:). Arquivo que não decodifica → null ("Formato não aceito").
async function imageSize(file: File): Promise<{ width: number; height: number } | null> {
  try {
    const bitmap = await createImageBitmap(file);
    const size = { width: bitmap.width, height: bitmap.height };
    bitmap.close();
    return size;
  } catch {
    return null;
  }
}

// Conferência no navegador antes do envio (formato, 20 MB, tamanho mínimo); a transparência e o
// resto o servidor confere pelo conteúdo. Devolve a mensagem de erro ou null.
export async function checkImageFile(file: File, tipo: AssetTipo): Promise<string | null> {
  const rule = fileRule[tipo];
  if (!rule.accepted.includes(file.type)) {
    return rule.transparent && RASTER.includes(file.type)
      ? tipo === "sticker"
        ? "O sticker precisa ter fundo transparente"
        : "A imagem precisa ter fundo transparente"
      : "Formato não aceito";
  }
  if (file.size > MAX_BYTES) return "Arquivo maior que 20 MB";
  const size = await imageSize(file);
  if (!size) return "Formato não aceito";
  if (size.width < rule.minSize || size.height < rule.minSize) return "Imagem pequena demais";
  return null;
}

// "persona-cozinha.png" → "persona-cozinha" (nome padrão no envio de um arquivo = um asset).
export const fileBaseName = (name: string) => name.replace(/\.[^.]+$/, "").slice(0, 80) || "Imagem";

// "Reação, promo , reação" → ["reação", "promo"] (a API normaliza do mesmo jeito).
export function parseTags(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.split(",")) {
    const tag = raw.trim().toLowerCase();
    if (tag && !out.includes(tag)) out.push(tag);
  }
  return out;
}

// Link absoluto (para colar no Flow/Veo ou mandar aos agentes).
export const absoluteUrl = (path: string) => new URL(path, window.location.origin).toString();

// Arquivos ativos de um papel, na ordem.
export function activeFiles(asset: Asset, role: FileRole): AssetFile[] {
  return asset.files.filter((f) => f.role === role && !f.archived).sort((a, b) => a.position - b.position);
}

export function archivedFiles(asset: Asset, role: FileRole): AssetFile[] {
  return asset.files.filter((f) => f.role === role && f.archived);
}

// 409 asset_in_use / revert_conflict: a lista de usos vem em details.usos.
export function usosFromError(err: unknown): Uso[] {
  if (!(err instanceof ApiError) || !Array.isArray(err.details.usos)) return [];
  return (err.details.usos as Uso[]).filter((u) => u && typeof u.rotulo === "string");
}

// --- query keys ---------------------------------------------------------------------------------
export interface AssetListFilters {
  tipo: AssetTipo[];
  tag: string[];
  q: string;
  archived: "false" | "all";
}
export const assetsKey = (perfilId: string) => ["assets", perfilId] as const;
export const assetsListKey = (perfilId: string, filters: AssetListFilters) => [...assetsKey(perfilId), "list", filters] as const;
export const libraryImagesKey = (perfilId: string, tipos: readonly AssetTipo[], q = "") =>
  [...assetsKey(perfilId), "imagens", [...tipos], q] as const;
export const assetKey = (id: string) => ["asset", id] as const;
export const assetVersionsKey = (id: string) => ["asset-versions", id] as const;

// --- histórico ----------------------------------------------------------------------------------
export const assetFieldLabel: Record<string, string> = {
  tipo: "Tipo",
  name: "Nome",
  description: "Descrição",
  tags: "Tags",
  prompt: "Prompt",
  voice_tone: "Tom de voz",
  image_rules: "Regras de imagem",
  primary_file_id: "Imagem principal",
  archived: "Arquivado",
  files: "Arquivos",
  // spec 025
  origem: "Origem",
  consentimento: "Consentimento",
  voz_id: "Voz padrão",
  identidade: "Checagem de identidade",
  kit_status: "Situação do kit",
};

interface SnapshotFile {
  id?: string;
  role?: FileRole;
  look?: string | null;
  label?: string | null;
  slot?: string | null;
  archived?: boolean;
}

export function formatAssetValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (field === "tipo" && typeof value === "string") return tipoLabel[value as AssetTipo] ?? value;
  if (field === "tags" && Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (field === "primary_file_id" && typeof value === "string") return `Arquivo ${value.slice(0, 8)}`;
  // spec 025
  if (field === "origem" && typeof value === "string") return ({ upload: "Upload", sintetico: "Sintético", pessoa_real: "Pessoa real" } as Record<string, string>)[value] ?? value;
  if (field === "kit_status" && typeof value === "string") return ({ incompleto: "Incompleto", completo: "Completo", atencao: "Atenção" } as Record<string, string>)[value] ?? value;
  if (field === "voz_id" && typeof value === "string") return `Voz ${value.slice(0, 8)}`;
  if (field === "identidade" && typeof value === "object") {
    const notas = (value as { notas?: Record<string, { nota?: unknown }> }).notas ?? {};
    const lista = Object.entries(notas).map(([slot, n]) => `${slot}: ${String(n.nota ?? "—")}`);
    return lista.length ? `Notas: ${lista.join(", ")}` : "Checagem feita";
  }
  if (field === "consentimento" && typeof value === "object") {
    const c = value as { nome?: unknown; data?: unknown; revogado_em?: unknown };
    const partes = [typeof c.nome === "string" ? c.nome : null, typeof c.data === "string" ? c.data.split("-").reverse().join("/") : null].filter(Boolean);
    return `${partes.join(", ") || "Registrado"}${c.revogado_em ? " (revogado)" : ""}`;
  }
  if (field === "files" && Array.isArray(value)) {
    if (value.length === 0) return "Nenhum";
    return (value as SnapshotFile[])
      .map((f, i) => {
        const name = f.slot || f.label || f.look || `${f.role ? roleLabel[f.role] : "Arquivo"} ${i + 1}`;
        return `${f.role ? roleLabel[f.role] : "Arquivo"}: ${name}${f.archived ? " (arquivado)" : ""}`;
      })
      .join("\n");
  }
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

// --- envio por XHR --------------------------------------------------------------------------------
// Mesmo protocolo do authFetch (e do uploadCorte): Bearer; num 401, um refresh e uma nova tentativa.
function xhrUpload<T>(url: string, form: () => FormData, onProgress?: (fraction: number) => void): Promise<T> {
  const send = (token: string | null) =>
    new Promise<{ status: number; body: unknown }>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", url);
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.responseType = "json";
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress?.(e.loaded / e.total);
      };
      xhr.onload = () => resolve({ status: xhr.status, body: xhr.response as unknown });
      xhr.onerror = () => reject(new TypeError("Falha de rede no envio"));
      xhr.send(form());
    });

  return (async () => {
    let res = await send(useAuth.getState().accessToken);
    if (res.status === 401) {
      const token = await refreshSession();
      if (!token) {
        useAuth.getState().clearSession();
        throw toApiError(401, res.body);
      }
      onProgress?.(0);
      res = await send(token);
    }
    // 413 vem do edge (corpo em HTML), antes da API: mesma mensagem da API.
    if (res.status === 413) throw new ApiError(413, "invalid_image", "Arquivo maior que 20 MB");
    if (res.status < 200 || res.status >= 300) throw toApiError(res.status, res.body);
    return res.body as T;
  })();
}

const enc = encodeURIComponent;

export interface FileFields {
  role: FileRole;
  look?: string;
  uso?: string;
  label?: string;
  quandoUsar?: string;
  notes?: string;
  // spec 025: `role=kit` com o slot (no `rosto_origem`, a origem); `role=variacao` com o `label`
  slot?: string;
  origem?: "upload" | "pessoa_real";
}

// POST /api/assets/{id}/arquivos: acrescenta um arquivo (sem version); o primeiro vira o principal.
export function uploadAssetFile(assetId: string, file: File, fields: FileFields, onProgress?: (fraction: number) => void) {
  return xhrUpload<AssetFileEnviado>(
    `/api/assets/${enc(assetId)}/arquivos`,
    () => {
      const form = new FormData();
      for (const [key, value] of Object.entries(fields)) {
        if (typeof value === "string" && value !== "") form.append(key, value);
      }
      form.append("file", file);
      return form;
    },
    onProgress,
  );
}

// POST /api/perfis/{id}/assets/arquivo: "um arquivo = um asset" (fundo, sticker, marca d'água,
// imagem), usado pelo envio múltiplo da aba e pelos seletores do kit.
// Spec 029: pela rota da agência (`POST /api/assets/arquivo`), com o perfil base opcional.
export function uploadSingleAsset(
  perfilId: string | null,
  tipo: AssetTipo,
  file: File,
  opts: { name?: string; tags?: string[] } = {},
  onProgress?: (fraction: number) => void,
) {
  return xhrUpload<{ asset: Asset; file: AssetFile }>(
    "/api/assets/arquivo",
    () => {
      const form = new FormData();
      if (perfilId) form.append("perfilId", perfilId);
      form.append("tipo", tipo);
      if (opts.name) form.append("name", opts.name);
      if (opts.tags?.length) form.append("tags", opts.tags.join(","));
      form.append("file", file);
      return form;
    },
    onProgress,
  );
}
