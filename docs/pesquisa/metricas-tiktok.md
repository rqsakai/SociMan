# Pesquisa: métricas de contas e posts do TikTok pela API

> Pesquisa para uma futura spec de coleta de métricas (base para machine learning). Só leitura:
> nenhuma API foi chamada e nenhuma credencial foi lida. Todas as fontes foram acessadas em
> **2026-09-30**. As páginas da TikTok API for Business são renderizadas por JavaScript e foram
> lidas num navegador. Legenda: **[confirmado]** está escrito na documentação oficial citada;
> **[não confirmado]** é inferência, fonte de terceiros ou ponto que a documentação não cobre, e
> precisa de teste.

## Resumo

1. **Etapa 1 cabe no app atual (Display API).** Os escopos `user.info.stats` e `video.list` dão
   seguidores, curtidas totais e número de vídeos da conta, e views, curtidas, comentários e
   compartilhamentos de cada vídeo **público**. O limite é de 600 req/min por endpoint. [confirmado]
   Não está documentado se o sandbox libera esses dois escopos, nem com que atraso os contadores
   são atualizados. [não confirmado] **Há 3 limitações:** o `video.list` só lista posts públicos, os
   contadores são sempre acumulados e não há alcance, tempo assistido nem audiência.
2. **Adicionar escopos exige reconectar as contas.** O token só carrega os escopos que o usuário
   aprovou, e a resposta do token traz `scope`. [confirmado] Um novo escopo precisa de nova
   autorização. [não confirmado, mas é o padrão OAuth, e a doc de Business diz o mesmo]
3. **As métricas ricas estão na TikTok API for Business (Accounts API).** É outro portal, com outro
   app e outro OAuth (`/tt_user/oauth2/token/`). Por vídeo: `reach`, `total_time_watched`,
   `average_time_watched`, `full_video_watched_rate`, retenção por segundo, fontes de tráfego,
   país, cidade e gênero dos espectadores, novos e recorrentes, `new_followers` e `favorites`. Por
   conta: série diária de views, perfil, curtidas e seguidores ganhos e perdidos, além de
   demografia. [confirmado] **Funciona com conta Pessoal ou Business** (algumas métricas são só de
   Business). Desde **20/03/2026**, porém, pede o *Accounts API Access Application Form* e passa
   por revisão. O dado chega com **24 a 48 h de atraso**, a conta tem histórico de só **60 dias**, e
   o post para de ser atualizado **365 dias** depois de publicado. [confirmado]
4. **A Research API não serve.** Ela é só para pesquisa acadêmica ou sem fins lucrativos, e em
   regiões específicas. [confirmado]
5. **TikTok Shop (afiliados):** existe a Affiliate Creator API no Partner Center, com pedidos de
   afiliado e links. Ela exige cadastro de desenvolvedor e revisão de app. Não confirmei a
   disponibilidade no Brasil. [não confirmado]
6. **Casar o vídeo com o destino:** o `status/fetch` do `publish_id` devolve
   `publicaly_available_post_id` **também no rascunho (inbox)**, mas só quando o dono publica em
   público e a moderação aprova. [confirmado] Como o dono pode finalizar horas ou dias depois, é
   preciso de um plano B: listar os vídeos e casar pelo horário e pela duração.

## 1. Display API (developers.tiktok.com, app atual)

### 1.1 Escopos e campos

| Escopo | Endpoint | Campos |
|---|---|---|
| `user.info.basic` (já temos) | `GET /v2/user/info/` | `open_id`, `union_id`, `avatar_url`, `avatar_url_100`, `avatar_large_url`, `display_name` |
| `user.info.profile` (já temos) | `GET /v2/user/info/` | `bio_description`, `profile_deep_link`, `is_verified`, `username` |
| **`user.info.stats`** (novo) | `GET /v2/user/info/` | `follower_count`, `following_count`, `likes_count`, `video_count` (este conta só os vídeos públicos) |
| **`video.list`** (novo) | `POST /v2/video/list/` e `POST /v2/video/query/` | objeto de vídeo (abaixo) |

[confirmado: Get User Info, Scopes Reference]

