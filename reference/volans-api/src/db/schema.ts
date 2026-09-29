import { index, integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const users = sqliteTable("users", {
  id: text("id").primaryKey(),
  name: text("name"),
  email: text("email").notNull().unique(),
  passwordHash: text("password_hash").notNull(),
  emailVerified: integer("email_verified", { mode: "boolean" }).notNull().default(false),
  createdAt: integer("created_at", { mode: "timestamp_ms" }).notNull(),
  updatedAt: integer("updated_at", { mode: "timestamp_ms" }).notNull(),
});

// Tokens single-use guardados APENAS como SHA-256 do token entregue por e-mail.
export const passwordResetTokens = sqliteTable(
  "password_reset_tokens",
  {
    tokenHash: text("token_hash").primaryKey(),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    expiresAt: integer("expires_at", { mode: "timestamp_ms" }).notNull(),
    usedAt: integer("used_at", { mode: "timestamp_ms" }),
  },
  (t) => [index("password_reset_tokens_user_idx").on(t.userId)],
);

export const emailVerificationTokens = sqliteTable(
  "email_verification_tokens",
  {
    tokenHash: text("token_hash").primaryKey(),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    expiresAt: integer("expires_at", { mode: "timestamp_ms" }).notNull(),
  },
  (t) => [index("email_verification_tokens_user_idx").on(t.userId)],
);

// Auditoria LGPD — user_id nulo para visitante anônimo (identificado por anon_id).
export const consentRecords = sqliteTable("consent_records", {
  id: text("id").primaryKey(),
  userId: text("user_id").references(() => users.id, { onDelete: "set null" }),
  anonId: text("anon_id"),
  categories: text("categories").notNull(),
  policyVersion: text("policy_version").notNull(),
  ip: text("ip"),
  userAgent: text("user_agent"),
  createdAt: integer("created_at", { mode: "timestamp_ms" }).notNull(),
});

// KV de dev sobre SQLite (sessões/refresh, rate limit). Em produção o adapter
// troca para o Edge KV da Azion mantendo a mesma interface (src/lib/kv.ts).
export const kvStore = sqliteTable("kv_store", {
  key: text("key").primaryKey(),
  value: text("value").notNull(),
  expiresAt: integer("expires_at", { mode: "timestamp_ms" }),
});
