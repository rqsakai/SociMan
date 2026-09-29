// KV sobre Redis (docker-compose; análogo do Edge KV da Azion). Mesma
// interface de src/lib/kv.ts — sessões/refresh e rate limit não sabem qual
// driver está por baixo. Vive em adapters/ por depender de rede/cliente Node.
import { createClient, type RedisClientType } from "redis";
import type { KV } from "../kv";

export function createRedisKV(url: string): KV {
  const client: RedisClientType = createClient({ url });
  client.on("error", (err) => console.error("[redis]", err.message));
  let connecting: Promise<unknown> | null = null;

  async function conn(): Promise<RedisClientType> {
    if (!client.isOpen) {
      connecting ??= client.connect();
      await connecting;
    }
    return client;
  }

  return {
    async get<T>(key: string): Promise<T | null> {
      const raw = await (await conn()).get(key);
      return raw === null ? null : (JSON.parse(raw) as T);
    },

    async set(key, value, opts) {
      const c = await conn();
      const serialized = JSON.stringify(value);
      if (opts?.ttlSeconds) {
        await c.set(key, serialized, { EX: opts.ttlSeconds });
      } else {
        await c.set(key, serialized);
      }
    },

    async delete(key) {
      await (await conn()).del(key);
    },

    async incr(key, opts) {
      const c = await conn();
      const count = await c.incr(key);
      // primeira batida da janela define o TTL; INCR é atômico no Redis
      if (count === 1) {
        await c.expire(key, opts.ttlSeconds);
      }
      return count;
    },
  };
}
