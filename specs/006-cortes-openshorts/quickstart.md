# Quickstart de validação: 006-cortes-openshorts

O contrato está em [contracts/http-api.md](contracts/http-api.md) e o modelo de dados em
[data-model.md](data-model.md). Faça um passo por vez, conferindo cada saída antes do próximo.

## Pré-requisitos
- Spec 004 validada: MinIO no HD, sentinela e o worker no ar.
- Stack em modo dev (`docker compose up -d --build`), com `api`, `worker`, **`agendador`**,
  `minio` e `imgproxy`.
- Migration `0006_cortes_openshorts` aplicada (o `start.sh` faz `alembic upgrade head`).
- Perfis "A Taverna Nerd" (com conta YouTube) e "Queridinhos" (com conta TikTok
  `@meusqueridinhos10`), com kit salvo.
- OpenShorts do host no ar: `curl -s http://localhost:8000/health` → `{"status":"ok"}`.

## 0. Chaves e conectividade (R6, R15)
Nunca imprima as chaves.
```bash
# 1) YouTube: copia a linha da chave já existente, sem mostrar o valor
grep '^YOUTUBE_API_KEY=' ~/.config/openclaw/youtube.env >> .env
grep -c '^YOUTUBE_API_KEY=' .env                    # 1
# 2) Anthropic: o dono cola a chave com o editor (nano .env), na linha ANTHROPIC_API_KEY=...
grep -c '^ANTHROPIC_API_KEY=' .env                  # 1
git check-ignore .env                               # .env (fora do git)
npm run check:secrets                               # ok (padrões AIza… e sk-ant-… nos rastreados)
docker compose up -d api agendador
docker compose exec agendador sh -c 'test -n "$YOUTUBE_API_KEY" && echo tem-chave'   # tem-chave
docker compose exec agendador python -c "import httpx;print(httpx.get('http://host.docker.internal:8000/health').text)"
```
- A última linha precisa mostrar `{"status":"ok"}`. Se der timeout, o ufw está bloqueando o
  bridge. Quem decide é o dono: `sudo ufw allow from 172.16.0.0/12 to any port 8000 proto tcp`.
- `docker compose logs agendador --tail 5` mostra "agendador pronto (lock ok): trilhas sync,
  openshorts, importacao, lembretes".
- `GET /api/integracoes` (logado) → `youtube: ok`, `openshorts: ok`, `claude: ok`. O corpo não
  tem nenhuma chave.

## 1. Canais-fonte (US1, princípio II)
Em `/app/fontes`:
- "Adicionar canal": cole `https://www.youtube.com/@theitnerd`. A prévia mostra nome, avatar,
  inscritos e total de vídeos, com "custo: 1 unidade". Ligue o canal a "A Taverna Nerd" e salve.
- O avatar vem de `/img/...` (DevTools → Network: nenhuma requisição a `ytimg`/`ggpht` saindo do
  navegador, e nenhum erro de CSP no console).
- Cole o mesmo canal de novo: aparece "Este canal já está cadastrado", com o link para o
  existente (US1-2).
- Como **dono**, mude o direito para "Próprio", com a nota "canal do dono". O histórico mostra a
  versão com autor e antes e depois.
- Como **membro**: o campo de direito aparece só para leitura, e
  `PUT /api/canais/<id>/direito` responde 403.
- Cadastre um segundo canal de terceiro e deixe como "Sem acordo": o selo de aviso aparece na
  lista (US1-4).

## 2. Sincronização, cota e descoberta (US2, SC-001)
- Logo depois do cadastro, o canal mostra "Sincronizando (N de M)". Anote o horário.
- `docker compose logs agendador | grep sync` mostra as páginas lidas e as unidades gastas.
- Em menos de 2 min (canal de até 500 vídeos), abra `/app/descobrir` com o perfil "A Taverna
  Nerd":
  - os vídeos aparecem com miniatura, título, canal, duração, publicação, views, views/h,
    pontuação e o **motivo em uma linha** ("… views/h … (N× a média do canal)", "Novo: publicado
    há …", "Duração boa para cortes (…)");
  - Shorts, lives e vídeos com mais de 3 h aparecem só com "mostrar não recomendados" e o aviso.
- Filtros: "até 20 min" e "não cortados", mais uma busca por texto. A lista responde em menos de
  1 s a cada filtro.
- `GET /api/integracoes` → `cotaYoutube.usadas` bate com a soma dos logs (cerca de 2 unidades a
  cada 50 vídeos + 1 do cadastro).
- **Cota (teste da API):** no pytest, `YT_QUOTA_DAILY=40` pausa a sync em 95% (`pausado_cota`),
  com uma notificação `cota_youtube` em 80%.
- **Chave inválida (teste da API):** um mock `400 keyInvalid` → canal `erro`, com a mensagem sem
  a chave. Sem a chave: 503 `youtube_unconfigured` no cadastro. O avulso por link continua
  funcionando.
- **Incremental:** `POST /api/canais/<id>/sincronizar` na mesma hora custa cerca de 2 unidades e
  não duplica vídeos.

## 3. Padrões e envio (US3, princípio II)
- Perfil "A Taverna Nerd" → aba **Padrões de corte**: 15–60 s, quantidade vazia, layout
  automático, legenda do kit e marca automática desligada. Salve (vira a v1).
- Em Descobrir, selecione **3 vídeos**: a barra "3 selecionados" aparece, e eles ficam em
  `/app/envios` → Selecionados. Cronometre do primeiro clique até "Enviar" (SC-002: < 1 min para
  5).
- Selecione de novo um vídeo já selecionado: o aviso "Já está nos selecionados" aparece, e só
  cria outro com confirmação.
- "Enviar para corte" num vídeo do canal "Sem acordo": o diálogo mostra "O direito autoral deste
  vídeo é de sua responsabilidade" e só envia com a confirmação. Pela API, sem `confirmarAviso`,
  responde 409 `aviso_direito` e nada é enviado.
- `GET /api/envios/<id>/versions`: a versão do envio tem autor, data, `sourceUrl`,
  `direito_no_envio: "sem_acordo"` e `aviso_confirmado: true`.
- Um vídeo "Próprio" é enviado sem aviso.
- Status ao vivo: "Na fila do OpenShorts (Nº)" → "Processando: N clipes prontos" →
  "Importando" → "Pronto".

## 4. OpenShorts fora e reinícios (FR-010, US3-5)
Com um envio `processando`:
```bash
docker compose restart agendador                              # o polling continua depois do reinício
cd ../openshorts && docker compose stop backend               # OpenShorts fora
```
- Um envio novo fica "Aguardando o OpenShorts", e o log mostra o backoff de 30 s → 5 min.
- `docker compose start backend`: em até 5 min, o envio sai sozinho para `processando` (o
  OpenShorts re-enfileira os próprios jobs pelos manifestos).
- **Teste automatizado equivalente:** `tests/integration/test_agendador_openshorts.py`, com o
  OpenShorts falso cobrindo queda, retorno, 429, `needs_confirmation`, 404 depois da retenção e
  `failed` com "No clips" → `sem_clipes`.

## 5. Clipes → cortes e notificação (US4, SC-003, SC-004)
- Quando o OpenShorts termina, em **menos de 1 min** o sino mostra "Envio pronto: <título> (N
  clipes)". Com a notificação do navegador ativada no sino, ela aparece também fora da aba.
