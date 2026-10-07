import createClient from "openapi-fetch";
import { isErrorCode, type ErrorCode } from "./errors";
import type { components, paths } from "./generated/schema";

export type User = components["schemas"]["User"];
export type AuthSession = components["schemas"]["AuthSession"];
export type AppConfig = components["schemas"]["AppConfig"];
export type LoginRequest = components["schemas"]["LoginIn"];
export type ChangePasswordRequest = components["schemas"]["ChangePasswordIn"];
export type CreateUserRequest = components["schemas"]["CreateUserIn"];
export type UpdateUserRequest = components["schemas"]["UpdateUserIn"];
export type SetPasswordRequest = components["schemas"]["SetPasswordIn"];
export type ForgotPasswordRequest = components["schemas"]["ForgotIn"];
export type ResetPasswordRequest = components["schemas"]["ResetIn"];
export type SecurityEvent = components["schemas"]["SecurityEvent"];
export type SecurityEventPage = components["schemas"]["SecurityEventPage"];
export type Perfil = components["schemas"]["Perfil"];
export type PerfilStatus = components["schemas"]["PerfilStatus"];
export type Conta = components["schemas"]["Conta"];
export type ContaStatus = components["schemas"]["ContaStatus"];
export type Platform = components["schemas"]["Platform"];
export type ImageRef = components["schemas"]["ImageRef"];
export type EntityVersion = components["schemas"]["Version"];
export type CreatePerfilRequest = components["schemas"]["CreatePerfilIn"];
export type UpdatePerfilRequest = components["schemas"]["UpdatePerfilIn"];
export type CreateContaRequest = components["schemas"]["CreateContaIn"];
export type UpdateContaRequest = components["schemas"]["UpdateContaIn"];
export type PerfilFilters = NonNullable<paths["/api/perfis"]["get"]["parameters"]["query"]>;
export type ImageKind = "logo" | "banner";
// 004-kit-de-marca
export type Kit = components["schemas"]["Kit"];
export type KitIn = components["schemas"]["KitIn"];
export type KitExport = components["schemas"]["KitExport"];
export type FontOption = components["schemas"]["FontOption"];
export type Cor = components["schemas"]["Cor"];
export type Legenda = components["schemas"]["Legenda"];
export type Gancho = components["schemas"]["Gancho"];
export type MarcaDagua = components["schemas"]["MarcaDagua"];
export type CardFinal = components["schemas"]["CardFinal"];
export type UserRef = components["schemas"]["UserRef"];
export type Fonte = components["schemas"]["Fonte"];
export type FontePadrao = components["schemas"]["FontePadrao"];
export type Corte = components["schemas"]["Corte"];
export type CorteStatus = components["schemas"]["CorteStatus"];
export type Armazenamento = components["schemas"]["Armazenamento"];
export type MidiaLink = components["schemas"]["MidiaLink"];
export type MidiaKind = "corte_original" | "corte_marcado" | "fonte" | "marca_dagua" | "fundo" | "imagem" | "conteudo_video";
export type CorteFilters = NonNullable<paths["/api/perfis/{perfil_id}/cortes"]["get"]["parameters"]["query"]>;
// 021-geracao-local
export type GeracaoDetalhe = components["schemas"]["GeracaoDetalhe"];
export type GeracaoResumo = components["schemas"]["GeracaoResumo"];
export type GeracaoEscolhida = components["schemas"]["GeracaoEscolhida"];
export type GeracaoInRequest = components["schemas"]["GeracaoIn"];
export type GeracaoStatus = components["schemas"]["GeracaoStatus"];
export type GeracaoAlvo = components["schemas"]["GeracaoAlvo"];
export type CandidatoGeracao = components["schemas"]["CandidatoGeracao"];
export type ImagemCandidato = components["schemas"]["ImagemCandidato"];
export type AudioPerfil = components["schemas"]["Audio"];
export type GeracaoFilters = NonNullable<paths["/api/perfis/{perfil_id}/geracoes"]["get"]["parameters"]["query"]>;
// 007-assets-do-perfil
export type Asset = components["schemas"]["Asset"];
export type AssetSummary = components["schemas"]["AssetSummary"];
export type AssetFile = components["schemas"]["AssetFile"];
export type AssetTipo = components["schemas"]["AssetTipo"];
export type FileRole = components["schemas"]["FileRole"];
export type Uso = components["schemas"]["Uso"];
export type LibraryImage = components["schemas"]["LibraryImage"];
export type TagCount = components["schemas"]["TagCount"];
export type AssetCreateRequest = components["schemas"]["AssetCreate"];
export type AssetPatchRequest = components["schemas"]["AssetPatch"];
export type FilePatchRequest = components["schemas"]["FilePatch"];
export type OrdemRequest = components["schemas"]["Ordem"];
export type AssetFilters = NonNullable<paths["/api/perfis/{perfil_id}/assets"]["get"]["parameters"]["query"]>;
export type LibraryImageFilters = paths["/api/perfis/{perfil_id}/assets/imagens"]["get"]["parameters"]["query"];
// 006-cortes-openshorts
export type Notificacao = components["schemas"]["Notificacao"];
export type NotificacaoTipo = components["schemas"]["NotificacaoTipo"];
export type NotificacaoFilters = NonNullable<paths["/api/notificacoes"]["get"]["parameters"]["query"]>;
export type CanalFonte = components["schemas"]["CanalFonte"];
export type CanalCandidato = components["schemas"]["CanalCandidato"];
export type CanalSyncStatus = components["schemas"]["CanalSync"];
export type Direito = components["schemas"]["CanalDireito"];
export type DireitoEnvio = components["schemas"]["DireitoEnvio"];
export type CreateCanalRequest = components["schemas"]["CreateCanalIn"];
export type UpdateCanalRequest = components["schemas"]["UpdateCanalIn"];
export type DireitoRequest = components["schemas"]["DireitoIn"];
export type CanalFilters = NonNullable<paths["/api/canais"]["get"]["parameters"]["query"]>;
export type VideoFonte = components["schemas"]["VideoFonte"];
export type VideoFonteFilters = NonNullable<paths["/api/videos-fonte"]["get"]["parameters"]["query"]>;
export type PadroesCorte = components["schemas"]["PadroesCorte"];
export type PadroesCorteRequest = components["schemas"]["PadroesCorteIn"];
export type Envio = components["schemas"]["Envio"];
export type EnvioStatus = components["schemas"]["EnvioStatus"];
export type EnvioEtapa = components["schemas"]["EnvioEtapa"];
export type EnvioConfig = components["schemas"]["EnvioConfig"];
// Campos com default no servidor saem obrigatórios no tipo gerado; aqui ficam opcionais.
type Defaulted<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;
export type SelecionarRequest = Defaulted<components["schemas"]["SelecionarIn"], "confirmarDuplicado">;
export type EnviarRequest = Defaulted<components["schemas"]["EnviarIn"], "confirmarAviso" | "confirmarDuplicado">;
export type EnvioFilters = NonNullable<paths["/api/envios"]["get"]["parameters"]["query"]>;
export type Sugestao = components["schemas"]["Sugestao"];
export type CalendarioItem = components["schemas"]["CalendarioItem"];
export type CalendarioSemData = components["schemas"]["SemData"];
export type CalendarioFilters = paths["/api/calendario"]["get"]["parameters"]["query"];
export type Integracoes = components["schemas"]["Integracoes"];
// 008-assistente-ia
export type TipoCampo = components["schemas"]["TipoCampo"];
export type TipoCampoId = TipoCampo["id"];
export type IaLimites = components["schemas"]["Limites"];
export type IaRegras = components["schemas"]["Regras"];
export type IaAlvo = components["schemas"]["Alvo"];
export type IaValor = components["schemas"]["Valor"];
export type IaSelecao = components["schemas"]["Selecao"];
export type IaChamada = components["schemas"]["IaChamada"];
export type IaDesfecho = IaChamada["desfecho"];
export type IaAplicacao = components["schemas"]["IaAplicacao"];
export type IaGerarRequest = components["schemas"]["GerarIn"];
export type IaResumo = components["schemas"]["IaResumo"];
export type IaChamadaFilters = NonNullable<paths["/api/ia/chamadas"]["get"]["parameters"]["query"]>;
// 017-guia-de-comunicacao
export type Guia = components["schemas"]["Guia"];
export type GuiaCampos = components["schemas"]["GuiaCampos"];
export type GuiaLimites = components["schemas"]["GuiaLimites"];
export type GuiaEfetivo = components["schemas"]["GuiaEfetivo"];
export type GuiaConflito = components["schemas"]["Conflito"];
export type GuiaContaOut = components["schemas"]["GuiaContaOut"];
export type GuiaIn = components["schemas"]["GuiaIn"];
export type GuiaEmojis = NonNullable<GuiaCampos["emojis"]>;
export type GuiaExemplo = components["schemas"]["Exemplo"];
export type GuiaMontarRequest = components["schemas"]["MontarIn"];
export type GuiaTestarRequest = components["schemas"]["TestarIn"];
export type GuiaVariacao = components["schemas"]["Variacao"];
// 014-central-de-conteudos
export type Origem = components["schemas"]["ConteudoOrigem"];
export type Situacao = components["schemas"]["Situacao"];
export type DestinoEstado = components["schemas"]["DestinoEstado"];
export type EstadoEfetivo = components["schemas"]["EstadoEfetivo"];
export type Modo = components["schemas"]["Modo"];
export type ModoInfo = components["schemas"]["ModoInfo"];
export type DestinoResumo = components["schemas"]["DestinoResumo"];
export type Destino = components["schemas"]["Destino"];
export type ConteudoItem = components["schemas"]["ConteudoItem"];
export type Conteudo = components["schemas"]["Conteudo"];
export type Atalhos = components["schemas"]["Atalhos"];
export type LoteResultado = components["schemas"]["LoteResultado"];
export type SlotSequencia = components["schemas"]["SlotSequencia"];
export type Previa = components["schemas"]["Previa"];
export type PropostaOpenshorts = components["schemas"]["PropostaOpenshorts"];
export type ConteudoFilters = NonNullable<paths["/api/conteudos"]["get"]["parameters"]["query"]>;
export type ResumoFilters = NonNullable<paths["/api/conteudos/resumo"]["get"]["parameters"]["query"]>;
export type CreateDestinoRequest = components["schemas"]["CreateDestinoIn"];
export type UpdateDestinoRequest = components["schemas"]["UpdateDestinoIn"];
export type AgendarRequest = Defaulted<components["schemas"]["AgendarIn"], "ignorarIntervalo">;
export type ReagendarRequest = Defaulted<components["schemas"]["ReagendarIn"], "ignorarIntervalo">;
export type LoteReagendarRequest = Defaulted<components["schemas"]["LoteReagendarIn"], "ignorarIntervalo">;
export type SequenciaRequest = components["schemas"]["SequenciaIn"];
export type SequenciaConfirmarRequest = components["schemas"]["SequenciaConfirmarIn"];
// 015-tiktok-rascunho
export type Conexao = components["schemas"]["Conexao"];
export type ConexaoEstado = Conexao["estado"];
export type Criador = components["schemas"]["Criador"];
export type PublicacaoConfig = components["schemas"]["PublicacaoConfig"];
export type Tentativa = components["schemas"]["Tentativa"];
export type TentativaFase = Tentativa["fase"];
export type OpcoesTikTok = components["schemas"]["OpcoesTikTok"];
export type RetornoRequest = components["schemas"]["RetornoIn"];
// 016-metricas-tiktok
export type EstadoColeta = components["schemas"]["EstadoColeta"];
export type PermissaoColeta = EstadoColeta["permissao"];
export type FotoVideo = components["schemas"]["FotoVideo"];
export type FotoConta = components["schemas"]["FotoConta"];
export type MarcoValor = components["schemas"]["MarcoValor"];
export type MarcoMetricas = components["schemas"]["MarcoMetricas"];
export type Marcos = components["schemas"]["Marcos"];
export type VideoResumo = components["schemas"]["VideoResumo"];
export type VideoDetalhe = components["schemas"]["VideoDetalhe"];
export type OrigemMetricas = VideoResumo["origem"];
export type VinculoMetodo = NonNullable<VideoResumo["vinculoMetodo"]>;
export type Candidato = components["schemas"]["Candidato"];
export type Vinculo = components["schemas"]["Vinculo"];
export type VinculoEstado = Vinculo["estado"];
export type VinculoRequest = components["schemas"]["VinculoIn"];
export type ContaMetricas = components["schemas"]["ContaMetricasOut"];
export type DestinoMetricas = components["schemas"]["DestinoMetricasOut"];
export type MetricasContaFilters = NonNullable<paths["/api/contas/{conta_id}/metricas"]["get"]["parameters"]["query"]>;
export type MetricasVideosFilters = NonNullable<paths["/api/metricas/videos"]["get"]["parameters"]["query"]>;
export type MetricasExportFilters = NonNullable<paths["/api/metricas/export"]["get"]["parameters"]["query"]>;
// 019-analytics
export type AnalyticsFiltros = NonNullable<paths["/api/analytics/visao-geral"]["get"]["parameters"]["query"]>;
export type AnalyticsFunilFiltros = NonNullable<paths["/api/analytics/funil"]["get"]["parameters"]["query"]>;
export type AnalyticsContexto = components["schemas"]["Contexto"];
export type AnalyticsContaOrdem = components["schemas"]["ContaOrdem"];
export type AnalyticsAmostra = components["schemas"]["Amostra"];
export type AnalyticsMedida = components["schemas"]["Medida"];
export type AnalyticsIndicador = components["schemas"]["Indicador"];
export type AnalyticsInsight = components["schemas"]["Insight"];
export type AnalyticsPostResumo = components["schemas"]["PostResumo"];
export type AnalyticsCelulaMapa = components["schemas"]["CelulaMapa"];
export type AnalyticsLinhaRanking = components["schemas"]["LinhaRanking"];
export type AnalyticsDispersao = components["schemas"]["Dispersao"];
export type AnalyticsCurva = components["schemas"]["Curva"];
export type AnalyticsDistribuicaoConta = components["schemas"]["DistribuicaoConta"];
export type AnalyticsRadarConta = components["schemas"]["RadarConta"];
export type AnalyticsEtapaFunil = components["schemas"]["EtapaFunil"];
export type AnalyticsOportunidade = components["schemas"]["Oportunidade"];
export type AnalyticsAlerta = components["schemas"]["Alerta"];
export type AnalyticsVisaoGeral = components["schemas"]["VisaoGeralOut"];
export type AnalyticsQuandoPostar = components["schemas"]["QuandoPostarOut"];
export type AnalyticsOQueFunciona = components["schemas"]["OQueFuncionaOut"];
export type AnalyticsCurvas = components["schemas"]["CurvasOut"];
export type AnalyticsContas = components["schemas"]["ContasOut"];
export type AnalyticsFunil = components["schemas"]["FunilOut"];
export type AnalyticsMercado = components["schemas"]["MercadoOut"];
export type AnalyticsAlertas = components["schemas"]["AlertasOut"];
// 022-publico
export type AnalyticsPublico = components["schemas"]["PublicoOut"];
export type AnalyticsPublicoConta = components["schemas"]["PublicoContaOut"];
export type AnalyticsPublicoContaRef = components["schemas"]["PublicoConta"];
export type AnalyticsPublicoDistribuicao = components["schemas"]["PublicoDistribuicao"];
export type AnalyticsPublicoAtividade = components["schemas"]["PublicoAtividade"];
export type AnalyticsPublicoAtividadeConta = components["schemas"]["PublicoAtividadeConta"];
export type AnalyticsPublicoEspectadores = components["schemas"]["PublicoEspectadores"];
export type StudioSecaoPublicoPrevia = components["schemas"]["SecaoPublicoPrevia"];
export type StudioCoberturaPublico = components["schemas"]["CoberturaPublico"];
// 020-historico-tiktok-studio (pelas rotas: o nome da classe Previa colide com outra no OpenAPI)
type StudioJson<T> = T extends { content: { "application/json": infer B } } ? B : never;
export type StudioPrevia = StudioJson<paths["/api/contas/{conta_id}/studio/previa"]["post"]["responses"]["201"]>;
export type StudioImportacao = components["schemas"]["Importacao"];
export type StudioCobertura = components["schemas"]["Cobertura"];
// 013-importacao (tipos pelas rotas: os nomes das classes da API colidem com os de outras specs)
type AgenciaJson<T> = T extends { content: { "application/json": infer B } } ? B : never;
export type AgenciaEstado = AgenciaJson<paths["/api/agencia/estado"]["get"]["responses"]["200"]>;
export type AgenciaPrevia = AgenciaJson<paths["/api/agencia/previa"]["post"]["responses"]["201"]>;
export type AgenciaImportacao = AgenciaJson<paths["/api/agencia/importacoes/{importacao_id}"]["get"]["responses"]["200"]>;
export type AgenciaImportacaoResumo = AgenciaJson<paths["/api/agencia/importacoes"]["get"]["responses"]["200"]>["items"][number];
export type AgenciaConfirmarRequest = NonNullable<paths["/api/agencia/importacoes"]["post"]["requestBody"]>["content"]["application/json"];
// 009-mcp (tipos pelas rotas, para não depender do nome das classes da API)
type Json<T> = T extends { content: { "application/json": infer B } } ? B : never;
export type McpCliente = Json<paths["/api/mcp/clientes/{cliente_id}"]["get"]["responses"][200]>["cliente"];
export type McpEscopo = McpCliente["escopo"];
export type McpSituacao = McpCliente["situacao"];
export type McpClienteFilters = NonNullable<paths["/api/mcp/clientes"]["get"]["parameters"]["query"]>;
export type McpClienteCreateRequest = NonNullable<paths["/api/mcp/clientes"]["post"]["requestBody"]>["content"]["application/json"];
export type McpClienteUpdateRequest = NonNullable<paths["/api/mcp/clientes/{cliente_id}"]["patch"]["requestBody"]>["content"]["application/json"];
export type McpConfig = Json<paths["/api/mcp/config"]["get"]["responses"][200]>;
export type McpChamada = Json<paths["/api/mcp/chamadas"]["get"]["responses"][200]>["chamadas"][number];
export type McpChamadaFilters = NonNullable<paths["/api/mcp/chamadas"]["get"]["parameters"]["query"]>;
export type Anotacao = Json<paths["/api/anotacoes/{anotacao_id}"]["get"]["responses"][200]>["anotacao"];
export type AnotacaoFilters = NonNullable<paths["/api/anotacoes"]["get"]["parameters"]["query"]>;
export type AnotacaoCreateRequest = NonNullable<paths["/api/anotacoes"]["post"]["requestBody"]>["content"]["application/json"];
export type AnotacaoResumoFilters = NonNullable<paths["/api/anotacoes/resumo"]["get"]["parameters"]["query"]>;
// 010-cenas
export type Cena = components["schemas"]["Cena"];
export type CenaResumo = components["schemas"]["CenaResumo"];
export type CenaStatus = components["schemas"]["CenaStatus"];
export type CenaModo = components["schemas"]["CenaModo"];
export type CenaPlano = components["schemas"]["CenaPlano"];
export type CenaMovimento = components["schemas"]["CenaMovimento"];
export type CenaTomada = components["schemas"]["Tomada"];
export type CenaPadroes = components["schemas"]["CenaPadroes"];
export type CenaAviso = Cena["avisos"][number]; // pelo Cena: o nome "Aviso" colide com o da 020
export type CenaIngrediente = components["schemas"]["Ingrediente"];
export type CenaPrompt = components["schemas"]["PromptOut"];
export type CenaCreateRequest = components["schemas"]["CenaIn"];
export type CenaPatchRequest = components["schemas"]["CenaPatch"];
export type AnotacaoCamposTexto = components["schemas"]["CamposProposta"];
export type AnotacaoCamposCena = components["schemas"]["CamposCena"];
export type CenaFilters = NonNullable<paths["/api/perfis/{perfil_id}/cenas"]["get"]["parameters"]["query"]>;
// 023-aprendizado
type S = components["schemas"];
export type AprendizadoTema = S["AprendizadoTema"];
export type AprendizadoTemaIn = S["AprendizadoTemaIn"];
export type AprendizadoTemaPatch = S["AprendizadoTemaPatch"];
export type AprendizadoClassificacao = S["AprendizadoClassificacao"];
export type AprendizadoClassificacaoPut = S["AprendizadoClassificacaoPut"];
export type AprendizadoClassificacoesFiltros = NonNullable<paths["/api/perfis/{perfil_id}/aprendizado/classificacoes"]["get"]["parameters"]["query"]>;
export type AprendizadoAnaliseFiltros = NonNullable<paths["/api/perfis/{perfil_id}/aprendizado/analise"]["get"]["parameters"]["query"]>;
export type AprendizadoDiagnosticoFiltros = NonNullable<paths["/api/perfis/{perfil_id}/aprendizado/diagnostico"]["get"]["parameters"]["query"]>;
export type AprendizadoAnalise = S["AprendizadoAnalise"];
export type AprendizadoAnaliseContexto = S["AprendizadoAnaliseContexto"];
export type AprendizadoEfeito = S["AprendizadoEfeito"];
export type AprendizadoAviso = S["AprendizadoAviso"];
export type AprendizadoBloco = S["AprendizadoBloco"];
export type AprendizadoCelulaMatriz = S["AprendizadoCelulaMatriz"];
export type AprendizadoConstantes = S["AprendizadoConstantes"];
export type AprendizadoRecomendacao = S["AprendizadoRecomendacao"];
export type AprendizadoDecisao = S["AprendizadoDecisao"];
export type AprendizadoDecidirIn = S["AprendizadoDecidirIn"];
export type AprendizadoPreferencias = S["AprendizadoPreferencias"];
export type AprendizadoPreferenciasOut = S["AprendizadoPreferenciasOut"];
export type AprendizadoPreferenciasEfetivas = S["AprendizadoPreferenciasEfetivas"];
export type AprendizadoPreferenciasPatch = S["AprendizadoPreferenciasPatch"];
export type AprendizadoPadrao = S["AprendizadoPadrao"];
export type AprendizadoAnaliseIa = S["AprendizadoAnaliseIa"];
export type AprendizadoAnaliseIaIn = S["AprendizadoAnaliseIaIn"];
export type AprendizadoEstimativa = S["AprendizadoEstimativa"];
export type AprendizadoEstimativaIn = S["AprendizadoEstimativaIn"];
export type AprendizadoHipotese = S["AprendizadoHipotese"];
export type AprendizadoHipoteseRecomendarIn = S["AprendizadoHipoteseRecomendarIn"];
export type AprendizadoSinal = S["AprendizadoSinal"];
export type AprendizadoItemChecklist = S["AprendizadoItemChecklist"];
export type AprendizadoConferencia = S["AprendizadoConferencia"];
export type AprendizadoConferenciaPut = S["AprendizadoConferenciaPut"];
export type AprendizadoDiagnostico = S["AprendizadoDiagnostico"];
export type AprendizadoPostDiagnostico = S["AprendizadoPostDiagnostico"];
export type AprendizadoAfinidade = S["AprendizadoAfinidade"];
export type AnalyticsMercadoFiltros = NonNullable<paths["/api/analytics/mercado"]["get"]["parameters"]["query"]>;
export type SecurityEventFilters = NonNullable<
  paths["/api/security-events"]["get"]["parameters"]["query"]
