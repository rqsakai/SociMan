import { ApiError, type ConexaoEstado, type Criador, type Destino, type Modo, type OpcoesTikTok, type PublicacaoConfig, type Tentativa, type TentativaFase } from "@sociman/contract";
import { useQuery, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";

export type { Conexao, ConexaoEstado, Criador, PublicacaoConfig, Tentativa, TentativaFase } from "@sociman/contract";

// Envio automático para a rede (spec 015): conexão da conta, interruptor "Publicação automática",
// fases das tentativas e rótulos em pt-BR. Tudo o que conecta, agenda em modo automático, tenta
// de novo ou confirma envio é só do dono humano (a API recusa o resto com 403).

export const conexaoKey = (contaId: string) => ["conexao", contaId] as const;
export const conexaoVersionsKey = (contaId: string) => ["conexao-versions", contaId] as const;
export const publicacaoConfigKey = ["publicacao-config"] as const;
export const publicacaoConfigVersionsKey = ["publicacao-config-versions"] as const;
export const tentativasKey = (destinoId: string) => ["tentativas", destinoId] as const;

// ---------------------------------------------------------------------------------------------
// Conexão da conta

export const conexaoEstadoLabel: Record<ConexaoEstado, string> = {
  nao_conectada: "Não conectada",
  conectada: "Conectada",
  precisa_reconectar: "Precisa reconectar",
};

export const conexaoEstadoTone: Record<ConexaoEstado, string> = {
  nao_conectada: "bg-secondary text-secondary-foreground",
  conectada: "bg-success text-success-foreground",
  precisa_reconectar: "bg-destructive text-destructive-foreground",
};

// Título do erro do login (a mensagem detalhada vem da API, em pt-BR).
export const conexaoErroTitulo: Record<string, string> = {
  conta_diferente: "Você entrou com outra conta da TikTok",
  escopo_faltando: "Faltou autorizar uma permissão",
  endereco_de_login: "Abra o SociMan no outro endereço",
  state_invalido: "O login expirou ou já foi usado",
  autorizacao_negada: "A autorização foi negada",
  conexao_em_uso: "Esta conta da TikTok já está conectada a outra conta do SociMan",
  identidade_indisponivel: "A TikTok não informou a identidade da conta",
  publicacao_nao_configurada: "O app da TikTok não está configurado no servidor",
  ja_conectada: "A conta já está conectada",
  rede_indisponivel: "A TikTok não respondeu",
  somente_humano: "Só um dono, pela tela do SociMan",
};

export function useConexao(contaId: string | null | undefined) {
  return useQuery({
    queryKey: conexaoKey(contaId ?? ""),
    queryFn: () => api.conexoes.get(contaId!),
    enabled: Boolean(contaId),
  });
}

// Conta que o dono estava conectando: a página de retorno usa para "Tentar de novo" e para voltar
// ao perfil quando a TikTok recusa (o `state` é opaco). Só sessionStorage, com try/catch.
const PENDENTE_KEY = "sociman.conexao.pendente";

export function guardarConexaoPendente(p: { contaId: string; perfilId: string }): void {
  try {
    window.sessionStorage.setItem(PENDENTE_KEY, JSON.stringify(p));
  } catch {
    // sem armazenamento: o retorno ainda funciona, só sem o "Tentar de novo" direto
  }
}

export function lerConexaoPendente(): { contaId: string; perfilId: string } | null {
  try {
    const raw = window.sessionStorage.getItem(PENDENTE_KEY);
    const v = raw ? (JSON.parse(raw) as unknown) : null;
    if (v && typeof v === "object" && typeof (v as { contaId?: unknown }).contaId === "string" && typeof (v as { perfilId?: unknown }).perfilId === "string") {
      return v as { contaId: string; perfilId: string };
    }
  } catch {
    // ignora
  }
  return null;
}

export function limparConexaoPendente(): void {
  try {
    window.sessionStorage.removeItem(PENDENTE_KEY);
  } catch {
    // ignora
  }
}

// Inicia o login oficial: a API devolve a URL da TikTok e o navegador sai do SociMan.
export async function iniciarConexao(contaId: string, perfilId: string): Promise<void> {
  const { autorizarUrl } = await api.conexoes.iniciar(contaId);
  guardarConexaoPendente({ contaId, perfilId });
  window.location.assign(autorizarUrl);
}

// 409 `endereco_de_login`: o login só funciona em outro endereço do SociMan.
export function abrirEm(err: unknown): string | null {
  if (!(err instanceof ApiError) || err.code !== "endereco_de_login") return null;
  return typeof err.details.abrirEm === "string" ? err.details.abrirEm : null;
}

// ---------------------------------------------------------------------------------------------
// Interruptor "Publicação automática"

export const situacaoAppLabel: Record<string, string> = {
  sandbox: "Sandbox (sem auditoria da TikTok)",
  auditado: "Auditado",
};

export function usePublicacaoConfig() {
  return useQuery({ queryKey: publicacaoConfigKey, queryFn: () => api.publicacao.config(), staleTime: 30_000 });
}

// Os dois níveis precisam estar ligados para qualquer envio (Clarifications Q3).
export const enviosLigados = (c: PublicacaoConfig | undefined) => Boolean(c?.servidorHabilitado && c?.enviosHabilitados);

export function enviosDesligadosTexto(c: PublicacaoConfig): string {
  if (!c.servidorHabilitado) return "O servidor está com a publicação desligada (PUBLICACAO_HABILITADA no .env).";
  return "O interruptor \"Publicação automática\" está desligado.";
}

export const AVISO_SANDBOX =
  "O app da TikTok está em sandbox: só as contas liberadas no portal da TikTok recebem o rascunho.";

// ---------------------------------------------------------------------------------------------
// Modos e execução

export const MODOS_AUTOMATICOS: Modo[] = ["criar_rascunho", "publicar", "rascunho_e_publicar"];
export const ehAutomatico = (modo: Modo | string) => MODOS_AUTOMATICOS.includes(modo as Modo);

export const faseLabel: Record<TentativaFase, string> = {
  iniciando: "Iniciando",
  enviando_partes: "Enviando o vídeo",
  processando: "A TikTok está processando",
  entregue: "Rascunho entregue",
  publicada: "Publicada",
  recusada: "Recusada",
  incerta: "Sem confirmação",
  sem_vaga: "Sem vaga",
};

export const faseTone: Record<TentativaFase, string> = {
  iniciando: "bg-info text-info-foreground",
  enviando_partes: "bg-info text-info-foreground",
  processando: "bg-info text-info-foreground",
  entregue: "bg-success text-success-foreground",
  publicada: "bg-success text-success-foreground",
  recusada: "bg-destructive text-destructive-foreground",
  incerta: "bg-warning text-warning-foreground",
  sem_vaga: "bg-warning text-warning-foreground",
};

export const disparoLabel: Record<string, string> = {
  agendador: "No horário",
  tentar_de_novo: "Tentar de novo",
  confirmado: "Envio confirmado",
};

// Percentual das partes enviadas (0 a 100), ou null antes de saber o total.
export function progressoPartes(t: Pick<Tentativa, "partesEnviadas" | "totalPartes"> | null | undefined): number | null {
  if (!t || t.totalPartes <= 0) return null;
  return Math.min(100, Math.round((t.partesEnviadas / t.totalPartes) * 100));
}

export function formatBytes(n: number): string {
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} KB`;
  return `${(n / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}

export function useTentativas(destinoId: string, enabled = true) {
  return useQuery({ queryKey: tentativasKey(destinoId), queryFn: () => api.destinos.tentativas(destinoId), enabled });
}

// Enquanto envia, o painel consulta de novo a cada 5 s (a trilha roda a cada 15 s).
export const execucaoAtiva = (d: Pick<Destino, "estado" | "estadoEfetivo">) => d.estado === "enviando" || d.estadoEfetivo === "aguardando_vaga";

export async function invalidarPublicacao(queryClient: QueryClient, destinoId?: string) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: publicacaoConfigKey }),
    ...(destinoId ? [queryClient.invalidateQueries({ queryKey: tentativasKey(destinoId) })] : []),
  ]);
}