**Objeto de vídeo** (pedido em `?fields=`): `id` (o "item_id"), `create_time` (época UTC em s),
`cover_image_url` (**expira em 6 h**), `share_url`, `video_description` (máx. 150 caracteres),
`title`, `duration` (s, inteiro), `height`, `width`, `embed_html`, `embed_link`, `like_count`,
`comment_count`, `share_count`, `view_count` e `is_aigc`. [confirmado: Video Object]

### 1.2 Paginação e filtros

- `video/list`: corpo `{cursor, max_count}`, com `max_count` padrão de 10 e **máximo de 20**. O
  `cursor` é uma época UTC em **ms**, e você pode passar um valor seu para listar os vídeos
  anteriores a ele. A resposta traz `videos`, `cursor` e `has_more`. A lista vem **só com posts
  públicos**, do mais novo para o mais antigo por `create_time`. [confirmado]
- `video/query`: `filters.video_ids` com **até 20 IDs** por chamada. A própria doc sugere usar
  esse endpoint para renovar os campos dos vídeos já conhecidos. [confirmado]
- O guia sugere um job em segundo plano "a cada ~12 h" para atualizar os dados. É só uma sugestão
  de exibição, não um limite. [confirmado]

### 1.3 Limites

- `/v2/user/info/`, `/v2/video/list/` e `/v2/video/query/`: **600 req/min cada**, em janela
  deslizante de 1 min. Ao estourar, a resposta é HTTP 429 `rate_limit_exceeded`. [confirmado] A doc
  não diz se o limite vale por app ou por token. [não confirmado]
- Token de acesso: 24 h. Refresh: 365 dias, e o refresh pode devolver um token novo. [confirmado]

### 1.4 Sandbox, auditoria e reautorização

- O sandbox aceita até 10 usuários-alvo e "não oferece" a Content Posting API para vídeos públicos
  nem a Data Portability. **Não menciona a Display API.** [confirmado: Add a Sandbox] Conclusão
  provável: `user.info.stats` e `video.list` funcionam no sandbox com as 2 contas-alvo. [não
  confirmado: testar no portal ligando os escopos no sandbox]
- Não achei na documentação se o sandbox devolve dados reais. Como o login e o rascunho usaram as
  contas reais, o esperado é que sim. [não confirmado]
- **Reconectar:** o `scope` volta na resposta do token. [confirmado] Cada conta precisa passar de
  novo pelo login com os escopos novos. O SociMan já tem esse fluxo (spec 015, "Reconectar"). [não
  confirmado quanto ao comportamento exato da TikTok ao acrescentar escopos]
- Também não achei a latência do `view_count` (tempo real ou atrasado). [não confirmado] Vale medir
  isso na etapa 1 antes de decidir se a coleta de hora em hora compensa.

## 2. TikTok API for Business: Accounts API (Organic API)

### 2.1 Requisitos

- Conta TikTok For Business, cadastro de desenvolvedor e um **app de desenvolvedor no portal
  business-api.tiktok.com** com a permissão "TikTok Accounts". É um app separado do app do
  developers.tiktok.com. [confirmado: Get started, Authorization]
- **Desde 20/03/2026**, é preciso preencher o *Accounts API Access Application Form* antes de
  submeter o app ou de pedir aumento de escopo com "TikTok Accounts", e o pedido passa por
  revisão. [confirmado] Não achei o prazo nem os critérios da revisão. [não confirmado]
- Serve para contas **Business e Pessoais**. Alguns campos são só de Business (`unique_video_views`,
  `daily_new_followers`, `daily_lost_followers`, `engaged_audience`, `profile_views` por post) e
  outros só de **Business verificada** (cliques em link, telefone, e-mail). [confirmado: Accounts
  Overview e campos]
- O dono da conta precisa ter publicado ao menos 1 vídeo e ter tocado em **"Ativar" na aba Análises**
  do app. A API só devolve o que aparece no TikTok Analytics. [confirmado]
