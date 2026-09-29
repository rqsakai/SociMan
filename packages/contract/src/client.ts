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
export type MidiaKind = "corte_original" | "corte_marcado" | "fonte" | "marca_dagua" | "fundo" | "imagem";
export type CorteFilters = NonNullable<paths["/api/perfis/{perfil_id}/cortes"]["get"]["parameters"]["query"]>;
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
export type Postagem = components["schemas"]["Postagem"];
export type EstadoPostagem = components["schemas"]["EstadoPostagem"];
export type Sugestao = components["schemas"]["Sugestao"];
export type CreatePostagemRequest = Defaulted<components["schemas"]["CreatePostagemIn"], "titulo" | "descricao">;
export type UpdatePostagemRequest = components["schemas"]["UpdatePostagemIn"];
export type CalendarioItem = components["schemas"]["CalendarioItem"];
export type CalendarioSemData = components["schemas"]["SemData"];
export type CalendarioFilters = paths["/api/calendario"]["get"]["parameters"]["query"];
export type Integracoes = components["schemas"]["Integracoes"];
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
    // Postagens (spec 006, US5): uma por conta de destino; o SociMan NÃO publica (princípio I).
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
      listDoCorte: (corteId: string, archived = false) =>
        unwrap(client.GET("/api/cortes/{corte_id}/postagens", { params: { path: { corte_id: corteId }, query: { archived } } })),
      create: (corteId: string, body: CreatePostagemRequest) =>
        unwrap(
          client.POST("/api/cortes/{corte_id}/postagens", {
            params: { path: { corte_id: corteId } },
            body: { titulo: "", descricao: "", ...body },
          }),
        ),
      get: (postagemId: string) =>
        unwrap(client.GET("/api/postagens/{postagem_id}", { params: { path: { postagem_id: postagemId } } })),
      update: (postagemId: string, body: UpdatePostagemRequest) =>
        unwrap(client.PATCH("/api/postagens/{postagem_id}", { params: { path: { postagem_id: postagemId } }, body })),
      postado: (postagemId: string, body: { version: number; postedUrl?: string | null }) =>
        unwrap(client.POST("/api/postagens/{postagem_id}/postado", { params: { path: { postagem_id: postagemId } }, body })),
      archive: (postagemId: string, version: number) =>
        unwrap(client.POST("/api/postagens/{postagem_id}/archive", { params: { path: { postagem_id: postagemId } }, body: { version } })),
      restore: (postagemId: string, version: number) =>
        unwrap(client.POST("/api/postagens/{postagem_id}/restore", { params: { path: { postagem_id: postagemId } }, body: { version } })),
      versions: (postagemId: string) =>
        unwrap(client.GET("/api/postagens/{postagem_id}/versions", { params: { path: { postagem_id: postagemId } } })),
      revert: (postagemId: string, version: number, toVersion: number) =>
        unwrap(
          client.POST("/api/postagens/{postagem_id}/revert", {
            params: { path: { postagem_id: postagemId } },
            body: { version, toVersion },
          }),
        ),
    },
    calendario: (query: CalendarioFilters) => unwrap(client.GET("/api/calendario", { params: { query } })),
    integracoes: () => unwrap(client.GET("/api/integracoes")),
    // Sino do painel (spec 006, R11): polling com `after` (id); marcar lidas só preenche `lida_em`.
    notificacoes: {
      list: (query: NotificacaoFilters = {}) => unwrap(client.GET("/api/notificacoes", { params: { query } })),
      marcarLidas: (body: { ids: number[] } | { todas: true }) =>
        unwrap(client.POST("/api/notificacoes/lidas", { body: { todas: false, ...body } })),
    },
    config: () => unwrap(client.GET("/api/config")),
    health: () => unwrap(client.GET("/api/health")),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
