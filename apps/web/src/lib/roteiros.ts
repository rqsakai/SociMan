import type {
  CenaMotor,
  Roteiro,
  RoteiroEtapa,
  RoteiroModo,
  RoteiroPortao,
  RoteiroStatus,
} from "@sociman/contract";
import { useInfiniteQuery, useQuery, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { uploadMultipart } from "./marcaApi";

export type {
  CenaMotor,
  Pronuncia,
  Roteiro,
  RoteiroCena,
  RoteiroEtapa,
  RoteiroGeracaoAberta,
  RoteiroModo,
  RoteiroNarracao,
  RoteiroPadroes,
  RoteiroPortao,
  RoteiroPortoes,
  RoteiroPosicao,
  RoteiroProduto,
  RoteiroResumo,
  RoteiroStatus,
  RoteiroTomada,
  RoteiroVideo,
} from "@sociman/contract";

// Roteiros com vídeo local (spec 011): rótulos pt-BR, a etapa de cada status, os hooks (polling de 2 s
// enquanto o roteiro trabalha sozinho) e o envio do keyframe pronto. O roteiro anda pela máquina do
// data-model: texto → narração → keyframes → clipes → prévia (final) → acabamento HD → conteúdo da 014.

export const statusRoteiroLabel: Record<RoteiroStatus, string> = {
  rascunho: "Rascunho",
  planejando: "Planejando",
  aguardando_texto: "Aguardando o texto",
  narrando: "Narrando",
  aguardando_narracao: "Aguardando a narração",
  gerando_keyframes: "Gerando keyframes",
  aguardando_keyframes: "Aguardando os keyframes",
  gerando_clipes: "Gerando clipes",
  aguardando_clipes: "Aguardando os clipes",
  montando: "Montando a prévia",
  aguardando_final: "Aguardando o final",
  finalizando: "Fazendo o acabamento HD",
  pronto: "Pronto",
  falhou: "Falhou",
};

const AGUARDANDO = "bg-warning text-warning-foreground";
const TRABALHANDO = "bg-info text-info-foreground";
export const statusRoteiroTone: Record<RoteiroStatus, string> = {
  rascunho: "bg-secondary text-secondary-foreground",
  planejando: TRABALHANDO,
  aguardando_texto: AGUARDANDO,
  narrando: TRABALHANDO,
  aguardando_narracao: AGUARDANDO,
  gerando_keyframes: TRABALHANDO,
  aguardando_keyframes: AGUARDANDO,
  gerando_clipes: TRABALHANDO,
  aguardando_clipes: AGUARDANDO,
  montando: TRABALHANDO,
  aguardando_final: AGUARDANDO,
  finalizando: TRABALHANDO,
  pronto: "bg-success text-success-foreground",
  falhou: "bg-destructive text-destructive-foreground",
};

export const STATUS_ROTEIRO = Object.keys(statusRoteiroLabel) as RoteiroStatus[];

export const etapaFalhouLabel: Record<RoteiroEtapa, string> = {
  plano: "o plano",
  narracao: "a narração",
  keyframes: "os keyframes",
  clipes: "os clipes",
  montagem: "a montagem da prévia",
  acabamento: "o acabamento HD",
};

export const motorLabel: Record<CenaMotor, string> = {
  minimax: "MiniMax (padrão)",
  wan: "Wan 2.2 (rosto sem fala)",
  wan_qualidade: "Wan 2.2 qualidade (tecido, giro; ~40 min)",
  ltx: "LTX",
};
export const MOTORES = Object.keys(motorLabel) as CenaMotor[];

export const modoLabel: Record<RoteiroModo, string> = { revisar: "Revisar", automatico: "Automático" };

// As 5 etapas da tela, na ordem do roteiro (o id é o do portão).
export type Etapa = RoteiroPortao;
export const ETAPAS: { id: Etapa; rotulo: string }[] = [
  { id: "texto", rotulo: "Texto" },
  { id: "narracao", rotulo: "Narração" },
  { id: "keyframes", rotulo: "Keyframes" },
  { id: "clipes", rotulo: "Clipes" },
  { id: "final", rotulo: "Final" },
];

const ETAPA_DO_STATUS: Record<RoteiroStatus, Etapa> = {
  rascunho: "texto",
  planejando: "texto",
  aguardando_texto: "texto",
  narrando: "narracao",
  aguardando_narracao: "narracao",
  gerando_keyframes: "keyframes",
  aguardando_keyframes: "keyframes",
  gerando_clipes: "clipes",
  aguardando_clipes: "clipes",
  montando: "final",
  aguardando_final: "final",
  finalizando: "final",
  pronto: "final",
  falhou: "texto",
};
const ETAPA_DA_FALHA: Record<RoteiroEtapa, Etapa> = {
  plano: "texto",
  narracao: "narracao",
  keyframes: "keyframes",
  clipes: "clipes",
  montagem: "final",
  acabamento: "final",
};

// A etapa onde o roteiro está agora (a aba que abre).
export const etapaAtual = (r: Pick<Roteiro, "status" | "etapaFalhou">): Etapa =>
  r.status === "falhou" && r.etapaFalhou ? ETAPA_DA_FALHA[r.etapaFalhou] : ETAPA_DO_STATUS[r.status];

// O portão em que o roteiro está parado (aprovar só vale nele).
export function portaoParado(status: RoteiroStatus): Etapa | null {
  const m = /^aguardando_(texto|narracao|keyframes|clipes|final)$/.exec(status);
  return m ? (m[1] as Etapa) : null;
}

const TRABALHANDO_STATUS: ReadonlySet<RoteiroStatus> = new Set(["planejando", "narrando", "gerando_keyframes", "gerando_clipes", "montando", "finalizando"]);
const ANDANDO = new Set(["na_fila", "rodando"]);

// O roteiro muda sozinho: uma etapa de trabalho ou uma geração aberta andando.
export function roteiroMudando(r: Roteiro): boolean {
  return (
    TRABALHANDO_STATUS.has(r.status) ||
    r.geracoesAbertas.some((g) => ANDANDO.has(g.status)) ||
    r.posicoes.some((p) => p.geracoesAbertas.some((g) => ANDANDO.has(g.status)))
  );
}

export const POLL_MS = 2000;
export const VELOCIDADE = { min: 0.9, max: 1.2, passo: 0.01, padrao: 1.08 } as const;
export const LIM = { nome: 120, brief: 4000, frase: 300, frases: 60, produtos: 6, instrucao: 2000, referencias: 6, palavra: 60 } as const;

// ---------------------------------------------------------------------------------------------
// Chaves e hooks

export const roteirosKey = ["roteiros"] as const;
export const roteiroKey = (id: string) => ["roteiro", id] as const;
export const roteiroVersoesKey = (id: string) => ["roteiro-versoes", id] as const;
export const roteiroPadroesKey = (perfilId: string) => ["roteiro-padroes", perfilId] as const;
export const pronunciasKey = (perfilId: string, arquivadas: boolean) => ["pronuncias", perfilId, arquivadas] as const;

export interface RoteiroFiltros {
  q?: string;
  status?: RoteiroStatus;
  arquivados?: boolean;
}

export function useRoteirosAgencia(perfilFiltro: string, filtros: RoteiroFiltros) {
  return useInfiniteQuery({
    queryKey: [...roteirosKey, "agencia", perfilFiltro, filtros] as const,
    queryFn: ({ pageParam }) =>
      api.roteiros.listarAgencia({
        perfilId: perfilFiltro === "todos" ? undefined : perfilFiltro,
        q: filtros.q || undefined,
        status: filtros.status ? [filtros.status] : undefined,
        archived: filtros.arquivados ?? false,
        limit: 25,
        cursor: pageParam,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.proximo ?? undefined,
  });
}

export function useRoteiro(id: string) {
  return useQuery({
    queryKey: roteiroKey(id),
    queryFn: () => api.roteiros.detalhe(id),
    enabled: id !== "",
    refetchInterval: (q) => (q.state.data && roteiroMudando(q.state.data) ? POLL_MS : false),
  });
}

export function useRoteiroVersoes(id: string) {
  return useQuery({ queryKey: roteiroVersoesKey(id), queryFn: () => api.roteiros.versoes(id), enabled: id !== "" });
}

export function useRoteiroPadroes(perfilId: string) {
  return useQuery({ queryKey: roteiroPadroesKey(perfilId), queryFn: () => api.roteiros.padroes(perfilId), enabled: perfilId !== "" });
}

export function usePronuncias(perfilId: string, arquivadas: boolean) {
  return useQuery({ queryKey: pronunciasKey(perfilId, arquivadas), queryFn: () => api.pronuncias.listar(perfilId, arquivadas), enabled: perfilId !== "" });
}

export async function invalidarRoteiro(qc: QueryClient, id: string) {
  await Promise.all([
    qc.invalidateQueries({ queryKey: roteiroKey(id) }),
    qc.invalidateQueries({ queryKey: roteiroVersoesKey(id) }),
    qc.invalidateQueries({ queryKey: roteirosKey }),
  ]);
}

// Keyframe pronto (PNG/JPG/WebP, até 20 MB): vira o keyframe da cena sem passar pela GPU.
export const KEYFRAME_ACCEPT = "image/png,image/jpeg,image/webp";
export function enviarKeyframe(roteiroId: string, ordem: number, version: number, arquivo: File, onProgress: (f: number) => void = () => {}) {
  return uploadMultipart<Roteiro>(
    `/api/roteiros/${encodeURIComponent(roteiroId)}/posicoes/${ordem}/keyframe`,
    () => {
      const form = new FormData();
      form.append("version", String(version));
      form.append("arquivo", arquivo);
      return form;
    },
    onProgress,
  );
}

// ---------------------------------------------------------------------------------------------
// Histórico (snapshot de `entity_versions` do roteiro)

export const roteiroFieldLabel: Record<string, string> = {
  nome: "Nome",
  brief: "Brief",
  avatar_id: "Avatar",
  voz_id: "Voz",
  velocidade: "Velocidade",
  frases: "Frases",
  produtos: "Produtos",
  posicoes: "Cenas",
  modo: "Modo",
  portoes: "Portões",
  status: "Estado",
  etapa_falhou: "Etapa que falhou",
  formato: "Formato",
  perfil_id: "Perfil",
  archived: "Arquivado",
};

export function formatRoteiroValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (field === "status" && typeof value === "string") return statusRoteiroLabel[value as RoteiroStatus] ?? value;
  if (field === "modo" && typeof value === "string") return modoLabel[value as RoteiroModo] ?? value;
  if (field === "frases" && Array.isArray(value)) return value.map((f, i) => `${i + 1}. ${String(f)}`).join("\n");
  if (field === "portoes" && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => `${k}: ${v ? "ligado" : "desligado"}`)
      .join(", ");
  }
  if (Array.isArray(value)) return `${value.length} itens`;
  if (field.endsWith("_id") && typeof value === "string") return `${value.slice(0, 8)}…`;
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}
