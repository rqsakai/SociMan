---

description: "Tarefas da feature 002-pwa"
---

# Tasks: SociMan instalável como app (002-pwa)

**Input**: Design documents from `/specs/002-pwa/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/pwa.md, quickstart.md

**Tests**: OBRIGATÓRIOS pelo princípio VI: `check:pwa`, `check:csp` inalterado, `test:e2e:pwa` e o
roteiro manual do quickstart.

**Organization**: tarefas agrupadas por user story. US1 = instalar (P1), US2 = sem rede (P2),
US3 = versão nova (P2).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Adicionar `vite-plugin-pwa` e `@vite-pwa/assets-generator` como devDependencies em `apps/web/package.json` (rodar `npm install` na raiz; atualiza `package-lock.json`)
- [X] T002 [P] Acrescentar `docker/certs/ca/` ao `.gitignore` e criar `docker/certs/ca/.gitkeep`
- [X] T003 [P] No `package.json` da raiz, criar os scripts:
  - `casa:up`: `npm run build -w @sociman/web && EDGE_MODE=prod docker compose --profile prod up -d`;
  - `check:pwa`: `node scripts/check-pwa.mjs`;
  - `test:e2e:pwa`: `playwright test -c playwright.pwa.config.ts`;
  - `icons`: `npm run icons -w @sociman/web`.

  Incluir `check:pwa` no `check:web` **depois** do `build`.

---

## Phase 2: Foundational (bloqueia todas as stories)

- [X] T004 Criar `apps/web/pwa/icon.svg`: letra "S" branca, centralizada, sobre `#0f172a`, com margem segura para maskable (80% de área útil). Criar também `apps/web/pwa-assets.config.ts` (preset `minimal-2023` do assets-generator, com fundo `#0f172a` no maskable e no apple). No `apps/web/package.json`, o script `icons` é `pwa-assets-generator`. Rodar e versionar em `apps/web/public/` os PNGs gerados: `pwa-64x64.png`, `pwa-192x192.png`, `pwa-512x512.png`, `maskable-icon-512x512.png`, `apple-touch-icon-180x180.png` e `favicon.ico`
- [X] T005 Configurar `VitePWA` em `apps/web/vite.config.ts`, exatamente como em contracts/pwa.md e data-model.md:
  - `registerType: "prompt"`, `injectRegister: null` (o registro é feito pelo módulo virtual), `devOptions: { enabled: false }`;
  - manifest com `name`/`short_name` "SociMan", `lang` "pt-BR", `start_url` "/app", `scope` e `id` "/", `display` "standalone", `theme_color` e `background_color` "#0f172a" e os ícones 64/192/512 (`any`) e 512 (`maskable`);
  - workbox com `globPatterns` `**/*.{js,css,html,svg,png,ico}`, `navigateFallback` "/index.html", `navigateFallbackDenylist` `[/^\/api\//, /^\/img\//, /^\/sociman-ca\./]`, sem `runtimeCaching`, e `cleanupOutdatedCaches: true`.

  **Não mexer** em `strictCsp` nem em `devCsp`.
- [X] T006 [P] Atualizar `apps/web/index.html`: `<meta name="theme-color" content="#0f172a">`, `<link rel="icon" href="/favicon.ico">`, `<link rel="apple-touch-icon" href="/apple-touch-icon-180x180.png">`, `<meta name="apple-mobile-web-app-capable" content="yes">`, `<meta name="apple-mobile-web-app-title" content="SociMan">` e `<meta name="description">`. Sem script inline. Acrescentar `/// <reference types="vite-plugin-pwa/react" />` em `apps/web/src/vite-env.d.ts`, criando o arquivo se não existir
- [X] T007 Criar `scripts/check-pwa.mjs`, que roda sobre `apps/web/dist`. Ele falha com uma mensagem clara se acontecer qualquer uma destas coisas:
  - falta `manifest.webmanifest`, ou os campos dele diferem do data-model;
  - algum ícone citado no manifest não existe;
  - falta `sw.js`;
  - o `sw.js` contém `runtimeCaching`, ou a lista de precache cita `/api` ou `/img`;
  - o `sw.js` não tem o denylist de navegação para `/api` e `/img`;
  - o `index.html` tem `<script>` sem `src`, ou não tem o link do manifest, o `theme-color` ou o `apple-touch-icon`.

  Rodar `npm run build -w @sociman/web && npm run check:pwa` e confirmar que passa. Depois confirmar que `npm run check:csp` continua verde.
