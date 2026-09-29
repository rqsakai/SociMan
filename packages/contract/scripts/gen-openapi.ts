import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { OpenAPIRegistry, OpenApiGeneratorV31 } from "@asteasolutions/zod-to-openapi";
import { z } from "zod";
import {
  apiErrorSchema,
  authSessionResponseSchema,
  configResponseSchema,
  consentRequestSchema,
  forgotPasswordRequestSchema,
  loginRequestSchema,
  meResponseSchema,
  okResponseSchema,
  registerRequestSchema,
  resetPasswordRequestSchema,
  verifyEmailRequestSchema,
} from "../src/index";

const registry = new OpenAPIRegistry();

const jsonBody = (schema: z.ZodType) => ({
  content: { "application/json": { schema } },
});

const errorResponses = {
  400: { description: "Erro de validação ou de negócio", ...jsonBody(apiErrorSchema) },
  401: { description: "Não autenticado", ...jsonBody(apiErrorSchema) },
  429: { description: "Rate limit excedido", ...jsonBody(apiErrorSchema) },
};

type Endpoint = {
  path: string;
  method: "get" | "post";
  summary: string;
  request?: z.ZodType;
  response: z.ZodType;
};

const endpoints: Endpoint[] = [
  {
    path: "/api/auth/register",
    method: "post",
    summary: "Cria usuário, dispara e-mail de verificação e abre sessão",
    request: registerRequestSchema,
    response: authSessionResponseSchema,
  },
  {
    path: "/api/auth/login",
    method: "post",
    summary: "Autentica com e-mail e senha (erro genérico, rate-limited)",
    request: loginRequestSchema,
    response: authSessionResponseSchema,
  },
  {
    path: "/api/auth/refresh",
    method: "post",
    summary: "Rotaciona o refresh token (cookie) e emite novo access token",
    response: authSessionResponseSchema,
  },
  {
    path: "/api/auth/logout",
    method: "post",
    summary: "Revoga a família de refresh e limpa o cookie",
    response: okResponseSchema,
  },
  {
    path: "/api/auth/password/forgot",
    method: "post",
    summary: "Solicita link de redefinição (sempre 200 — sem enumeração)",
    request: forgotPasswordRequestSchema,
    response: okResponseSchema,
  },
  {
    path: "/api/auth/password/reset",
    method: "post",
    summary: "Redefine a senha e revoga todas as sessões do usuário",
    request: resetPasswordRequestSchema,
    response: okResponseSchema,
  },
  {
    path: "/api/auth/verify-email",
    method: "post",
    summary: "Confirma o e-mail do usuário",
    request: verifyEmailRequestSchema,
    response: okResponseSchema,
  },
  {
    path: "/api/auth/me",
    method: "get",
    summary: "Usuário atual (a partir do access token)",
    response: meResponseSchema,
  },
  {
    path: "/api/consent",
    method: "post",
    summary: "Registra consentimento LGPD (auditoria)",
    request: consentRequestSchema,
    response: okResponseSchema,
  },
  {
    path: "/api/config",
    method: "get",
    summary: "Config pública do app (espelho dos [config] que o front valida)",
    response: configResponseSchema,
  },
  { path: "/api/health", method: "get", summary: "Health check", response: okResponseSchema },
];

for (const e of endpoints) {
  registry.registerPath({
    method: e.method,
    path: e.path,
    summary: e.summary,
    ...(e.request ? { request: { body: jsonBody(e.request) } } : {}),
    responses: {
      200: { description: "OK", ...jsonBody(e.response) },
      ...errorResponses,
    },
  });
}

const generator = new OpenApiGeneratorV31(registry.definitions);
const doc = generator.generateDocument({
  openapi: "3.1.0",
  info: {
    title: "SociMan API",
    version: "0.1.0",
    description:
      "Contrato REST do starter de autenticação. Access token via Bearer; refresh token em cookie httpOnly path-scoped a /api/auth/refresh.",
  },
});

const out = fileURLToPath(new URL("../openapi.json", import.meta.url));
writeFileSync(out, JSON.stringify(doc, null, 2));
console.log(`openapi.json gerado em ${out}`);