// Rótulos dos campos novos no snapshot do destino e da configuração (data-model).
export const destinoFieldLabel015: Record<string, string> = {
  agendado_por: "Agendado por",
  opcoes_rede: "Opções da rede",
  envio_snapshot: "O que será enviado",
  envio_confirmado_por: "Envio confirmado por",
  falha_motivo: "Motivo da falha",
  rede_post_id: "Post na rede",
};

export const conexaoFieldLabel: Record<string, string> = {
  open_id: "Identificador na rede",
  username: "@",
  display_name: "Apelido",
  escopos: "Permissões",
  estado: "Estado",
  motivo: "Motivo",
  conectado_por: "Conectada por",
  desconectado_em: "Desconectada em",
  desconectado_por: "Desconectada por",
};

export const publicacaoConfigFieldLabel: Record<string, string> = { envios_habilitados: "Publicação automática" };

// ---------------------------------------------------------------------------------------------
// Publicar no horário (US3, research R13): a tela obrigatória da TikTok.

export type Privacidade = OpcoesTikTok["privacidade"];
export type Comercial = NonNullable<OpcoesTikTok["comercial"]>;

export const PRIVACIDADES: Privacidade[] = ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"];

export const privacidadeLabel: Record<Privacidade, string> = {
  PUBLIC_TO_EVERYONE: "Todos",
  MUTUAL_FOLLOW_FRIENDS: "Amigos (seguidores mútuos)",
  FOLLOWER_OF_CREATOR: "Seguidores",
  SELF_ONLY: "Só eu",
};

