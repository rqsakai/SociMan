import type { z } from "zod";
import { apiErrorSchema, type ErrorCode } from "./errors";
import {
  authSessionResponseSchema,
  meResponseSchema,
  okResponseSchema,
  type ForgotPasswordRequest,
  type LoginRequest,
  type RegisterRequest,
  type ResetPasswordRequest,
  type VerifyEmailRequest,
} from "./schemas/auth";
import { configResponseSchema } from "./schemas/config";
import { type ConsentRequest } from "./schemas/consent";

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

export interface ApiClientOptions {
  baseUrl?: string;
  // Ponto de injeção para o app: anexar Authorization, retry pós-refresh etc.
  fetchFn?: typeof fetch;
}

async function parseResponse<T>(res: Response, schema: z.ZodType<T>): Promise<T> {
  if (!res.ok) {
    let code: ErrorCode = "internal_error";
    let message = `HTTP ${res.status}`;
    try {
      const parsed = apiErrorSchema.parse(await res.json());
      code = parsed.error.code;
      message = parsed.error.message;
    } catch {
      // corpo não segue o contrato de erro — mantém o genérico
    }
    throw new ApiError(res.status, code, message);
  }
  return schema.parse(await res.json());
}

export function createApiClient(options: ApiClientOptions = {}) {
  const baseUrl = options.baseUrl ?? "";
  const fetchFn = options.fetchFn ?? fetch;

  const post = (path: string, body?: unknown) =>
    fetchFn(`${baseUrl}${path}`, {
      method: "POST",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });

  const get = (path: string) => fetchFn(`${baseUrl}${path}`);

  return {
    auth: {
      register: async (body: RegisterRequest) =>
        parseResponse(await post("/api/auth/register", body), authSessionResponseSchema),
      login: async (body: LoginRequest) =>
        parseResponse(await post("/api/auth/login", body), authSessionResponseSchema),
      refresh: async () =>
        parseResponse(await post("/api/auth/refresh"), authSessionResponseSchema),
      logout: async () => parseResponse(await post("/api/auth/logout"), okResponseSchema),
      forgotPassword: async (body: ForgotPasswordRequest) =>
        parseResponse(await post("/api/auth/password/forgot", body), okResponseSchema),
      resetPassword: async (body: ResetPasswordRequest) =>
        parseResponse(await post("/api/auth/password/reset", body), okResponseSchema),
      verifyEmail: async (body: VerifyEmailRequest) =>
        parseResponse(await post("/api/auth/verify-email", body), okResponseSchema),
      me: async () => parseResponse(await get("/api/auth/me"), meResponseSchema),
    },
    consent: {
      record: async (body: ConsentRequest) =>
        parseResponse(await post("/api/consent", body), okResponseSchema),
    },
    config: async () => parseResponse(await get("/api/config"), configResponseSchema),
    health: async () => parseResponse(await get("/api/health"), okResponseSchema),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
