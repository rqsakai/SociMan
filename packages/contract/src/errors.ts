import type { components } from "./generated/schema";

// O OpenAPI tipa `ErrorBody.code` como string; a lista fechada vem do contrato
// (specs/001-auth/contracts/http-api.md).
export const errorCodes = [
  "validation_error",
  "invalid_credentials",
  "email_not_verified",
  "email_in_use",
  "invalid_token",
  "unauthorized",
  "rate_limited",
  "internal_error",
  "forbidden",
  "password_change_required",
  "last_owner",
  "not_found",
  "conflict",
] as const;

export type ErrorCode = (typeof errorCodes)[number];

export type ApiErrorBody = components["schemas"]["ErrorEnvelope"];

export function isErrorCode(value: unknown): value is ErrorCode {
  return typeof value === "string" && (errorCodes as readonly string[]).includes(value);
}
