# Pesquisa (Phase 0): 015-tiktok-rascunho

Base: [spec.md](spec.md), constitution 4.0.0 (princípio I), `docs/pesquisa/publicacao-redes.md`
(chamada aqui de **pesquisa**) e o plano da 014 (`specs/014-central-de-conteudos/`, chamado de
**014**). Nenhuma API da TikTok foi chamada; o que depende do sandbox está marcado
**[testar no sandbox]** e entra no [quickstart](quickstart.md).

Nomes usados aqui:
- **destino**: uma linha de `postagens` (014 R2);
- **conexão**: a ligação de uma conta TikTok do SociMan a uma autorização OAuth;
- **tentativa**: uma execução de envio de um destino (tabela `publicacao_tentativas`);
- **executor**: o código de uma rede que faz a tentativa (`publicacao/tiktok/`).

---

## R1. Fluxo OAuth e endereço de retorno (FR-001, FR-003)

- **Decisão:** o retorno da TikTok cai numa **rota do SPA**, `/app/conexoes/retorno`, e o SPA
  conclui a conexão com um `POST` autenticado. Há dois endereços, ambos configurados no `.env` e
  registrados no portal da TikTok:
  | Plataforma no portal | Endereço (`redirect_uri`) | PKCE | Quando |
  |---|---|---|---|
  | **Web** (Login Kit Web) | `https://192.168.86.47:8543/app/conexoes/retorno` (`TIKTOK_REDIRECT_WEB`) | não | padrão: celular ou desktop com a CA da casa |
  | **Desktop** (Login Kit Desktop) | `http://localhost:8180/app/conexoes/retorno` (`TIKTOK_REDIRECT_DESKTOP`) | S256 obrigatório | se o portal recusar IP privado; login feito no `sakai-desktop` |

  Fluxo:
  1. o dono clica **Conectar** → `POST /api/contas/{id}/conexao/iniciar`. A API escolhe o
     endereço pelo `Host` que o edge repassou (IP da casa → Web; `localhost` → Desktop). Se o
     endereço correspondente não estiver configurado, responde 409 `endereco_de_login` com o
     outro endereço para abrir ("Abra o SociMan em http://localhost:8180 no sakai-desktop");
  2. a API gera o `state` (R2) e, no Desktop, o `code_verifier`; devolve `{autorizarUrl}`;
  3. o SPA navega (`window.location.assign`) para `https://www.tiktok.com/v2/auth/authorize/`;
  4. a TikTok devolve o **navegador** para `…/app/conexoes/retorno?code=…&state=…` (ou
     `error=…`). A TikTok nunca chama o SociMan;
  5. a página do SPA (já logada, com o Bearer da sessão) faz `POST /api/conexoes/retorno`
     `{code, state, error?, errorDescription?}`; a API valida (R2, R3), troca o código, cifra os
     tokens (R4) e responde com a conta conectada. O SPA volta para a conta.
- **Por quê:**
  - o retorno numa rota do SPA reaproveita a autenticação normal (Bearer + `RequireOwner`), sem
    depender de cookie: o cookie de renovação só vai para `/api/auth/refresh`, e um `GET` de
    callback na API chegaria sem sessão;
  - o edge já serve o SPA nos dois endereços (HTTPS pelo IP da casa, HTTP em `localhost`), então
    **o edge não muda** (sem `location` nova);
  - navegação de topo não é afetada pela CSP (`form-action` e `connect-src` continuam `'self'`).
- **PKCE no Desktop:** `code_verifier` de 64 caracteres (`secrets.token_urlsafe(48)`), guardado
  só no Redis junto do `state`. A documentação do Desktop descreve o `code_challenge` como
  SHA-256 do verifier; o formato (hex ou base64url) varia entre as versões da doc
  **[testar no sandbox]**: fica numa função única (`oauth.code_challenge`) com teste de unidade.
- **O portal pode recusar IP privado ou porta não padrão** (pesquisa §1.1). Por isso os dois
  endereços são configuração independente: o SociMan funciona com um, com o outro ou com os
  dois. O quickstart §2 registra qual o portal aceitou.
- **Alternativas rejeitadas:**
  - **callback `GET` na API** (`/api/conexoes/callback`): sem sessão; exigiria confiar só no
    `state` e redirecionar de volta ao SPA, com uma rota pública a mais;
  - **domínio próprio com ACME DNS-01:** resolveria TikTok e Google de uma vez, mas é infra nova
    (VIII) para um problema que o Desktop resolve; fica para a spec do YouTube, se for preciso;
  - **servidor local temporário (loopback) aberto pela API:** a API roda num container e não
    abre porta no host.

## R2. `state` anti-CSRF e vínculo ao dono (FR-001, FR-010)

