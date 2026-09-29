# Implementation Plan: SociMan instalável como app (002-pwa)

**Branch**: `002-pwa` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-pwa/spec.md`

## Summary

Transformar o SPA num PWA instalável na rede de casa:
- **Certificado:** um script cria uma CA da casa e emite o certificado do edge para
  `192.168.86.47` e `localhost`. O edge serve a CA pública por HTTP e redireciona o resto do HTTP
  do IP da casa para o HTTPS.
- **Build:** o de produção ganha o manifest, os ícones e um service worker (`vite-plugin-pwa`)
  que só guarda os arquivos da interface, sem `/api` e sem dados. Ele tem aviso de versão nova e
  tela "Sem conexão".
- **Modo casa:** passa a ser o build de produção sob a CSP estrita, que não muda. O modo dev e os
  e2e existentes seguem iguais.

Detalhes em [research.md](research.md), [data-model.md](data-model.md),
[contracts/pwa.md](contracts/pwa.md) e [quickstart.md](quickstart.md).

## Technical Context

**Language/Version**: TypeScript 5 / React 19 / Vite 8 (web); nginx 1.27 (edge); POSIX sh + openssl (certificados)

**Primary Dependencies**: **novas (dev):** `vite-plugin-pwa` (Workbox) e `@vite-pwa/assets-generator`. A API não recebe nenhuma dependência nova.

**Storage**: Cache Storage do navegador (só precache dos arquivos do build); certificados em `docker/certs/` (fora do git)

**Testing**:
- `check:pwa` (Node, sobre o build), que entra no `check:web`;
- `check:csp`, que continua igual;
- `test:e2e:pwa`, um projeto Playwright contra a stack em modo prod via HTTPS;
- os e2e de dev, que continuam iguais;
- validação manual no Android e no desktop.

**Target Platform**: Chrome/Edge no Android e no desktop (obrigatório); Safari no iOS (melhor esforço)

**Project Type**: web application (SPA + edge nginx); a API não muda

**Performance Goals**: abrir em menos de 2 s depois da primeira visita; tela "Sem conexão" em menos de 2 s

**Constraints**:
- CSP estrita sem exceções novas;
- o SW nunca toca `/api` nem `/img`;
- o certificado vale para `192.168.86.47` e `localhost`;
- sem sudo no host (o `ufw` e a CA do desktop ficam a cargo do dono);
- não usar as portas 8000, 5175, 18789, 6379, 1025 e 8025.

**Scale/Scope**: 1 manifest, cerca de 6 ícones, 1 SW gerado, 2 componentes (sem conexão e versão nova), 1 script de certificado, 1 guia, ajustes no nginx

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|---|---|---|
| I. Nenhum agente publica | ✅ | sem integração externa; o T023 da 001 continua valendo |
| II. Direito primeiro | n/a | |
| III. Marca em tokens | n/a (parcial) | as cores do tema ficam num único lugar (manifest e `theme-color`); o kit de marca é a spec 004 |
| IV. Contrato é a fonte única | ✅ | a API não muda; o `check:contract` continua |
| V. Segurança e segredos | ✅ | a CSP estrita não muda (R5); o SW não guarda API nem tokens (R3); a chave da CA fica gitignored com permissão 600 (FR-004b); só a CA pública vai por HTTP, com a impressão digital para conferir (R7) |
| VI. Testes antes de pronto | ✅ | `check:pwa`, `test:e2e:pwa` e o roteiro manual (quickstart §7–8) |
| VII. Humano no controle | n/a | nenhuma mutação de dados |
| VIII. Simplicidade | ✅ com justificativa | duas devDependencies (tabela abaixo); nenhum serviço novo, porque o certificado usa o `alpine/openssl` que o compose já tem |

**Reavaliação pós-design:** mantida.

## Project Structure

### Documentation (this feature)

```text
specs/002-pwa/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/pwa.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/web/
├── package.json                    # + vite-plugin-pwa, @vite-pwa/assets-generator (dev); script "icons"
├── vite.config.ts                  # + VitePWA({...}) conforme contracts/pwa.md (dev desligado)
├── index.html                      # + theme-color, apple-touch-icon, apple-mobile-web-app-*
├── pwa/icon.svg                    # fonte do ícone ("S" sobre #0f172a)
├── pwa-assets.config.ts            # preset do assets-generator
├── public/                         # PNGs gerados (versionados) + favicon
└── src/
    ├── main.tsx / App.tsx          # monta <UpdatePrompt/>; boot trata falha de rede
    ├── components/UpdatePrompt.tsx # "Nova versão disponível" / "Atualizar" (useRegisterSW)
    ├── components/Offline.tsx      # "Sem conexão com o SociMan" / "Tentar de novo"
    ├── lib/authActions.ts          # bootstrapSession distingue falha de rede × 401
    └── vite-env.d.ts               # tipos de virtual:pwa-register/react

docker/nginx/default.conf.template  # 301 HTTP→HTTPS para $LAN_HOST; /sociman-ca.(crt|cer) por HTTP
docker/nginx/05-edge-mode.envsh     # exporta LAN_HOST (padrão 192.168.86.47); CSP INALTERADA
docker/nginx/web-prod.conf          # Cache-Control: no-cache (sw/manifest/index) e immutable (assets)
docker-compose.yml                  # edge: env LAN_HOST; volume da CA pública (ro)
scripts/certs-casa.sh               # CA da casa + cert do servidor via alpine/openssl
scripts/check-pwa.mjs               # validação do build (entra no check:web)
.gitignore                          # + docker/certs/ca/
docs/guia-certificado-casa.md       # guia pt-BR: Android, iPhone, Linux, Windows, renovação
e2e-pwa/                            # Playwright (baseURL https://localhost:8543, ignoreHTTPSErrors)
playwright.pwa.config.ts
package.json                        # + check:pwa, test:e2e:pwa, casa:up, icons
CLAUDE.md                           # modo casa, certificados, guia
```

**Structure Decision**: tudo cabe na estrutura existente. A mudança fica no `apps/web` (build e
UI), no `docker/nginx` (edge) e em `scripts/` (certificados e checagem). O backend não muda.

## Complexity Tracking

| Item | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| `vite-plugin-pwa` (dev) | gera o manifest e um SW versionado, com precache e hook de atualização, sem script inline | SW à mão: fácil errar o versionamento e a limpeza de cache |
| `@vite-pwa/assets-generator` (dev) | gera todos os tamanhos de ícone, incluindo maskable e Apple, a partir de um SVG | PNGs à mão: trabalhoso e sujeito a erro de tamanho |
| exceção HTTP para a CA pública | o celular precisa baixar a CA antes de confiar no HTTPS | só pelo guia com cabo ou mensageiro: fica como opção no guia, mas é mais atrito |
| projeto Playwright separado (`e2e-pwa`) | o SW só existe em modo prod, e os e2e de dev rodam em modo dev | colocar tudo num projeto só: exigiria trocar a stack no meio da suíte |