- **Usos permitidos:** gerir a presença orgânica das próprias contas, incluindo "analisar insights
  do perfil e dos posts". **Usos proibidos:** agregar dados de criadores para montar um programa de
  afiliados próprio, e baixar vídeos ou migrar conteúdo. [confirmado: Accounts Overview] O uso do
  SociMan (as contas do dono) se encaixa no permitido. [não confirmado: depende da revisão]
- **Redirect do OAuth:** precisa ser absoluto, `https://`, **sem porta**, terminar em `/` e não ter
  query nem `#`. [confirmado: Authorization] O redirect atual do SociMan
  (`https://192.168.86.47:8543/...`) **não passa**, porque tem porta. Seria preciso publicar o edge
  na 443 ou usar um domínio. Não confirmei se o portal aceita IP privado. [não confirmado]
- `auth_code` vale 10 min. O token da conta vale 1 dia e é renovado por
  `/tt_user/oauth2/refresh_token/`. [confirmado: FAQs]

### 2.2 Conta: `GET /open_api/v1.3/business/get/`

- Parâmetros: `business_id` (o `open_id` do token), `start_date` e `end_date` (UTC, padrão dos
  últimos 7 dias) e `fields`. **O histórico máximo é de 60 dias.** [confirmado]
- Valores de hoje (sem atraso): `followers_count` (`user.info.stats`), `following_count`,
  `total_likes`, `videos_count` e perfil. [confirmado]
- Série diária (`metrics[]`, escopo `user.insights`, atraso de **24 a 48 h**): `video_views`,
  `unique_video_views`, `profile_views`, `likes`, `comments`, `shares`, `followers_count` do dia,
  `daily_total_followers`, `daily_new_followers`, `daily_lost_followers`, `engaged_audience` e
  `audience_activity` (seguidores ativos por hora, a partir de 100 seguidores), mais os cliques
  (Business verificada). [confirmado]
- Demografia dos **seguidores** (a partir de 100 seguidores): `audience_ages` (18-24 … 55+),
  `audience_genders`, `audience_countries` e `audience_cities`. [confirmado]
- `video_views` soma orgânico e pago. As `likes` diárias não descontam as curtidas retiradas.
  [confirmado]

### 2.3 Posts: `GET /open_api/v1.3/business/video/list/`

- Parâmetros: `business_id`, `fields` (inclua sempre `item_id`), `filters.video_ids`, `cursor`
  (época em ms) e `max_count` (máx. 20). A resposta cobre **todos os posts públicos** e os "só em
  anúncios". [confirmado]
- As métricas são **acumuladas desde a publicação**, e não há série diária por post. O limite de
  60 dias não vale aqui. **O post para de ser atualizado 365 dias depois de publicado.** [confirmado]
- Campos com escopo `video.list`: `item_id`, `media_type`, `is_ad`, `thumbnail_url`, `share_url`,
  `embed_url`, `caption`, `create_time`, `video_duration` (float), `likes`, `comments`, `shares`,
  `favorites`, `reach` e `video_views`. [confirmado]
- Campos com escopo `video.insights`: `total_time_watched`, `average_time_watched`,
  `full_video_watched_rate`, `new_followers`, `profile_views` (Business), `video_view_retention`
  (`second` e `percentage`), `impression_sources` (For You, Follow, Sound, Personal Profile, Search,
  Direct Message, Others), `audience_genders`, `audience_countries` (top 10), `audience_cities` (top
  10), `audience_types` (NEW_VIEWER, RETURN_VIEWER, FOLLOWER_PERCENT, NON_FOLLOWER_PERCENT),
  `engagement_likes` (curtidas por segundo) e os cliques (Business verificada). [confirmado]
- **Latência:** `item_id`, `create_time`, `caption` e as URLs chegam na hora. Todas as métricas
  chegam com **24 a 48 h** de atraso. [confirmado: Accounts Insights data latency]
- `reach`, a taxa de conclusão, o tempo assistido, as fontes e os países somem se o vídeo ficar
  **mais de 7 dias sem atividade**. [confirmado] Por isso, vale gravar esses valores antes que
  sumam.
- Um post filtrado por violação (por exemplo, direito autoral de música) **não aparece** na
  resposta. [confirmado] Isso importa para os cortes.

### 2.4 Limites