>;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: ErrorCode,
    message: string,
    // Campo recusado (ex.: `hook.cor_fundo` no 400 `invalid_kit`) e detalhes extras
    // (ex.: `details.fields` no 409 `font_in_use`), quando a API manda.
    public readonly field: string | null = null,
    public readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Monta o ApiError a partir do corpo de erro já lido (JSON ou texto).
export function toApiError(status: number, body: unknown): ApiError {
  const error = (
    body as { error?: { code?: unknown; message?: unknown; field?: unknown; details?: unknown } } | null
  )?.error;
  if (isErrorCode(error?.code) && typeof error.message === "string") {
    const details =
      error.details && typeof error.details === "object" ? (error.details as Record<string, unknown>) : {};
    const field =
      typeof error.field === "string" ? error.field : typeof details.field === "string" ? details.field : null;
    return new ApiError(status, error.code, error.message, field, details);
  }
  // corpo não segue o contrato de erro — mantém o genérico
  return new ApiError(status, "internal_error", `HTTP ${status}`);
}

export interface ApiClientOptions {
  baseUrl?: string;
  // Ponto de injeção para o app: anexar Authorization, retry pós-refresh etc.
  // O openapi-fetch chama com um `Request` já montado.
  fetchFn?: typeof fetch;
}

async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) throw toApiError(response.status, error);
  return data as T;
}

