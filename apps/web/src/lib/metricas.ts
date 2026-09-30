import { ApiError } from "@sociman/contract";
import { useInfiniteQuery, useQuery, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { conexaoKey } from "./publicacao";

// Métricas da TikTok (spec 016): estado da coleta na conta, vínculo do post com o destino,
// desempenho (curva e marcos), ranking e exportação. Tudo é leitura; ligar, escolher, colar e
// desfazer vínculo, reconectar e desconectar são só do dono humano (a API recusa o resto com 403).

import type {
  Candidato,
  Marcos,
  MarcoValor,
  MetricasContaFilters,
  MetricasVideosFilters,
  OrigemMetricas,
  VideoResumo,
  Vinculo,
  VinculoEstado,
  VinculoMetodo,
} from "@sociman/contract";

export type {
  Candidato,
  ContaMetricas,
  DestinoMetricas,
  EstadoColeta,
  FotoConta,
  FotoVideo,
  MarcoMetricas,
  Marcos,
  MarcoValor,
  MetricasExportFilters,
  MetricasVideosFilters,
  OrigemMetricas,
  PermissaoColeta,
  VideoDetalhe,
  VideoResumo,
  Vinculo,
  VinculoEstado,
  VinculoMetodo,
} from "@sociman/contract";

export type OrdemRanking = NonNullable<MetricasVideosFilters["ordem"]>;
export type Resolucao = NonNullable<MetricasContaFilters["resolucao"]>;
type Contador = "views" | "likes" | "comments" | "shares";

// ---------------------------------------------------------------------------------------------
// Chaves das queries

export const metricasContaKey = (contaId: string, filtros: object = {}) => ["metricas-conta", contaId, filtros] as const;
export const metricasVideosKey = (filtros: object) => ["metricas-videos", filtros] as const;
export const metricasVideoKey = (id: string) => ["metricas-video", id] as const;
export const destinoMetricasKey = (destinoId: string) => ["destino-metricas", destinoId] as const;

// Depois de ligar, desfazer, reconectar ou desconectar: métricas do destino, ranking, vídeos, contas
// e a conexão (o `EstadoColeta` vem nela).
export async function invalidarMetricas(queryClient: QueryClient, opts: { destinoId?: string; contaId?: string } = {}) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: opts.destinoId ? destinoMetricasKey(opts.destinoId) : ["destino-metricas"] }),
    queryClient.invalidateQueries({ queryKey: ["metricas-videos"] }),
    queryClient.invalidateQueries({ queryKey: ["metricas-video"] }),
    queryClient.invalidateQueries({ queryKey: opts.contaId ? ["metricas-conta", opts.contaId] : ["metricas-conta"] }),
    ...(opts.contaId ? [queryClient.invalidateQueries({ queryKey: conexaoKey(opts.contaId) })] : []),
  ]);
}

// ---------------------------------------------------------------------------------------------
// Rótulos

export const origemMetricasLabel: Record<OrigemMetricas, string> = {
  corte: "Corte",
  video_proprio: "Vídeo próprio",
  fora: "Fora do SociMan",
  anonima: "Conta anônima",
};

export const vinculoMetodoLabel: Record<VinculoMetodo, string> = {
  envio: "pelo envio",
  casamento: "pela lista de vídeos",
  link: "pelo link",
  escolha: "escolhido",
};

export const vinculoEstadoLabel: Record<VinculoEstado, string> = {
  vinculado: "Ligado ao post",
  buscando: "Procurando o post",
  a_confirmar: "Escolha o post",
  sem_vinculo: "Sem post ligado",
  indisponivel: "Post indisponível",
};

export const vinculoEstadoTone: Record<VinculoEstado, string> = {
  vinculado: "bg-success text-success-foreground",
  buscando: "bg-info text-info-foreground",
  a_confirmar: "bg-warning text-warning-foreground",
  sem_vinculo: "bg-secondary text-secondary-foreground",
  indisponivel: "bg-destructive text-destructive-foreground",
};

export const legendaCompatLabel: Record<Candidato["legenda"], string> = {
  compativel: "legenda parecida",
  neutra: "legenda curta",
  incompativel: "legenda diferente",
};

export const contadorLabel: Record<Contador, string> = {
  views: "Visualizações",
  likes: "Curtidas",
  comments: "Comentários",
  shares: "Compartilhamentos",
};

export const MARCOS = [
  { id: "h1", label: "1 h", horas: 1 },
  { id: "h24", label: "24 h", horas: 24 },
  { id: "d7", label: "7 dias", horas: 24 * 7 },
  { id: "d30", label: "30 dias", horas: 24 * 30 },
] as const satisfies readonly { id: keyof Marcos; label: string; horas: number }[];

