# Conectores (Adapters) — arquitetura, configuração e extensão

Este starter é construído sobre **conectores plugáveis**: cada recurso externo
(banco, KV, e-mail, storage, imagem) é uma **interface** (contrato) com uma ou
mais **implementações** (adapters), escolhida por **variável de ambiente** e
injetada nos handlers. Os handlers nunca conhecem a implementação — só o
contrato. Trocar de backing é **configuração, não código**.

## O padrão em uma imagem

```
handler (Request, deps) -> Response        ← depende só das INTERFACES
        │
        ▼
   HandlerDeps  { db, kv, email, storage, images, passwords, tokens, env }
        │
        ├─ buildDeps(env)      → Node/Docker  (apps/api/src/handlers/deps.ts)
        └─ getEdgeDeps(args)   → borda Azion  (apps/api-edge/src/edgeDeps.ts)
                │
                ▼
        select*(env) escolhe o ADAPTER por env var
                │
                ▼
   Contrato (interface)  ─implementado por─  Adapter  ─fala com─  backing
   src/lib/kv.ts                             adapters/redisKv.ts    Redis
```

- **Contratos**: `src/lib/{kv,storage,imaging}.ts`, `src/services/emailService.ts`.
- **Adapters**: `src/lib/adapters/*.ts` (Node/infra) e `apps/api-edge/src/*.ts` (borda).
- **Seleção**: funções `select*` em `deps.ts` (Node) e a montagem em `edgeDeps.ts` (borda).
- **Injeção**: `HandlerDeps` — o objeto que todo handler recebe.

## Regra de ouro: dois runtimes

O mesmo código roda em dois lugares, e isso decide **onde cada adapter pode viver**:

| Runtime | O que pode | Adapters |
|---|---|---|
| **Node/Docker** (`deps.ts`) | tudo (node:*, TCP, libs nativas) | todos |
| **Borda Azion** (`edgeDeps.ts`) | **só APIs web-standard** (`fetch`, WebCrypto, Request/Response) — **sem `node:*`, sem socket TCP** | apenas os edge-safe |

> **Ao criar um adapter que a borda vai importar, use SÓ web-standard.** Um
> `import` de `nodemailer`/`fs`/cliente TCP quebra o bundle do isolate. Por isso
> a seleção é separada: `deps.ts` (Node) importa todos; `edgeDeps.ts` (borda) só
> os edge-safe.

## Catálogo de conectores

| Conector | Contrato | Adapters | Seleciona por | Edge-safe? |
|---|---|---|---|---|
| **Banco** | Drizzle `Db` | `adapters/db.ts` (libSQL, Node) · `api-edge/edgeDb.ts` (Edge SQL REST) | `DATABASE_URL` (Node) · args na borda | REST sim; libSQL não |
| **KV** | `KV` (`lib/kv.ts`) | `SqliteKV` (sobre o Db) · `adapters/redisKv.ts` · `api-edge/azionKv.ts` (nativo) | `KV_DRIVER=sqlite\|redis` | SqliteKV/Azion sim; redis não |
| **E-mail** | `EmailProvider` (`services/emailService.ts`) | `adapters/{resendEmail,smtpEmail,stubEmail,fileEmail}.ts` | `EMAIL_PROVIDER=resend\|smtp\|stub\|file` | resend/stub sim; smtp/file não |
| **Object Storage** | `ObjectStorage` (`lib/storage.ts`) | `adapters/s3Storage.ts` (S3/MinIO) | `STORAGE_DRIVER=none\|s3` | não (aws-sdk, Node) |
| **Image Processor** | `ImageProcessor` (`lib/imaging.ts`) | `adapters/imgproxy.ts` (URLs assinadas) | `IMAGE_DRIVER=none\|imgproxy` | sim (fetch/WebCrypto) |
| **Hash de senha** | `PasswordService` (`services/passwordService.ts`) | argon2id (`hash-wasm`) · pbkdf2 (WebCrypto) | `PASSWORD_HASH=argon2id\|pbkdf2` | sim |
| **Env/segredos** | — | `process.env` (Node) · `Azion.env.get()` (Variables, borda) | — | — |

`TokenService` (JWT `jose` + refresh no KV) e `PasswordService` são **serviços
core**, não conectores trocáveis — mas o TokenService **depende** do conector KV.

## Como configurar (por ambiente)

Todas as chaves estão em [`.env.example`](../.env.example). Resumo por ambiente:

- **Dev local** (`npm run dev`): defaults — `KV_DRIVER=sqlite`, `EMAIL_PROVIDER=stub`,
  `STORAGE_DRIVER=none`, `DATABASE_URL=file:./data/dev.db`. Zero config.
