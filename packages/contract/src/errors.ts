import { z } from "zod";

export const errorCodes = [
  "validation_error",
  "invalid_credentials",
  "email_not_verified",
  "email_in_use",
  "invalid_token",
  "unauthorized",
  "rate_limited",
  "internal_error",
] as const;

export type ErrorCode = (typeof errorCodes)[number];

export const apiErrorSchema = z.object({
  error: z.object({
    code: z.enum(errorCodes),
    message: z.string(),
  }),
});

export type ApiErrorBody = z.infer<typeof apiErrorSchema>;
