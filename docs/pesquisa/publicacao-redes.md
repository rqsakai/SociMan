# Pesquisa: rascunho, agendamento e publicação nas redes

> Pesquisa para a futura spec `014-publicacao-redes` (ver `docs/visao.md`, item 14). Só leitura:
> nenhuma API foi chamada e nenhuma credencial foi lida. Todas as fontes foram acessadas em
> **2026-09-29**. Legenda: **[confirmado]** está escrito na documentação oficial citada;
> **[não confirmado]** é inferência, fonte de terceiros ou ponto que a documentação não cobre, e
> precisa de teste no sandbox.

## Resumo

1. **O TikTok não deve aprovar a auditoria do SociMan.** As diretrizes da própria TikTok listam como
   "não aceitável" tanto "uma ferramenta utilitária para enviar conteúdo às contas que você ou sua
   equipe gerencia" quanto "um app que copia conteúdo de outras plataformas para o TikTok". A revisão
   de apps também recusa apps "de uso privado ou pessoal" e apps "em desenvolvimento ou teste".
   **[confirmado]** O SociMan se encaixa nos três casos: é uma ferramenta interna e publica cortes do
   YouTube. O mais provável é que o app fique para sempre **sem auditoria**.
2. **Sem auditoria, o Direct Post só publica como `SELF_ONLY`** (só o dono vê o post), para no
   máximo 5 usuários a cada 24 h, e **a conta precisa estar privada na hora do post**.
   **[confirmado]** Não dá para testar isso na @atavernanerd nem na @meusqueridinhos10 sem torná-las
   privadas.
3. **O caminho viável é o rascunho (upload para a caixa de entrada).** O SociMan envia o vídeo, o
   dono recebe uma notificação no app do TikTok e termina ali a legenda, a privacidade e o link de
   produto. **[confirmado]** Não está documentado se o rascunho tem restrição de visibilidade para
   app sem auditoria, nem se o sandbox deixa publicar em público um rascunho que o dono finaliza no
   app. **[não confirmado]** Esse é o primeiro teste a fazer.
4. **Rede local sem domínio funciona com `FILE_UPLOAD`**, em que o SociMan envia o arquivo em
   chunks por conexão de saída. **[confirmado]** `PULL_FROM_URL` exige domínio ou prefixo de URL
   verificado em HTTPS e público, e os webhooks exigem um endpoint público. Portanto: FILE_UPLOAD e
   consulta periódica do status (`status/fetch`).
5. **O redirect do OAuth é o ponto sensível.** No Login Kit Web, o redirect precisa ser HTTPS,
   estático e registrado no app. **[confirmado]** Não está documentado se o portal aceita IP privado
   (`https://192.168.86.47:8543/...`). Como o navegador só é redirecionado e a TikTok nunca chama esse
   endereço, deve funcionar, mas isso **não está confirmado**. Plano B oficial: o Login Kit Desktop
   aceita `http://localhost:<porta>` ou `127.0.0.1:*` com PKCE S256. **[confirmado]** Nesse caso, o
   login é feito no próprio `sakai-desktop`.
6. **Nenhuma das três redes agenda nativamente pela API, exceto o YouTube.** No TikTok não existe
   campo de horário. **[confirmado pela ausência na referência; fontes de terceiros confirmam]** No
   Instagram, a documentação de publicação não menciona agendamento. **[não confirmado que não
   exista]** O YouTube tem `status.publishAt`, que só vale com `privacyStatus=private`.
   **[confirmado]** No TikTok e no Instagram, o agendador do SociMan envia na hora marcada.
7. **O YouTube também fica privado sem auditoria.** Todo vídeo enviado por `videos.insert` a partir
   de projeto não verificado criado depois de 28/07/2020 fica privado. **[confirmado]** A cota mudou:
   o `videos.insert` tem balde próprio, com **100 chamadas por dia** a 1 unidade cada, separado das
   10.000 unidades. **[confirmado]** Com a tela de consentimento em "Testing", o refresh token expira
   em **7 dias**. **[confirmado pela ajuda do Google Cloud]** No Google, o redirect **não aceita IP
   cru**, só `localhost`. **[confirmado]**
