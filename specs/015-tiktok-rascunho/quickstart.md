# Quickstart: 015-tiktok-rascunho

Roteiro de verificação depois do `/speckit-implement`, **um passo por vez**: mostrar o comando,
explicar em uma linha, rodar, ler a saída e só então seguir. Os §1 e §2 são automáticos e usam a
TikTok **falsa**. Os §3 a §6 são com o dono e usam a TikTok **real** (sandbox). Nenhum agente
chama a TikTok real por conta própria.

**Regra de segredos:** nunca rode `cat .env` nem imprima valores. Para conferir se uma variável
existe, use só o nome: `grep -oE '^(TIKTOK_CLIENT_KEY|TIKTOK_CLIENT_SECRET|SOCIMAN_TOKENS_KEY|PUBLICACAO_HABILITADA)=' .env`.

## §0. Antes de tudo
1. **Backup do banco** (a 0010 mexe em `postagens`):
   `docker compose exec postgres pg_dump -U sociman -Fc sociman > ~/backup-sociman-$(date +%Y%m%d%H%M%S).dump`
   (fora do repositório).
2. **Chave dos tokens** (passo do **dono**; nenhum agente lê nem imprime o valor): gere a chave e
   grave direto no `.env`, sem imprimir e sem duplicar:
   `grep -q '^SOCIMAN_TOKENS_KEY=' .env || { printf '\n' >> .env; python3 -c "import secrets,base64;print('SOCIMAN_TOKENS_KEY='+base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())" >> .env; }`.
   **Verificar:** `grep -c '^SOCIMAN_TOKENS_KEY=' .env` → `1` e `stat -c %a .env` → `600`.
   Guarde uma cópia da **linha** junto do backup do banco (sem ela, os tokens do backup não
   decifram e as contas precisam ser reconectadas).
3. **Variáveis** no `.env` da raiz (nomes em `contracts/http-api.md`): `PUBLICACAO_HABILITADA=false`
   (liga só no §3), `TIKTOK_APP_SITUACAO=sandbox`, `TIKTOK_REDIRECT_WEB` e
   `TIKTOK_REDIRECT_DESKTOP`. `TIKTOK_CLIENT_KEY` e `TIKTOK_CLIENT_SECRET` já existem.
   **Verificar:** o `grep -oE` acima lista os nomes.
4. **Portal da TikTok** (developers.tiktok.com, app do dono, **Sandbox**), feito pelo dono:
   - produtos: Login Kit e Content Posting API; escopos `user.info.basic`, `user.info.profile`,
     `video.upload`, `video.publish`;
   - Login Kit **Web**: redirect `https://192.168.86.47:8543/app/conexoes/retorno`;
   - Login Kit **Desktop**: redirect `http://localhost:8180/app/conexoes/retorno`;
   - usuários-alvo do sandbox: @atavernanerd e @meusqueridinhos10.
   **Registrar:** o portal aceitou o endereço Web (IP privado, porta 8543)? `sim / não (mensagem)`.
   Se não aceitou, deixe `TIKTOK_REDIRECT_WEB` vazio e use o Desktop.
5. Suba a stack: `docker compose up -d --build api agendador edge`. **Verificar:**
   `curl -s http://localhost:8180/api/health` → `{"status":"ok",...}` e
   `docker compose logs agendador | grep -i "trilha publicacao"` → "ociosa:
   PUBLICACAO_HABILITADA desligada no servidor".

## §1. Testes automáticos
1. `npm run test:api` → tudo verde, inclusive `test_migration_0010`, `test_idempotencia_envio`,
   `test_guardas_015` e `test_logs_sem_segredo`.
2. `docker compose exec api uv run ruff check .` → sem erros.
3. `npm run gen:contract && npm run check:web` → contrato em dia, CSP igual, sem segredos.
4. `npm run test:e2e -- e2e/publicacao.spec.ts` → verde (a TikTok falsa; o login é interceptado).
5. **Guarda do princípio I:** `docker compose exec api uv run pytest tests/unit/test_constitution_guards.py -q`
   → verde, e `grep -rn "open.tiktokapis.com" apps/api/src` só mostra
   `publicacao/tiktok/cliente.py`.

## §2. Conectar as contas (US1, SC-001)
Para cada conta, **uma de cada vez**, com o cronômetro ligado:
1. Pelo celular ou pelo desktop com a CA da casa, abra `https://192.168.86.47:8543`, entre como
   dono, vá ao perfil **Taverna** → Contas → @atavernanerd → **Conectar**.
2. Na TikTok, entre **com @atavernanerd** e autorize todas as permissões.
3. **Verificar:** a conta aparece "Conectada", com @, apelido, foto e data, e os modos "Criar
   rascunho" (disponível) e "Publicar" (disponível com o aviso de sandbox).
   **Registrar:** tempo total (SC-001 < 2 min).