export const ordemLabel: Record<OrdemRanking, string> = {
  views7d: "Visualizações em 7 dias",
  views24h: "Visualizações em 24 h",
  engajamento: "Engajamento",
  velocidade: "Velocidade (views/h)",
  publicadoEm: "Data de publicação",
};

export const escopoLabel: Record<string, string> = {
  "user.info.stats": "números da conta",
  "video.list": "lista de vídeos",
};

// ---------------------------------------------------------------------------------------------
// Formatação (datas em America/Sao_Paulo pelo lib/tz)

const inteiro = new Intl.NumberFormat("pt-BR");
const compacto = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
const pct = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 1 });

export const formatNumero = (n: number | null | undefined) => (n === null || n === undefined ? "—" : inteiro.format(n));
export const formatCompacto = (n: number | null | undefined) => (n === null || n === undefined ? "—" : n < 10_000 ? inteiro.format(n) : compacto.format(n));
export const formatEngajamento = (n: number | null | undefined) => (n === null || n === undefined ? "—" : pct.format(n));
export const formatVelocidade = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : `${n < 10 ? n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }) : inteiro.format(Math.round(n))}/h`;

// Idade em horas → "45 min", "12 h", "3 d".
export function formatIdadeHoras(h: number): string {
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 48) return `${Math.round(h * 10) / 10} h`.replace(".", ",");
  return `${Math.round((h / 24) * 10) / 10} d`.replace(".", ",");
}

// "0:42" / "1:05".
export function formatDuracaoS(s: number | null | undefined): string {
  if (s === null || s === undefined) return "—";
  const t = Math.round(s);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

// Minutos em relação à âncora: "12 min depois", "3 h antes".
export function formatDistancia(min: number): string {
  const abs = Math.abs(min);
  const txt = abs < 60 ? `${abs} min` : abs < 48 * 60 ? `${Math.round(abs / 6) / 10} h`.replace(".", ",") : `${Math.round(abs / 144) / 10} dias`.replace(".", ",");
  return min < 0 ? `${txt} antes` : `${txt} depois`;
}

// Link de um vídeo no SociMan: o conteúdo (na aba da conta) quando ligado, senão a página do vídeo.
export function linkDoVideo(v: Pick<VideoResumo, "id" | "conteudoId" | "contaId">): string {
  if (v.conteudoId) return `/app/conteudos/${v.conteudoId}${v.contaId ? `?conta=${v.contaId}` : ""}`;
  return `/app/metricas/videos/${v.id}`;
}

export const nomeDaConta = (v: Pick<VideoResumo, "conta" | "serieRotulo">) => (v.conta ? `@${v.conta.handle.replace(/^@/, "")}` : (v.serieRotulo ?? "Conta anônima"));

// 409 `confirmar_anonimizacao` ao desconectar: o que será anonimizado.
export function anonimizacaoPendente(err: unknown): { videos: number; fotos: number; conta: string | null } | null {
  if (!(err instanceof ApiError) || err.code !== "confirmar_anonimizacao") return null;
  const d = err.details;
  return {
    videos: typeof d.videos === "number" ? d.videos : 0,
    fotos: typeof d.fotos === "number" ? d.fotos : 0,
    conta: typeof d.conta === "string" ? d.conta : null,
  };
}

// Texto de R13 (o mesmo na confirmação antecipada e depois do 409).
export function textoAnonimizacao(conta: string, videos: number, fotos: number): string {
  const n = `${inteiro.format(videos)} ${videos === 1 ? "vídeo" : "vídeos"}, ${inteiro.format(fotos)} ${fotos === 1 ? "foto" : "fotos"}`;
  return `As métricas de ${conta} (${n}) serão anonimizadas: os números ficam, mas sem a conta, os links, as legendas e o elo com os conteúdos. Isso não pode ser desfeito.`;
}

// ---------------------------------------------------------------------------------------------
// Queries

export function useDestinoMetricas(destinoId: string, enabled = true) {
  return useQuery({ queryKey: destinoMetricasKey(destinoId), queryFn: () => api.destinos.metricas(destinoId), enabled });
}

export function useMetricasVideo(id: string) {
  return useQuery({ queryKey: metricasVideoKey(id), queryFn: () => api.metricas.video(id), enabled: Boolean(id) });
}

export function useMetricasConta(contaId: string, filtros: { de?: string; ate?: string; resolucao?: Resolucao }) {
  return useQuery({
    queryKey: metricasContaKey(contaId, filtros),
    queryFn: () => api.metricas.conta(contaId, filtros),
    enabled: Boolean(contaId),
  });
}

export const RANKING_LIMITE = 50;

export function useRanking(filtros: MetricasVideosFilters) {
  return useInfiniteQuery({
    queryKey: metricasVideosKey(filtros),
    queryFn: ({ pageParam }) => api.metricas.videos({ ...filtros, limite: RANKING_LIMITE, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });
}
