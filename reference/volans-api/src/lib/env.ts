import { z } from "zod";
import { randomToken } from "./crypto";

// Toda configuração numérica/[config] do brief vive aqui, lida do ambiente.
// NADA deste módulo pode vazar para o bundle do frontend.
const envSchema = z.object({
  APP_URL: z.string().default("http://localhost:5173"),
  // Nome do app — vira a claim `aud` dos JWTs (dois apps Volans com o mesmo
  // secret por engano NÃO aceitam tokens um do outro).
  APP_NAME: z.string().default("boilerplate-01-auth"),
  // O pipeline da Azion seta "production" no deploy. NODE_ENV NÃO é confiável
  // no isolate (pode nem existir) — por isso a flag própria.
  VOLANS_ENV: z.enum(["development", "production"]).default("development"),
  // Sem default: em produção é obrigatório (getEnv lança); em dev, ausente →
  // um secret efêmero forte é gerado por processo.
  JWT_SECRET: z
    .string()
    .min(32, "JWT_SECRET precisa de pelo menos 32 caracteres (use openssl rand -base64 32)")
    .optional(),
  ACCESS_TTL: z.coerce.number().int().positive().default(15 * 60), // segundos
  REFRESH_TTL: z.coerce.number().int().positive().default(7 * 24 * 60 * 60), // segundos
  // Janela em que o refresh da geração anterior ainda é aceito após rotação
  // (cobre respostas de refresh perdidas em navegação). 0 = estrito.
  REFRESH_GRACE: z.coerce.number().int().min(0).default(60), // segundos
  PASSWORD_HASH: z.enum(["argon2id", "pbkdf2"]).default("argon2id"),
  PASSWORD_MIN_LENGTH: z.coerce.number().int().min(8).default(8),
  ARGON2_MEMORY_KIB: z.coerce.number().int().positive().default(19456),
  ARGON2_ITERATIONS: z.coerce.number().int().positive().default(2),
  ARGON2_PARALLELISM: z.coerce.number().int().positive().default(1),
  PBKDF2_ITERATIONS: z.coerce.number().int().positive().default(600_000),
  RESET_TOKEN_TTL: z.coerce.number().int().positive().default(15 * 60), // segundos
  VERIFY_TOKEN_TTL: z.coerce.number().int().positive().default(24 * 60 * 60), // segundos
  DATABASE_URL: z.string().default("file:./data/dev.db"),
  // KV: "sqlite" (tabela local, default do dev sem Docker) ou "redis"
  // (docker-compose, análogo do Edge KV). Mesma interface (src/lib/kv.ts).
  KV_DRIVER: z.enum(["sqlite", "redis"]).default("sqlite"),
  REDIS_URL: z.string().default("redis://localhost:6379"),
  // Object Storage (análogo S3/MinIO) — "none" desliga; recipes de upload usam
  // a interface ObjectStorage (src/lib/storage.ts)
  STORAGE_DRIVER: z.enum(["none", "s3"]).default("none"),
  S3_ENDPOINT: z.string().optional(),
  S3_REGION: z.string().default("us-east-1"),
  S3_ACCESS_KEY: z.string().optional(),
  S3_SECRET_KEY: z.string().optional(),
  S3_BUCKET: z.string().default("volans-dev"),
  // Image Processor (análogo do da Azion; imgproxy no compose) — URLs servidas
  // pelo edge em IMGPROXY_PUBLIC_PATH. Interface em src/lib/imaging.ts.
  IMAGE_DRIVER: z.enum(["none", "imgproxy"]).default("none"),
  IMGPROXY_PUBLIC_PATH: z.string().default("/img"),
  IMGPROXY_KEY: z.string().optional(), // hex; sem key/salt = URLs /unsafe (SÓ dev)
  IMGPROXY_SALT: z.string().optional(),
  EMAIL_PROVIDER: z.string().default("stub"),
  EMAIL_FILE: z.string().default("./data/outbox.jsonl"),
  // Remetente dos e-mails (o domínio precisa estar verificado no provider).
  EMAIL_FROM: z.string().default("Volans <no-reply@volan.theitnerd.io>"),
  // BYOK: a API key do provider do CLIENTE (Resend etc.). Na borda vem de uma
  // Azion Variable (secret); em Node/Docker, do ambiente.
  RESEND_API_KEY: z.string().optional(),
  SMTP_HOST: z.string().default("localhost"),
  SMTP_PORT: z.coerce.number().int().positive().default(1025),
  SMTP_FROM: z.string().default("Volans <no-reply@volans.local>"),
  // auth/TLS do SMTP do cliente (opcional; Mailpit no docker não usa)
  SMTP_USER: z.string().optional(),
  SMTP_PASS: z.string().optional(),
  SMTP_SECURE: z
    .string()
    .optional()
    .transform((v) => v === "1" || v === "true"),
  CONSENT_POLICY_VERSION: z.string().default("2026-08"),
  // true SOMENTE quando um proxy confiável (nginx do compose / edge da Azion)
  // está na frente reescrevendo X-Real-IP. Sem isso, nenhum header de IP é
  // confiável (X-Forwarded-For cru é spoofável) e o rate limit usa "local".
  TRUSTED_PROXY: z
    .string()
    .optional()
    .transform((v) => v === "1" || v === "true"),
});

type ParsedEnv = z.infer<typeof envSchema>;

// Depois do getEnv(), JWT_SECRET é sempre string (obrigatório em produção,
// gerado em dev) — o resto do app não lida com a ausência.
export type Env = Omit<ParsedEnv, "JWT_SECRET"> & { JWT_SECRET: string };

export function isProduction(env: Pick<ParsedEnv, "VOLANS_ENV">): boolean {
  return env.VOLANS_ENV === "production" || process.env.NODE_ENV === "production";
}

let cached: Env | null = null;

// `source` permite injetar o ambiente em runtimes sem process.env gravável
// (o isolate da Azion é Deno-based e congela process.env — os args da
// function entram por aqui). Sem argumento, lê process.env normalmente.
export function getEnv(source?: Record<string, string | undefined>): Env {
  if (cached) return cached;

  const parsed = envSchema.parse(source ?? process.env);

  let secret = parsed.JWT_SECRET;
  if (!secret) {
    if (isProduction(parsed)) {
      throw new Error(
        "JWT_SECRET é obrigatório em produção (mínimo 32 caracteres) — configure via pipeline. " +
          "Sem ele, todos os tokens do app seriam forjáveis.",
      );
    }
    // Dev sem secret: um efêmero forte por processo. Access tokens deixam de
    // valer no restart, mas o refresh é OPACO (hash no KV, independe do JWT)
    // e re-emite a sessão de forma transparente no próximo reload.
    secret = randomToken();
    console.warn(
      "[env] JWT_SECRET ausente — gerado um secret efêmero para este processo (ok em dev). " +
        "Em produção o pipeline DEVE definir JWT_SECRET.",
    );
  }

  cached = { ...parsed, JWT_SECRET: secret };
  return cached;
}

export function resetEnvForTests(): void {
  cached = null;
}
