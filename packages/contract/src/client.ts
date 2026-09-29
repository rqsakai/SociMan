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
export type MidiaKind = "corte_original" | "corte_marcado" | "fonte" | "marca_dagua" | "fundo";
export type CorteFilters = NonNullable<paths["/api/perfis/{perfil_id}/cortes"]["get"]["parameters"]["query"]>;
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
    config: () => unwrap(client.GET("/api/config")),
    health: () => unwrap(client.GET("/api/health")),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
