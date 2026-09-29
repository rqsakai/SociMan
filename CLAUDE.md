# CLAUDE.md: SociMan

Gestão de contas de mídia social da agência: contas, kit de marca, avatares e poses, cenas, scripts, canais-fonte, vídeos e padrões de corte. A IA acessa tudo por MCP. Docs em pt-BR.

## Como trabalhar (o dono)
- **Um passo por vez:** mostre o comando, explique em uma linha, rode, leia a saída e só então siga.
- **Spec Driven Development com o GitHub Spec Kit:** `/speckit-constitution`, depois `/speckit-specify`, `/speckit-clarify`, `/speckit-plan`, `/speckit-tasks` e `/speckit-implement`. **Nada de código de feature sem spec aprovada.** As specs ficam em `specs/NNN-nome/`.
- A visão e o backlog de specs estão em `docs/visao.md`. A constitution está em `.specify/memory/constitution.md`.
- Commit e push só quando o dono pedir. Mensagens em pt-BR, no imperativo.

## Stack
```
apps/web            SPA React 19 + Vite + Tailwind 4 (copiado do volans; auth UI pronta)
packages/contract   Zod + client tipado (herdado do volans; será gerado do OpenAPI do FastAPI)
apps/api            FastAPI (Python 3.12, uv), SQLAlchemy 2 + Alembic, PostgreSQL
redis / mailpit     sessões e limites de tentativa (Redis, AOF) / e-mail de dev (Mailpit)
docker/nginx        edge: /api → api:3001, /img → imgproxy, / → SPA; headers e CSP
reference/volans-api  API TypeScript original do volans (SÓ referência para portar a auth; não roda)
docs/reference/volans arquitetura, ADRs e produto do volans (referência)
.specify/ .claude/skills  Spec Kit
```

## Comandos
```bash
docker compose up -d                        # stack: http://localhost:8180  https://localhost:8543
curl http://localhost:8180/api/health       # {"status":"ok","db":"ok","redis":"ok"}
npm run test:api [-- args do pytest]      # API em stack EFÊMERA (docker-compose.test.yml): sobe Postgres/Redis/MinIO, roda o pytest e faz down -v sempre; pode rodar em paralelo
docker compose exec api uv run pytest       # alternativa rápida no dev (banco sociman_test + Redis DB 15; NUNCA duas ao mesmo tempo)
docker compose exec api uv run ruff check .
npm run check:web                           # check:contract + typecheck + build + check:bundle/csp/secrets
npm run gen:contract                        # OpenAPI do FastAPI → packages/contract (roda no host, sem Docker)
npm run test:e2e [-- args do playwright]  # Playwright em stack EFÊMERA (docker-compose.e2e.yml, projeto sociman-e2e, edge :8280/:8643, Mailpit :8127): sobe tudo, roda e faz down -v sempre; NUNCA toca o dev
docker compose exec api uv run sociman create-owner --email E --name N [--force]   # primeiro dono
docker compose exec api uv run sociman set-password --email E                      # senha de emergência
docker compose exec api uv run sociman reset-db --yes                              # zera banco+Redis (não roda em produção)
./scripts/certs-casa.sh [IP]                # CA da casa + certificado do edge (IP padrão 192.168.86.47); guia: docs/guia-certificado-casa.md
npm run casa:up                             # MODO CASA: build de produção + EDGE_MODE=prod + perfil prod (PWA instalável)
npm run test:e2e:pwa                        # e2e do PWA na stack efêmera (perfil pwa: build em .e2e/pwa-dist + EDGE_MODE=prod); não precisa do modo casa
docker compose --profile prod stop web-prod && docker compose up -d edge   # volta ao modo dev
./scripts/data-setup.sh check|init|count|migrate|compare|verify   # HD de dados (MinIO + work) — ver spec 004 quickstart §0
docker compose logs -f worker               # worker de vídeo (`sociman worker`): fila de cortes, ffmpeg
```
**Modo casa:** use `https://192.168.86.47:8543` nos aparelhos (com a CA da casa instalada). `http://192.168.86.47:8180` redireciona para lá; a CA pública fica em `http://192.168.86.47:8180/sociman-ca.cer`.
Portas: edge 8180/8543, console do MinIO 9101 (minioadmin/minioadmin, **só dev**), Mailpit (e-mails de dev) em **127.0.0.1:8126**. Postgres, API, Redis, SMTP e imgproxy ficam só na rede interna. **Não use** 8000/5175 (OpenShorts), 18789 (OpenClaw) nem 6379/1025/8025 (arka-manager, já ocupadas no host).

