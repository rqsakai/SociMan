# Pesquisa (Fase 0): 002-pwa

## R1. Onde o PWA roda: modo "casa" = build de produção
- **Decisão:** o PWA (manifest + service worker) só existe no **build de produção**, servido pelo
  perfil `prod` do compose (`web-prod` atrás do edge, `EDGE_MODE=prod`, CSP estrita). No modo dev
  (Vite com HMR), o service worker fica **desligado**.
- **Por quê:**
  - Um service worker no dev server prende versões velhas e atrapalha o HMR.
  - O uso diário do dono pela rede de casa deve ser o build estável e sob a CSP estrita, que é o
    que o princípio V pede.
- **Consequência:** o uso em casa sobe com `npm run build && EDGE_MODE=prod docker compose
  --profile prod up -d`. O dev (`:8180` com Vite) continua como está, e os e2e atuais também.
- **Alternativas:** SW também em dev (`devOptions`): rejeitada pelo risco de cache de dev e pela
  CSP frouxa do dev.

## R2. Ferramenta de PWA
- **Decisão:** `vite-plugin-pwa` (Workbox, estratégia `generateSW`).
  - O registro é feito pelo módulo virtual `virtual:pwa-register/react`, que entra no bundle. Não
    há script inline, então a CSP estrita continua valendo (FR-008).
  - `registerType: "prompt"` dá o aviso "Nova versão disponível / Atualizar" (FR-009). Sem
    aceitar, o SW novo assume quando todas as janelas fecham, ou seja, na próxima abertura
    (FR-010).
  - `devOptions.enabled: false`.
- **Por quê:** é o padrão de fato do Vite, gera o manifest e o SW precacheado por versão e tem
  hook React para o aviso de atualização.
- **Alternativas:**
  - SW escrito à mão: mais código, e fácil de errar o versionamento do cache.
  - `@serwist/vite`: equivalente, mas com menos uso no ecossistema Vite.

## R3. O que o SW guarda (FR-005, FR-007, SC-004)
- **Decisão:**
  - **Precache** só dos arquivos do build: `index.html`, `assets/*.js|css`, ícones e manifest.
  - **Sem `runtimeCaching`.**
  - `navigateFallback: "/index.html"` com `navigateFallbackDenylist: [/^\/api\//, /^\/img\//]`.
  - O SW não intercepta `/api` nem `/img`, então essas requisições vão direto à rede, com o cookie
    de sessão (`Path=/api/auth/refresh`) intocado.
  - Tokens continuam só na memória do JS (spec 001).
  - Cache antigo é limpo na ativação (`cleanupOutdatedCaches`).
- **Verificação:** `check:pwa` inspeciona o `sw.js` gerado. Ele falha se aparecer
  `runtimeCaching`, qualquer URL `/api` na lista de precache, ou se faltar o denylist.

## R4. Tela "Sem conexão" (US2)
- **Decisão:** o shell abre do precache. No boot, o `bootstrapSession` já chama o refresh, e uma
  **falha de rede** (TypeError do `fetch`, não 401) passa a mostrar a tela "Sem conexão com o
  SociMan" com o botão "Tentar de novo", que refaz o boot.
  - Durante o uso, um erro de rede numa chamada mostra a mensagem de conexão já existente.
  - `navigator.onLine` só serve de pista visual; a fonte da verdade é a falha do `fetch`.
- **Alternativas:** página offline separada servida pelo SW. Desnecessária, porque o próprio
  shell está no precache.

## R5. CSP estrita com service worker e manifest
- **Decisão:** **nenhuma mudança de CSP.**
  - `worker-src` cai em `script-src 'self'` e `manifest-src` cai em `default-src 'self'`, e os
    dois arquivos são da própria origem.
  - Ícones são arquivos `'self'`.
  - `check:csp` segue igual (FR-008, SC-006).
- **Cuidado:** não usar `injectRegister: "inline"`; usar o import do módulo virtual.

## R6. HTTPS confiável na rede de casa (FR-004, decisão do dono: CA local)
- **Decisão:** o script `scripts/certs-casa.sh` gera, com `openssl` dentro do container
  `alpine/openssl` que o compose já usa (sem instalar nada no host e sem sudo):
  1. **CA da casa**, que só é criada se ainda não existir:
     - `docker/certs/ca/sociman-ca.key`, com permissão 600 e **gitignored**;
     - `docker/certs/ca/sociman-ca.crt`, pública, com `basicConstraints=CA:TRUE` e validade de
       10 anos.
  2. **Certificado do servidor** `docker/certs/localhost.pem` / `localhost-key.pem`, que são os
     arquivos que o nginx já lê:
     - SAN `IP:192.168.86.47, DNS:localhost, IP:127.0.0.1`;
     - `extendedKeyUsage=serverAuth`;
     - validade de **825 dias**, o limite aceito pelo iOS e pelo Chrome;
     - o script pode reemitir o certificado sem mexer na CA.
  3. Uma cópia da CA em DER, `sociman-ca.cer`, para facilitar a instalação no Android.

  O IP é parâmetro do script (padrão `192.168.86.47`).