8. **O Instagram aceita envio local.** O container `REELS` aceita `video_url` público ou *upload
   retomável* por `rupload.facebook.com` com o arquivo local. **[confirmado]** Limite de 100 posts
   por 24 h. Exige conta profissional (Business ou Creator). Não confirmei se um app em modo
   desenvolvimento publica para usuários com papel no app sem App Review. **[não confirmado]**
9. **Conteúdo comercial e de IA têm campo na API.** O TikTok tem `brand_content_toggle` ("Parceria
   paga"; exige post público), `brand_organic_toggle` ("Conteúdo promocional"/sua marca) e
   `is_aigc`. O YouTube tem `paidProductPlacementDetails.hasPaidProductPlacement` e
   `status.containsSyntheticMedia`. **[confirmado]** O **link de produto do TikTok Shop** (âncora de
   afiliado) não aparece na Content Posting API. **[não confirmado; provavelmente só no app]** Isso
   reforça o rascunho para vídeos de afiliado.
10. **Na constitution, o princípio I (INEGOCIÁVEL) precisa de emenda MAJOR** (4.0.0), e a guarda
    `tests/unit/test_constitution_guards.py` proíbe hoje, por nome, `tiktok`, `publish`,
    `open.tiktokapis.com`, `videos.insert` e `graph.facebook.com`. Recomendação: emenda em dois
    degraus, com rascunho primeiro (seção 5).

**Caminho recomendado:** (a) emendar o princípio I só para **rascunho iniciado por humano**; (b)
spec 014 com "conta conectada" (OAuth por conta, tokens cifrados), TikTok **inbox + FILE_UPLOAD +
status/fetch** no sandbox com as 2 contas; (c) teste empírico: o rascunho chega? o dono consegue
publicar em público pelo app? (d) só depois discutir o Direct Post e o YouTube.

---

## 1. TikTok: Content Posting API

### 1.1 OAuth (Login Kit)
- Autorização: `https://www.tiktok.com/v2/auth/authorize/` com `client_key`, `scope` (separado por
  vírgula), `redirect_uri`, `state` e `response_type=code`. **[confirmado]** (Login Kit Web)
- Redirect (web): até 10 URIs, cada uma com menos de 512 caracteres, absoluta, **começando com
  `https`**, estática (sem query), sem `#`, igual a uma URI registrada. **[confirmado]** Não está
  documentado se o portal aceita IP privado ou porta não padrão. **[não confirmado]**
- Redirect (desktop): só `localhost` ou `127.0.0.1`, **com porta** (curinga `*` permitido), PKCE
  obrigatório com `S256` e verifier de 43 a 128 caracteres. **[confirmado]**
- Token: `POST https://open.tiktokapis.com/v2/oauth/token/` (troca e refresh). O `access_token` vale
  **24 h** (`expires_in=86400`) e o `refresh_token` vale **365 dias** (`refresh_expires_in=31536000`).
  **O refresh pode devolver um refresh token novo, e o novo deve ser usado.** Revogação em
  `POST /v2/oauth/revoke/`. **[confirmado]**
- Escopos: `video.upload` (rascunho na caixa de entrada) e `video.publish` (Direct Post e
  `creator_info`). Os dois exigem aprovação no app e autorização do usuário. **[confirmado]**
- Tokens são **por conta** (`open_id`). Cada conta autoriza separadamente. **[confirmado]**

**Implicações para a rede local:** o redirect é só do navegador, e a TikTok não chama o SociMan.
Opções, em ordem:
1. registrar `https://192.168.86.47:8543/api/contas-conectadas/tiktok/callback/` no app web
   (testar no portal; o celular e o desktop com a CA da casa completam o fluxo);
2. se o portal recusar IP, usar a plataforma Desktop com `http://localhost:<porta>/...` e PKCE,
   fazendo o login no `sakai-desktop`;
3. um domínio próprio (o DNS pode apontar para o IP privado; o certificado exigiria ACME DNS-01).
   É mais trabalho, mas também resolveria o YouTube (seção 2).

### 1.2 Transferência de mídia
| | `FILE_UPLOAD` | `PULL_FROM_URL` |
|---|---|---|
| Quem busca | o SociMan faz `PUT` no `upload_url` (saída) | a TikTok baixa a URL |
| Requisito | nenhum de rede | domínio ou prefixo **verificado**, `https`, sem redirect, acessível pela internet |
| Na LAN | **funciona** | não funciona |

- Chunks de **5 MB a 64 MB** (o último chega a 128 MB), de 1 a 1.000 chunks, **sequenciais**.
  Arquivo menor que 5 MB vai inteiro, e arquivo maior que 64 MB vai em vários chunks. O
  `upload_url` vale **1 h**. **[confirmado]**
- Vídeo: MP4 (recomendado), WebM ou MOV; H.264 (recomendado), H.265, VP8 ou VP9; de 23 a 60 fps; de
  360 a 4096 px por lado; até **10 min** pela API; até **4 GB**. **[confirmado]** O limite real de
  duração por criador vem em `max_video_post_duration_sec`. Os cortes da 006 (1080×1920, curtos)
  cabem.

### 1.3 Rascunho (upload para a caixa de entrada) × Direct Post
| | Rascunho (`/v2/post/publish/inbox/video/init/`) | Direct Post (`/v2/post/publish/video/init/`) |
|---|---|---|
| Escopo | `video.upload` | `video.publish` |
| Textos e privacidade | definidos **pelo dono no app** (a API não recebe `post_info`) | enviados na API (`post_info`) |
| Resultado | notificação no app; o dono "clica na notificação para continuar a edição e concluir o post" | post criado direto |
| Limite | **até 5 rascunhos pendentes a cada 24 h** (erro `spam_risk_too_many_pending_share`) | cerca de 15 posts por dia por criador (`spam_risk_too_many_posts`) |
| UX obrigatória | não documentada | extensa (1.4) |
| Sem auditoria | restrição não documentada **[não confirmado]** | só `SELF_ONLY`, conta privada, 5 usuários por 24 h |
| Taxa | 6 req/min por token | 6 req/min por token |

Todos os dados da tabela são **[confirmado]**, salvo onde está marcado. Fontes: referências de
upload e Direct Post e as diretrizes de compartilhamento.

### 1.4 UX obrigatória do Direct Post (diretrizes de compartilhamento)
- Consultar `POST /v2/post/publish/creator_info/query/` (escopo `video.publish`, 20 req/min) **toda
  vez** que a tela de postagem abrir. Mostrar o **apelido** do criador (e o avatar;
  `creator_avatar_url` vale 2 h). Se a API disser que o criador não pode postar agora, parar e
  pedir que ele tente depois. Respeitar `max_video_post_duration_sec`.
- **Privacidade em lista, sem valor padrão**, com só as opções de `privacy_level_options`.
- Toggles de **Comentário, Dueto e Costura**, nenhum pré-marcado, desabilitados quando o criador os
  desligou no app (`comment_disabled`, `duet_disabled`, `stitch_disabled`).
- **Divulgação de conteúdo comercial:** toggle desligado por padrão. Ao ligar, o usuário escolhe
  entre "Sua marca", que rotula como "Conteúdo promocional" (`brand_organic_toggle`), e "Conteúdo de
  marca", que rotula como "Parceria paga" (`brand_content_toggle`). **Conteúdo de marca não pode
  ser privado**: desabilitar a opção ou mudar para público.
- **Consentimento:** "Ao postar, você concorda com a Confirmação de Uso de Música do TikTok" (com
  conteúdo de marca, cita também a Política de Conteúdo de Marca).
- **Pré-visualização** antes de postar, aviso de que o processamento leva alguns minutos, e
  acompanhamento do status.
- Proibido acrescentar marca d'água ou logo promocional do app. O texto pré-preenchido deve ser
  editável.

Tudo acima é **[confirmado]**. Observação: a marca d'água do kit (spec 004) é do perfil, não do app.
Pela letra da regra deve ser aceita, mas um revisor pode ler diferente. **[não confirmado]**

### 1.5 Status do post
`POST /v2/post/publish/status/fetch/` com `publish_id`, até 30 req/min. Estados:
`PROCESSING_UPLOAD`, `PROCESSING_DOWNLOAD`, `SEND_TO_USER_INBOX` (rascunho entregue),
`PUBLISH_COMPLETE` e `FAILED` (`fail_reason`: `file_format_check_failed`,
`duration_check_failed`, `spam_risk_*` e outros). `publicaly_available_post_id` (grafia da API)
só aparece depois da moderação de post público. Há webhooks (`post.publish.complete`,
`post.publish.failed`, `post.publish.publicly_available`), mas eles **exigem um endpoint público**.
Na LAN, a alternativa é consultar o status periodicamente. **[confirmado]**

### 1.6 Sandbox e app sem auditoria
- Sandbox: até **10 usuários-alvo** e até 5 sandboxes por app, sem revisão. "O sandbox não oferece
  a Content Posting API para vídeos públicos." **[confirmado]**
- Sem auditoria: todo conteúdo fica **privado**, só `SELF_ONLY`, até 5 usuários por 24 h, e as
  contas **precisam estar privadas** na hora do post. **[confirmado]**
- Não está documentado se um rascunho enviado pelo sandbox pode virar post público quando o dono o
  finaliza no app. **[não confirmado]** É o teste decisivo.
- Credenciais do sandbox × produção: a documentação não detalha. A configuração do sandbox é
  "importada" para o rascunho de produção. **[não confirmado]**

### 1.7 Auditoria (produção)
Requisitos: site oficial público e completo (não pode ser landing nem tela de login), Política de
Privacidade e Termos visíveis no site, vídeo de demonstração do fluxo completo (até 5 vídeos de
50 MB, gravados no sandbox) e domínio do site igual ao do vídeo. **Recusa:** apps de uso privado
ou pessoal, apps em desenvolvimento, ferramenta para as contas da própria equipe, e cópia de
conteúdo de outras plataformas. **[confirmado]** Conclusão: **não conte com a auditoria.**

### 1.8 Agendamento
A API não tem campo de data futura, nem no rascunho nem no Direct Post. **[confirmado pela ausência
na referência]** O agendamento fica no SociMan: o agendador faz o upload na hora. No rascunho, o
dono ainda precisa concluir o post no app, então a "hora" é, na prática, a hora do lembrete.

### 1.9 Conteúdo comercial, afiliado e IA
- `brand_content_toggle` e `brand_organic_toggle` só valem no Direct Post. `is_aigc` rotula
  conteúdo gerado por IA, o que é relevante para os vídeos de avatar (spec 011 e seguintes).
  **[confirmado]**
- Âncora ou link de produto do TikTok Shop: não encontrei na Content Posting API. **[não confirmado;
  provável que só exista no app ou em APIs do Shop/Affiliate, que não pesquisei]**

---

## 2. YouTube (Shorts)
- `videos.insert` com upload retomável, escopo `youtube.upload` (ou `youtube`/`youtube.force-ssl`),
  até 256 GB. **Cota:** balde próprio de **100 inserts por dia**, a 1 unidade cada, separado das
  10.000 unidades dos outros métodos. **[confirmado]** (Isso muda a conta da cota da 006, que só lê.)
- **Projeto não verificado criado depois de 28/07/2020:** todo vídeo fica **privado** até passar
  pela auditoria de conformidade. **[confirmado]** Não verifiquei se a auditoria do YouTube recusa
  ferramenta interna como a do TikTok. **[não confirmado]**
- `status.privacyStatus`: `private`, `public` ou `unlisted`. `status.publishAt` (**agendamento
  nativo**) só com `private`. `status.selfDeclaredMadeForKids` (declaração do canal; defina sempre).
  `status.containsSyntheticMedia` (conteúdo alterado ou sintético; avatares).
  `paidProductPlacementDetails.hasPaidProductPlacement` (divulgação de publicidade paga).
  **[confirmado]**
- Short: vídeo quadrado ou vertical de **até 3 min** é classificado sozinho. A API não tem flag de
  Short. **[confirmado pela ajuda do YouTube]**
- OAuth: redirect em HTTPS, **sem IP cru** (exceto localhost) e com TLD da lista pública.
  `access_type=offline` e `prompt=consent` para obter refresh token. **[confirmado]** Com a tela de
  consentimento em "Testing", são até 100 usuários de teste e o **refresh token expira em 7 dias**.
  `youtube.upload` é escopo sensível e exige verificação para sair de Testing (de 3 a 5 dias úteis).
  **[confirmado pela ajuda do Google Cloud]** Na LAN: login pelo `sakai-desktop` com `localhost`, ou
  domínio próprio.
- Rascunho no YouTube = upload `private`. O dono revisa no Studio e publica, ou usa `publishAt`.

## 3. Instagram Reels (Graph API)
- Conta profissional (Business ou Creator). Com o Instagram Login não é preciso ter Página do
  Facebook. Escopos: `instagram_business_content_publish` (Instagram Login) ou
  `instagram_content_publish` (Facebook Login). **[confirmado]**
- Fluxo: `POST /<IG_ID>/media` com `media_type=REELS` e `video_url` **público**, **ou** upload
  retomável por `rupload.facebook.com` com o arquivo local (útil na LAN). Consultar o `status_code`
  (`IN_PROGRESS`, `FINISHED`, `ERROR`, `EXPIRED` em 24 h; recomendação: 1 vez por minuto, por até
  5 min) e depois `POST /<IG_ID>/media_publish`. **[confirmado]**
- Limite: 100 posts pela API por 24 h (`GET /<IG_ID>/content_publishing_limit`). **[confirmado]**
- Agendamento: a página não menciona. **[não confirmado; assumir que o SociMan envia na hora]**
- Não há rascunho: a API publica direto.
- Modo desenvolvimento, App Review, validade do token longo (60 dias?) e regras do redirect: não
  confirmados nesta rodada.

---

## 4. Desenho de alto nível (agnóstico de rede)

### 4.1 Entidades
- **Conta conectada**: liga uma **Conta** da spec 003 (perfil + plataforma + @) a uma credencial
  OAuth. Guarda `provedor`, `id_externo` (`open_id` ou canal), apelido e avatar do último
  `creator_info`, escopos concedidos, `estado` (`ativa`, `expirada`, `revogada`, `erro`), quem
  conectou e quando. Conectar e desconectar só pelo **dono**, com `history.record`.
- **Credencial** (tabela separada, fora do histórico): `access_token` e `refresh_token` **cifrados**
  (AES-GCM, chave `SOCIAL_TOKEN_KEY` no `.env`, com `key_id` para rotação), com validades. O refresh
  corre em transação com `SELECT ... FOR UPDATE`, porque o TikTok **rotaciona** o refresh token e
  dois workers não podem gastá-lo ao mesmo tempo. Os tokens nunca voltam pela API nem pelo MCP.
- **Mídia publicável**: o objeto no bucket `sociman-videos`, com duração, tamanho e hash (sha256).
  Origem polimórfica: `corte` (006), `video_avatar` ou `video_afiliado` (specs 010 a 012) e
  `video_proprio` (upload do dono). Assim, o mesmo fluxo serve para os três casos.
- **Publicação** (amplia a **Postagem** da 006, uma por mídia e conta de destino): textos
  versionados, `modo` (`rascunho` ou `direto`), opções da rede **escolhidas pelo humano**
  (privacidade, toggles, divulgação comercial, `is_aigc` ou `containsSyntheticMedia`, feita para
  crianças) e `agendado_para`. `aprovado_por` e `aprovado_em` guardam o snapshot do que o humano
  confirmou, incluindo o texto de consentimento exibido.
- **Tentativa** (só INSERT): cada chamada à rede, com `publish_id`, `publicaly_available_post_id` ou
  `videoId`, status bruto, erro, duração e chave de idempotência.

### 4.2 Estados
```
rascunho ──(humano aprova e agenda)──> agendado ──(agendador)──> enviando
   ^                                       │                        │
   └──────(humano cancela ou remarca)──────┘                        ├─> rascunho_enviado  (TikTok: SEND_TO_USER_INBOX; YouTube: private)
                                                                    ├─> publicado         (PUBLISH_COMPLETE, public ou publishAt atingido)
                                                                    └─> falhou            (com motivo; nova tentativa só por humano)
```
- `postado` marcado à mão (006) continua existindo para quem posta pelo celular.
- `rascunho_enviado → publicado` pode ser confirmado pelo `status/fetch` ou marcado à mão, porque o
  dono conclui o post no app.

### 4.3 Agendador
- Nova trilha no `agendador` existente (padrão da fila de cortes: `SELECT ... FOR UPDATE SKIP
  LOCKED`). Pega publicações `agendado` com `agendado_para <= agora` e passa para `enviando` na
  mesma transação.
- **No envio**, consulta `creator_info` de novo. Se as opções aprovadas deixaram de valer
  (privacidade fora de `privacy_level_options`, duração acima do máximo, toggles desligados no app),
  a publicação vai para `falhou` com motivo, **sem trocar a escolha do humano**.
- Respeita os limites por conta: 5 rascunhos pendentes a cada 24 h, 6 init/min e cerca de 15 posts
  por dia no TikTok; 100 inserts por dia no YouTube; 100 posts por 24 h no Instagram. Mostra a cota
  restante na tela, como na cota do YouTube da 006.
- Acompanha o `status/fetch` com recuo (30 req/min por token) até chegar a um estado terminal.
- `PUBLICACAO_HABILITADA=false` no `.env` desliga a trilha inteira (chave geral).

### 4.4 Idempotência
- As redes não têm chave de idempotência. **[TikTok e YouTube: não encontrei]** Por isso: chave
  local = `publicacao_id + versão + hash da mídia`, índice único parcial "uma tentativa `enviando`
  por publicação", e o `publish_id` é gravado **antes** do upload.
- Se o init der timeout sem resposta, o estado vira `incerto` → `falhou` com o aviso "verifique no
  app antes de reenviar". **Nunca** repetir o init sozinho, para não gerar post duplicado nem gastar
  um dos 5 rascunhos pendentes.
- Retentar o chunk (PUT) dentro da mesma hora do `upload_url` é seguro. Depois disso, é uma nova
  tentativa manual.

### 4.5 Superfície e guarda
- Rotas novas só em `publicacao/`: conectar, callback, desconectar, aprovar e agendar, cancelar,
  reenviar. Todas exigem **sessão de usuário humano** (cookie), e as de aprovar e conectar exigem
  papel **dono**.
- O servidor MCP (009) **não expõe** nenhuma delas. A IA pode ler o estado das publicações, mas não
  pode aprovar, agendar nem enviar.
- A rede precisa de saída do container da API ou do worker para `open.tiktokapis.com`,
  `www.googleapis.com` e `graph.instagram.com`. O avatar do criador (CDN da TikTok, TTL de 2 h)
  passa pelo imgproxy ou é baixado para o MinIO, para não abrir `img-src` na CSP.

---

## 5. Conflito com a constitution (princípio I)

Texto atual (3.0.0): "O SociMan, sua API e suas tools MCP NÃO DEVEM ter endpoint, integração,
credencial nem job que publique conteúdo em rede social [...] Qualquer spec que proponha publicação
automática é rejeitada." Qualquer opção abaixo **redefine** o princípio, e a regra de versão da
constitution manda **MAJOR → 4.0.0**.

### Opção A: só rascunho privado ("o SociMan entrega, o humano publica")
> O SociMan PODE enviar um vídeo como **rascunho** a uma conta conectada (caixa de entrada do
> TikTok, upload `private` no YouTube) **somente por ação explícita de um usuário humano**. Ele
> NÃO DEVE publicar nem tornar público: a publicação acontece no app da rede, feita pelo dono.
> Nenhum agente, IA ou cliente MCP envia, agenda ou conecta contas. Todo envio fica no histórico.
- **Prós:** preserva o espírito do princípio (o humano posta); casa com o fluxo que funciona sem
  auditoria no TikTok; o link de produto e a música ficam no app; risco de banimento mínimo.
- **Riscos:** o "agendamento" vira lembrete (o dono ainda abre o app); no YouTube, o dono não pode
  usar `publishAt` pelo SociMan; o Instagram fica de fora (não tem rascunho).

### Opção B: publicação por ação humana explícita (proposta do team-lead)
> Publicar ou agendar em rede social só por **ação humana explícita**: um usuário humano com papel
> de dono aprova **cada** post, com a conta, os textos, a privacidade e as divulgações visíveis, e
> define a hora. O SociMan executa no horário aprovado. Nenhum agente, IA ou cliente MCP publica,
> agenda ou aprova. Tudo é auditado (autor, snapshot aprovado, resposta da rede) e reversível quando
> a rede permitir. Existe uma chave geral para desligar tudo.
- **Prós:** entrega o pedido completo (agendar e publicar); YouTube com `publishAt`; Instagram
  possível.
- **Riscos:** no TikTok não serve sem auditoria (só `SELF_ONLY` com a conta privada); "aprovou
  ontem, publicou hoje" pode sair com contexto velho (mitigado pela revalidação do `creator_info` e
  pela chave geral); risco maior para as contas se um bug publicar em massa (mitigar com limite por
  conta por dia e confirmação por post, nunca em lote).