- **40 req/min por conta autorizada e por endpoint**, mais um limite global do app para todos os
  endpoints da Accounts API: 600 req/min (Basic) ou 1.000 (Advanced ou superior). [confirmado:
  Accounts API rate limits]

## 3. TikTok Shop: afiliados (só o essencial)

- Há 3 famílias de API no **TikTok Shop Partner Center**: Affiliate Seller, Affiliate Partner
  (agências) e **Affiliate Creator**. Elas cobrem colaborações, busca de produtos e criadores,
  geração de links promocionais e busca de **pedidos de afiliado** para medir conversão.
  [confirmado: blog oficial da TikTok for Developers]
- Requisitos: cadastro como desenvolvedor de app de afiliado no Partner Center e revisão de app.
  [confirmado] Não confirmei se existe para o Brasil, nem se há métricas de **cliques** por vídeo.
  [não confirmado] Só faz sentido depois que os perfis estiverem vendendo como afiliados.

## 4. Research API

- Elegível só para instituições acadêmicas (EUA, EEE, Reino Unido, Canadá, Suíça), pesquisa sem
  fins lucrativos na UE e, no Brasil, acadêmicos ou ONGs que estudam segurança online de jovens. O
  pesquisador precisa ser "independente de interesses comerciais". [confirmado] **Não serve para o
  SociMan.**

## 5. Casar o vídeo da API com o destino do SociMan

1. **Caminho principal [confirmado]:** o `POST /v2/post/publish/status/fetch/` com o `publish_id`
   devolve `publicaly_available_post_id` (lista, com a grafia da TikTok). No **upload para o inbox**,
   o ID "só é devolvido se o post for publicado para o público e aprovado pela moderação". A
   moderação costuma levar menos de 1 min, mas pode levar horas. Assumo que esse ID é o mesmo `id`
   do `video.list` e o `item_id` do Business. [não confirmado, mas muito provável]
2. **Problema:** a spec 015 encerra o `status/fetch` 2 h depois do upload (fase `incerta`), e o
   dono pode finalizar o rascunho dias depois. A doc não diz por quanto tempo o `status/fetch` fica
   consultável. [não confirmado] **Proposta:** enquanto o destino estiver "entregue no inbox" e sem
   `post_id`, repetir o `status/fetch` em intervalos cada vez maiores (1 h, 6 h, 24 h) por até 7 a
   14 dias.
3. **Plano B, casar pela lista:** `video.list` da conta com `cursor` a partir da entrega e
   candidatos com `create_time ≥ entregue_em` e `|duration − duração do corte| ≤ 1 s`. Desempate
   pela legenda (o dono cola a legenda do kit com "Copiar textos") e pela capa. Com 1 candidato,
   casa sozinho. Com 2 ou mais, fica "a confirmar", e o dono escolhe na tela. [inferência]
4. **Plano C, manual:** o dono cola a URL do post (`share_url` traz `/video/<id>`).
5. O webhook de Content Posting (evento "post publicamente disponível") existe, mas não confirmei
   o formato do payload. Além disso, ele exigiria uma URL pública. [não confirmado] A casa não
   expõe o SociMan, então o polling é o caminho.
6. **Post privado ou "Só eu"** não aparece no `video.list` nem devolve `post_id`. Esses posts ficam
   sem métricas. [confirmado para o `video.list`]

## 6. Desenho recomendado da coleta para ML

### 6.1 O que guardar

- **`metricas_video_snapshot`** (série temporal, só inserção): `video_id` (TikTok), `destino_id`
  (SociMan), `conta_id`, `coletado_em`, `fonte` (`display`|`business`), `idade_min` (coletado_em −
  create_time), `view_count`, `like_count`, `comment_count`, `share_count` e, quando vier do
  Business, `favorites`, `reach`, `total_time_watched`, `average_time_watched`,
  `full_video_watched_rate`, `new_followers` e um `jsonb` com os campos em lista (retenção, fontes,
  audiência, `engagement_likes`). Com fonte Business, guarde também a **data de referência** do
  dado (T−1/T−2), porque ele chega atrasado.
