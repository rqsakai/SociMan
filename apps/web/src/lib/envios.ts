import { toApiError, type Envio, type EnvioEtapa, type EnvioStatus, type PadroesCorte } from "@sociman/contract";
import { refreshSession } from "./api";
import { useAuth } from "./authStore";

export type { Envio, EnvioConfig, EnvioEtapa, EnvioStatus, PadroesCorte } from "@sociman/contract";

// Seleção e envio ao OpenShorts (spec 006, US2–US4): rótulos pt-BR, texto do status ao vivo,
// padrões de corte, envio do avulso por arquivo (XHR, com progresso) e chaves do TanStack Query.

export const envioStatusLabel: Record<EnvioStatus, string> = {
  selecionado: "Selecionado",
  na_fila: "Na fila",
  aguardando_openshorts: "Aguardando o SociShorts",
  confirmar_qualidade: "Confirmar qualidade",
  processando: "Processando",
  importando: "Importando",
  pronto: "Pronto",
  sem_clipes: "Sem clipes",
  falhou: "Falhou",
  descartado: "Descartado",
};

// Envios em andamento: a lista faz polling de 5 s enquanto houver algum (http-api.md).
export const ANDAMENTO: EnvioStatus[] = ["na_fila", "aguardando_openshorts", "processando", "importando"];
export const emAndamento = (e: Pick<Envio, "status">) => ANDAMENTO.includes(e.status);

// "Na fila (2º)", "Processando 45%", "Importando 4/6". A etapa real vem em `etapaMensagem`.
export function envioStatusText(e: Pick<Envio, "status" | "queuePosition" | "progress" | "clipsTotal" | "clipsImportados">): string {
  switch (e.status) {
    case "na_fila":
      return e.queuePosition ? `Na fila (${e.queuePosition}º)` : "Na fila";
    case "processando":
      return `Processando ${e.progress}%`;
    case "importando":
      return `Importando ${e.clipsImportados}/${e.clipsTotal ?? "?"}`;
    case "pronto":
      return e.clipsImportados === 1 ? "Pronto: 1 clipe" : `Pronto: ${e.clipsImportados} clipes`;
    default:
      return envioStatusLabel[e.status];
  }
}

// Etapa real do OpenShorts (FR-010a). O detalhe com o % da etapa e o "clipe N de M" vem pronto da
// API (`etapaMensagem`); o rótulo é o fallback e o nome na lista de etapas do detalhe.
export const envioEtapaLabel: Record<EnvioEtapa, string> = {
  fila: "Na fila do SociShorts",
  baixando: "Baixando o vídeo",
  transcrevendo: "Transcrevendo o vídeo",
  escolhendo_momentos: "Escolhendo os momentos",
  processando_clipes: "Cortando os clipes",
  legendas: "Aplicando legendas do kit",
  importando: "Importando",
  concluido: "Pronto",
  erro: "Erro",
};

// Linha única do andamento, com o % geral junto: "Processando 10% · Transcrevendo o vídeo 25%",
// "Processando 55% · Cortando clipe 3 de 9 (cenas 40%)"; na fila, só "Na fila do OpenShorts (2º)".
export function envioProgressoTexto(e: Pick<Envio, "status" | "progress" | "etapa" | "etapaMensagem">): string | null {
  if (e.status !== "processando" && e.status !== "importando") return null;
  const detalhe = e.etapaMensagem || (e.etapa ? envioEtapaLabel[e.etapa] : null);
  if (e.etapa === "fila") return detalhe;
  return detalhe ? `Processando ${e.progress}% · ${detalhe}` : `Processando ${e.progress}%`;
}

// Etapas mostradas no detalhe do envio, na ordem; a das legendas só com a legenda do kit.
export function envioEtapasLista(legendaKit: boolean): EnvioEtapa[] {
  const etapas: EnvioEtapa[] = ["fila", "baixando", "transcrevendo", "escolhendo_momentos", "processando_clipes"];
  if (legendaKit) etapas.push("legendas");
  etapas.push("importando", "concluido");
  return etapas;
}

export const envioStatusTone: Record<EnvioStatus, string> = {
  selecionado: "bg-secondary text-secondary-foreground",
  na_fila: "bg-info text-info-foreground",
  aguardando_openshorts: "bg-warning text-warning-foreground",
  confirmar_qualidade: "bg-warning text-warning-foreground",
  processando: "bg-info text-info-foreground",
  importando: "bg-info text-info-foreground",
  pronto: "bg-success text-success-foreground",
  sem_clipes: "bg-muted text-muted-foreground",
  falhou: "bg-destructive text-destructive-foreground",
  descartado: "bg-muted text-muted-foreground",
};

// ---------------------------------------------------------------------------------------------
// Padrões de corte (FR-008, R8)

export const layoutLabel: Record<PadroesCorte["layout"], string> = {
  auto: "Automático",
  none: "Sem layout (corte simples)",
  split: "Tela dividida",
  screencast: "Tela + rosto",
  speaker_cut: "Troca de quem fala",
};
export const formatoLabel: Record<PadroesCorte["formato"], string> = { vertical: "Vertical (9:16)", square: "Quadrado (1:1)" };
export const legendaLabel: Record<PadroesCorte["legenda"], string> = {
  kit: "Legenda do kit do perfil",
  gerador: "Legenda do SociShorts",
  nenhuma: "Sem legenda",
};

