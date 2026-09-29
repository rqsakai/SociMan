import type { Db } from "../lib/adapters/db";
import { getDb } from "../lib/adapters/db";
import { createFileEmailProvider } from "../lib/adapters/fileEmail";
import { createImgproxyProcessor } from "../lib/adapters/imgproxy";
import { createRedisKV } from "../lib/adapters/redisKv";
import { createResendEmailProvider } from "../lib/adapters/resendEmail";
import { createS3Storage } from "../lib/adapters/s3Storage";
import { createSmtpEmailProvider } from "../lib/adapters/smtpEmail";
import { createStubEmailProvider } from "../lib/adapters/stubEmail";
import { getEnv, isProduction, type Env } from "../lib/env";
import type { ImageProcessor } from "../lib/imaging";
import { SqliteKV, type KV } from "../lib/kv";
import type { ObjectStorage } from "../lib/storage";
import type { EmailProvider } from "../services/emailService";
import { createPasswordService, type PasswordService } from "../services/passwordService";
import { createTokenService, type TokenService } from "../services/tokenService";

// Injeção de dependências dos handlers: produção usa getDefaultDeps();
// testes montam o mesmo objeto sobre um DB :memory: (tests/helpers).
// Os drivers (KV, e-mail, storage) são selecionados por env — mesma interface,
// backing diferente (dev local: sqlite/stub; docker: redis/smtp/minio;
// Azion: Edge KV/provider real via pipeline).
export interface HandlerDeps {
  db: Db;
  kv: KV;
  passwords: PasswordService;
  tokens: TokenService;
  email: EmailProvider;
  storage: ObjectStorage | null;
  images: ImageProcessor | null;
  env: Env;
}

function selectKv(db: Db, env: Env): KV {
  return env.KV_DRIVER === "redis" ? createRedisKV(env.REDIS_URL) : new SqliteKV(db);
}

function selectEmail(env: Env): EmailProvider {
  switch (env.EMAIL_PROVIDER) {
    case "file":
      return createFileEmailProvider(env.EMAIL_FILE);
    case "smtp":
      return createSmtpEmailProvider({
        host: env.SMTP_HOST,
        port: env.SMTP_PORT,
        from: env.SMTP_FROM,
        user: env.SMTP_USER,
        pass: env.SMTP_PASS,
        secure: env.SMTP_SECURE,
      });
    case "resend":
      if (!env.RESEND_API_KEY) {
        throw new Error("EMAIL_PROVIDER=resend exige RESEND_API_KEY");
      }
      return createResendEmailProvider({ apiKey: env.RESEND_API_KEY, from: env.EMAIL_FROM });
    case "stub":
      return createStubEmailProvider();
    default:
      // falha alto: um EMAIL_PROVIDER desconhecido em produção significaria não
      // enviar e-mail silenciosamente
      throw new Error(`EMAIL_PROVIDER desconhecido: "${env.EMAIL_PROVIDER}"`);
  }
}

function selectImages(env: Env): ImageProcessor | null {
  if (env.IMAGE_DRIVER !== "imgproxy") return null;
  // Em produção, URLs /unsafe são custo de compute aberto ao público — o
  // processamento de imagem é um dos 4 limites do modelo de custo.
  if (isProduction(env) && (!env.IMGPROXY_KEY || !env.IMGPROXY_SALT)) {
    throw new Error(
      "IMAGE_DRIVER=imgproxy em produção exige IMGPROXY_KEY e IMGPROXY_SALT (URLs assinadas)",
    );
  }
  return createImgproxyProcessor({
    publicPath: env.IMGPROXY_PUBLIC_PATH,
    keyHex: env.IMGPROXY_KEY,
    saltHex: env.IMGPROXY_SALT,
  });
}

function selectStorage(env: Env): ObjectStorage | null {
  if (env.STORAGE_DRIVER !== "s3") return null;
  if (!env.S3_ACCESS_KEY || !env.S3_SECRET_KEY) {
    throw new Error("STORAGE_DRIVER=s3 exige S3_ACCESS_KEY e S3_SECRET_KEY");
  }
  return createS3Storage({
    endpoint: env.S3_ENDPOINT,
    region: env.S3_REGION,
    accessKey: env.S3_ACCESS_KEY,
    secretKey: env.S3_SECRET_KEY,
    bucket: env.S3_BUCKET,
  });
}

export function buildDeps(db: Db, kv: KV, env: Env): HandlerDeps {
  return {
    db,
    kv,
    env,
    passwords: createPasswordService({
      algorithm: env.PASSWORD_HASH,
      argon2: {
        memoryKib: env.ARGON2_MEMORY_KIB,
        iterations: env.ARGON2_ITERATIONS,
        parallelism: env.ARGON2_PARALLELISM,
      },
      pbkdf2: { iterations: env.PBKDF2_ITERATIONS },
    }),
    tokens: createTokenService(kv, {
      jwtSecret: env.JWT_SECRET,
      accessTtlSeconds: env.ACCESS_TTL,
      refreshTtlSeconds: env.REFRESH_TTL,
      graceSeconds: env.REFRESH_GRACE,
      audience: env.APP_NAME,
    }),
    email: selectEmail(env),
    storage: selectStorage(env),
    images: selectImages(env),
  };
}

const globalForDeps = globalThis as unknown as { __volansDeps?: HandlerDeps };

export function getDefaultDeps(): HandlerDeps {
  if (!globalForDeps.__volansDeps) {
    const env = getEnv();
    const db = getDb();
    globalForDeps.__volansDeps = buildDeps(db, selectKv(db, env), env);
  }
  return globalForDeps.__volansDeps;
}