### Opção C (recomendada): A agora, B depois, por conta e por rede
> Mesmo texto de A, mais: "Uma emenda futura PODE liberar a publicação direta por rede, desde que a
> spec prove as salvaguardas de B."
- **Prós:** entrega valor já (rascunho no TikTok sandbox), sem prometer o que a TikTok não deve
  auditar.
- **Riscos:** exige uma segunda emenda MAJOR mais adiante.

### O que mais muda
- `apps/api/tests/unit/test_constitution_guards.py`: trocar a proibição geral por **lista
  permitida**: `PUBLISH_TERMS`, `PUBLISH_ENDPOINTS` e `SOCIAL_SDKS` passam a valer em todo o `src/`
  **exceto** no módulo `publicacao/`; nenhuma rota de publicação sem dependência de sessão humana;
  nenhuma tool MCP com `publish`, `schedule` ou `connect`. Na opção A, um teste de que o cliente só
  chama `inbox/video/init` (nunca `video/init`) e só envia `privacyStatus=private`. A docstring atual
  ("as próximas specs só ampliam as listas; nunca as reduzem") também muda.
- `../CLAUDE.md` (agência): "**Quem posta é o dono (humano); nenhum agente publica**" e "Nenhum
  agente publica". Continua verdade para os agentes do OpenClaw, mas precisa da ressalva "o SociMan
  pode enviar rascunho (ou publicar) por ação do dono".
