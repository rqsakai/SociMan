import { and, eq, isNotNull, lte, sql } from "drizzle-orm";
import { kvStore } from "../db/schema";
import type { Db } from "./adapters/db";

// Interface mínima de KV usada por sessões/refresh e rate limit.
// Em produção o pipeline fornece uma implementação sobre o Edge KV da Azion;
// tudo que o app exige está descrito aqui.
export interface KV {
  get<T>(key: string): Promise<T | null>;
  set(key: string, value: unknown, opts?: { ttlSeconds?: number }): Promise<void>;
  delete(key: string): Promise<void>;
  // Incremento atômico com janela: se a chave não existe ou expirou, recomeça
  // em 1 com novo TTL. Retorna o valor do contador após o incremento.
  incr(key: string, opts: { ttlSeconds: number }): Promise<number>;
}

export class SqliteKV implements KV {
  constructor(private readonly db: Db) {}

  async get<T>(key: string): Promise<T | null> {
    const row = await this.db.query.kvStore.findFirst({ where: eq(kvStore.key, key) });
    if (!row) return null;
    if (row.expiresAt !== null && row.expiresAt.getTime() <= Date.now()) {
      // expiração lazy
      await this.db
        .delete(kvStore)
        .where(and(eq(kvStore.key, key), isNotNull(kvStore.expiresAt), lte(kvStore.expiresAt, new Date())));
      return null;
    }
    return JSON.parse(row.value) as T;
  }

  async set(key: string, value: unknown, opts?: { ttlSeconds?: number }): Promise<void> {
    const expiresAt = opts?.ttlSeconds ? new Date(Date.now() + opts.ttlSeconds * 1000) : null;
    const serialized = JSON.stringify(value);
    await this.db
      .insert(kvStore)
      .values({ key, value: serialized, expiresAt })
      .onConflictDoUpdate({
        target: kvStore.key,
        set: { value: serialized, expiresAt },
      });
  }

  async delete(key: string): Promise<void> {
    await this.db.delete(kvStore).where(eq(kvStore.key, key));
  }

  async incr(key: string, opts: { ttlSeconds: number }): Promise<number> {
    const now = Date.now();
    const expiresAt = now + opts.ttlSeconds * 1000;
    // Upsert atômico com RETURNING em UM statement (= 1 round-trip no driver
    // REST da borda; o de dois passos custava 2 idas ao Edge SQL a ~2s cada).
    // libsql (dev/docker) e o REST do Edge SQL aceitam RETURNING; o driver
    // nativo azion:sql NÃO — por isso a borda usa o REST (ver edgeDb.ts).
    // Janela expirada reinicia em 1.
    const row = await this.db.get<{ value: string }>(sql`
      INSERT INTO kv_store ("key", value, expires_at)
      VALUES (${key}, '1', ${expiresAt})
      ON CONFLICT("key") DO UPDATE SET
        value = CASE
          WHEN kv_store.expires_at IS NOT NULL AND kv_store.expires_at <= ${now}
            THEN '1'
          ELSE CAST(CAST(kv_store.value AS INTEGER) + 1 AS TEXT)
        END,
        expires_at = CASE
          WHEN kv_store.expires_at IS NOT NULL AND kv_store.expires_at <= ${now}
            THEN ${expiresAt}
          ELSE kv_store.expires_at
        END
      RETURNING value
    `);
    // objeto {value} no driver libsql local; ARRAY de valores no sqlite-proxy
    const value = Array.isArray(row) ? row[0] : row?.value;
    return Number(value ?? 0);
  }
}