- **Por quê usar openssl e não o binário `mkcert`:** o resultado é o mesmo (CA local escolhida
  pelo dono), mas é reproduzível pelo compose e não exige baixar binário nem `mkcert -install`
  com sudo no host.
- **Alternativa:** baixar o `mkcert` para `~/.local/bin`. É viável, mas acrescenta um binário ao
  host e dá o mesmo resultado.
- **O `certgen` atual** (autoassinado, só localhost) continua como fallback: ele só gera se
  `localhost.pem` não existir.

## R7. Como o celular obtém a CA (o ovo e a galinha)
- **Problema:** antes de instalar a CA, o celular não confia no HTTPS, então não dá para baixar a
  CA por HTTPS.
- **Decisão:** o edge serve **só a CA pública** por HTTP em `http://192.168.86.47:8180/sociman-ca.crt`
  (e `.cer`).
  - Essa é a única exceção ao redirecionamento para HTTPS (FR-004c).
  - A CA é pública, e o risco de alguém trocá-la na rede de casa é aceito e documentado.
  - O guia recomenda conferir a impressão digital (SHA-256), que o script imprime.
- **Alternativa:** copiar o arquivo por cabo ou mensageiro. Também é possível, e fica no guia
  como opção.

## R8. Redirecionamento HTTP → HTTPS (FR-004c)
- **Decisão:** no `server` do edge, quando a requisição é HTTP e o `$host` é o IP da casa
  (variável `LAN_HOST`, padrão `192.168.86.47`), responder `301` para
  `https://$host:8543$request_uri`.
  - Exceção: `/sociman-ca.crt` e `/sociman-ca.cer` (R7).
  - `localhost`/`127.0.0.1` em HTTP não mudam, para o dev e os e2e continuarem funcionando.
- **Alternativa:** um `server` separado só para HTTP. Rejeitada por ser mais configuração para o
  mesmo efeito.

## R9. Ícones
- **Decisão:** um SVG-fonte simples em `apps/web/pwa/icon.svg` (letra "S" sobre a cor do tema).
  - `@vite-pwa/assets-generator` (devDependency) gera os PNGs, que são **versionados**:
    64/192/512, maskable 512 e `apple-touch-icon` 180, mais o favicon.
  - Cor do tema: `#0f172a`. O fundo usa a mesma cor.
- **Alternativas:** desenhar os PNGs à mão (trabalhoso) ou gerar a cada build (mais uma etapa no
  CI sem ganho).

## R10. Cabeçalhos de cache
- **Decisão:** no `web-prod.conf`:
  - `sw.js`, `registerSW.js`, `manifest.webmanifest` e `index.html` recebem
    `Cache-Control: no-cache`, porque o navegador precisa checar a versão nova;
  - `assets/*` (com hash no nome) recebem `Cache-Control: public, max-age=31536000, immutable`.
  - O tipo MIME `.webmanifest` é forçado para `application/manifest+json` na própria location
    (`types {}` + `default_type`). Verificado na implementação: o `mime.types` do nginx 1.27 **não**
    mapeia essa extensão e servia `application/octet-stream`.

## R11. Testes (princípio VI)
- **Decisão:**
  1. **`npm run check:pwa`**, um script Node que roda depois do build e entra no `check:web`. Ele
     valida:
     - o manifest: campos obrigatórios, `start_url=/app`, `display=standalone`, e os ícones que
       ele cita existem;
     - o `sw.js`, conforme R3;
     - que o `index.html` não tem script inline e tem o link do manifest, o `theme-color` e o
       `apple-touch-icon`.
  2. **e2e PWA** (`e2e-pwa/`, projeto Playwright separado) contra a stack em modo prod via HTTPS,
     com `ignoreHTTPSErrors` porque o Chromium do teste não tem a CA. Ele verifica:
     - o SW registra;
     - offline (`context.setOffline(true)`) mostra "Sem conexão com o SociMan" e "Tentar de novo"
       volta;
     - depois de login e navegação, o Cache Storage não tem nenhuma URL `/api` (SC-004);
     - o redirecionamento HTTP → HTTPS pelo IP da casa (via `request` com header Host).

     Roda com `npm run test:e2e:pwa`, com a stack em prod.
  3. **Validação manual** no Android e no desktop (SC-001, SC-002, SC-005), registrada no
     quickstart.
- **Alternativas:** rodar o SW nos e2e de dev. Rejeitada porque o SW fica desligado em dev (R1).