- [X] T008 [P] Ajustar `docker/nginx/web-prod.conf`:
  - `location = /sw.js`, `= /registerSW.js`, `= /manifest.webmanifest` e `= /index.html` com `add_header Cache-Control "no-cache"`;
  - `location /assets/` com `add_header Cache-Control "public, max-age=31536000, immutable"`;
  - manter o fallback de SPA (`try_files $uri /index.html`).

**Checkpoint**: `npm run check:web` verde, com `check:pwa`. `npm run check:csp` sem mudança de política.

---

## Phase 3: User Story 1 - Instalar o SociMan (Priority: P1) 🎯 MVP

**Goal**: HTTPS confiável pelo IP da casa, redirecionamento HTTP → HTTPS, a CA baixável e o app instalável.

**Independent Test**: quickstart §1–4.

### Testes da US1

- [X] T009 [P] [US1] Criar `playwright.pwa.config.ts`:
  - `testDir` `e2e-pwa`;
  - `baseURL` `https://localhost:8543`, `ignoreHTTPSErrors: true`;
  - `workers: 1`;
  - `globalSetup` que espera `/api/health` e reaproveita `e2e/global-setup.ts` (reset-db, dono de teste, Mailpit).

  Criar `e2e-pwa/install.spec.ts`, que verifica:
  - o `/manifest.webmanifest` responde 200 com `name` "SociMan" e `start_url` "/app";
  - o `<link rel="manifest">` está no HTML;
  - depois de abrir `/login`, o SW fica registrado e `activated` (`navigator.serviceWorker.ready`);
  - `request.get('http://localhost:8180/')` responde sem redirecionamento;
  - `request.get('http://localhost:8180/app', { headers: { Host: '192.168.86.47:8180' }, maxRedirects: 0 })` responde 301 com `Location` `https://192.168.86.47:8543/app`;
  - `/sociman-ca.crt` com o mesmo Host responde 200 começando com `-----BEGIN CERTIFICATE-----`.

### Implementação da US1

- [X] T010 [US1] Criar `scripts/certs-casa.sh` (POSIX sh, `set -eu`), que usa `docker run --rm --user 1000:1000 -v "$PWD/docker/certs:/certs" alpine/openssl`:
  - recebe o IP como argumento (padrão `192.168.86.47`);
  - (1) se `docker/certs/ca/sociman-ca.key` não existir, cria a CA: RSA 3072, `CN=SociMan CA da casa`, `basicConstraints=critical,CA:TRUE`, `keyUsage=critical,keyCertSign,cRLSign`, 3650 dias, e `chmod 600` na chave;
  - (2) emite `docker/certs/localhost.pem` e `localhost-key.pem`, assinados pela CA: RSA 2048, `CN=SociMan`, `subjectAltName=IP:<IP>,DNS:localhost,IP:127.0.0.1`, `extendedKeyUsage=serverAuth`, `basicConstraints=CA:FALSE`, 825 dias;
  - (3) exporta a CA em DER em `docker/certs/ca/sociman-ca.cer` e copia o PEM para `docker/certs/ca/sociman-ca.crt`;
  - (4) imprime a impressão digital SHA-256 da CA e a validade do certificado do servidor;
  - (5) roda `docker compose restart edge`.

  Rodar o script e verificar com `openssl s_client -connect 127.0.0.1:8543` que o SAN tem o IP e que o emissor é a CA da casa.