export function createApiClient(options: ApiClientOptions = {}) {
  const fetchFn = options.fetchFn ?? fetch;
  const client = createClient<paths>({
    baseUrl: options.baseUrl ?? "",
    fetch: (request) => fetchFn(request),
  });

  return {
    auth: {
      login: (body: LoginRequest) => unwrap(client.POST("/api/auth/login", { body })),
      refresh: () => unwrap(client.POST("/api/auth/refresh")),
      logout: () => unwrap(client.POST("/api/auth/logout")),
      me: () => unwrap(client.GET("/api/auth/me")),
      verifyEmail: (body: { token: string }) =>
        unwrap(client.POST("/api/auth/verify-email", { body })),
      resendVerification: (body: { email: string }) =>
        unwrap(client.POST("/api/auth/verify-email/resend", { body })),
      changePassword: (body: ChangePasswordRequest) =>
        unwrap(client.POST("/api/auth/password/change", { body })),
      forgotPassword: (body: ForgotPasswordRequest) =>
        unwrap(client.POST("/api/auth/password/forgot", { body })),
      resetPassword: (body: ResetPasswordRequest) =>
        unwrap(client.POST("/api/auth/password/reset", { body })),
    },
    users: {
      list: () => unwrap(client.GET("/api/users")),
      create: (body: CreateUserRequest) => unwrap(client.POST("/api/users", { body })),
      update: (userId: string, body: UpdateUserRequest) =>
        unwrap(client.PATCH("/api/users/{user_id}", { params: { path: { user_id: userId } }, body })),
      setPassword: (userId: string, body: SetPasswordRequest) =>
        unwrap(
          client.POST("/api/users/{user_id}/password", { params: { path: { user_id: userId } }, body }),
        ),
      resendVerification: (userId: string) =>
        unwrap(
          client.POST("/api/users/{user_id}/verification", { params: { path: { user_id: userId } } }),
        ),
    },
    securityEvents: {
      list: (query: SecurityEventFilters = {}) =>
        unwrap(client.GET("/api/security-events", { params: { query } })),
    },
    perfis: {
      list: (query: PerfilFilters = {}) => unwrap(client.GET("/api/perfis", { params: { query } })),
      slugSuggestion: (name: string) =>
        unwrap(client.GET("/api/perfis/slug-suggestion", { params: { query: { name } } })),
      create: (body: CreatePerfilRequest) => unwrap(client.POST("/api/perfis", { body })),
      get: (perfilId: string) =>
        unwrap(client.GET("/api/perfis/{perfil_id}", { params: { path: { perfil_id: perfilId } } })),
      update: (perfilId: string, body: UpdatePerfilRequest) =>
        unwrap(client.PATCH("/api/perfis/{perfil_id}", { params: { path: { perfil_id: perfilId } }, body })),
      archive: (perfilId: string, version: number) =>
        unwrap(
          client.POST("/api/perfis/{perfil_id}/archive", {
            params: { path: { perfil_id: perfilId } },
            body: { version },
          }),
        ),
      restore: (perfilId: string, version: number) =>
        unwrap(
          client.POST("/api/perfis/{perfil_id}/restore", {
            params: { path: { perfil_id: perfilId } },
            body: { version },
          }),
        ),
      versions: (perfilId: string) =>
        unwrap(
          client.GET("/api/perfis/{perfil_id}/versions", { params: { path: { perfil_id: perfilId } } }),
        ),
      revert: (perfilId: string, version: number, toVersion: number) =>
        unwrap(
          client.POST("/api/perfis/{perfil_id}/revert", {
            params: { path: { perfil_id: perfilId } },
            body: { version, toVersion },
          }),
        ),
      // multipart/form-data: o openapi-fetch repassa FormData sem serializar e
      // deixa o navegador montar o Content-Type com o boundary.
      uploadImage: (perfilId: string, kind: ImageKind, file: Blob, version: number) => {
        const form = new FormData();
        form.append("file", file);
        form.append("version", String(version));
        const init = { params: { path: { perfil_id: perfilId } }, body: form as never };
        return unwrap(
          kind === "logo"
            ? client.PUT("/api/perfis/{perfil_id}/logo", init)
            : client.PUT("/api/perfis/{perfil_id}/banner", init),
        );
      },
      clearImage: (perfilId: string, kind: ImageKind, version: number) => {
        const init = { params: { path: { perfil_id: perfilId } }, body: { version } };
        return unwrap(
          kind === "logo"
            ? client.POST("/api/perfis/{perfil_id}/logo/clear", init)
            : client.POST("/api/perfis/{perfil_id}/banner/clear", init),
        );
      },
    },
    kit: {
      get: (perfilId: string) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/kit", { params: { path: { perfil_id: perfilId } } })),
      put: (perfilId: string, body: KitIn) =>
        unwrap(client.PUT("/api/perfis/{perfil_id}/kit", { params: { path: { perfil_id: perfilId } }, body })),
      versions: (perfilId: string) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/kit/versions", { params: { path: { perfil_id: perfilId } } })),
      revert: (perfilId: string, version: number, toVersion: number) =>
        unwrap(
          client.POST("/api/perfis/{perfil_id}/kit/revert", {
            params: { path: { perfil_id: perfilId } },
            body: { version, toVersion },
          }),
        ),
      export: (perfilId: string) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/kit/export", { params: { path: { perfil_id: perfilId } } })),
      // O arquivo com o nome que a API manda (Content-Disposition: kit-<slug>-v<n>.json).
      exportFile: async (perfilId: string): Promise<{ blob: Blob; filename: string }> => {
        const { data, error, response } = await client.GET("/api/perfis/{perfil_id}/kit/export", {
          params: { path: { perfil_id: perfilId }, query: { download: true } },
          parseAs: "blob",
        });
        if (!response.ok || !data) throw toApiError(response.status, error);
        const disposition = response.headers.get("content-disposition") ?? "";
        const filename = /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? "kit.json";
        return { blob: data, filename };
      },
    },
    fontes: {
      padrao: () => unwrap(client.GET("/api/fontes-padrao")),
      list: (perfilId: string, archived = false) =>
        unwrap(
          client.GET("/api/perfis/{perfil_id}/fontes", {
            params: { path: { perfil_id: perfilId }, query: { archived } },
          }),
        ),
      upload: (perfilId: string, file: Blob, name: string) => {
        const form = new FormData();
        form.append("file", file);
        form.append("name", name);
        return unwrap(
          client.POST("/api/perfis/{perfil_id}/fontes", {
            params: { path: { perfil_id: perfilId } },
            body: form as never,
          }),
        );
      },
      rename: (fontId: string, version: number, name: string) =>
        unwrap(client.PATCH("/api/fontes/{font_id}", { params: { path: { font_id: fontId } }, body: { version, name } })),
      archive: (fontId: string, version: number) =>
        unwrap(client.POST("/api/fontes/{font_id}/archive", { params: { path: { font_id: fontId } }, body: { version } })),
      restore: (fontId: string, version: number) =>
        unwrap(client.POST("/api/fontes/{font_id}/restore", { params: { path: { font_id: fontId } }, body: { version } })),
      versions: (fontId: string) =>
        unwrap(client.GET("/api/fontes/{font_id}/versions", { params: { path: { font_id: fontId } } })),
    },
    marcaDagua: {
      list: (perfilId: string) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/marca-dagua", { params: { path: { perfil_id: perfilId } } })),
      upload: (perfilId: string, file: Blob) => {
        const form = new FormData();
        form.append("file", file);
        return unwrap(
          client.POST("/api/perfis/{perfil_id}/marca-dagua", {
            params: { path: { perfil_id: perfilId } },
            body: form as never,
          }),
        );
      },
    },
    // Imagens de fundo do gancho e do card final (FR-005b); enviar não altera o kit.
    fundos: {
      list: (perfilId: string) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/fundos", { params: { path: { perfil_id: perfilId } } })),
      upload: (perfilId: string, file: Blob) => {
        const form = new FormData();
        form.append("file", file);
        return unwrap(
          client.POST("/api/perfis/{perfil_id}/fundos", {
            params: { path: { perfil_id: perfilId } },
            body: form as never,
          }),
        );
      },
    },
    // Biblioteca de assets (spec 007). Os envios (POST multipart …/arquivos e …/assets/arquivo)
    // ficam no app, por XHR, para ter o progresso do upload. Nenhuma rota DELETE.
    assets: {
      list: (perfilId: string, query: AssetFilters = {}) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/assets", { params: { path: { perfil_id: perfilId }, query } })),
      create: (perfilId: string, body: AssetCreateRequest) =>
        unwrap(client.POST("/api/perfis/{perfil_id}/assets", { params: { path: { perfil_id: perfilId } }, body })),
      images: (perfilId: string, query: LibraryImageFilters) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/assets/imagens", { params: { path: { perfil_id: perfilId }, query } })),
      get: (assetId: string) =>
        unwrap(client.GET("/api/assets/{asset_id}", { params: { path: { asset_id: assetId } } })),
      update: (assetId: string, body: AssetPatchRequest) =>
        unwrap(client.PATCH("/api/assets/{asset_id}", { params: { path: { asset_id: assetId } }, body })),
      updateFile: (assetId: string, fileId: string, body: FilePatchRequest) =>
        unwrap(
          client.PATCH("/api/assets/{asset_id}/arquivos/{file_id}", {
            params: { path: { asset_id: assetId, file_id: fileId } },
            body,
          }),
        ),
      reorder: (assetId: string, body: OrdemRequest) =>
        unwrap(client.PUT("/api/assets/{asset_id}/ordem", { params: { path: { asset_id: assetId } }, body })),
      archiveFile: (assetId: string, fileId: string, version: number) =>
        unwrap(
          client.POST("/api/assets/{asset_id}/arquivos/{file_id}/archive", {
            params: { path: { asset_id: assetId, file_id: fileId } },
            body: { version },
          }),
        ),
      restoreFile: (assetId: string, fileId: string, version: number) =>
        unwrap(
          client.POST("/api/assets/{asset_id}/arquivos/{file_id}/restore", {
            params: { path: { asset_id: assetId, file_id: fileId } },
            body: { version },
          }),
        ),
      archive: (assetId: string, version: number) =>
        unwrap(client.POST("/api/assets/{asset_id}/archive", { params: { path: { asset_id: assetId } }, body: { version } })),
      restore: (assetId: string, version: number) =>
        unwrap(client.POST("/api/assets/{asset_id}/restore", { params: { path: { asset_id: assetId } }, body: { version } })),
      versions: (assetId: string) =>
        unwrap(client.GET("/api/assets/{asset_id}/versions", { params: { path: { asset_id: assetId } } })),
      revert: (assetId: string, version: number, toVersion: number) =>
        unwrap(
          client.POST("/api/assets/{asset_id}/revert", {
            params: { path: { asset_id: assetId } },
            body: { version, toVersion },
          }),
        ),
    },
    // O envio (POST multipart) fica no app, por XHR, para ter o progresso do upload.
    cortes: {
      list: (perfilId: string, query: CorteFilters = {}) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/cortes", { params: { path: { perfil_id: perfilId }, query } })),
      get: (corteId: string) =>
        unwrap(client.GET("/api/cortes/{corte_id}", { params: { path: { corte_id: corteId } } })),
      retry: (corteId: string, version: number) =>
        unwrap(client.POST("/api/cortes/{corte_id}/retry", { params: { path: { corte_id: corteId } }, body: { version } })),
      versions: (corteId: string) =>
        unwrap(client.GET("/api/cortes/{corte_id}/versions", { params: { path: { corte_id: corteId } } })),
      // spec 006: gancho editável em revisão, "Aplicar marca" (lote até 30) e arquivar/restaurar
      update: (corteId: string, body: { version: number; hookText: string }) =>
        unwrap(client.PATCH("/api/cortes/{corte_id}", { params: { path: { corte_id: corteId } }, body })),
      aplicarMarca: (items: { corteId: string; version: number }[]) =>
        unwrap(client.POST("/api/cortes/aplicar-marca", { body: { items } })),
      archive: (corteId: string, version: number) =>
        unwrap(client.POST("/api/cortes/{corte_id}/archive", { params: { path: { corte_id: corteId } }, body: { version } })),
      restore: (corteId: string, version: number) =>
        unwrap(client.POST("/api/cortes/{corte_id}/restore", { params: { path: { corte_id: corteId } }, body: { version } })),
    },
    armazenamento: () => unwrap(client.GET("/api/armazenamento")),
    midia: {
      links: (items: { kind: MidiaKind; id: string }[]) => unwrap(client.POST("/api/midia/links", { body: { items } })),
    },
    contas: {
      create: (perfilId: string, body: CreateContaRequest) =>
        unwrap(
          client.POST("/api/perfis/{perfil_id}/contas", { params: { path: { perfil_id: perfilId } }, body }),
        ),
      update: (contaId: string, body: UpdateContaRequest) =>
        unwrap(client.PATCH("/api/contas/{conta_id}", { params: { path: { conta_id: contaId } }, body })),
      archive: (contaId: string, version: number) =>
        unwrap(
          client.POST("/api/contas/{conta_id}/archive", {
            params: { path: { conta_id: contaId } },
            body: { version },
          }),
        ),
      restore: (contaId: string, version: number) =>
        unwrap(
          client.POST("/api/contas/{conta_id}/restore", {
            params: { path: { conta_id: contaId } },
            body: { version },
          }),
        ),
      revert: (contaId: string, version: number, toVersion: number) =>
        unwrap(
          client.POST("/api/contas/{conta_id}/revert", {
            params: { path: { conta_id: contaId } },
            body: { version, toVersion },
          }),
        ),
      versions: (contaId: string) =>
        unwrap(client.GET("/api/contas/{conta_id}/versions", { params: { path: { conta_id: contaId } } })),
      // spec 014: os quatro modos de agendamento, com o motivo dos indisponíveis
      modos: (contaId: string) =>
        unwrap(client.GET("/api/contas/{conta_id}/modos", { params: { path: { conta_id: contaId } } })),
    },
    // Conexão da conta com a rede (spec 015). Iniciar, desconectar e criador são só do dono humano;
    // o retorno do login é o SPA que envia (`/app/conexoes/retorno`).
    conexoes: {
      get: (contaId: string) =>
        unwrap(client.GET("/api/contas/{conta_id}/conexao", { params: { path: { conta_id: contaId } } })),
      iniciar: (contaId: string) =>
        unwrap(client.POST("/api/contas/{conta_id}/conexao/iniciar", { params: { path: { conta_id: contaId } } })),
      retorno: (body: RetornoRequest) => unwrap(client.POST("/api/conexoes/retorno", { body })),
      // spec 016: com métricas guardadas, sem `confirmoAnonimizar` → 409 `confirmar_anonimizacao`
      desconectar: (contaId: string, version: number, confirmoAnonimizar = false) =>
        unwrap(
          client.POST("/api/contas/{conta_id}/conexao/desconectar", {
            params: { path: { conta_id: contaId } },
            body: { version, confirmoAnonimizar },
          }),
        ),
      criador: (contaId: string) =>
        unwrap(client.GET("/api/contas/{conta_id}/conexao/criador", { params: { path: { conta_id: contaId } } })),
      versions: (contaId: string) =>
        unwrap(client.GET("/api/contas/{conta_id}/conexao/versions", { params: { path: { conta_id: contaId } } })),
    },
    // Métricas da TikTok (spec 016): só leitura; a exportação é só do dono (ZIP por Blob).
    metricas: {
      conta: (contaId: string, query: MetricasContaFilters = {}) =>
        unwrap(client.GET("/api/contas/{conta_id}/metricas", { params: { path: { conta_id: contaId }, query } })),
      videos: (query: MetricasVideosFilters = {}) => unwrap(client.GET("/api/metricas/videos", { params: { query } })),
      video: (videoId: string) =>
        unwrap(client.GET("/api/metricas/videos/{video_id}", { params: { path: { video_id: videoId } } })),
      // O arquivo com o nome que a API manda (Content-Disposition: sociman-metricas-AAAAMMDD-AAAAMMDD.zip).
      exportFile: async (query: MetricasExportFilters): Promise<{ blob: Blob; filename: string }> => {
        const { data, error, response } = await client.GET("/api/metricas/export", { params: { query }, parseAs: "blob" });
        if (!response.ok || !data) throw toApiError(response.status, error);
        const disposition = response.headers.get("content-disposition") ?? "";
        const filename = /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? "sociman-metricas.zip";
        return { blob: data, filename };
      },
    },
    // Analytics de decisão (spec 019): 8 abas, só leitura (GET), dono e membro; custo de IA do funil só para o dono.
    analytics: {
      visaoGeral: (query: AnalyticsFiltros = {}) => unwrap(client.GET("/api/analytics/visao-geral", { params: { query } })),
      quandoPostar: (query: AnalyticsFiltros = {}) => unwrap(client.GET("/api/analytics/quando-postar", { params: { query } })),
      oQueFunciona: (query: AnalyticsFiltros = {}) => unwrap(client.GET("/api/analytics/o-que-funciona", { params: { query } })),
      curvas: (query: AnalyticsFiltros = {}) => unwrap(client.GET("/api/analytics/curvas", { params: { query } })),
      contas: (query: AnalyticsFiltros = {}) => unwrap(client.GET("/api/analytics/contas", { params: { query } })),
      funil: (query: AnalyticsFunilFiltros = {}) => unwrap(client.GET("/api/analytics/funil", { params: { query } })),
      mercado: (query: AnalyticsMercadoFiltros = {}) => unwrap(client.GET("/api/analytics/mercado", { params: { query } })),
      alertas: (query: AnalyticsFiltros = {}) => unwrap(client.GET("/api/analytics/alertas", { params: { query } })),
      // spec 022: a aba Público (dados importados do TikTok Studio)
      publico: (query: AnalyticsFiltros = {}) => unwrap(client.GET("/api/analytics/publico", { params: { query } })),
      // ordem estável de todas as contas (cor fixa por conta, FR-006)
      ordemContas: () => unwrap(client.GET("/api/analytics/ordem-contas")),
    },
    // Histórico do TikTok Studio (spec 020): prévia (multipart, nada gravado), confirmar e desfazer só
    // do dono humano; a lista e a cobertura são leitura de todos.
    studio: {
      previa: (contaId: string, arquivos: Blob[]) => {
        const form = new FormData();
        for (const a of arquivos) form.append("arquivos", a, a instanceof File ? a.name : undefined);
        return unwrap(
          client.POST("/api/contas/{conta_id}/studio/previa", { params: { path: { conta_id: contaId } }, body: form as never }),
        );
      },
      confirmar: (contaId: string, body: { previaId: string; confirmoConta?: boolean }) =>
        unwrap(
          client.POST("/api/contas/{conta_id}/studio/importacoes", {
            params: { path: { conta_id: contaId } },
            body: { confirmoConta: false, ...body },
          }),
        ),
      importacoes: (contaId: string) =>
        unwrap(client.GET("/api/contas/{conta_id}/studio/importacoes", { params: { path: { conta_id: contaId } } })),
      cobertura: (contaId: string) =>
        unwrap(client.GET("/api/contas/{conta_id}/studio/cobertura", { params: { path: { conta_id: contaId } } })),
      desfazer: (importacaoId: string, version: number) =>
        unwrap(
          client.POST("/api/studio/importacoes/{importacao_id}/desfazer", {
            params: { path: { importacao_id: importacaoId } },
            body: { version },
          }),
        ),
    },
    // Importação da agência (spec 013): prévia, confirmar e desfazer só do dono humano; o estado, a
    // lista e o detalhe são leitura de todos.
    agencia: {
      estado: () => unwrap(client.GET("/api/agencia/estado")),
      previa: () => unwrap(client.POST("/api/agencia/previa")),
      confirmar: (body: AgenciaConfirmarRequest) => unwrap(client.POST("/api/agencia/importacoes", { body })),
      importacoes: () => unwrap(client.GET("/api/agencia/importacoes")),
      importacao: (importacaoId: string) =>
        unwrap(client.GET("/api/agencia/importacoes/{importacao_id}", { params: { path: { importacao_id: importacaoId } } })),
      desfazer: (importacaoId: string, version: number) =>
        unwrap(
          client.POST("/api/agencia/importacoes/{importacao_id}/desfazer", {
            params: { path: { importacao_id: importacaoId } },
            body: { version },
          }),
        ),
    },
    // Interruptor "Envios automáticos" (spec 015): só o dono humano muda; o nível do servidor é leitura.
    publicacao: {
      config: () => unwrap(client.GET("/api/publicacao/config")),
      updateConfig: (body: { version: number; enviosHabilitados: boolean }) =>
        unwrap(client.PUT("/api/publicacao/config", { body })),
      configVersions: () => unwrap(client.GET("/api/publicacao/config/versions")),
    },
    // Canais-fonte (spec 006, US1). O direito e o revert são só do dono. Nenhuma rota DELETE.
    canais: {
      resolver: (entrada: string) => unwrap(client.POST("/api/canais/resolver", { body: { entrada } })),
      create: (body: CreateCanalRequest) => unwrap(client.POST("/api/canais", { body })),
      list: (query: CanalFilters = {}) => unwrap(client.GET("/api/canais", { params: { query } })),
      get: (canalId: string) => unwrap(client.GET("/api/canais/{canal_id}", { params: { path: { canal_id: canalId } } })),
      update: (canalId: string, body: UpdateCanalRequest) =>
        unwrap(client.PATCH("/api/canais/{canal_id}", { params: { path: { canal_id: canalId } }, body })),
      direito: (canalId: string, body: DireitoRequest) =>
        unwrap(client.PUT("/api/canais/{canal_id}/direito", { params: { path: { canal_id: canalId } }, body })),
      sincronizar: (canalId: string) =>
        unwrap(client.POST("/api/canais/{canal_id}/sincronizar", { params: { path: { canal_id: canalId } } })),
      archive: (canalId: string, version: number) =>
        unwrap(client.POST("/api/canais/{canal_id}/archive", { params: { path: { canal_id: canalId } }, body: { version } })),
      restore: (canalId: string, version: number) =>
        unwrap(client.POST("/api/canais/{canal_id}/restore", { params: { path: { canal_id: canalId } }, body: { version } })),
      versions: (canalId: string) =>
        unwrap(client.GET("/api/canais/{canal_id}/versions", { params: { path: { canal_id: canalId } } })),
      revert: (canalId: string, version: number, toVersion: number) =>
        unwrap(
          client.POST("/api/canais/{canal_id}/revert", { params: { path: { canal_id: canalId } }, body: { version, toVersion } }),
        ),
    },
    // Descoberta (spec 006, US2): paginação por cursor opaco.
    videosFonte: {
      list: (query: VideoFonteFilters = {}) => unwrap(client.GET("/api/videos-fonte", { params: { query } })),
      get: (videoId: string) => unwrap(client.GET("/api/videos-fonte/{video_id}", { params: { path: { video_id: videoId } } })),
    },
    // Padrões de corte do perfil (spec 006, FR-008); versão 0 = padrão nunca salvo.
    padroesCorte: {
      get: (perfilId: string) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/padroes-corte", { params: { path: { perfil_id: perfilId } } })),
      put: (perfilId: string, body: PadroesCorteRequest) =>
        unwrap(client.PUT("/api/perfis/{perfil_id}/padroes-corte", { params: { path: { perfil_id: perfilId } }, body })),
      versions: (perfilId: string) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/padroes-corte/versions", { params: { path: { perfil_id: perfilId } } })),
      revert: (perfilId: string, version: number, toVersion: number) =>
        unwrap(
          client.POST("/api/perfis/{perfil_id}/padroes-corte/revert", {
            params: { path: { perfil_id: perfilId } },
            body: { version, toVersion },
          }),
        ),
    },
    // Seleção e envio ao OpenShorts (spec 006, US2–US4). O avulso por arquivo fica no app, por XHR.
    envios: {
      selecionar: (perfilId: string, body: SelecionarRequest) =>
        unwrap(
          client.POST("/api/perfis/{perfil_id}/envios", {
            params: { path: { perfil_id: perfilId } },
            body: { confirmarDuplicado: false, ...body },
          }),
        ),
      list: (query: EnvioFilters = {}) => unwrap(client.GET("/api/envios", { params: { query } })),
      get: (envioId: string) => unwrap(client.GET("/api/envios/{envio_id}", { params: { path: { envio_id: envioId } } })),
      enviar: (body: EnviarRequest) =>
        unwrap(client.POST("/api/envios/enviar", { body: { confirmarAviso: false, confirmarDuplicado: false, ...body } })),
      confirmarQualidade: (envioId: string, body: { version: number; enviar: boolean }) =>
        unwrap(client.POST("/api/envios/{envio_id}/confirmar-qualidade", { params: { path: { envio_id: envioId } }, body })),
      retry: (envioId: string, version: number) =>
        unwrap(client.POST("/api/envios/{envio_id}/retry", { params: { path: { envio_id: envioId } }, body: { version } })),
      archive: (envioId: string, version: number) =>
        unwrap(client.POST("/api/envios/{envio_id}/archive", { params: { path: { envio_id: envioId } }, body: { version } })),
      versions: (envioId: string) =>
        unwrap(client.GET("/api/envios/{envio_id}/versions", { params: { path: { envio_id: envioId } } })),
    },
    // Sugestões de texto da 006 (deprecated; as rotas de postagem saíram na 014, que usa destinos).
    postagens: {
      sugerir: (corteId: string, body: { contaId: string; outraVersao?: boolean }) =>
        unwrap(
          client.POST("/api/cortes/{corte_id}/sugestoes", {
            params: { path: { corte_id: corteId } },
            body: { outraVersao: false, ...body },
          }),
        ),
      sugestoes: (corteId: string) =>
        unwrap(client.GET("/api/cortes/{corte_id}/sugestoes", { params: { path: { corte_id: corteId } } })),
    },
    // Assistente de IA (spec 008): gerar nunca salva; o Aplicar é o save de cada tela com `ia`.
    // Regras (mutações), registro e resumo são só do dono. Nenhuma rota DELETE.
    ia: {
      tipos: () => unwrap(client.GET("/api/ia/tipos")),
      tipo: (tipo: TipoCampoId) => unwrap(client.GET("/api/ia/tipos/{tipo}", { params: { path: { tipo } } })),
      updateRegras: (tipo: TipoCampoId, body: { version: number; texto: string }) =>
        unwrap(client.PUT("/api/ia/tipos/{tipo}/regras", { params: { path: { tipo } }, body })),
      padrao: (tipo: TipoCampoId, version: number) =>
        unwrap(client.POST("/api/ia/tipos/{tipo}/padrao", { params: { path: { tipo } }, body: { version } })),
      versions: (tipo: TipoCampoId) => unwrap(client.GET("/api/ia/tipos/{tipo}/versions", { params: { path: { tipo } } })),
      revert: (tipo: TipoCampoId, version: number, toVersion: number) =>
        unwrap(client.POST("/api/ia/tipos/{tipo}/revert", { params: { path: { tipo } }, body: { version, toVersion } })),
      gerar: (body: IaGerarRequest) => unwrap(client.POST("/api/ia/gerar", { body })),
      descartar: (chamadaId: string) =>
        unwrap(client.POST("/api/ia/chamadas/{chamada_id}/descartar", { params: { path: { chamada_id: chamadaId } } })),
      chamadas: (query: IaChamadaFilters = {}) => unwrap(client.GET("/api/ia/chamadas", { params: { query } })),
      chamada: (chamadaId: string) =>
        unwrap(client.GET("/api/ia/chamadas/{chamada_id}", { params: { path: { chamada_id: chamadaId } } })),
      resumo: (mes?: string) => unwrap(client.GET("/api/ia/resumo", { params: { query: mes ? { mes } : {} } })),
      // spec 017: montar e testar o guia (só o dono); nenhum dos dois salva o guia
      guiaMontar: (body: GuiaMontarRequest) => unwrap(client.POST("/api/ia/guia/montar", { body })),
      guiaTestar: (body: GuiaTestarRequest) => unwrap(client.POST("/api/ia/guia/testar", { body })),
    },
    // Guia de comunicação do perfil e da conta (spec 017). PUT e revert só do dono; sem DELETE
    // ("limpar" é salvar vazio).
    guias: {
      perfil: (perfilId: string) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/guia", { params: { path: { perfil_id: perfilId } } })),
      updatePerfil: (perfilId: string, body: GuiaIn) =>
        unwrap(client.PUT("/api/perfis/{perfil_id}/guia", { params: { path: { perfil_id: perfilId } }, body })),
      perfilVersions: (perfilId: string) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/guia/versions", { params: { path: { perfil_id: perfilId } } })),
      revertPerfil: (perfilId: string, version: number, toVersion: number) =>
        unwrap(
          client.POST("/api/perfis/{perfil_id}/guia/revert", {
            params: { path: { perfil_id: perfilId } },
            body: { version, toVersion },
          }),
        ),
      conta: (contaId: string) =>
        unwrap(client.GET("/api/contas/{conta_id}/guia", { params: { path: { conta_id: contaId } } })),
      updateConta: (contaId: string, body: GuiaIn) =>
        unwrap(client.PUT("/api/contas/{conta_id}/guia", { params: { path: { conta_id: contaId } }, body })),
      contaVersions: (contaId: string) =>
        unwrap(client.GET("/api/contas/{conta_id}/guia/versions", { params: { path: { conta_id: contaId } } })),
      revertConta: (contaId: string, version: number, toVersion: number) =>
        unwrap(
          client.POST("/api/contas/{conta_id}/guia/revert", {
            params: { path: { conta_id: contaId } },
            body: { version, toVersion },
          }),
        ),
    },
    // Central de conteúdos (spec 014). O vídeo próprio (POST multipart) fica no app, por XHR.
    conteudos: {
      list: (query: ConteudoFilters = {}) => unwrap(client.GET("/api/conteudos", { params: { query } })),
      resumo: (query: ResumoFilters = {}) => unwrap(client.GET("/api/conteudos/resumo", { params: { query } })),
      get: (conteudoId: string) =>
        unwrap(client.GET("/api/conteudos/{conteudo_id}", { params: { path: { conteudo_id: conteudoId } } })),
      update: (conteudoId: string, body: { version: number; titulo: string }) =>
        unwrap(client.PATCH("/api/conteudos/{conteudo_id}", { params: { path: { conteudo_id: conteudoId } }, body })),
      archive: (conteudoId: string, version: number) =>
        unwrap(client.POST("/api/conteudos/{conteudo_id}/archive", { params: { path: { conteudo_id: conteudoId } }, body: { version } })),
      restore: (conteudoId: string, version: number) =>
        unwrap(client.POST("/api/conteudos/{conteudo_id}/restore", { params: { path: { conteudo_id: conteudoId } }, body: { version } })),
      versions: (conteudoId: string) =>
        unwrap(client.GET("/api/conteudos/{conteudo_id}/versions", { params: { path: { conteudo_id: conteudoId } } })),
      revert: (conteudoId: string, version: number, toVersion: number) =>
        unwrap(
          client.POST("/api/conteudos/{conteudo_id}/revert", {
            params: { path: { conteudo_id: conteudoId } },
            body: { version, toVersion },
          }),
        ),
      addDestino: (conteudoId: string, body: CreateDestinoRequest) =>
        unwrap(client.POST("/api/conteudos/{conteudo_id}/destinos", { params: { path: { conteudo_id: conteudoId } }, body })),
      // spec 018: todas as contas do conteúdo de uma vez (só dono humano). Desaprovar com agendados
      // exige `confirmo` (sem ele, 409 `confirmacao_necessaria`).
      aprovarTodas: (conteudoId: string) =>
        unwrap(client.POST("/api/conteudos/{conteudo_id}/aprovar-todas", { params: { path: { conteudo_id: conteudoId } } })),
      desaprovarTodas: (conteudoId: string, confirmo: boolean) =>
        unwrap(client.POST("/api/conteudos/{conteudo_id}/desaprovar-todas", { params: { path: { conteudo_id: conteudoId } }, body: { confirmo } })),
    },
    // Destino = conteúdo × conta. Aprovar, recusar, aprovar em lote e reverter são só do dono.
    destinos: {
      get: (destinoId: string) =>
        unwrap(client.GET("/api/destinos/{destino_id}", { params: { path: { destino_id: destinoId } } })),
      update: (destinoId: string, body: UpdateDestinoRequest) =>
        unwrap(client.PATCH("/api/destinos/{destino_id}", { params: { path: { destino_id: destinoId } }, body })),
      pedirAprovacao: (destinoId: string, body: { version: number; nota?: string | null }) =>
        unwrap(client.POST("/api/destinos/{destino_id}/pedir-aprovacao", { params: { path: { destino_id: destinoId } }, body })),
      aprovar: (destinoId: string, version: number) =>
        unwrap(client.POST("/api/destinos/{destino_id}/aprovar", { params: { path: { destino_id: destinoId } }, body: { version } })),
      recusar: (destinoId: string, body: { version: number; motivo: string }) =>
        unwrap(client.POST("/api/destinos/{destino_id}/recusar", { params: { path: { destino_id: destinoId } }, body })),
      postado: (destinoId: string, body: { version: number; postedUrl?: string | null }) =>
        unwrap(client.POST("/api/destinos/{destino_id}/postado", { params: { path: { destino_id: destinoId } }, body })),
      archive: (destinoId: string, version: number) =>
        unwrap(client.POST("/api/destinos/{destino_id}/archive", { params: { path: { destino_id: destinoId } }, body: { version } })),
      restore: (destinoId: string, version: number) =>
        unwrap(client.POST("/api/destinos/{destino_id}/restore", { params: { path: { destino_id: destinoId } }, body: { version } })),
      versions: (destinoId: string) =>
        unwrap(client.GET("/api/destinos/{destino_id}/versions", { params: { path: { destino_id: destinoId } } })),
      revert: (destinoId: string, version: number, toVersion: number) =>
        unwrap(
          client.POST("/api/destinos/{destino_id}/revert", {
            params: { path: { destino_id: destinoId } },
            body: { version, toVersion },
          }),
        ),
      loteAprovar: (body: { contaId: string; conteudoIds: string[] }) => unwrap(client.POST("/api/destinos/lote/aprovar", { body })),
      lotePedirAprovacao: (body: { contaId: string; conteudoIds: string[]; nota?: string | null }) =>
        unwrap(client.POST("/api/destinos/lote/pedir-aprovacao", { body })),
      // spec 015: execução do envio automático (tentar de novo e confirmar envio: só dono humano)
      tentativas: (destinoId: string) =>
        unwrap(client.GET("/api/destinos/{destino_id}/tentativas", { params: { path: { destino_id: destinoId } } })),
      tentarDeNovo: (destinoId: string, body: { version: number; confirmoQueNaoChegou?: boolean }) =>
        unwrap(
          client.POST("/api/destinos/{destino_id}/tentar-de-novo", {
            params: { path: { destino_id: destinoId } },
            body: { confirmoQueNaoChegou: false, ...body },
          }),
        ),
      // "Enviar agora" (T099): agenda para já num modo automático; `aviso` quando fica pausado
      enviarAgora: (destinoId: string, body: { version: number; modo?: Modo; conferiNoApp?: boolean | null }) =>
        unwrap(client.POST("/api/destinos/{destino_id}/enviar-agora", { params: { path: { destino_id: destinoId } }, body: { modo: "criar_rascunho", ...body } })),
      confirmarEnvio: (destinoId: string, version: number) =>
        unwrap(client.POST("/api/destinos/{destino_id}/confirmar-envio", { params: { path: { destino_id: destinoId } }, body: { version } })),
      // spec 016: desempenho e vínculo com o post (ligar, escolher, colar e desfazer: só dono humano)
      metricas: (destinoId: string) =>
        unwrap(client.GET("/api/destinos/{destino_id}/metricas", { params: { path: { destino_id: destinoId } } })),
      vinculo: (destinoId: string) =>
        unwrap(client.GET("/api/destinos/{destino_id}/vinculo", { params: { path: { destino_id: destinoId } } })),
      vincular: (destinoId: string, body: VinculoRequest) =>
        unwrap(client.POST("/api/destinos/{destino_id}/vinculo", { params: { path: { destino_id: destinoId } }, body })),
      desfazerVinculo: (destinoId: string, version: number) =>
        unwrap(client.POST("/api/destinos/{destino_id}/vinculo/desfazer", { params: { path: { destino_id: destinoId } }, body: { version } })),
    },
    // Agendamento no destino (spec 014): só o modo lembrete executa. 409 intervalo_conflito → reenviar
    // com ignorarIntervalo: true.
    agendamentos: {
      create: (body: AgendarRequest) =>
        unwrap(client.POST("/api/agendamentos", { body: { ignorarIntervalo: false, ...body } })),
      update: (destinoId: string, body: ReagendarRequest) =>
        unwrap(
          client.PATCH("/api/destinos/{destino_id}/agendamento", {
            params: { path: { destino_id: destinoId } },
            body: { ignorarIntervalo: false, ...body },
          }),
        ),
      cancelar: (destinoId: string, version: number) =>
        unwrap(
          client.POST("/api/destinos/{destino_id}/agendamento/cancelar", {
            params: { path: { destino_id: destinoId } },
            body: { version },
          }),
        ),
      loteReagendar: (body: LoteReagendarRequest) =>
        unwrap(client.POST("/api/agendamentos/lote/reagendar", { body: { ignorarIntervalo: false, ...body } })),
      loteCancelar: (body: { itens: { destinoId: string; version: number }[] }) =>
        unwrap(client.POST("/api/agendamentos/lote/cancelar", { body })),
      sequenciaPrevia: (body: SequenciaRequest) => unwrap(client.POST("/api/agendamentos/sequencia/previa", { body })),
      sequencia: (body: SequenciaConfirmarRequest) => unwrap(client.POST("/api/agendamentos/sequencia", { body })),
    },
    calendario: (query: CalendarioFilters) => unwrap(client.GET("/api/calendario", { params: { query } })),
    integracoes: () => unwrap(client.GET("/api/integracoes")),
    // Sino do painel (spec 006, R11): polling com `after` (id); marcar lidas só preenche `lida_em`.
    notificacoes: {
      list: (query: NotificacaoFilters = {}) => unwrap(client.GET("/api/notificacoes", { params: { query } })),
      marcarLidas: (body: { ids: number[] } | { todas: true }) =>
        unwrap(client.POST("/api/notificacoes/lidas", { body: { todas: false, ...body } })),
    },
    // Clientes MCP dos agentes (spec 009): tudo só do dono humano. O `token` vem SÓ no create e no
    // rotacionar, uma vez; nenhuma outra resposta o traz.
    mcp: {
      clientes: (query: McpClienteFilters = {}) => unwrap(client.GET("/api/mcp/clientes", { params: { query } })),
      cliente: (clienteId: string) =>
        unwrap(client.GET("/api/mcp/clientes/{cliente_id}", { params: { path: { cliente_id: clienteId } } })),
      create: (body: McpClienteCreateRequest) => unwrap(client.POST("/api/mcp/clientes", { body })),
      update: (clienteId: string, body: McpClienteUpdateRequest) =>
        unwrap(client.PATCH("/api/mcp/clientes/{cliente_id}", { params: { path: { cliente_id: clienteId } }, body })),
      suspender: (clienteId: string, version: number) =>
        unwrap(client.POST("/api/mcp/clientes/{cliente_id}/suspender", { params: { path: { cliente_id: clienteId } }, body: { version } })),
      reativar: (clienteId: string, version: number) =>
        unwrap(client.POST("/api/mcp/clientes/{cliente_id}/reativar", { params: { path: { cliente_id: clienteId } }, body: { version } })),
      rotacionar: (clienteId: string, version: number) =>
        unwrap(client.POST("/api/mcp/clientes/{cliente_id}/rotacionar", { params: { path: { cliente_id: clienteId } }, body: { version } })),
      revogar: (clienteId: string, version: number) =>
        unwrap(client.POST("/api/mcp/clientes/{cliente_id}/revogar", { params: { path: { cliente_id: clienteId } }, body: { version } })),
      versions: (clienteId: string) =>
        unwrap(client.GET("/api/mcp/clientes/{cliente_id}/versions", { params: { path: { cliente_id: clienteId } } })),
      config: () => unwrap(client.GET("/api/mcp/config")),
      updateConfig: (body: { version: number; habilitado: boolean }) => unwrap(client.PUT("/api/mcp/config", { body })),
      configVersions: () => unwrap(client.GET("/api/mcp/config/versions")),
      chamadas: (query: McpChamadaFilters = {}) => unwrap(client.GET("/api/mcp/chamadas", { params: { query } })),
    },
    // Cenas para o Flow/Veo (spec 010). O envio de tomada (multipart) fica no app, por XHR, para ter o
    // progresso. Nenhuma rota DELETE.
    cenas: {
      list: (perfilId: string, query: CenaFilters = {}) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/cenas", { params: { path: { perfil_id: perfilId }, query } })),
      create: (perfilId: string, body: CenaCreateRequest) =>
        unwrap(client.POST("/api/perfis/{perfil_id}/cenas", { params: { path: { perfil_id: perfilId } }, body })),
      get: (cenaId: string) => unwrap(client.GET("/api/cenas/{cena_id}", { params: { path: { cena_id: cenaId } } })),
      update: (cenaId: string, body: CenaPatchRequest) =>
        unwrap(client.PATCH("/api/cenas/{cena_id}", { params: { path: { cena_id: cenaId } }, body })),
      duplicar: (cenaId: string) => unwrap(client.POST("/api/cenas/{cena_id}/duplicar", { params: { path: { cena_id: cenaId } } })),
      pronta: (cenaId: string, version: number) =>
        unwrap(client.POST("/api/cenas/{cena_id}/pronta", { params: { path: { cena_id: cenaId } }, body: { version } })),
      rascunho: (cenaId: string, version: number) =>
        unwrap(client.POST("/api/cenas/{cena_id}/rascunho", { params: { path: { cena_id: cenaId } }, body: { version } })),
      remontar: (cenaId: string, version: number) =>
        unwrap(client.POST("/api/cenas/{cena_id}/remontar", { params: { path: { cena_id: cenaId } }, body: { version } })),
      archive: (cenaId: string, version: number) =>
        unwrap(client.POST("/api/cenas/{cena_id}/arquivar", { params: { path: { cena_id: cenaId } }, body: { version } })),
      restore: (cenaId: string, version: number) =>
        unwrap(client.POST("/api/cenas/{cena_id}/restaurar", { params: { path: { cena_id: cenaId } }, body: { version } })),
      versions: (cenaId: string) => unwrap(client.GET("/api/cenas/{cena_id}/versions", { params: { path: { cena_id: cenaId } } })),
      revert: (cenaId: string, version: number, toVersion: number) =>
        unwrap(client.POST("/api/cenas/{cena_id}/revert", { params: { path: { cena_id: cenaId } }, body: { version, toVersion } })),
      tomadas: (cenaId: string, arquivadas = false) =>
        unwrap(client.GET("/api/cenas/{cena_id}/tomadas", { params: { path: { cena_id: cenaId }, query: { arquivadas } } })),
      escolher: (cenaId: string, tomadaId: string, version: number) =>
        unwrap(
          client.POST("/api/cenas/{cena_id}/tomadas/{tomada_id}/escolher", {
            params: { path: { cena_id: cenaId, tomada_id: tomadaId } },
            body: { version },
          }),
        ),
      tomadaUpdate: (tomadaId: string, version: number, nota: string) =>
        unwrap(client.PATCH("/api/cenas/tomadas/{tomada_id}", { params: { path: { tomada_id: tomadaId } }, body: { version, nota } })),
      tomadaArchive: (tomadaId: string, version: number) =>
        unwrap(client.POST("/api/cenas/tomadas/{tomada_id}/arquivar", { params: { path: { tomada_id: tomadaId } }, body: { version } })),
      tomadaRestore: (tomadaId: string, version: number) =>
        unwrap(client.POST("/api/cenas/tomadas/{tomada_id}/restaurar", { params: { path: { tomada_id: tomadaId } }, body: { version } })),
      padroes: (perfilId: string) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/cenas/padroes", { params: { path: { perfil_id: perfilId } } })),
      padroesPut: (perfilId: string, body: { version: number; estilo: string; negative: string }) =>
        unwrap(client.PUT("/api/perfis/{perfil_id}/cenas/padroes", { params: { path: { perfil_id: perfilId } }, body })),
      doConteudo: (conteudoId: string) =>
        unwrap(client.GET("/api/conteudos/{conteudo_id}/cenas", { params: { path: { conteudo_id: conteudoId } } })),
      definirDoConteudo: (conteudoId: string, version: number, cenaIds: string[]) =>
        unwrap(client.PUT("/api/conteudos/{conteudo_id}/cenas", { params: { path: { conteudo_id: conteudoId } }, body: { version, cenaIds } })),
    },
    // Anotações e propostas dos agentes (spec 009, US4). Aplicar é pelo save do destino
    // (`propostaId` no `destinos.update`); descartar é humano, reverter só do dono.
    anotacoes: {
      list: (query: AnotacaoFilters = {}) => unwrap(client.GET("/api/anotacoes", { params: { query } })),
      get: (anotacaoId: string) =>
        unwrap(client.GET("/api/anotacoes/{anotacao_id}", { params: { path: { anotacao_id: anotacaoId } } })),
      create: (body: AnotacaoCreateRequest) => unwrap(client.POST("/api/anotacoes", { body })),
      archive: (anotacaoId: string, version: number) =>
        unwrap(client.POST("/api/anotacoes/{anotacao_id}/archive", { params: { path: { anotacao_id: anotacaoId } }, body: { version } })),
      descartar: (anotacaoId: string, body: { version: number; motivo?: string | null }) =>
        unwrap(client.POST("/api/anotacoes/{anotacao_id}/descartar", { params: { path: { anotacao_id: anotacaoId } }, body })),
      versions: (anotacaoId: string) =>
        unwrap(client.GET("/api/anotacoes/{anotacao_id}/versions", { params: { path: { anotacao_id: anotacaoId } } })),
      revert: (anotacaoId: string, version: number, toVersion: number) =>
        unwrap(
          client.POST("/api/anotacoes/{anotacao_id}/revert", { params: { path: { anotacao_id: anotacaoId } }, body: { version, toVersion } }),
        ),
      resumo: (query: AnotacaoResumoFilters = {}) => unwrap(client.GET("/api/anotacoes/resumo", { params: { query } })),
    },
    // Aprender com o desempenho (spec 023). Leituras calculadas na API; escritas só do dono humano.
    aprendizado: {
      temas: {
        list: (perfilId: string, query: { arquivados?: boolean } = {}) =>
          unwrap(client.GET("/api/perfis/{perfil_id}/aprendizado/temas", { params: { path: { perfil_id: perfilId }, query } })),
        create: (perfilId: string, body: AprendizadoTemaIn) =>
          unwrap(client.POST("/api/perfis/{perfil_id}/aprendizado/temas", { params: { path: { perfil_id: perfilId } }, body })),
        lote: (perfilId: string, body: { temas: AprendizadoTemaIn[]; chamadaId?: string | null }) =>
          unwrap(client.POST("/api/perfis/{perfil_id}/aprendizado/temas/lote", { params: { path: { perfil_id: perfilId } }, body })),
        update: (temaId: string, body: AprendizadoTemaPatch) =>
          unwrap(client.PATCH("/api/aprendizado/temas/{tema_id}", { params: { path: { tema_id: temaId } }, body })),
        archive: (temaId: string, version: number) =>
          unwrap(client.POST("/api/aprendizado/temas/{tema_id}/archive", { params: { path: { tema_id: temaId } }, body: { version } })),
        restore: (temaId: string, version: number) =>
          unwrap(client.POST("/api/aprendizado/temas/{tema_id}/restore", { params: { path: { tema_id: temaId } }, body: { version } })),
        juntar: (temaId: string, body: { version: number; destinoId: string }) =>
          unwrap(client.POST("/api/aprendizado/temas/{tema_id}/juntar", { params: { path: { tema_id: temaId } }, body })),
        versions: (temaId: string) =>
          unwrap(client.GET("/api/aprendizado/temas/{tema_id}/versions", { params: { path: { tema_id: temaId } } })),
        revert: (temaId: string, version: number, toVersion: number) =>
          unwrap(client.POST("/api/aprendizado/temas/{tema_id}/revert", { params: { path: { tema_id: temaId } }, body: { version, toVersion } })),
      },
      taxonomiaPropor: (perfilId: string, body: { instrucao: string }) =>
        unwrap(client.POST("/api/perfis/{perfil_id}/aprendizado/taxonomia/propor", { params: { path: { perfil_id: perfilId } }, body })),
      classificacoes: {
        list: (perfilId: string, query: AprendizadoClassificacoesFiltros = {}) =>
          unwrap(client.GET("/api/perfis/{perfil_id}/aprendizado/classificacoes", { params: { path: { perfil_id: perfilId }, query } })),
        put: (videoId: string, body: AprendizadoClassificacaoPut) =>
          unwrap(client.PUT("/api/aprendizado/classificacoes/{video_id}", { params: { path: { video_id: videoId } }, body })),
        versions: (videoId: string) =>
          unwrap(client.GET("/api/aprendizado/classificacoes/{video_id}/versions", { params: { path: { video_id: videoId } } })),
        revert: (videoId: string, version: number, toVersion: number) =>
          unwrap(
            client.POST("/api/aprendizado/classificacoes/{video_id}/revert", { params: { path: { video_id: videoId } }, body: { version, toVersion } }),
          ),
      },
      classificarPendentes: (perfilId: string) =>
        unwrap(client.POST("/api/perfis/{perfil_id}/aprendizado/classificar-pendentes", { params: { path: { perfil_id: perfilId } } })),
      analise: (perfilId: string, query: AprendizadoAnaliseFiltros = {}) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/aprendizado/analise", { params: { path: { perfil_id: perfilId }, query } })),
      recomendacoes: (perfilId: string, query: { contaId?: string; medida?: "h1" | "h24" | "d7" } = {}) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/aprendizado/recomendacoes", { params: { path: { perfil_id: perfilId }, query } })),
      decidir: (perfilId: string, body: AprendizadoDecidirIn) =>
        unwrap(client.POST("/api/perfis/{perfil_id}/aprendizado/recomendacoes/decidir", { params: { path: { perfil_id: perfilId } }, body })),
      reverterDecisao: (decisaoId: string, version: number) =>
        unwrap(client.POST("/api/aprendizado/decisoes/{decisao_id}/revert", { params: { path: { decisao_id: decisaoId } }, body: { version } })),
      preferencias: {
        get: (perfilId: string, contaId?: string) =>
          unwrap(client.GET("/api/perfis/{perfil_id}/aprendizado/preferencias", { params: { path: { perfil_id: perfilId }, query: contaId ? { contaId } : {} } })),
        patch: (perfilId: string, body: AprendizadoPreferenciasPatch, contaId?: string) =>
          unwrap(
            client.PATCH("/api/perfis/{perfil_id}/aprendizado/preferencias", { params: { path: { perfil_id: perfilId }, query: contaId ? { contaId } : {} }, body }),
          ),
        versions: (perfilId: string, contaId?: string) =>
          unwrap(
            client.GET("/api/perfis/{perfil_id}/aprendizado/preferencias/versions", { params: { path: { perfil_id: perfilId }, query: contaId ? { contaId } : {} } }),
          ),
        revert: (perfilId: string, version: number, toVersion: number, contaId?: string) =>
          unwrap(
            client.POST("/api/perfis/{perfil_id}/aprendizado/preferencias/revert", {
              params: { path: { perfil_id: perfilId }, query: contaId ? { contaId } : {} },
              body: { version, toVersion },
            }),
          ),
      },
      analises: {
        estimativa: (perfilId: string, body: AprendizadoEstimativaIn) =>
          unwrap(client.POST("/api/perfis/{perfil_id}/aprendizado/analises/estimativa", { params: { path: { perfil_id: perfilId } }, body })),
        create: (perfilId: string, body: AprendizadoAnaliseIaIn) =>
          unwrap(client.POST("/api/perfis/{perfil_id}/aprendizado/analises", { params: { path: { perfil_id: perfilId } }, body })),
        list: (perfilId: string, query: { cursor?: string } = {}) =>
          unwrap(client.GET("/api/perfis/{perfil_id}/aprendizado/analises", { params: { path: { perfil_id: perfilId }, query } })),
        get: (analiseId: string) =>
          unwrap(client.GET("/api/aprendizado/analises/{analise_id}", { params: { path: { analise_id: analiseId } } })),
        recomendarHipotese: (analiseId: string, indice: number, body: AprendizadoHipoteseRecomendarIn) =>
          unwrap(
            client.POST("/api/aprendizado/analises/{analise_id}/hipoteses/{indice}/recomendar", {
              params: { path: { analise_id: analiseId, indice } },
              body,
            }),
          ),
      },
      diagnostico: (perfilId: string, query: AprendizadoDiagnosticoFiltros = {}) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/aprendizado/diagnostico", { params: { path: { perfil_id: perfilId }, query } })),
      postDiagnostico: (videoId: string) =>
        unwrap(client.GET("/api/aprendizado/posts/{video_id}/diagnostico", { params: { path: { video_id: videoId } } })),
      conferencia: (videoId: string, item: string, body: AprendizadoConferenciaPut) =>
        unwrap(client.PUT("/api/aprendizado/posts/{video_id}/conferencias/{item}", { params: { path: { video_id: videoId, item } }, body })),
    },
    // Geração local (spec 021): pedir, acompanhar e decidir (escritas só de humano). O envio de
    // áudio (multipart) fica no app, por XHR, para ter o progresso. Nenhuma rota DELETE.
    geracoes: {
      criar: (perfilId: string, body: GeracaoInRequest) =>
        unwrap(client.POST("/api/perfis/{perfil_id}/geracoes", { params: { path: { perfil_id: perfilId } }, body })),
      listar: (perfilId: string, query: GeracaoFilters = {}) =>
        unwrap(client.GET("/api/perfis/{perfil_id}/geracoes", { params: { path: { perfil_id: perfilId }, query } })),
      detalhe: (geracaoId: string) =>
        unwrap(client.GET("/api/geracoes/{geracao_id}", { params: { path: { geracao_id: geracaoId } } })),
      versoes: (geracaoId: string) =>
        unwrap(client.GET("/api/geracoes/{geracao_id}/versoes", { params: { path: { geracao_id: geracaoId } } })),
      escolher: (geracaoId: string, body: { candidatoId: string; version: number; alvoVersion: number }) =>
        unwrap(client.POST("/api/geracoes/{geracao_id}/escolher", { params: { path: { geracao_id: geracaoId } }, body })),
      cancelar: (geracaoId: string, version: number) =>
        unwrap(client.POST("/api/geracoes/{geracao_id}/cancelar", { params: { path: { geracao_id: geracaoId } }, body: { version } })),
      tentarDeNovo: (geracaoId: string, version: number) =>
        unwrap(client.POST("/api/geracoes/{geracao_id}/tentar-de-novo", { params: { path: { geracao_id: geracaoId } }, body: { version } })),
      gerarOutras: (geracaoId: string, version: number) =>
        unwrap(client.POST("/api/geracoes/{geracao_id}/gerar-outras", { params: { path: { geracao_id: geracaoId } }, body: { version } })),
      audio: (audioId: string) => unwrap(client.GET("/api/audios/{audio_id}", { params: { path: { audio_id: audioId } } })),
    },
    config: () => unwrap(client.GET("/api/config")),
    health: () => unwrap(client.GET("/api/health")),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
