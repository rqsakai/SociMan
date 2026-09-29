# ADR 0002 — Argon2id (hash-wasm) como hash default, PBKDF2 fallback

**Status:** Aceita

## Contexto

O hash de senha precisa rodar no **isolate V8 da borda** (não Node completo).
`bcrypt` nativo está fora. O brief pede Argon2id default com opção configurável.
Restrição confirmada por canário (`/api/_canary`): **Argon2id-WASM instancia e
roda no isolate da Azion**.

## Decisão

- **Default: Argon2id via `hash-wasm`** (WASM roda no isolate), parâmetros OWASP
  edge-conscious: `m=19456 KiB, t=2, p=1`.
- **Fallback: PBKDF2-SHA256 via WebCrypto** (`PASSWORD_HASH=pbkdf2`), 600k
  iterações — zero-WASM, caso algum runtime não instancie WASM.
- Armazenar como **PHC string** (`$argon2id$...` / `$pbkdf2-sha256$...`).
- `verify()` despacha pelo **prefixo do hash armazenado**, não pela env — trocar
  `PASSWORD_HASH` só afeta hashes novos; migração de algoritmo é transparente.

## Consequências

- Custo de compute do hash é o maior por request de auth — é o preço da
  segurança (ver [../product/overview.md](../product/overview.md)).
- Ambos os caminhos usam só APIs edge-compatible (WASM / WebCrypto).
- Implementação: `apps/api/src/services/passwordService.ts`.