- **Docker** (`docker-compose.dev.yml`, [.env.docker](../.env.docker)): `KV_DRIVER=redis`,
  `EMAIL_PROVIDER=smtp` (Mailpit), `STORAGE_DRIVER=s3` (MinIO), `IMAGE_DRIVER=imgproxy`,
  `DATABASE_URL=http://libsql:8080`.
- **Borda Azion** (produção): config **não-sensível** nos `function_args` do Terraform
  (`infra/azion/main.tf`); **segredos** como Azion **Variables** lidos por
  `Azion.env.get()` (`JWT_SECRET`, `AZION_SQL_TOKEN`, `RESEND_API_KEY`). Ver
  `apps/api-edge/src/edgeDeps.ts`.

### Segredos: nunca em texto plano

- **Node/Docker**: via ambiente (`process.env`), fora do git (`.env` é gitignored).
- **Borda**: via **Azion Variables** (secret) → `Azion.env.get("NOME")`. Nunca nos
  `function_args` (que são legíveis na config da function). Nunca no repo.

## Como estender — adicionar um adapter novo

O fluxo é sempre o mesmo. Exemplo: adicionar um provider de e-mail **Postmark**.

**1. Escreva o adapter** implementando o contrato, em `src/lib/adapters/`:

```ts
// apps/api/src/lib/adapters/postmarkEmail.ts
import { emailMessages, type EmailProvider } from "../../services/emailService";

export function createPostmarkEmailProvider(config: { token: string; from: string }): EmailProvider {
  async function send(to: string, subject: string, text: string) {
    const res = await fetch("https://api.postmarkapp.com/email", {
      method: "POST",
      headers: {
        "X-Postmark-Server-Token": config.token,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ From: config.from, To: to, Subject: subject, TextBody: text }),
    });
    if (!res.ok) throw new Error(`Postmark ${res.status}: ${(await res.text()).slice(0, 200)}`);
  }
  return {
    async sendVerificationEmail(to, link) { const m = emailMessages.verification(link); await send(to, m.subject, m.text); },
    async sendPasswordResetEmail(to, link) { const m = emailMessages.reset(link); await send(to, m.subject, m.text); },
  };
}
```

> Como é só `fetch`, é **edge-safe** → pode ser usado na borda também.

**2. Adicione a opção no env** (`src/lib/env.ts`):

```ts
POSTMARK_TOKEN: z.string().optional(),
// EMAIL_PROVIDER já é string livre; se fosse enum, adicione "postmark"
```

**3. Fie na seleção.** Node — `selectEmail` em `deps.ts`:

```ts
case "postmark":
  if (!env.POSTMARK_TOKEN) throw new Error("EMAIL_PROVIDER=postmark exige POSTMARK_TOKEN");
  return createPostmarkEmailProvider({ token: env.POSTMARK_TOKEN, from: env.EMAIL_FROM });
```

Borda (se edge-safe) — `edgeDeps.ts`: leia `POSTMARK_TOKEN` de `Azion.env.get()`,
inclua no `getEnv({...})` e selecione. Só importe adapters edge-safe aqui.

**4. Teste** (mock do `fetch`, como `tests/emailService.test.ts`), rode `npm test`.

**5. Configure**: `EMAIL_PROVIDER=postmark` + o segredo (env no Node; Azion
Variable na borda). Deploy. Zero mudança nos handlers.

### Estendendo outros conectores

Mesma receita, trocando o contrato:
- **KV novo** (ex.: Upstash): implemente `KV` (`get/set/delete/incr`), adicione a
  `KV_DRIVER`, fie em `selectKv`. Edge-safe se for por `fetch`.
- **Storage novo** (ex.: R2): implemente `ObjectStorage` (`put/get/delete`),
  adicione a `STORAGE_DRIVER`, fie em `selectStorage`.
- **Banco**: o contrato é o Drizzle `Db`; um backing novo é um driver Drizzle
  (ver `edgeDb.ts` que usa `sqlite-proxy` sobre o REST do Edge SQL).

## Checklist ao adicionar um adapter

- [ ] Implementa o contrato (interface) — nada além.
- [ ] Se a borda vai usar: **só web-standard** (`fetch`/WebCrypto), sem `node:*`.
- [ ] Segredos por env/Variable — nunca hardcoded, nunca no repo.
- [ ] Opção adicionada ao env (`env.ts`) e à seleção (`deps.ts` e/ou `edgeDeps.ts`).
- [ ] Falha alto se mal configurado (não degrade silencioso em produção).
- [ ] Teste unitário (mock da borda de rede).
- [ ] Se for edge: confirme que o bundle não puxou lib Node
      (`grep <lib> apps/api-edge/dist/function.js`).