- **`metricas_conta_snapshot`**: `follower_count`, `following_count`, `likes_count`,
  `video_count` e, com Business, a série diária (`metrics[]`) e a demografia.
- **Features do SociMan** (já estão no banco e entram por join, sem copiar): perfil e nicho,
  canal-fonte e seu status, gancho (texto e estilo), score da recomendação do corte, duração,
  layout, legenda e hashtags do kit, horário e dia da semana da publicação (em
  `America/Sao_Paulo`), intervalo desde o post anterior da conta, seguidores da conta no momento da
  publicação e se o post foi feito pelo rascunho ou pelo Direct Post.
- **Rótulos para ML** (calculados, não coletados): views em 1 h, 24 h, 7 d e 30 d (interpolação
  entre snapshots), taxa de engajamento (curtidas + comentários + compartilhamentos)/views e, com
  Business, taxa de conclusão e retenção.

### 6.2 Frequência por idade do post

| Idade do post | Display API (contadores) | Business (insights, T+24–48 h) |
|---|---|---|
| 0–48 h | a cada 1 h | — (não há dado ainda) |
| 2–30 dias | 1× por dia | 1× por dia |
| 30–90 dias | 1× por semana | 1× por semana |
| 90–365 dias | 1× por mês | 1× por mês (para de atualizar em 365 d) |
| conta | 1× por dia | 1× por dia (`business/get` dos últimos 7 dias, que sobrepõe e corrige atrasos) |

- Agrupar por conta: um `video/query` com até 20 IDs por chamada, independente de quantos vídeos
  a conta tenha naquela faixa de idade.
- **Orçamento:** com 2 contas e cerca de 2 posts por dia cada, há no máximo ~8 vídeos nas primeiras
  48 h. Isso dá 1 chamada por conta por hora, cerca de 50 por dia para a faixa horária, mais
  algumas dezenas diárias. **É menos de 0,1% do limite** (600/min). O limite do Business (40/min por
  conta) também sobra. O gargalo não é a TikTok, e sim o volume de dados para ML: 2 contas geram
  poucas centenas de posts por ano.
- A coleta roda no agendador que o SociMan já tem (spec 015), com as mesmas regras de token e
  refresh. Um 429 recua e tenta de novo. Um `scope_not_authorized` marca a conta para reconectar.

### 6.3 Privacidade e termos

- Os dados são das **próprias contas do dono** (métricas agregadas, sem dados de espectadores
  individuais). A demografia vem da TikTok em percentuais agregados. [confirmado]
- Termos de desenvolvedor: o dado obtido serve só para "desenvolver, manter e dar suporte" ao app.
  É proibido coletar dados pessoais de usuários para fins não autorizados ou montar bases sem
  autorização. [confirmado: Developer Terms, II.1 e III.3(h)] Quando o acesso termina, o dado
  obtido deve ser apagado. [não confirmado: aparece em resumo de busca, e não achei no texto lido]
- **Não achei na documentação um prazo de retenção**, nem uma regra sobre treinar modelos com as
  métricas das próprias contas. [não confirmado] A leitura conservadora tem 4 pontos:
  1. usar o dado só para as decisões internas do SociMan;
  2. não repassar a terceiros;
  3. ao receber `authorization.removed` ou ao desconectar uma conta, parar a coleta;
  4. ter um jeito de expurgar as métricas daquela conta.

  O ponto 4 conflita com o "sem DELETE" da constitution e precisa de uma decisão do dono.
- `cover_image_url` e `thumbnail_url` expiram (6 h). Não guarde a URL como se fosse permanente. Se
  quiser a capa para ML, use a capa do próprio corte, que o SociMan já tem no MinIO.

## 7. Recomendação por etapas

**Etapa 1 (viável agora, app atual no sandbox):**
1. No portal, ligar `user.info.stats` e `video.list` no sandbox e reconectar as 2 contas.
2. Spec nova: `post_id` pelo `status/fetch` estendido (§5.2), casamento pela lista (§5.3) e confirmação
   pelo dono; snapshots da conta 1× por dia e dos vídeos na cadência da §6.2.