- `CLAUDE.md` do SociMan ("O SociMan **nunca publica**"), `docs/visao.md` (item 1 e FR-017 da 006) e
  a docstring de `postagem/models.py`.
- Segredos: `TIKTOK_CLIENT_KEY`/`SECRET` já estão no `.env`; somam-se `SOCIAL_TOKEN_KEY` e as
  credenciais do Google e da Meta. O `check:secrets` precisa conhecer os padrões novos.
- Rede e CSP: saída HTTPS a partir dos containers; `img-src` para o avatar do criador (ou proxy);
  rota de callback no edge (`/api/...`, sem mudança de location).

---

## 6. Riscos e perguntas para o dono

**Riscos**
- O TikTok pode recusar a auditoria para sempre (ferramenta interna e cortes de terceiros), e o
  Direct Post público fica fora de alcance.
- Enviar cortes de terceiros pela API deixa rastro do app de terceiros em cada envio, o que pode
  pesar numa denúncia de direito autoral. O princípio II mantém a responsabilidade com o dono.
- O teste de Direct Post exige deixar as contas privadas, o que afeta as contas reais.
- Os tokens de rede social são o segredo mais valioso do sistema: cifrar, nunca expor, e revogar ao
  desconectar.

**Perguntas (no máximo 5)**
1. Você aceita que, no TikTok, o SociMan chegue só ao **rascunho** (você conclui no app), já que a
   auditoria para publicar direto é improvável?