export const comercialLabel: Record<Comercial, string> = {
  nenhum: "Nenhuma",
  sua_marca: "Sua marca (conteúdo promocional)",
  parceria_paga: "Conteúdo de marca (parceria paga)",
};

// Frase de consentimento (a mesma de `publicacao/tiktok/opcoes.py`) que a TikTok exige ao lado do botão (música; com conteúdo de marca, também
// a Política de Conteúdo de Marca). Vai no `consentimento.texto` exatamente como foi exibida.
export function consentimentoTexto(comercial: Comercial): string {
  return comercial === "parceria_paga"
    ? "Ao postar, você concorda com a Política de Conteúdo de Marca e com a Confirmação de Uso de Música da TikTok."
    : "Ao postar, você concorda com a Confirmação de Uso de Música da TikTok.";
}

// Combinações que a TikTok recusa (a API valida de novo: 400 `opcoes_invalidas`).
export function opcoesProblemas(
  c: Pick<Criador, "privacyLevelOptions">,
  o: { privacidade: Privacidade | ""; comercial: Comercial },
): string[] {
  const out: string[] = [];
  if (o.privacidade && !c.privacyLevelOptions.includes(o.privacidade)) out.push("Esta privacidade não está disponível para a conta.");
  if (o.comercial === "parceria_paga" && o.privacidade === "SELF_ONLY") out.push("Parceria paga não pode ser publicada como \"só você\"");
  return out;
}

// 400 `opcoes_invalidas`: os motivos (`details.problemas`) das regras que a API recusou.
export function problemasDaApi(err: unknown): string[] {
  if (!(err instanceof ApiError) || err.code !== "opcoes_invalidas") return [];
  const p = err.details.problemas;
  if (!Array.isArray(p)) return [];
  // `[{campo, motivo}]` (a API) ou texto simples
  return p
    .map((x: unknown) => (typeof x === "string" ? x : x && typeof x === "object" && typeof (x as { motivo?: unknown }).motivo === "string" ? (x as { motivo: string }).motivo : null))
    .filter((x): x is string => x !== null);
}

// Ação possível depois de uma falha (R19; `Tentativa.acao` vem como código).
export const acaoLabel: Record<string, string> = {
  tentar_de_novo: "Tente de novo.",
  tentar_de_novo_conferido: "Confira no app se chegou antes de tentar de novo.",
  reagendar: "Reagende e escolha de novo.",
  reconectar: "Reconecte a conta na aba Contas do perfil.",
  trocar_video: "Troque o vídeo e tente de novo.",
  deixar_privada: "Deixe a conta privada no app e tente de novo.",
  verificar_app: "Verifique a conta no app da rede.",
  esperar: "O SociMan tenta de novo sozinho.",
};
export const acaoTexto = (acao: string | null | undefined) => (acao ? (acaoLabel[acao] ?? acao) : null);