3. Medir empiricamente a latência do `view_count` (2 snapshots seguidos com 1 h de intervalo num
   post novo). Se não mudar de hora em hora, reduzir a cadência.
4. Pré-requisito: o dono publicar os rascunhos **em público** (SC-005 da 015 ainda "a confirmar").

**Etapa 2 (exige aprovação):** criar um app no business-api.tiktok.com, preencher o *Accounts API
Access Application Form*, resolver o redirect sem porta (edge na 443 ou domínio) e conectar as
contas por um segundo OAuth (`user.insights` e `video.insights`). Isso acrescenta retenção, taxa de
conclusão, fontes de tráfego e audiência, que são as features que mais explicam o desempenho.
Converter as contas para **Business** libera o resto (`reach` único, seguidores ganhos e perdidos
por dia).

**Etapa 3 (opcional):** Affiliate Creator API, quando houver vendas de afiliado.

## 8. Perguntas ao dono

1. As 2 contas são **Pessoais** ou **Business**? Você aceita convertê-las para Business, o que
   libera métricas extras na etapa 2?
2. Posso ligar `user.info.stats` e `video.list` no sandbox, e você reconecta as 2 contas? Isso abre
   o consentimento da TikTok de novo.
3. Na etapa 2, para o redirect sem porta: prefere abrir a 443 do edge na LAN ou usar um domínio?
   Quer mesmo encarar a revisão do formulário da Accounts API agora?
4. Retenção: as métricas ficam para sempre? Se uma conta for desconectada, as métricas dela são
   apagadas (exceção ao "sem DELETE") ou só anonimizadas?

## Fontes (acessadas em 2026-09-30)

- Display API, Overview: https://developers.tiktok.com/doc/display-api-overview
- Display API, Get Started: https://developers.tiktok.com/doc/display-api-get-started
- Get User Info: https://developers.tiktok.com/doc/tiktok-api-v2-get-user-info
- List Videos: https://developers.tiktok.com/doc/tiktok-api-v2-video-list
- Query Videos: https://developers.tiktok.com/doc/tiktok-api-v2-video-query
- Video Object: https://developers.tiktok.com/doc/tiktok-api-v2-video-object
- Rate Limits (v2): https://developers.tiktok.com/doc/tiktok-api-v2-rate-limit
- Scopes Reference: https://developers.tiktok.com/doc/tiktok-api-scopes
- Token management: https://developers.tiktok.com/doc/oauth-user-access-token-management
- Sandbox: https://developers.tiktok.com/doc/add-a-sandbox
- Content Posting, Get Post Status: https://developers.tiktok.com/doc/content-posting-api-reference-get-video-status
- Content Posting, Upload: https://developers.tiktok.com/doc/content-posting-api-reference-upload-video
- Webhooks, Events: https://developers.tiktok.com/doc/webhooks-events
- Research API: https://developers.tiktok.com/products/research-api/
- Developer Guidelines: https://developers.tiktok.com/doc/our-guidelines-developer-guidelines
- Developer Terms of Service: https://www.tiktok.com/legal/page/global/tik-tok-developer-terms-of-service/en
- Business, Accounts Overview: https://business-api.tiktok.com/portal/docs/accounts-api-overview/v1.3
- Business, Get started: https://business-api.tiktok.com/portal/docs/get-started/v1.3
- Business, Authorization: https://business-api.tiktok.com/portal/docs/accounts-api-authorization/v1.3
- Business, FAQs: https://business-api.tiktok.com/portal/docs/accounts-api-authorization-faqs/v1.3
- Business, Rate limits: https://business-api.tiktok.com/portal/docs/accounts-api-rate-limits/v1.3
- Business, Data latency: https://business-api.tiktok.com/portal/docs/accounts-insights-data-latency/v1.3
- Business, Get profile data: https://business-api.tiktok.com/portal/docs/get-profile-data-of-a-tiktok-account/v1.3
- Business, Get post data: https://business-api.tiktok.com/portal/docs/get-post-data-of-a-tiktok-account/v1.3
- TikTok Shop Affiliate APIs (blog oficial): https://developers.tiktok.com/blog/2024-tiktok-shop-affiliate-apis-launch-developer-opportunity