2. Qual emenda: **A** (só rascunho), **B** (publicação com aprovação por post) ou **C** (A agora,
   B depois)?
3. Só o **dono** aprova e envia, ou membros também podem (com o dono aprovando)?
4. Vale ter um **domínio próprio** (redirect HTTPS estável para TikTok e Google) ou o login das
   contas pode ser feito sempre no `sakai-desktop` (localhost)?
5. Depois do TikTok, qual é a próxima rede: **YouTube** (tem agendamento nativo, mas exige projeto
   Google e auditoria para sair do privado) ou **Instagram**?

## Fontes (acessadas em 2026-09-29)
- TikTok, Content Posting API, Get Started (Direct Post): https://developers.tiktok.com/doc/content-posting-api-get-started
- TikTok, Get Started (Upload): https://developers.tiktok.com/doc/content-posting-api-get-started-upload-content
- TikTok, Direct Post (referência): https://developers.tiktok.com/doc/content-posting-api-reference-direct-post
- TikTok, Upload (caixa de entrada): https://developers.tiktok.com/doc/content-posting-api-reference-upload-video
- TikTok, Media Transfer Guide: https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide
- TikTok, Query Creator Info: https://developers.tiktok.com/doc/content-posting-api-reference-query-creator-info
- TikTok, Get Post Status: https://developers.tiktok.com/doc/content-posting-api-reference-get-video-status
- TikTok, Content Sharing Guidelines: https://developers.tiktok.com/doc/content-sharing-guidelines
- TikTok, App Review Guidelines: https://developers.tiktok.com/doc/app-review-guidelines
- TikTok, Sandbox: https://developers.tiktok.com/doc/add-a-sandbox
- TikTok, Login Kit Web: https://developers.tiktok.com/doc/login-kit-web
- TikTok, Login Kit Desktop: https://developers.tiktok.com/doc/login-kit-desktop
- TikTok, Token Management: https://developers.tiktok.com/doc/oauth-user-access-token-management
- Terceiros (só para confirmar a falta de agendamento): https://postproxy.dev/how-to/schedule-tiktok-posts/
- YouTube, videos.insert: https://developers.google.com/youtube/v3/docs/videos/insert
- YouTube, recurso Video: https://developers.google.com/youtube/v3/docs/videos
- YouTube, custo de cota: https://developers.google.com/youtube/v3/determine_quota_cost
- YouTube, o que é Short: https://support.google.com/youtube/answer/15424877
- Google, OAuth para apps web: https://developers.google.com/identity/protocols/oauth2/web-server
- Google Cloud, público do app (Testing, 7 dias): https://support.google.com/cloud/answer/15549945
- Google, verificação de escopo sensível: https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification
- Instagram, Content Publishing: https://developers.facebook.com/docs/instagram-platform/content-publishing/
- Instagram, API com Instagram Login: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login
