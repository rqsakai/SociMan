# Contrato: 002-pwa

## HTTP (edge nginx)
| Requisição | Resposta |
|---|---|
| `GET http://192.168.86.47:8180/<caminho>` | `301 Location: https://192.168.86.47:8543/<caminho>` |
| `GET http://192.168.86.47:8180/sociman-ca.crt` | `200`, `application/x-x509-ca-cert`, a CA em PEM (sem redirecionamento; R7) |
| `GET http://192.168.86.47:8180/sociman-ca.cer` | `200`, `application/x-x509-ca-cert`, a CA em DER |
| `GET http://localhost:8180/...` | sem mudança (dev/e2e) |
| `GET https://…:8543/manifest.webmanifest` | `200`, `application/manifest+json`, `Cache-Control: no-cache` (modo prod) |
| `GET https://…:8543/sw.js` | `200`, JS, `Cache-Control: no-cache`, `Service-Worker-Allowed` não é necessário (escopo `/`) |
| `GET https://…:8543/assets/*` | `Cache-Control: public, max-age=31536000, immutable` |
| CSP | **igual** à atual (estrita em prod, dev inalterado) |

## Service worker (Workbox `generateSW`)
- `registerType: "prompt"`, `clientsClaim: false`, `skipWaiting` só quando o usuário aceita.
- `globPatterns`: `**/*.{js,css,html,svg,png,ico}` (o manifest entra pelo próprio plugin).
- `navigateFallback: "/index.html"`, `navigateFallbackDenylist: [/^\/api\//, /^\/img\//, /^\/sociman-ca\./]`.
- `runtimeCaching`: **nenhum**.
- `cleanupOutdatedCaches: true`.
- Registro: `import { useRegisterSW } from "virtual:pwa-register/react"` (sem script inline).

## Interface (textos exatos, usados pelos e2e)
| Situação | Texto / controle |
|---|---|
| boot com falha de rede | título "Sem conexão com o SociMan", botão "Tentar de novo" |
| versão nova | "Nova versão disponível" + botão "Atualizar" (em `role="status"`, não alert) |

## Scripts
| Comando | Efeito |
|---|---|
| `./scripts/certs-casa.sh [IP]` | cria a CA da casa (se não existir) e (re)emite o certificado do servidor para `IP` (padrão `192.168.86.47`) + `localhost`; imprime a impressão digital SHA-256 da CA; reinicia o edge |
| `npm run check:pwa` | valida o build (manifest, ícones, `sw.js` sem `/api` nem `runtimeCaching`, sem script inline) — incluído no `check:web` |
| `npm run icons` | regenera os PNGs a partir de `apps/web/pwa/icon.svg` |
| `npm run test:e2e:pwa` | e2e do PWA contra a stack em modo prod (HTTPS) |
| `npm run casa:up` | `npm run build` + `EDGE_MODE=prod docker compose --profile prod up -d` |