- [X] T011 [US1] Edge:
  - em `docker/nginx/05-edge-mode.envsh`, exportar `LAN_HOST="${LAN_HOST:-192.168.86.47}"`, **sem tocar nas CSPs**;
  - em `docker-compose.yml`, passar `LAN_HOST: ${LAN_HOST:-192.168.86.47}` ao `edge` e montar `./docker/certs/ca/sociman-ca.crt` e `.cer` como somente leitura em `/usr/share/nginx/ca/`;
  - em `docker/nginx/default.conf.template`, para HTTP (`$scheme = http`) com `$host = ${LAN_HOST}`, responder `return 301 https://$host:8543$request_uri;`, exceto `location ~ ^/sociman-ca\.(crt|cer)$`, que serve de `/usr/share/nginx/ca/` com `default_type application/x-x509-ca-cert`;
  - `localhost` continua sem redirecionamento;
  - como `$host` sai sem porta, testar com Host `192.168.86.47:8180` e com `192.168.86.47`.

  Rodar `docker compose up -d edge`, conferir `nginx -t` no container e checar com `curl` como no quickstart §2.
- [X] T012 [US1] Criar `docs/guia-certificado-casa.md` (pt-BR):
  - o que é a CA da casa e por que é segura para uso doméstico;
  - como gerar e renovar (`./scripts/certs-casa.sh`, e reinstalar só se a CA mudar);
  - como baixar a CA pelo celular (`http://192.168.86.47:8180/sociman-ca.cer`) ou por cabo;
  - como conferir a impressão digital SHA-256;
  - passo a passo para Android, iPhone (com "Ajustes de Confiança de Certificado"), Chrome no Linux (`chrome://settings/certificates`) e Windows;
  - como instalar o app no Android, no desktop e no iPhone;
  - problemas comuns: IP mudou, aviso de certificado, e acesso por HTTP;
  - aviso: nunca compartilhar `sociman-ca.key`.
- [X] T013 [US1] Rodar `npm run casa:up` e `npm run test:e2e:pwa` (`install.spec.ts`) até passar. Depois voltar a stack para o modo dev (`docker compose --profile prod stop web-prod && docker compose up -d edge`) e confirmar que `npm run test:e2e` segue com 7/7

**Checkpoint**: a US1 instala no desktop e no Android com a CA instalada (validação manual: quickstart §3–4).

---

## Phase 4: User Story 2 - Abrir sem rede (Priority: P2)

**Goal**: com falha de rede no boot, aparece a tela "Sem conexão com o SociMan" com o botão "Tentar de novo"; nada da API fica guardado.

**Independent Test**: quickstart §5.

### Testes da US2

- [X] T014 [P] [US2] Criar `e2e-pwa/offline.spec.ts`:
  - (a) login com o dono de teste, navegar para `/app/usuarios` e `/app/seguranca`, e depois listar todas as URLs em `caches` (via `page.evaluate`): nenhuma pode conter `/api/` ou `/img/`. Também não pode haver token (`eyJ`) em `localStorage`, `sessionStorage` ou IndexedDB (SC-004). Repetir a checagem depois de "Sair" (FR-011);
  - (b) com o SW ativo, `context.setOffline(true)` e reload: a tela mostra "Sem conexão com o SociMan" em menos de 2 s (SC-003);
  - (c) `setOffline(false)` e clique em "Tentar de novo": volta ao login ou ao app.

### Implementação da US2

- [X] T015 [US2] Em `apps/web/src/lib/api.ts` e `apps/web/src/lib/authActions.ts`, fazer o `refreshSession` distinguir falha de rede (`TypeError` do `fetch`) de resposta 401 ou erro. O `bootstrapSession` passa a devolver `"ok" | "guest" | "offline"`, e o store (`authStore.ts`) ganha o estado `status: "offline"`. Não mexer no single-flight nem no `sessionEpoch`
- [X] T016 [US2] Criar `apps/web/src/components/Offline.tsx` com título "Sem conexão com o SociMan", texto curto ("Verifique se você está na rede de casa e se o SociMan está ligado.") e o botão "Tentar de novo", que refaz o `bootstrapSession`. Em `apps/web/src/App.tsx`, mostrar `<Offline/>` quando `status === "offline"`. Usar os componentes de `ui.tsx`. `npm run check:web` verde

**Checkpoint**: US1 e US2 prontas. Validação: quickstart §5 e `test:e2e:pwa` verde.

---

## Phase 5: User Story 3 - Versão nova (Priority: P2)

**Goal**: o aviso "Nova versão disponível" com o botão "Atualizar"; ao aceitar, recarrega sem perder a sessão.

**Independent Test**: quickstart §6.

### Testes da US3

