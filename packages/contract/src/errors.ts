import type { components } from "./generated/schema";

// O OpenAPI tipa `ErrorBody.code` como string; a lista fechada vem do contrato
// (specs/001-auth, 003-contas-sociais e 004-kit-de-marca, contracts/http-api.md).
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
  "slug_in_use",
  "handle_in_use",
  "active_platform_exists",
  "version_conflict",
  "revert_conflict",
  "invalid_image",
  // 004-kit-de-marca
  "invalid_kit",
  "invalid_font",
  "font_name_in_use",
  "font_in_use",
  "invalid_video",
  "invalid_hook",
  "payload_too_large",
  "storage_unavailable",
  "storage_full",
  "perfil_archived",
  "not_ready",
  "invalid_link",
] as const;

export type ErrorCode = (typeof errorCodes)[number];

export type ApiErrorBody = components["schemas"]["ErrorEnvelope"];

export function isErrorCode(value: unknown): value is ErrorCode {
  return typeof value === "string" && (errorCodes as readonly string[]).includes(value);
}
