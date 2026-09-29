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
export type SecurityEventFilters = NonNullable<
  paths["/api/security-events"]["get"]["parameters"]["query"]
>;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: ErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Monta o ApiError a partir do corpo de erro já lido (JSON ou texto).
export function toApiError(status: number, body: unknown): ApiError {
  const error = (body as { error?: { code?: unknown; message?: unknown } } | null)?.error;
  if (isErrorCode(error?.code) && typeof error.message === "string") {
    return new ApiError(status, error.code, error.message);
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
    config: () => unwrap(client.GET("/api/config")),
    health: () => unwrap(client.GET("/api/health")),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