- [X] T017 [P] [US3] Criar `e2e-pwa/update.spec.ts`:
  - abrir o app com o SW ativo e fazer login;
  - rodar um build novo com mudança observável: `VITE_BUILD_ID` diferente, exibido num `data-build` do `<html>`, depois `npm run build -w @sociman/web` com a env;
  - o `web-prod` serve o `dist` montado, então não precisa reiniciar;
  - chamar `registration.update()` via `page.evaluate`;
  - esperar o texto "Nova versão disponível" e clicar em "Atualizar";
  - o `data-build` novo aparece, e a sessão continua (a URL fica em `/app`, sem `/login`).

  Ao final, reconstruir o build normal.

### Implementação da US3

- [X] T018 [US3] Criar `apps/web/src/components/UpdatePrompt.tsx` com `useRegisterSW` de `virtual:pwa-register/react`:
  - com `needRefresh`, mostrar um aviso fixo (`role="status"`) com "Nova versão disponível" e os botões "Atualizar" (`updateServiceWorker(true)`) e "Agora não" (fecha o aviso);
  - em dev (sem SW), o componente não renderiza nada;
  - checar atualização quando a janela volta a ter foco e a cada 60 min.

  Montar o componente em `apps/web/src/App.tsx`. Expor `data-build` no `<html>` a partir de `import.meta.env.VITE_BUILD_ID`, com fallback para a data do build definida no `vite.config.ts` via `define`.
- [X] T019 [US3] Garantir que "Atualizar" preserva a sessão. O reload refaz o `bootstrapSession`, e o refresh pelo cookie recupera a sessão. Validar no `update.spec.ts`

**Checkpoint**: todas as stories prontas.

---

## Phase 6: Polish

- [X] T020 [P] Atualizar `CLAUDE.md` (SociMan) com:
  - o modo casa (`npm run casa:up`, que roda em prod);
  - o endereço `https://192.168.86.47:8543`;
  - `./scripts/certs-casa.sh` e o guia `docs/guia-certificado-casa.md`;
  - `test:e2e:pwa`, que exige modo prod, contra o `test:e2e`, que exige modo dev;
  - a armadilha "service worker só no build de produção".
- [X] T021 [P] Atualizar `docs/visao.md`: a 002 como implementada, com as decisões (CA da casa, IP fixo, SW só com os arquivos da interface)
- [X] T022 Verificação completa:
  - `npm run check:web` (com `check:pwa`, `check:csp` e `check:contract`);
  - `docker compose exec api uv run pytest` (não deve mudar);
  - `npm run test:e2e` (modo dev), que zera o banco de dev: pedir autorização ao dono antes;
  - `npm run casa:up && npm run test:e2e:pwa`;
  - validação manual do dono no Android e no desktop (quickstart §3–6), medindo SC-001, SC-002, SC-003 e SC-005.

  Registrar os resultados no fim do `quickstart.md`.

---

## Dependencies & Execution Order

- **Fase 1 → Fase 2 → US1**. A US2 e a US3 dependem da Fase 2 (SW ativo) e podem andar juntas.
  Os e2e delas (T014, T017) precisam do modo casa da US1 (T010, T011) rodando.
- **Arquivos compartilhados:** `App.tsx` é tocado pela T016 e pela T018. Se forem feitas em
  paralelo, uma delas integra no final.
- O Polish vem depois de todas as stories.

### Parallel Opportunities
- **Fase 1:** T002 e T003.
- **Fase 2:** T006 e T008 em paralelo com T004 → T005 → T007.
- **US1:** T009 e T012 em paralelo com T010 → T011.
- **US2 e US3:** T014–T016 em paralelo com T017–T019 (atenção ao `App.tsx`).
- **Polish:** T020 e T021.

## Implementation Strategy

- **MVP:** Fase 1, Fase 2 e US1 (T001–T013). O app já instala.
- **Depois:** US2, US3 e Polish. Cada checkpoint é validado antes do próximo, e os passos
  manuais ficam com o dono.

## Notes
- Commit só quando o dono pedir.
- `test:e2e` (dev) e `test:e2e:pwa` (prod) exigem modos diferentes da stack. Não rode os dois ao
  mesmo tempo.
- As duas suítes zeram o banco de dev (reset-db). Avisar o dono antes.