4. Se o passo 1 der erro de endereço (portal recusou o IP ou `endereco_de_login`), refaça no
   `sakai-desktop` por `http://localhost:8180` (Desktop + PKCE). **Registrar** qual endereço
   funcionou e, no Desktop, se o `code_challenge` foi aceito.
5. **Conta errada (US1-3):** com @meusqueridinhos10 logada no navegador, clique em Conectar em
   @atavernanerd → a tela diz "Você entrou como @meusqueridinhos10, mas esta conta é
   @atavernanerd" e nada é gravado. Saia da TikTok no navegador e conecte @meusqueridinhos10 na
   conta certa.
6. **Membro (US1-2):** entre como membro → vê o estado, sem Conectar/Desconectar.
7. **Desconectar e reconectar (US1-4):** Desconectar @meusqueridinhos10 → "não conectada";
   Conectar de novo → volta com o mesmo @. **Verificar** no histórico da conta: conectada,
   desconectada, conectada, com o autor.
8. **Segredo:** `docker compose logs api agendador | grep -iE "access_token|refresh_token|code_verifier|upload_token"`
   → nenhuma linha com valor (só nomes de campo, se houver).

## §3. Primeiro teste real: rascunho no horário (US2, SC-002, SC-005)
1. Na tela de configuração de publicação: **Envios automáticos** desligado. No `.env`,
   `PUBLICACAO_HABILITADA=true` e `docker compose up -d agendador api`. **Verificar:** a tela
   mostra "Servidor: ligado · Envios automáticos: desligado".
2. Escolha um corte **pronto** da Taverna (1080×1920, poucos segundos) → **Agendar** → conta
   @atavernanerd → modo **Criar rascunho no horário** → daqui a **5 minutos** → Aprovar e
   agendar. Faça o mesmo com um corte do outro perfil para @meusqueridinhos10, no mesmo horário.
3. **Interruptor (US4-1):** deixe o horário passar com "Envios automáticos" desligado →
   **Verificar:** os dois ficam "Pausado" e `docker compose logs agendador` não mostra chamada à
   TikTok. Ligue o interruptor antes de completar 1 h → os dois saem na próxima volta (até 15 s).
4. **Verificar**, com o cronômetro: o estado passa por "Enviando" (com partes) e chega a
   "Rascunho criado"; o sino avisa com **Copiar textos**; o **app da TikTok** mostra a
   notificação e o rascunho na caixa de entrada das duas contas.
   **Registrar** por conta: horário agendado, horário do "Rascunho criado", horário da
   notificação no app (SC-002 ≤ 5 min).
5. No app, abra o rascunho, cole os textos (**Copiar textos**), escolha a privacidade **Pública**
   e publique. **Registrar (SC-005)**:
   | Conta | Rascunho chegou? | Conseguiu publicar em **público** pelo app? | Visibilidade final | Mensagem da TikTok (se houver) |
   |---|---|---|---|---|
   | @atavernanerd | | | | |
   | @meusqueridinhos10 | | | | |
6. No SociMan, marque **Postado** com o link do post. **Verificar:** o destino vira "Postado".
7. Copie a tabela do passo 5 para a seção "Resultado do teste real" no fim deste arquivo (data e
   quem fez). Esse resultado decide se o fluxo de rascunho serve para as contas de verdade.

## §4. Idempotência, limites e falhas (SC-003, FR-007)
1. **Reinício no meio:** agende um corte maior (ou dois) para daqui a 3 min e, quando o estado
   mostrar "Enviando", rode `docker compose restart agendador`. **Verificar:** o envio retoma e
   termina em "Rascunho criado", e a caixa de entrada do app tem **um** rascunho para esse vídeo.
   Se o reinício cair entre o envio e a resposta, o estado mostra "Falhou — a TikTok pode ter
   recebido": confira no app antes de "Tentar de novo".
2. **5 pendentes:** não finalize rascunhos no app e agende o 6º do dia para a mesma conta →
   **Verificar:** "Aguardando vaga na TikTok", com o horário da próxima tentativa, e um aviso.
   **Registrar** se a TikTok liberou antes das 24 h locais (Q1).
3. **Falha traduzida:** agende um vídeo próprio fora das regras (ex.: horizontal 4K de 11 min) →
   o agendamento mostra o aviso; no horário, "Falhou" com o motivo em pt-BR e **Tentar de novo**.
4. **Vencido:** desligue "Envios automáticos", agende para daqui a 2 min, espere mais de 1 h e
   religue → o destino aparece "Vencido" com **Confirmar envio agora** e **Reagendar**; nada sai
   sem o clique.
5. **Interruptor no meio do envio** (R11): com um corte grande em "Enviando", desligue "Envios
   automáticos" → o destino aparece "Pausado" e `docker compose logs agendador` não mostra mais
   PUT de parte; religue em poucos minutos → o envio retoma e chega a "Rascunho criado", com
   **um** rascunho no app.