export const padroesFieldLabel: Record<string, string> = {
  clip_min_s: "Duração mínima (s)",
  clip_max_s: "Duração máxima (s)",
  quantidade: "Quantidade de clipes",
  layout: "Layout",
  formato: "Formato",
  legenda: "Legenda",
  marca_automatica: "Aplicar a marca sozinho",
  conta_padrao_id: "Conta padrão",
};

export function formatPadroesValue(field: string, value: unknown): string {
  if (value === null || value === undefined) return field === "quantidade" ? "O SociShorts decide" : "—";
  if (field === "layout") return layoutLabel[value as PadroesCorte["layout"]] ?? String(value);
  if (field === "formato") return formatoLabel[value as PadroesCorte["formato"]] ?? String(value);
  if (field === "legenda") return legendaLabel[value as PadroesCorte["legenda"]] ?? String(value);
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  return String(value);
}

// Mesmas faixas da API (400 `invalid_padroes` com `field`).
export function validatePadroes(p: { clipMinS: number; clipMaxS: number; quantidade: number | null }): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!Number.isInteger(p.clipMinS) || p.clipMinS < 5 || p.clipMinS > 175) errors.clipMinS = "Use de 5 a 175 segundos";
  if (!Number.isInteger(p.clipMaxS) || p.clipMaxS < 10 || p.clipMaxS > 180) errors.clipMaxS = "Use de 10 a 180 segundos";
  else if (!errors.clipMinS && p.clipMaxS < p.clipMinS + 5) errors.clipMaxS = "A máxima precisa ser pelo menos 5 s maior que a mínima";
  if (p.quantidade !== null && (!Number.isInteger(p.quantidade) || p.quantidade < 1 || p.quantidade > 15)) errors.quantidade = "Use de 1 a 15, ou deixe vazio";
  return errors;
}

// `field` da API (snake_case) → chave do formulário.
export const padroesApiField: Record<string, string> = {
  clip_min_s: "clipMinS",
  clip_max_s: "clipMaxS",
  quantidade: "quantidade",
  conta_padrao_id: "contaPadraoId",
};

// ---------------------------------------------------------------------------------------------
// Histórico do envio

export const envioFieldLabel: Record<string, string> = {
  status: "Status",
  config: "Configuração",
  direito_no_envio: "Direito na geração",
  aviso_confirmado: "Aviso confirmado",
  source_title: "Título da fonte",
  source_url: "Link da fonte",
  canal_fonte_id: "Canal",
  video_fonte_id: "Vídeo",
  origem: "Origem",
  archived: "Arquivado",
};

export const origemLabel: Record<Envio["origem"], string> = {
  canal: "Canal-fonte",
  avulso_link: "Avulso (link)",
  avulso_arquivo: "Avulso (arquivo)",
};

// ---------------------------------------------------------------------------------------------
// Envio avulso por arquivo (FR-007, R16): até 2 GB, por XHR para ter o progresso. Mesmo protocolo
// do authFetch: Bearer; num 401, um refresh e uma nova tentativa.

export const MAX_ARQUIVO_BYTES = 2 * 1024 * 1024 * 1024;
export const ARQUIVO_ACEITO = ["video/mp4", "video/quicktime", "video/webm", "video/x-matroska"];

export function uploadEnvioArquivo(
  perfilId: string,
  file: File,
  titulo: string,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<{ envio: Envio }> {
  const send = (token: string | null) =>
    new Promise<{ status: number; body: unknown }>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/perfis/${encodeURIComponent(perfilId)}/envios/arquivo`);
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.responseType = "json";
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(e.loaded / e.total);
      };
      xhr.onload = () => resolve({ status: xhr.status, body: xhr.response as unknown });
      xhr.onerror = () => reject(new TypeError("Falha de rede no envio"));
      xhr.onabort = () => reject(new DOMException("Envio cancelado", "AbortError"));
      signal?.addEventListener("abort", () => xhr.abort(), { once: true });
      const form = new FormData();
      form.append("titulo", titulo);
      form.append("file", file);
      xhr.send(form);
    });

  return (async () => {
    let res = await send(useAuth.getState().accessToken);
    if (res.status === 401) {
      const token = await refreshSession();
      if (!token) {
        useAuth.getState().clearSession();
        throw toApiError(401, res.body);
      }
      onProgress(0);
      res = await send(token);
    }
    if (res.status < 200 || res.status >= 300) throw toApiError(res.status, res.body);
    return res.body as { envio: Envio };
  })();
}

export const enviosKey = (params: object = {}) => ["envios", params] as const;
export const envioKey = (id: string) => ["envio", id] as const;
export const envioVersionsKey = (id: string) => ["envio-versions", id] as const;
export const padroesKey = (perfilId: string) => ["padroes-corte", perfilId] as const;
export const padroesVersionsKey = (perfilId: string) => ["padroes-corte-versions", perfilId] as const;