## Frontend (desde a spec 005)
- UI com **shadcn/ui** (Radix) + Tailwind 4 + TanStack Query + **TanStack Table v9** (API nova: use `dataTableColumns<T>()` de `components/data-table`, não exemplos da v8).
- Componentes do shadcn em `apps/web/src/components/ui/` (adicione com `npx shadcn@latest add <nome>` dentro de `apps/web`); painel em `components/shell/` (AppShell, Sidebar, Topbar, AuthShell, MetricCard, HeaderCard, `usePageMeta`); tabelas com `components/data-table/DataTable`.
- Formulários: `components/ui/field.tsx` (`Field` + `NativeSelect`: `<select>` nativo, e os e2e dependem dele). Confirmações em AlertDialog (`role="alertdialog"`).
- Referência visual: `docs/design/layout-referencia.md` (Material Dashboard React, só inspiração). CSP: `style-src 'unsafe-inline'` aceito, `script-src` estrito (ADR 0001).
- Vitrine de componentes só em dev: `/app/_showcase`.

## Kit de marca e cortes (desde a spec 004)
- **MinIO no HD:** `${SOCIMAN_DATA_DIR}` (padrão `/media/sakai/BACKUP/tiktok/sociman`) tem `minio/`, `work/` e o sentinela `.sociman-volume`. Buckets: `sociman` (imagens), `sociman-fonts` e `sociman-videos`. O volume antigo `sociman_minio-data` ficou como cópia de segurança, sem uso.
- **Código:** `datadir.py` (sentinela, espaço livre, 503/507), `storage.py` (`bucket="imagens"|"fontes"|"videos"`, sem delete), `midia.py` + `router_midia.py` (links HMAC `/api/midia/{token}` com Range; vídeo com validade, fonte e marca d'água sem validade), `marca/` (tokens, kit, exportação para o OpenShorts, fontes, marca d'água) e `cortes/` (probe, render com Pillow, compose com ffmpeg, fila com SKIP LOCKED, worker).
- **Edge:** as rotas de upload grande têm `location` própria no `default.conf.template`: cortes com 520m e sem buffering, fontes com 11m. `/api/midia/` sem buffering.
- **Gancho:** quem queima é o SociMan. Ao gerar cortes no OpenShorts, **não** use `auto_hook` (a exportação traz `openshorts.hook.enabled=false`).

## Cortes com o OpenShorts (desde a spec 006)
- **Pacotes:** `canais/` (canais-fonte, cliente do YouTube, sync, cota, pontuação), `envios/` (seleção, padrões de corte, envio, cliente do OpenShorts, acompanhamento, importação), `postagem/` (textos com o Claude, postagens, lembretes), `notificacoes/` e `integracoes.py`. Rotas `/api/canais`, `/api/videos-fonte`, `/api/envios`, `/api/postagens`, `/api/calendario`, `/api/notificacoes`, `/api/integracoes`. **Sem "youtube" nem "tiktok" em rotas e operationIds** (guarda do princípio I).
- **Serviço `agendador`** (`sociman agendador`, mesma imagem da API, advisory lock no PG): 4 trilhas (`sync`, `openshorts`, `importacao`, `lembretes`). Logs: `docker compose logs -f agendador`; depois de mudar esse código, `docker compose restart agendador`.
- **Chaves** `YOUTUBE_API_KEY` e `ANTHROPIC_API_KEY` no `.env` da raiz (só api e agendador). Sem elas, a sync fica ociosa e as sugestões respondem 503 `claude_unconfigured`. `GET /api/integracoes` mostra o estado sem expor valores.
- **OpenShorts** em `http://host.docker.internal:8000` (`extra_hosts`): corpo com `auto_hook: false` e `captions: false`, legenda do kit via `/api/subtitle`. Os clipes viram cortes em `revisao`; "Aplicar marca" leva para `na_fila`. A importação precisa rodar dentro das 24 h de retenção do OpenShorts e deduplica pelo trecho do vídeo.
- **Direito (princípio II):** `enviar` responde 409 `aviso_direito` sem `confirmarAviso: true` para canal `sem_acordo` e envio avulso; o histórico grava `direitoNoEnvio` e quem confirmou. Envio e corte não têm `revert` (exceção aprovada do princípio VII).
- **Postagens:** uma por corte e conta; `postado` só por ação humana. Avisos "Hora de postar" no sino e no navegador **com o app aberto** (sem Web Push).
- **Edge:** `location` própria de 2100m para o envio avulso de arquivo. Miniaturas do YouTube passam pelo imgproxy (`IMGPROXY_ALLOWED_SOURCES`).
- **Testes:** fakes em `apps/api/tests/fakes/` (YouTube, OpenShorts, Claude); no e2e, o serviço `openshorts-fake` (`e2e/fakes/server.py`) responde também `/youtube/v3`. Nenhum teste chama serviço real.