## §5. Publicar no horário (US3), opcional
Só com uma conta de teste **privada** (a TikTok exige, sem auditoria). **Não** use as contas
reais sem deixá-las privadas, o que afeta o público delas. Pergunte ao dono antes.
1. **Agendar** → modo **Publicar** → a tela mostra apelido e foto consultados na hora,
   privacidade **sem valor**, três toggles desmarcados, divulgação comercial desligada e a frase
   de consentimento; "Agendar" desabilitado até preencher.
2. Privacidade pública aparece indisponível com a explicação (sandbox). "Parceria paga" +
   "Só eu" → recusado com a regra.
3. "Só eu", daqui a 5 min → "Publicado"; o post privado aparece no perfil do app.

## §6. Recusa a IA, agente e MCP (SC-004)
Enquanto a 009 não existe, a prova é o teste automatizado: `docker compose exec api uv run pytest
tests/integration/test_guardas_015.py -q` → verde (cada rota de dono humano recusa um ator
`mcp_client`, nada muda, e o evento `publicacao_recusada` aparece em Segurança).

## §7. Voltar ao estado seguro
Ao terminar os testes do dia: "Envios automáticos" desligado; se quiser o corte físico,
`PUBLICACAO_HABILITADA=false` e `docker compose up -d agendador api`.

---

## Resultado do teste real (preencher no §3.7)
- Data:
- Quem fez:
- Endereço de login que funcionou (Web / Desktop):
- SC-001 (tempo de conexão por conta):
- SC-002 (atraso até a notificação no app, por conta):
- SC-005 (tabela do §3.5):
- Observações (limite de pendentes, mensagens da TikTok, etc.):

## Resultado da verificação automática com a TikTok falsa (§1.4)
- Data: 2026-09-29. Quem rodou: agente `e2e-015` (trilha E).
- `flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/publicacao.spec.ts`: **6/6 verdes** (7,0 min), com a US3.
  - US1: conectar pela tela (Login Kit Desktop pelo `localhost`, com PKCE), conta diferente recusada com a explicação e nada gravado, membro vendo só o estado (sem Conectar/Desconectar, sem "Envios automáticos", 403 na API), desconectar (revogação na TikTok falsa) e reconectar.
  - US2: corte pronto em "Criar rascunho" para o próximo minuto → "Enviando" → "Rascunho criado", com **um** init de inbox sem `post_info`; sino, "Copiar textos" (área de transferência) e "Marcar como postado". Falha no processamento → "Falhou" com o motivo em pt-BR → "Tentar de novo" → rascunho. Init sem resposta → "a TikTok pode ter recebido"; a API recusa sem a confirmação (409 `confirmacao_necessaria`), o init não se repete sozinho, e só sai depois de "Conferi no app e o rascunho não chegou".
  - US4: com o botão desligado, o agendamento fica "Pausado" e nenhum init nem parte chega à TikTok falsa; ao religar (com a confirmação), sai. Vencido há 2 h não sai sozinho e só sai com "Confirmar envio agora" (tentativa com `disparo = confirmado`).
  - US3: a tela do Publicar abre com o apelido consultado na hora, a privacidade sem valor (só "Só eu" habilitada no sandbox), os três toggles desmarcados (costura bloqueada pela conta) e "Aprovar e agendar" desabilitado; parceria paga + "Só eu" é recusada (tela e API, 400 `opcoes_invalidas`); "Só eu" para o próximo minuto chega a "Publicado" com "Ver o post", com um Direct Post só com as opções escolhidas e nenhum rascunho.
  - Princípio I: no navegador, a única ida à TikTok é o login, interceptado pelo Playwright; na API e no agendador, o cliente aponta para a falsa e os hosts reais da TikTok resolvem para 127.0.0.1.
- Suíte inteira: 33/34 na primeira rodada; a falha foi em `cortes-openshorts.spec.ts` (seletor "Modo" da 014, corrigido pelo líder), fora da `publicacao.spec.ts`. A confirmação das duas rodadas verdes ficou com o líder.
- Capturas: `.playwright-mcp/sociman/015-*.png`.

## Resultado do teste real no sandbox (2026-09-29, com o dono)

| Passo | Resultado |
|---|---|
| Portal aceitou o redirect com o IP da casa | ✅ `https://192.168.86.47:8543/app/conexoes/retorno` |
| Conectar @atavernanerd | ✅ conectada, credencial cifrada |
| 1º envio "Criar rascunho" | ❌ `invalid_params`: vídeo de 22.540.575 bytes declarado como 1 parte de 16 MB. Corrigido: até 64 MB vai inteiro (`chunk_size == video_size`); os fakes passaram a aplicar a regra |
| 2º envio (Tentar de novo) | ✅ init 200 → PUT 201 (1 parte) → status `SEND_TO_USER_INBOX` em ~70 s |
| Rascunho no app | ✅ chegou ao **app** (não aparece no TikTok Studio web), com o vídeo **marcado** (gancho, legenda do kit, marca d'água) |
| Legenda | vem vazia: o modo rascunho da API não aceita texto; o dono cola com "Copiar textos" |
| SC-005 (publicar em público a partir do rascunho) | a confirmar pelo dono |