- **Decisão:** `state = secrets.token_urlsafe(32)`, guardado no Redis em
  `conexao:state:{state}` com TTL de **10 min** e valor `{userId, contaId, plataforma
  ("web"|"desktop"), redirectUri, codeVerifier?}`. No retorno, a API faz `GETDEL` (uso único) e
  confere:
  1. o `state` existe (senão 400 `state_invalido`: "O pedido de conexão expirou; clique em
     Conectar de novo");
  2. `userId` do `state` = usuário da sessão, e ele **continua** dono ativo, com `actor.kind ==
     "user"` (R15);
  3. a conta do `state` continua TikTok, não arquivada e não `encerrada`;
  4. se veio `error` (o dono negou), nada é guardado e a resposta é 409 `autorizacao_negada`.
- **Por quê:** o `state` amarra a volta a quem começou; guardar no servidor (em vez de assinar
  um token) permite uso único. O Redis já guarda estado efêmero de autenticação (constitution:
  "Redis não é banco de registro"); se o Redis cair, o dono só clica em Conectar de novo.
- **Alternativa rejeitada:** `state` como JWT assinado sem registro: não dá uso único sem outra
  tabela.

## R3. A conta autorizada tem de ser a conta cadastrada (FR-001, US1-3)

- **Decisão:** depois da troca do código:
  1. **escopos:** a resposta traz `scope`; sem `video.upload` → 409 `escopo_faltando` ("Marque
     todas as permissões ao autorizar"). `video.publish` é opcional: sem ele, a conta conecta só
     com "Criar rascunho";
  2. **identidade:** `GET /v2/user/info/?fields=open_id,username,display_name,avatar_url`
     (escopos `user.info.basic` e `user.info.profile`). `username` é comparado com
     `contas.handle` (sem `@`, `casefold`). Diferente → **revoga** o token na TikTok (melhor
     esforço), nada é guardado e a resposta é 409 `conta_diferente`: "Você entrou como @x, mas
     esta conta é @y. Saia da TikTok no navegador e entre com @y";
  3. **reconexão:** se a conta já teve conexão, o `open_id` novo tem de ser igual ao antigo
     (409 `conta_diferente`, mesma mensagem). Um `open_id` já ligado a **outra** conta ativa → 409
     `conexao_em_uso`.
- **Escopos pedidos:** `user.info.basic,user.info.profile,video.upload,video.publish`
  (`TIKTOK_SCOPES`, com esse padrão). Todos precisam estar ligados no app do portal
  **[testar no sandbox]**.
- **Se o `username` não vier** (escopo `user.info.profile` não aprovado no sandbox): cai para
  `creator_info/query` (`creator_username`, exige `video.publish`). Sem nenhum dos dois, a
  conexão é recusada com 409 `identidade_indisponivel`: não conectamos sem conferir a conta.
- **Por quê:** o `open_id` é por app e por usuário e não aparece no perfil; o `@` é o que o dono
  cadastrou na 003. Comparar os dois impede o erro comum de autorizar com a conta errada que já
  estava logada no navegador.
- **Se o dono trocar o @ na TikTok:** a reconexão falha com a mensagem acima; o dono corrige o @
  da conta no SociMan (a 003 já permite) e conecta de novo.

## R4. Cifra dos tokens (FR-002, princípio V)

- **Decisão:** AES-256-GCM com a biblioteca `cryptography` (`AESGCM`), numa tabela separada
  (`conexao_credenciais`, data-model):
  - chave `SOCIMAN_TOKENS_KEY` no `.env` da raiz (32 bytes em base64url, gerada por
    `python -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`),
    repassada pelo compose **só** à `api` e ao `agendador` (o `worker` não recebe);
  - nonce de 12 bytes aleatório por cifragem, gravado junto (`nonce || ciphertext`);
  - **AAD** = `"{conexao_id}:{campo}"` (`access` ou `refresh`): um token copiado para outra linha
    ou outro campo não decifra;
  - `key_id` = os 8 primeiros hex do SHA-256 da chave, gravado por linha. Rotação:
    `SOCIMAN_TOKENS_KEY_ANTERIOR` (opcional) decifra linhas antigas, e toda renovação regrava com
    a chave atual; o comando `sociman tokens recifrar` regrava todas de uma vez;
  - no `Settings`, as duas chaves são `SecretStr`; sem `SOCIMAN_TOKENS_KEY`, **conectar** responde
    503 `publicacao_nao_configurada` e a trilha `publicacao` fica ociosa com o motivo no log.
- **Nunca no log nem na resposta:**
  - tokens só existem decifrados em variável local dentro de `publicacao/`; nenhum schema de
    saída tem campo de token; `conexao_credenciais` não tem `__versioned_fields__` e nunca passa
    por `history.snapshot`;
  - o cliente HTTP da TikTok não registra corpo nem URL de upload (o `upload_url` leva
    `upload_token`); todo texto de erro passa por `redact()` (como `canais/youtube.py`), que
    troca `access_token`, `refresh_token`, `code`, `code_verifier`, `client_secret` e
    `upload_token` por `***`;
  - o logger `httpx` continua em WARNING (já é assim desde a 006);
  - o `_scrub` de `auth/events.py` já remove chaves com `token` dos detalhes de eventos;
  - `check:secrets` ganha o padrão `SOCIMAN_TOKENS_KEY=` com valor e `TIKTOK_CLIENT_SECRET=` com
    valor em arquivos rastreados.
- **Testes:** cifra e decifra; AAD trocado falha; `key_id` anterior decifra e regrava; varredura
  do log (caplog) de um fluxo completo de conexão, renovação e envio no fake: nenhum token,
  código, verifier nem `upload_token` aparece.
- **Por quê:** os tokens são o segredo mais valioso do sistema (pesquisa §6). `cryptography` é a
  implementação de referência do AES-GCM em Python; a stdlib não tem cifra simétrica.
- **Alternativas rejeitadas:**
  - **`pgcrypto` no Postgres:** a chave iria em cada query (log do Postgres, `pg_stat_statements`);
  - **Fernet** (da mesma biblioteca): AES-CBC + HMAC sem AAD; o AAD por linha é o que impede a
    troca de tokens entre contas;
  - **tokens no Redis:** perder o Redis desconectaria todas as contas (e o Redis não é banco de
    registro);
  - **sem cifra, confiando no disco:** o backup do banco levaria os tokens em claro.

## R5. Renovação com rotação do refresh, sob `FOR UPDATE` (FR-002)

- **Decisão:** uma função só, `conexoes.token_valido(conexao_id) -> str`, usada pela trilha e
  pelas rotas (`creator_info`):
  1. abre **uma sessão própria** (transação curta, fora da transação de quem chama);
  2. `SELECT … FROM conexao_credenciais WHERE conexao_id = … FOR UPDATE`;
  3. se o `access_token` vale por mais de 5 min, devolve e sai;
  4. senão, chama `POST /v2/oauth/token/` com `grant_type=refresh_token`, grava o **novo**
     `access_token`, o **novo** `refresh_token` (a TikTok pode rotacionar; se vier igual, regrava
     igual) e as validades, e faz **commit imediatamente**;
  5. resposta `invalid_grant` (ou equivalente de refresh revogado/expirado) → conexão
     `precisa_reconectar` (com `history.record`, ator `system:publicacao`), credencial apagada,
     aviso `conexao_precisa_reconectar` aos donos, e `ConexaoPerdida` para quem chamou;
  6. erro de rede ou 5xx → **não** marca nada; `ConexaoIndisponivel` (a trilha tenta na próxima
     volta).
- **Por quê `FOR UPDATE`:** a API (tela do Direct Post) e o agendador podem renovar ao mesmo
  tempo; com rotação, o segundo gastaria um refresh já invalidado e derrubaria a conexão. A trava
  na linha serializa: o segundo espera, relê e encontra o token novo (passo 3).
- **Risco residual:** a TikTok aceita o refresh e o commit falha (queda no meio) → o refresh novo
  se perde e o antigo pode não valer mais. Consequência: `precisa_reconectar` na próxima
  renovação, com aviso. É raro e recuperável em 2 minutos (SC-001); o commit imediato no passo 4
  minimiza a janela.
- **Vencimento do refresh (365 dias):** a trilha avisa os donos uma vez quando faltam 30 dias
  (`refresh_expira_em`), com "Reconecte a conta". Sem job extra: a checagem roda na volta normal.
- **Revogação ao desconectar:** `POST /v2/oauth/revoke/` em melhor esforço (falha de rede não
  impede desconectar); a credencial é apagada na mesma transação (data-model,
  `conexao_credenciais`).

## R6. Trilha nova `publicacao` no agendador (FR-005)

- **Decisão:** uma trilha nova, `publicacao`, em `trilhas_padrao()`, com intervalo
  `AGENDADOR_PUBLICACAO_S` (padrão **15 s**) e `ociosa()` com os motivos, na ordem:
  "`PUBLICACAO_HABILITADA` desligada no servidor", "chave dos tokens ausente", "HD de dados sem o
  sentinela". Cada volta:
  1. **retomar** as tentativas abertas (R8), uma de cada vez, avançando um passo cada;
  2. **reivindicar** destinos vencidos: `estado = 'agendado' AND modo <> 'lembrete' AND
     planned_at <= now()` com a conta conectada, o interruptor ligado e a janela de 1 h respeitada
     (R11), com `FOR UPDATE SKIP LOCKED`, até 5 por volta;
  3. uma vez por hora: avisos de refresh perto de vencer (R5).
  Cada passo que muda estado faz **commit** antes de chamar a rede (R8).
- **Por quê trilha nova e não a `lembretes`:** a `lembretes` só avisa e o guarda da 014 prova que
  ela não muda estado de destino; misturar execução nela quebraria essa prova. A trilha nova tem
  o próprio guarda (R16) e fica ociosa sozinha quando a publicação está desligada.
- **Por quê no agendador e não no `worker`:** o worker é a fila de ffmpeg da 004 (um corte por
  vez, CPU); um upload de rede não deve esperar render nem o contrário. O agendador já tem lock
  único (advisory lock), estado no Postgres e retomada após reinício, que é exatamente o que o
  envio precisa. O container do agendador já monta o HD e fala com o MinIO.
- **Nome:** a 014 R13 chamou a trilha de `execucao`; `publicacao` casa com o nome do módulo e do
  interruptor. O guarda da 014 (nomes de `trilhas_padrao()`) passa a ser
  `{sync, openshorts, importacao, lembretes, publicacao}`.
- **Alternativas rejeitadas:**
  - **processo novo** (`sociman publicador`): serviço a mais no compose, com o mesmo lock e o
    mesmo laço (VIII);
  - **fila no Redis:** estado de envio precisa sobreviver (o Redis não é banco de registro).

## R7. Máquina de estados do envio (FR-005, FR-011)

- **Decisão:** dois níveis, seguindo a regra da 014 R3 (grava-se só decisão humana e resultado
  de execução; o que depende do relógio ou da configuração é derivado).

  **Destino** (`postagens.estado`, gravado). A 015 acrescenta `enviando` ao enum e passa a gravar
  os três valores reservados:

  | Transição | Quem | Onde (guarda de AST) |
  |---|---|---|
  | `agendado → enviando` | trilha, ao reivindicar | `publicacao/trilha.py::_reivindicar` |
  | `enviando → rascunho_criado` / `publicado` / `falhou` | trilha, ao concluir | `publicacao/trilha.py::_concluir` |
  | `enviando → agendado` | trilha, quando a tentativa termina **sem ter criado nada** (sem vaga, conta desconectada antes do init) | `publicacao/trilha.py::_devolver` |
  | `falhou → agendado` ("Tentar de novo", horário = agora) | dono humano | `publicacao/service.py::tentar_de_novo` |
  | `rascunho_criado → postado` ("Postado", link opcional) | humano | `postagem/service.py::marcar_postado` (a 014 amplia a origem) |

  **Tentativa** (`publicacao_tentativas.fase`, gravada pela trilha; ver R8):
  ```
  iniciando ──init ok──▶ enviando_partes ──última parte──▶ processando ──status──▶ entregue | publicada
      │                        │                               │
      ├─init recusado──▶ recusada (motivo)                     └─FAILED──▶ recusada (fail_reason)
      ├─sem vaga (local ou spam_risk_too_many_pending_share)──▶ sem_vaga
      └─sem resposta──▶ incerta           enviando_partes ──url expirou / parte recusada──▶ recusada
  ```
  | Fase final | Destino fica | Motivo e ação na tela |
  |---|---|---|
  | `entregue` (`SEND_TO_USER_INBOX`) | `rascunho_criado` | "Rascunho na caixa de entrada da TikTok" · **Copiar textos**, **Postado** |
  | `publicada` (`PUBLISH_COMPLETE`) | `publicado` | link quando a TikTok informar |
  | `recusada` | `falhou` | motivo em pt-BR (R19) · **Tentar de novo** |
  | `incerta` | `falhou` (`falha_incerta = true`) | "A TikTok pode ter recebido. Confira no app antes de tentar de novo" · **Tentar de novo** com confirmação |
  | `sem_vaga` | `agendado` (derivado `aguardando_vaga`) | "Aguardando vaga na TikTok (5 rascunhos em 24 h); nova tentativa às HH:MM" |

  **Estados efetivos novos** (derivados em `conteudos/consulta.py`, a expressão única da 014),
  inseridos na ordem da 014 depois de `atencao`:
  `pausado` (automático, vencido, interruptor desligado) → `vencido` (automático, `planned_at <=
  now() - 1 h`, sem confirmação, sem tentativa aberta) → `aguardando_vaga` (última tentativa
  `sem_vaga` com `proxima_em > now()`). `atencao` ganha os motivos "Conta não conectada" e
  "Conta precisa reconectar" para destinos automáticos. `enviando` vem do estado gravado.
- **Por quê derivar `pausado`, `vencido` e `aguardando_vaga`:** dependem do relógio, da
  configuração ou da última tentativa; gravá-los exigiria a trilha reescrever destinos que ela
  não está enviando (histórico poluído, 014 R3).
- **Histórico (FR-011, VII):** cada transição do destino chama `history.record` com
  `actor_kind = "system:publicacao"` e `details = {acao, tentativaId, publishId?, motivo?}`; as
  ações humanas (tentar de novo, confirmar vencido) usam o usuário. A tela "Histórico do envio"
  junta: aprovação e agendamento (versões do destino, com autor) + as tentativas (início, fim,
  fase, `publish_id`, versão do arquivo, motivo).

## R8. Idempotência e retomada após reinício (FR-006, SC-003)

- **Decisão:** a chamada `init` é o único passo que **cria** algo na TikTok e não tem chave de
  idempotência (pesquisa §4.4). Regra: **nunca repetir um `init` automaticamente.**
  1. **reivindicar** (uma transação): `agendado → enviando` + `INSERT` da tentativa em fase
     `iniciando`, com `video_ref`, `etag` e tamanho do objeto → **commit**;
  2. **init** (fora de transação): `inbox/video/init` (rascunho) ou `video/init` (publicar) com
     `source_info = FILE_UPLOAD`, `video_size`, `chunk_size`, `total_chunk_count`. Antes de
     chamar, grava `init_enviado_em` → commit;
  3. resposta ok → grava `publish_id`, `upload_url` (cifrado, porque leva o `upload_token`),
     `upload_url_expira_em = now + 55 min` e fase
     `enviando_partes` → **commit antes do primeiro PUT**;
  4. cada parte enviada → `partes_enviadas += 1` → commit;
  5. última parte → fase `processando`, `proxima_consulta_em` → commit; depois, `status/fetch`
     até um estado final (R7).
  **Retomada** (passo 1 da volta, R6), pela fase gravada:
  | Fase encontrada | O que a trilha faz |
  |---|---|
  | `iniciando` sem `init_enviado_em` | o init nunca saiu: chama o init (seguro) |
  | `iniciando` com `init_enviado_em` e sem `publish_id` | **não sabe** se a TikTok criou: fase `incerta`, destino `falhou` com `falha_incerta` |
  | `enviando_partes` com `upload_url` ainda válido | reenvia a partir de `partes_enviadas` (o PUT de uma parte é repetível; a parte em voo é reenviada inteira) **[testar no sandbox: PUT repetido da mesma faixa]** |
  | `enviando_partes` com `upload_url` vencido | `recusada`: "O envio parou no meio e o link da TikTok expirou; tente de novo" (sem upload completo não há rascunho) |
  | `processando` | continua o `status/fetch` |
- **Garantias no banco:**
  - `uq_tentativas_destino_aberta (destino_id) WHERE fase IN ('iniciando','enviando_partes',
    'processando')`: no máximo uma tentativa aberta por destino;
  - `uq_tentativas_publish_id (publish_id)`;
  - o destino só sai de `agendado` para `enviando` numa transação com `SKIP LOCKED` (dois
    agendadores são impossíveis pelo advisory lock, e mesmo assim a trava de linha segura);
  - "Tentar de novo" é ação humana, cria a tentativa `numero + 1`, e numa `incerta` exige
    `confirmoQueNaoChegou: true` (Clarifications Q4). A mesma confirmação vale para **qualquer**
    caminho que devolva um destino `falhou` com `falha_incerta` a `agendado`: reagendar
    (individual ou em lote) e agendar de novo pelo `POST /api/agendamentos`. Uma função só no
    service (`exigir_confirmacao_incerta`) atende os quatro caminhos.
- **Timeout do `status/fetch`:** sem estado final em 2 h desde o fim do upload → `incerta`
  ("A TikTok não confirmou; confira no app").
- **Teste (SC-003):** no fake, matar a trilha (exceção injetada) depois de cada commit e antes de
  cada chamada, reiniciar e conferir: exatamente um `init` por destino no registro de pedidos do
  fake, ou nenhum rascunho duplicado e a tentativa `incerta` quando o corte foi entre o envio e a
  resposta.

## R9. Envio em partes a partir do MinIO no HD (FR-005)

- **Decisão:** streaming direto do MinIO para a TikTok, sem arquivo temporário:
  - o arquivo é o **vídeo final vigente** no momento da reivindicação: `cortes.result_key`
    (origem corte) ou `conteudos.video_key` (vídeo próprio), via a mesma expressão `video_ref` da
    014. A tentativa grava `video_ref`, `video_bytes` e o `etag` do objeto (`stat_object`);
  - `chunk_size = 16 MB` (`storage.PART_SIZE`); arquivo < 5 MB vai inteiro (`chunk_size =
    video_size`, 1 parte); `total_chunk_count = video_size // chunk_size`, e a última parte
    absorve o resto (fica abaixo de 32 MB, dentro do limite de 128 MB);
  - cada parte: `storage.get_range(key, offset, length, bucket="videos")` (função nova, só
    leitura, com `offset/length` do MinIO) → `PUT upload_url` com `Content-Range: bytes
    a-b/total` e `Content-Type: video/mp4`; até 3 tentativas por parte com recuo (1, 4, 16 s);
  - o SHA-256 é calculado durante o envio e gravado ao fim (`video_sha256`): é a "versão do
    arquivo enviado" (FR-011);
  - **o vídeo não pode mudar no meio:** o `result_key` do corte é fixo por corte (a marca
    reaplicada sobrescreve o mesmo objeto). Duas defesas: (a) "Aplicar marca" e "Arquivar"
    respondem 409 `envio_em_andamento` enquanto um destino do conteúdo está `enviando`; (b) cada
    `get_range` confere o `etag`; mudou → `recusada` ("O vídeo mudou durante o envio").
- **Validação antes (edge case):** ao **agendar** em modo automático, a API confere o que já sabe
  do conteúdo (duração ≤ 600 s, tamanho ≤ 4 GB, lados entre 360 e 4096 px) e devolve **avisos**
  (`avisosRede`), sem bloquear; no Direct Post, `max_video_post_duration_sec` do `creator_info`
  bloqueia. O resto (codec, fps) fica para a TikTok, com o motivo traduzido (R19). Os cortes da
  004 saem em H.264 1080×1920 e cabem.
- **Por quê:** o HD é o lugar dos arquivos (constitution); baixar para `work/tmp` e depois
  enviar dobraria a E/S sem ganho. `FILE_UPLOAD` é o único modo possível sem endereço público
  (pesquisa §1.2).
- **Alternativa rejeitada:** `PULL_FROM_URL`: exige domínio verificado e acessível pela
  internet.

## R10. Limites da TikTok por conta (FR-007)

- **Decisão:**
  - **rascunhos pendentes (5 em 24 h, Clarifications Q1 = A):** antes do init de rascunho, a
    trilha conta as tentativas da conexão em modo `criar_rascunho` com `init_enviado_em >= now()
    - 24 h` e fase em `iniciando`, `enviando_partes`, `processando`, `entregue` ou `incerta`
    (as abertas e as incertas contam: a TikTok pode já ter o rascunho). Com 5 ou mais →
    tentativa `sem_vaga` (sem init) com `proxima_em` = o menor `init_enviado_em` contado + 24 h,
    o destino volta a `agendado` e o dono recebe **um** aviso `envio_aguardando_vaga` por
    destino. O erro `spam_risk_too_many_pending_share` no init tem o mesmo tratamento (com
    `proxima_em = now + 1 h`). A contagem local é conservadora: a API não informa quando o dono
    concluiu um rascunho no app **[testar no sandbox]**;
  - **taxas por token** (6 init/min, 30 status/min, 20 creator_info/min): um limitador no Redis
    compartilhado pela API e pelo agendador, `publicacao:taxa:{conexao}:{endpoint}:{minuto}`
    (`INCR` + `EXPIRE 70`), com limites 1 abaixo dos da TikTok. Estourou → a trilha adia o passo
    para a próxima volta; a rota do `creator_info` responde 429 `tente_em_instantes`. Um
    `rate_limit_exceeded` da TikTok adia 60 s;
  - **posts diretos (~15/dia):** `spam_risk_too_many_posts` → `recusada` com o motivo (não há
    espera automática no Direct Post: o dono decide).
- **Por quê Redis:** já é o lugar dos limites de tentativa (auth) e é compartilhado pelos dois
  processos; perder o Redis só zera contadores de um minuto.
- **Alternativa rejeitada:** limitador em memória: a API e o agendador são processos diferentes.

## R11. Interruptor geral e vencidos (FR-009, US4)

- **Decisão:** dois níveis, os dois precisam estar ligados para qualquer envio:
  1. **`PUBLICACAO_HABILITADA`** no `.env` da raiz (padrão `false`), o nome da constitution:
     desligado, a trilha fica ociosa e **nenhuma** rota liga o envio. Só quem tem acesso ao
     servidor muda;
  2. **"Envios automáticos"** na tela (`publicacao_config.envios_habilitados`, padrão
     desligado): o dono liga e desliga pela UI (`PUT /api/publicacao/config`), com histórico.
  Desligado (qualquer um): os destinos automáticos vencidos aparecem como `pausado`; nada é
  reivindicado; a tela mostra qual nível está desligado.
  **Vencidos:** a trilha só reivindica `planned_at > now() - 1 h` **ou** `envio_confirmado_em >=
  planned_at`. Um destino automático com `planned_at <= now() - 1 h` (interruptor religado, SociMan
  fora do ar, conta reconectada) fica `vencido` e mostra **Confirmar envio agora** (dono,
  `POST /api/destinos/{id}/confirmar-envio`, grava `envio_confirmado_por/em` com histórico) ou
  **Reagendar**. Ao religar o interruptor, a resposta traz a contagem de vencidos e a tela
  oferece "Revisar vencidos" (lista filtrada pelo atalho novo `vencidos`).
- **Tentativas em andamento ao desligar** (corrigido na análise de 2026-09-29, para cumprir o
  princípio I, "desligado, … sem enviar nada", e a Clarifications Q3, "só envia com os dois
  ligados"): com **qualquer** nível desligado, a trilha não faz **nenhum** init e **nenhum** PUT
  de parte. Com `PUBLICACAO_HABILITADA` desligada, a trilha fica ociosa e não faz chamada nenhuma
  (R6). Com só o botão desligado, a trilha ainda consulta o `status/fetch` das tentativas em
  `processando` (leitura: o vídeo já foi entregue inteiro e só falta a TikTok confirmar). Uma
  tentativa parada em `enviando_partes` retoma ao religar se o `upload_url` ainda valer (R8);
  senão vira `recusada` ("O envio foi interrompido pelo interruptor e o link da TikTok expirou;
  tente de novo"), sem risco de rascunho duplicado, porque sem upload completo a TikTok não cria
  rascunho. O destino continua `enviando` e aparece como `pausado` (data-model, estado efetivo).
  A tela avisa: "N envios em andamento ficaram pausados".
- **Por quê dois níveis:** o `.env` é o corte físico que nenhuma sessão (nem uma sessão de dono
  roubada) liga; a tela é o controle do dia a dia que a spec pede.
- **Alternativa rejeitada:** só a tela: um token de dono comprometido ligaria tudo; só o `.env`:
  a spec pede o interruptor na tela (US4).

## R12. Capacidades por configuração: sandbox ou auditado (FR-004, FR-013)

- **Decisão:** `conteudos/capacidades.py` (014 R4) mantém as três camadas, agora preenchidas:
  1. **a rede oferece o modo?** (tabela de fatos da 014, sem mudança);
  2. **existe executor?** `publicacao.registro.executor_para(platform)`: só TikTok na 015
     (`criar_rascunho` e `publicar`; `rascunho_e_publicar` segue "O TikTok não permite publicar
     um rascunho pela API");
  3. **a conta pode?** conexão `conectada`, com o escopo do modo (`video.upload` para rascunho,
     `video.publish` para publicar); senão "Conecte a conta" ou "Reconecte a conta".
  `ModoInfo` ganha `aviso: str | null`. A situação do app vem de `TIKTOK_APP_SITUACAO`
  (`sandbox` | `auditado`, padrão `sandbox`):
  | Situação | `publicar` |
  |---|---|
  | `sandbox` | disponível, com aviso: "Sem auditoria da TikTok, o post sai **só para você** e a conta precisa estar privada" |
  | `auditado` | disponível, sem aviso; as opções de privacidade vêm do `creator_info` |
  O interruptor desligado **não** torna o modo indisponível (dá para agendar); a tela avisa que
  ficará pausado.
- **Por quê variável de ambiente:** a situação do app é um fato do portal da TikTok, não uma
  decisão do dia a dia; muda com um restart, sem nova versão (edge case da spec).
- **FR-013:** YouTube e Instagram entram como `publicacao/youtube/` e `publicacao/instagram/`,
  cada um com um executor registrado em `publicacao/registro.py` (R20); a central (014) não muda.

## R13. Direct Post: tela obrigatória, `creator_info` na hora e revalidação (FR-008, US3)

- **Decisão:**
  - ao abrir o modo **Publicar** no `AgendarDialog`, o SPA chama `GET
    /api/contas/{id}/conexao/criador` (dono), que consulta `creator_info/query` **na hora** (sem
    cache) e devolve apelido, @, avatar (R14), `privacyLevelOptions`, `comentarioDesligado`,
    `duetoDesligado`, `costuraDesligada`, `duracaoMaximaS` e `podePostar`. Com `podePostar =
    false`, a tela para e mostra "A TikTok não deixa esta conta postar agora; tente mais tarde";
  - campos (schema `OpcoesTikTok`, validado na API):
    | Campo | Regra |
    |---|---|
    | `privacidade` | **obrigatório, sem padrão**; só valores de `privacyLevelOptions`; em `sandbox` só `SELF_ONLY` (os outros aparecem desabilitados com o motivo) |
    | `permitirComentario`, `permitirDueto`, `permitirCostura` | obrigatórios (true/false), **nenhum pré-marcado**; `false` e bloqueados quando a conta desligou |
    | `comercial` | `nenhum` (padrão, toggle desligado) \| `sua_marca` (→ `brand_organic_toggle`, "Conteúdo promocional") \| `parceria_paga` (→ `brand_content_toggle`, "Parceria paga") |
    | `conteudoIa` | `is_aigc` (padrão false) |
    | `consentimento` | o texto exibido (música; com `parceria_paga`, também a Política de Conteúdo de Marca) e `aceitoEm` |
    Combinações recusadas (400 `opcoes_invalidas` com a regra): `parceria_paga` + `SELF_ONLY`;
    privacidade fora das opções; toggle ligado que a conta desligou;
  - ao **agendar**, a API grava `postagens.opcoes_rede` e um **`envio_snapshot`** `{legenda,
    opcoes, consentimento, videoRef}`: a legenda é montada dos textos do destino (descrição +
    hashtags, até 2.200 caracteres; o título entra como primeira linha se houver). A trilha
    envia o **snapshot**, não os textos vivos;
  - **editar textos ou opções** de um destino `agendado` em modo publicar: só dono; a edição
    regrava o snapshot (é uma nova confirmação humana, com versão no histórico). Um membro recebe
    403 `somente_dono` (Clarifications Q2 = A);
  - **no horário**, a trilha consulta `creator_info` de novo; se a privacidade escolhida saiu das
    opções, a duração passou do máximo, um toggle ligado foi desligado na conta ou `podePostar`
    é falso → `recusada` com o motivo, **sem trocar a escolha do humano**;
  - a pré-visualização é o player da 014 no próprio diálogo; o aviso "a TikTok leva alguns
    minutos para processar" aparece ao confirmar.
- **Modo rascunho:** a API do inbox não recebe `post_info` (pesquisa §1.3). O snapshot guarda
  só `videoRef`; os textos ficam na tela para **Copiar textos**.
- **Por quê snapshot:** o que o dono confirmou na tela obrigatória é o que vai para a rede
  (princípio I: "no modo que esse dono escolheu"). A 014 (Q2) deixou textos editáveis sem nova
  aprovação porque no lembrete quem posta é o humano; aqui quem posta é o SociMan.

## R14. Avatar do criador sem abrir a CSP

- **Decisão:** a API baixa o avatar (`avatar_url` do `user/info` na conexão; `creator_avatar_url`
  a cada `creator_info`) pelo cliente de `publicacao/tiktok/`, valida com `imaging.py` (Pillow,
  pelo conteúdo, até 1 MB), grava no bucket `imagens` como `conexoes/{conexao_id}/avatar-{sha8}.
  <ext>` e guarda a chave em `conexoes.avatar_key`. A tela usa a URL `/img` assinada (imgproxy),
  como as demais imagens. Mesma imagem (hash) → não regrava.
- **Por quê:** a CSP fica igual (`img-src 'self' data:`; princípio V: nenhuma origem externa), e o
  link da CDN da TikTok vence em 2 h.
- **Alternativa rejeitada:** imgproxy buscando a URL externa: exigiria liberar fontes HTTP
  arbitrárias no imgproxy.

## R15. Recusa a IA, agente e MCP (FR-010, US4-3)

- **Decisão:** uma dependência nova, **`RequireHumanOwner`** (`auth/deps.py`): `require_owner` +
  `actor.kind == "user"`. Qualquer outro `kind` (o `mcp_client` que a 009 vai criar, `system:*`,
  ou um futuro token de agente) → 403 `somente_humano` ("Só um dono, pela interface, pode fazer
  isto") e um `SecurityEvent` `publicacao_recusada` com o `kind`, a rota e a conta.
  Usada em: conectar (iniciar e retorno), desconectar, `PUT /api/publicacao/config`, tentar de
  novo, confirmar envio e, **dentro do service**, em aprovar, agendar, reagendar (individual,
  em lote e pelo calendário), editar o snapshot, cancelar (individual e em lote) e arquivar
  (destino, conteúdo ou corte com destino automático `agendado`, porque arquivar cancela) quando
  o modo é automático (as rotas da 014 continuam `RequireUser`/`RequireOwner`; o service chama
  `exigir_humano_dono(actor)` quando o modo não é `lembrete`).
- **Defesa na execução:** ao reivindicar, a trilha confere `aprovado_por` e `agendado_por`
  preenchidos (CHECK no banco) e que a última versão `agendado`/`reagendado` do destino tem
  `actor_kind = 'user'`; senão `recusada` com "Agendamento sem decisão humana" e evento de
  segurança. É redundante de propósito (princípio I é inegociável).
- **MCP (009):** a 009 não pode expor nenhuma rota com `RequireHumanOwner` (guarda R16.5).
- **Teste:** para cada rota da lista, um override de `current_user` com `Actor(kind="mcp_client",
  user=<dono>)` → 403 `somente_humano`, nenhuma linha muda, evento gravado.

## R16. Guardas do princípio I depois da 015 (FR-012, SC-004)

`tests/unit/test_constitution_guards.py` ganha a seção "spec 015". **Nenhuma lista encolhe**
(`test_listas_do_guarda_nao_encolheram` continua):
1. **Endpoints no código:** `test_codigo_fonte_sem_endpoint_de_publicacao` passa a aceitar uma
   exceção por pasta, `PERMITIDO_EM = {"open.tiktokapis.com": "publicacao/tiktok/"}`. Os outros
   endpoints da lista continuam proibidos em todo o `src/`. Por isso o endereço padrão da API
   **não** fica no `config.py`: `TIKTOK_API_URL` vazio = a constante de `publicacao/tiktok/
   cliente.py`.
2. **Quem importa o cliente:** nenhum módulo fora de `publicacao/` importa `publicacao.tiktok`
   (varredura de `import`/`from`), exceto `publicacao/registro.py`.
3. **Lista fechada do cliente:** `publicacao/tiktok/cliente.py` tem `ALLOWED` com exatamente os
   pedidos de R21; o PUT de partes só vai para `https://` em host terminado em `.tiktokapis.com`
   (ou o host do fake em teste); o init de rascunho nunca leva `post_info`; o init direto só leva
   `privacy_level` do snapshot.
4. **Estados:** o guarda de AST da 014 (atribuição de `rascunho_criado`, `publicado`, `falhou`)
   passa a ter como únicos lugares permitidos `publicacao/trilha.py::_concluir`; `enviando` só em
   `_reivindicar`; `postado` continua só em `postagem/service.py::marcar_postado`.
5. **Rotas:** `test_nenhuma_rota_de_publicacao` continua sem exceção: nenhum caminho nem
   `operationId` da 015 contém `tiktok`, `publish`, `share`… (R21). Um teste novo confere que as
   rotas da lista de R15 têm `require_human_owner` na árvore de dependências.
6. **Agendador:** trilhas = `{sync, openshorts, importacao, lembretes, publicacao}`; com
   `PUBLICACAO_HABILITADA=false` ou o interruptor da tela desligado, uma volta da trilha com
   destinos vencidos não faz nenhum pedido ao fake e não muda nenhum destino (SC-004).
7. **Banco:** CHECKs da 0010 (data-model) provados com `INSERT`/`UPDATE` direto.
8. **Docstring do guarda:** passa a dizer "as listas só crescem; exceções só por pasta de
   `publicacao/`, uma por rede, criada por spec".

## R17. O que a migration `0010_publicacao_tiktok` faz com os CHECKs da 014

- **Decisão:** relaxar, não remover a defesa:
  - `ck_postagens_modo_014` (só `lembrete`) → **`ck_postagens_modo_015`**: `modo IN
    ('lembrete','criar_rascunho','publicar') AND antecedencia_min IS NULL`
    (`rascunho_e_publicar` continua impossível no banco até existir executor);
  - `ck_postagens_estados_015` (proibia `rascunho_criado`, `publicado`, `falhou`) → removido e
    substituído por **`ck_postagens_execucao`**: esses estados e `enviando` só com `modo <>
    'lembrete'`;
  - novos: `ck_postagens_auto_decisao` (modo automático em `agendado`/`enviando` exige
    `aprovado_por` e `agendado_por`), `ck_postagens_publicar_snapshot` (modo `publicar` em
    `agendado`/`enviando` exige `opcoes_rede` e `envio_snapshot`).
- **Downgrade:** recusa se existir destino com `modo <> 'lembrete'`, conexão ou tentativa;
  senão recria os CHECKs da 014 e apaga as tabelas novas (o valor `enviando` fica no enum, como
  no padrão da 0007).

## R18. TikTok falsa para pytest e e2e (VI)

- **pytest:** `tests/fakes/tiktok_fake.py`, no padrão de `tests/fakes/__init__.py`: um
  `httpx.MockTransport` com estado, injetado por `get_tiktok_client(transport=…)` e por
  `rodar(db, client=…)`. Simula: troca de código (com e sem PKCE, conferindo o verifier),
  refresh **com rotação** (o refresh antigo vira `invalid_grant` depois de usado), revogação,
  `user/info` (com `username` configurável para o teste de conta diferente), `creator_info`,
  init de inbox e direto, PUT de partes (confere `Content-Range` e ordem), `status/fetch` com
  N passos até `SEND_TO_USER_INBOX` ou `PUBLISH_COMPLETE`, e as falhas: timeout no init, 5xx
  numa parte, `spam_risk_too_many_pending_share`, `rate_limit_exceeded`,
  `access_token_invalid`, `unaudited_client_can_only_post_to_private_accounts`, `FAILED` com cada
  `fail_reason`. `requests` registra tudo (guardas e SC-003). Respostas em
  `tests/fixtures/tiktok/*.json`, sem nenhum token real.
- **e2e:** o `e2e/fakes/server.py` ganha `/tiktok/v2/...` (mesmas rotas, stdlib), e o
  `docker-compose.e2e.yml` aponta `TIKTOK_API_URL` e `TIKTOK_UPLOAD_HOSTS` para ele, com
  `TIKTOK_CLIENT_KEY`/`SECRET` e `SOCIMAN_TOKENS_KEY` **fixos de teste**, `PUBLICACAO_HABILITADA=
  true` e `AGENDADOR_PUBLICACAO_S=2`. O login no navegador é interceptado pelo Playwright
  (`page.route("https://www.tiktok.com/v2/auth/authorize/**")`), que redireciona para
  `/app/conexoes/retorno?code=e2e-<handle>&state=<state>`: o e2e nunca sai da máquina.
- **Nenhum teste chama a TikTok real.** O teste real é manual, com o dono (quickstart §3).

## R19. Motivos em pt-BR e ação possível (SC-006)

`publicacao/tiktok/erros.py` mapeia o `error.code` do init e o `fail_reason` do status para
`(motivo, acao)`; o código cru fica em `publicacao_tentativas.codigo_rede`. Exemplos (a lista
exata é conferida na doc ao implementar):

| Código da TikTok | Motivo na tela | Ação |
|---|---|---|
| `spam_risk_too_many_pending_share` | Já há 5 rascunhos esperando na TikTok nas últimas 24 h | espera automática (R10) |
| `spam_risk_too_many_posts` | A conta atingiu o limite de posts do dia | Reagendar para amanhã |
| `unaudited_client_can_only_post_to_private_accounts` | Sem auditoria, a conta precisa estar privada para publicar | Deixe a conta privada no app e tente de novo |
| `privacy_level_option_mismatch` | A privacidade escolhida não está mais disponível para a conta | Reagendar e escolher de novo |
| `access_token_invalid`, `scope_not_authorized` | A autorização da conta não vale mais | Reconectar |
| `file_format_check_failed`, `duration_check_failed`, `frame_rate_check_failed`, `picture_size_check_failed` | O vídeo está fora das regras da TikTok (formato / duração / fps / tamanho) | Trocar o vídeo e tentar de novo |
| `spam_risk_user_banned_from_posting` | A TikTok bloqueou postagens desta conta | Verificar no app |
| timeout sem resposta no init | A TikTok pode ter recebido; confira no app | Tentar de novo (com confirmação) |
| outro | "A TikTok recusou o envio (código X)" | Tentar de novo |

## R20. Interface de executor por rede (FR-013)

- **Decisão:** `publicacao/executor.py` define o contrato; a trilha é genérica e fala só com ele:
  ```text
  class ExecutorRede(Protocol):
      rede: Platform
      modos: frozenset[Modo]                        # capacidades da camada 2 (R12)
      escopos_por_modo: dict[Modo, str]
      def iniciar(ctx, tentativa) -> Iniciado | SemVaga | Recusado            # init
      def enviar_parte(ctx, tentativa, indice, dados) -> None                  # upload
      def consultar(ctx, tentativa) -> EmAndamento | Entregue | Publicado | Recusado
      def validar_opcoes(opcoes, criador) -> list[Problema]                    # R13
      def consultar_criador(ctx) -> Criador                                     # tela obrigatória
  ```
  `ctx` traz o cliente HTTP e o `token_valido()` (R5). `publicacao/registro.py` tem
  `EXECUTORES = {Platform.tiktok: TikTokExecutor}`. A máquina de estados (R7, R8), o
  interruptor, os vencidos, o histórico e os avisos ficam na trilha e valem para qualquer rede.
- **Por quê:** a spec pede o desenho pronto para YouTube e Instagram (FR-013) sem mudar a
  central; a pesquisa mostra que as duas cabem no mesmo contrato (init, upload retomável,
  consulta de status).
- **Não é antecipação (VIII):** só há uma implementação; o Protocol é o mínimo para a trilha não
  importar código da TikTok (o que também simplifica o guarda R16.2).

## R21. Rotas e nomes sem "tiktok" (princípio I, guarda de rotas)

- **Decisão:** os recursos são **neutros de rede**, e o guarda de rotas continua sem exceção:
  - `/api/contas/{id}/conexao` (+ `/iniciar`, `/desconectar`, `/criador`), `/api/conexoes/retorno`,
    `/api/publicacao/config`, `/api/destinos/{id}/tentativas`, `/tentar-de-novo`,
    `/confirmar-envio`;
  - `operationId`: `conexoes_*`, `publicacao_config_*`, `destinos_tentativas`,
    `destinos_tentar_de_novo`, `destinos_confirmar_envio`. Nenhum contém `publish` nem `share`
    (`publicacao` não casa com `publish`);
  - a rede aparece só no **corpo** (`rede: "tiktok"`), como os modos na 014.
- **Pedidos do cliente TikTok (`ALLOWED`):** `POST /v2/oauth/token/`, `POST /v2/oauth/revoke/`,
  `GET /v2/user/info/`, `POST /v2/post/publish/creator_info/query/`, `POST
  /v2/post/publish/inbox/video/init/`, `POST /v2/post/publish/video/init/`, `POST
  /v2/post/publish/status/fetch/`, `PUT <upload_url>` (host restrito) e `GET <avatar>` (host de
  CDN restrito a `*.tiktokcdn.com`/`*.tiktokcdn-us.com`, só imagem, até 1 MB).
- **Por quê:** manter o guarda de rotas intacto é mais forte do que abrir exceção nele; o
  contrato é gerado (IV) e o MCP (009) herdará nomes neutros.
