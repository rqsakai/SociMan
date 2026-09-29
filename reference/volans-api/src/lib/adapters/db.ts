// ÚNICO módulo (junto com env.ts) autorizado a tocar infraestrutura local.
// Em produção na Azion, o pipeline troca a factory por `@libsql/client/web`
// (HTTP) — o resto do app só conhece a interface do Drizzle.
import { createClient, type Client } from "@libsql/client";
import { drizzle, type LibSQLDatabase } from "drizzle-orm/libsql";
import * as schema from "../../db/schema";
import { getEnv } from "../env";

export type Db = LibSQLDatabase<typeof schema>;

const globalForDb = globalThis as unknown as { __volansDb?: { client: Client; db: Db } };

export function getDb(): Db {
  if (!globalForDb.__volansDb) {
    const client = createClient({ url: getEnv().DATABASE_URL });
    globalForDb.__volansDb = { client, db: drizzle(client, { schema }) };
  }
  return globalForDb.__volansDb.db;
}

export function createTestDb(): { db: Db; client: Client } {
  const client = createClient({ url: ":memory:" });
  return { client, db: drizzle(client, { schema }) };
}