## Biblioteca de assets (desde a spec 007)
- **Código:** pacote `assets/` (modelos `assets`/`asset_files`, `service`, `busca`, `usos`, `backfill`, routers `/api/perfis/{id}/assets…` e `/api/assets/{id}…`); `entity_type = "asset"` no `history.py`. Aba **Assets** do perfil (`?aba=assets`) e detalhe em `/app/assets/:id`.
- **Tipo × `image_kind`:** `avatar`→`avatar`, `cenario`/`fundo`→`fundo`, `sticker`/`marca_dagua`→`watermark` (transparência obrigatória), `imagem`→`imagem`. Os arquivos continuam em `images` (o kit e os cortes não mudaram de referência); a migração `0005_assets` pôs toda imagem de fundo e marca d'água da 004 num asset (`system:migration`).
- **Limite de 20 MB:** o edge tem `location` própria com `client_max_body_size 21m` para `…/assets/arquivo` e `/api/assets/{id}/arquivos`, para a recusa vir da API (o resto de `/api/` segue com 8m). O imgproxy tem `IMGPROXY_MAX_SRC_RESOLUTION=40`.
- **Links:** `MidiaKind imagem` assina sem validade (`AssetFile.link` estável e `downloadUrl`).
- **Arquivar:** só o uso no **kit** bloqueia (409 `asset_in_use`); cortes só informam. O kit guarda o `fundo_imagem_id` mesmo com fundo `cor`: para liberar a imagem, escolha outra.
- **Seletores do kit** (fundo e marca d'água) listam da biblioteca (`GET …/assets/imagens`) com "Abrir biblioteca"; "Enviar imagem" cria o asset. As rotas antigas `…/fundos` e `…/marca-dagua` ficam `deprecated`.

## Assistente de IA (desde a spec 008)
- **Código:** pacote `ia/` (`tipos.py` com os 13 tipos de campo **em código**, `regras_padrao.py`, `prompt.py` com a base fixa `ia/1`, `cliente.py`, `saida.py`, `custo.py`, `service.py`, `service_regras.py`, `aplicacao.py`, router `/api/ia/*` com `operationId` `ia_*`). As regras editadas pelo dono ficam em `ia_regras` (sem linha = padrão do código; `entity_type = "ia_regra"`, "Voltar ao padrão" grava `texto = NULL`). Tela `/app/assistente-ia` (Regras para todos; Registro e Resumo só o dono).
- **Registro:** `ia_chamadas` é a `sugestoes_texto` da 006 renomeada (mesmos ids; as linhas antigas viram `postagem.textos`). Toda geração é gravada, inclusive com erro (503/504/502), com desfecho `sem_acao`/`aplicada`/`editada`/`descartada`/`erro` e custo aproximado.
- **Aplicar salva só o campo** (1 clique) pelo save normal da tela, com `ia: [{ tipoCampo, chamadaId, itens? }]` no corpo (`PATCH` de asset, perfil e postagem, `PUT` do kit com os tokens **salvos**, `POST` que cria a postagem). O `ia.aplicacao.marcar` roda antes do `history.record` e grava `details.ia` (o selo "com ajuda da IA"); o autor continua o humano. Gerar nunca salva. As outras alterações não salvas continuam no formulário.
- **Bordões e séries** usam o formato `sugestoes` (marcar, "Gerar mais" com aceitos e rejeitados da sessão, lista do kit ≤ 20). Hashtags são `lista`; "Sugerir textos" da postagem é `textos_postagem`.
- **`ANTHROPIC_BASE_URL`** (vazio = padrão do SDK) só é usado no e2e, apontando para o `openshorts-fake` (`POST /v1/messages`: "lento" e "fora do limite" na instrução ativam os modos de erro). As rotas de sugestões da 006 (`/api/cortes/{id}/sugestoes`) ficam `deprecated`.

## Armadilhas
1. **Containers rodam como UID 1000.** Se uma pasta de bind mount não existir, o Docker a cria como root (foi o que aconteceu com `docker/certs`). Crie antes.
2. **CSP estrita em produção** (herdada do volans). `check:csp` compara `apps/web/vite.config.ts` com `docker/nginx/05-edge-mode.envsh`. Mudou um, mude o outro.
3. **A API confia em `X-Forwarded-*`** (`--forwarded-allow-ips='*'`) porque só o edge a alcança. Nunca publique a porta da API.
4. **Não mate processos por nome** (`pkill -f vite` mata processos dentro dos containers). Use porta ou PID.
5. **Segredos:** `.env` é gitignored, e `check:secrets` roda sobre os arquivos rastreados. Credenciais do compose são só de dev.
6. **O contrato é gerado** (constitution, princípio IV): não edite `packages/contract/openapi.json` nem `src/generated/` à mão. Mudou rota ou schema na API → `npm run gen:contract`. O `check:contract` acusa divergência.
7. **Sessão do banco com `DbSession` (scope="function")**: no escopo padrão o FastAPI commita depois de enviar a resposta e o SPA lê dado velho. Nunca declare `Depends(get_db)` direto (há teste de regressão).
8. **Negação que precisa ficar registrada** (ex.: `login_failed`) é commitada antes do erro (`_deny` em `auth/service.py`), porque o `get_db` faz rollback quando a rota levanta exceção. Revogação de sessões no Redis só **depois** do commit.
9. **E-mail que não pode revelar se a conta existe** (reenvio de verificação, esqueci a senha) sai em BackgroundTask, para o tempo de resposta ser igual.
10. **`JWT_SECRET`** fica em `apps/api/.env` (gitignored). Sem ele a API usa um segredo efêmero e toda sessão cai a cada reload.
11. **Service worker só no build de produção** (modo casa). Em dev (Vite) não há SW. O e2e do PWA usa o HTTP de localhost porque o Chromium de teste não tem a CA e recusa SW com certificado inválido.
12. **Chaves da CA** ficam em `docker/certs/ca/` (gitignored, 600). Nunca compartilhe `sociman-ca.key`; só `sociman-ca.crt/.cer` são públicos.
13. **Mudou `docker/nginx/*`?** Rode `docker compose restart edge`. O template é montado como arquivo, e `up -d` não recria o container.
14. **Specs de domínio usam `history.py`** (princípio VII): toda mutação chama `history.record` na mesma transação (autor, antes/depois), cada entidade tem `version` (controle otimista → 409 `version_conflict`) e `__versioned_fields__`/`__immutable_fields__`. **Não existe DELETE no domínio**: arquivar/restaurar; reversão só pelo dono.
15. **Imagens:** `storage.py` (MinIO, bucket privado, sem delete) + `imaging.py` (validação Pillow pelo conteúdo, URLs `/img` do imgproxy). `IMGPROXY_KEY`/`IMGPROXY_SALT` no `.env` da raiz assinam as URLs; sem eles é `unsafe` (só dev). O edge aceita até 8 MB em `/api/`; a API limita a 5 MB.
16. **FastAPI 0.141 envolve rotas incluídas em `_IncludedRouter`**: procurar rota em `app.routes` não funciona (use `app.openapi()`).

17. **Armazenamento NVMe × HD** (constitution 2.1.0): no NVMe ficam a aplicação, o PostgreSQL e o Redis (o que precisa ser rápido); o MinIO inteiro (imagens, fontes, vídeos), os temporários do ffmpeg, downloads e exportações vão para o HD em `/media/sakai/BACKUP/tiktok` (partição BACKUP, 2,1 TB). O uso do HD exige o arquivo marcador `.sociman-volume` (sem ele, recusa: HD desmontado encheria o NVMe) e um piso de espaço livre.
18. **e2e isolado do dev:** `npm run test:e2e` e `test:e2e:pwa` sobem o projeto compose `sociman-e2e` (outra rede, volumes em tmpfs, portas 8280/8643/8127 só em 127.0.0.1) e o derrubam com `down -v`; o banco de dev e o usuário do dono ficam intactos. **Nunca rode `npx playwright test` direto**: sem `E2E_BASE_URL`/`E2E_MAILPIT_URL`/`E2E_COMPOSE` ele falha de propósito, e o `compose()` dos helpers recusa qualquer projeto que não seja `sociman-e2e`. Os dois modos usam o mesmo nome de projeto: não rode dois e2e ao mesmo tempo.

## Regras de negócio herdadas da agência (não mudam)
- O SociMan **nunca publica** em rede social.
- Direito autoral é responsabilidade do dono (constitution 3.0.0, princípio II): o SociMan não bloqueia. O canal-fonte tem status informativo (`proprio`, `parceiro`, `programa_de_cortes`, `sem_acordo`) que só o dono muda; `sem_acordo` ou envio avulso mostra aviso, e todo envio para corte fica no histórico.