- `/app/envios/<id>`: os **N clipes** (o mesmo `clips_total` de `GET /api/status/<job>` no
  OpenShorts) estão lado a lado, com player, trecho, gancho sugerido e legenda **no estilo do
  kit** (fonte, cores e posição da aba Marca).
- Arquive um clipe (some da lista; "mostrar arquivados" traz de volta).
- Edite o gancho de outro e "Aplicar marca" em dois: eles vão para `na_fila` e depois `pronto`
  (worker da 004), com gancho, marca d'água e card.
- Aba Cortes do perfil: os clipes aparecem com origem "OpenShorts", canal e trecho.
- Ligue "Aplicar marca automaticamente" nos padrões e faça um novo envio: os clipes chegam já em
  `na_fila` (US4-3).
- Arquivos no HD: `ls /media/sakai/BACKUP/tiktok/sociman/minio/sociman-videos/perfis/<id>/cortes/`
  mostra os `original.mp4` e depois os `marcado.mp4`.

## 6. Textos, agenda e "Hora de postar" (US5, SC-005, SC-006)
- Num corte pronto → seção Postagem → aba "TikTok @meusqueridinhos10" → "Sugerir textos":
  - em menos de 15 s, chegam título (≤ 100), descrição (≤ 2.000) e 3 a 8 hashtags em pt-BR, no
    tom do perfil (bordões e séries do kit aparecem quando fazem sentido);
  - "Outra versão" traz um ângulo diferente;
  - `GET /api/cortes/<id>/sugestoes` lista as duas, com o modelo `claude-sonnet-5-5`.
- Edite o título, escolha amanhã às 19:00 e salve. O histórico da postagem mostra a versão.
- `/app/calendario` (semana): o corte aparece amanhã às 19:00, com a cor do perfil e o ícone do
  TikTok. Arraste para quinta às 20:00: a remarcação é salva (e desfeita se der 409). No celular,
  o toque abre "Remarcar".
- **SC-006:** com 7 cortes prontos na coluna "Prontos sem data", agende a semana arrastando. O
  tempo precisa ficar abaixo de 5 min.
- **Hora de postar:** agende um corte para daqui a 2 min. Na hora (± 30 s), o sino e o navegador
  mostram "Hora de postar: <título> no TikTok", e o clique abre o corte, com "Copiar título /
  descrição / hashtags" e "Baixar vídeo". Marque "Postado", com o link: o estado muda, e nenhuma
  requisição sai para o TikTok (Network e logs do agendador).
- **Falha do Claude:** com `ANTHROPIC_API_KEY` vazia e `docker compose up -d api`, o botão
  aparece desabilitado com a explicação, e os campos seguem editáveis à mão.

## 7. Opcional: e2e com o OpenShorts real
Faça só com o dono por perto (leva de 10 a 20 min em CPU). Use um vídeo CC-BY de cerca de 5 min
(o mesmo do teste da agência em 2026-09-24), por link avulso, com padrões 15–45 s e 3 clipes.
Confira as seções 3 e 5 de ponta a ponta. O e2e automático (`e2e/cortes-openshorts.spec.ts`) usa
o **OpenShorts falso** da stack e2e e não depende do real.

## 8. Guardas e verificação final
```bash
cd apps/api && uv run pytest && uv run ruff check .
npm run check:web          # contrato regenerado + check:secrets com os padrões novos
npm run test:e2e
```
- `tests/unit/test_constitution_guards.py`:
  - nenhuma rota tem `youtube`, `tiktok`, `publish` ou `share`;
  - os clientes do OpenShorts e do YouTube só fazem pedidos da lista fechada;
  - nenhum arquivo cita `/api/social`, `upload-post` nem `open.tiktokapis.com`;
  - `postado` só é atribuído por `postagem.service.marcar_postado`.
- `tests/integration/test_direito.py`: 403 do membro, 409 `aviso_direito`, histórico do envio e
  direito que não bloqueia.
