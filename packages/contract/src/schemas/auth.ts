import { z } from "zod";
import { passwordSchema } from "../password";

export const emailSchema = z.string().trim().toLowerCase().pipe(z.email("E-mail inválido"));

export const userSchema = z.object({
  id: z.string(),
  name: z.string().nullable(),
  email: z.string(),
  emailVerified: z.boolean(),
  createdAt: z.string(),
});
export type User = z.infer<typeof userSchema>;

export const registerRequestSchema = z.object({
  name: z.string().trim().min(1).max(120).optional(),
  email: emailSchema,
  password: passwordSchema(),
});
export type RegisterRequest = z.infer<typeof registerRequestSchema>;

export const loginRequestSchema = z.object({
  email: emailSchema,
  password: z.string().min(1),
});
export type LoginRequest = z.infer<typeof loginRequestSchema>;

// Resposta comum de register/login/refresh: access token no body,
// refresh token vai APENAS no cookie httpOnly path-scoped.
export const authSessionResponseSchema = z.object({
  accessToken: z.string(),
  user: userSchema,
});
export type AuthSessionResponse = z.infer<typeof authSessionResponseSchema>;

export const okResponseSchema = z.object({ ok: z.literal(true) });
export type OkResponse = z.infer<typeof okResponseSchema>;

export const forgotPasswordRequestSchema = z.object({
  email: emailSchema,
});
export type ForgotPasswordRequest = z.infer<typeof forgotPasswordRequestSchema>;

export const resetPasswordRequestSchema = z.object({
  token: z.string().min(1),
  newPassword: passwordSchema(),
});
export type ResetPasswordRequest = z.infer<typeof resetPasswordRequestSchema>;

export const verifyEmailRequestSchema = z.object({
  token: z.string().min(1),
});
export type VerifyEmailRequest = z.infer<typeof verifyEmailRequestSchema>;

export const meResponseSchema = z.object({
  user: userSchema,
});
export type MeResponse = z.infer<typeof meResponseSchema>;
