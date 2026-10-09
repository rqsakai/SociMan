# Implementation Plan: Fontes, seleção de vídeos e cortes com o OpenShorts (006-cortes-openshorts)

**Branch**: `006-cortes-openshorts` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-cortes-openshorts/spec.md`

## Summary

Terceira spec de domínio. Ela fecha o fluxo **canal → vídeo → OpenShorts → corte com a marca →
postagem preparada**, sem publicar nada (princípio I). Absorve o item `008-canais-fonte-e-videos`
do backlog em `docs/visao.md`. Tem cinco blocos:

- **Canais-fonte (US1, P1):**
  - cadastro por link, `@` ou ID, resolvido com `channels.list` da YouTube Data API v3 (1 unidade);
  - status de direito **informativo**, que só o dono muda (constitution 3.0.0, princípio II), com
    evidência opcional (link ou nota);
  - ligação N:N com perfis, histórico, arquivamento e reversão, como na 003.
- **Descoberta (US2, P1):**
  - um serviço novo, **`agendador`** (a mesma imagem da API, rodando `sociman agendador`), busca
    todos os vídeos pela playlist de uploads (2 unidades a cada 50 vídeos). Depois sincroniza de
    forma incremental e renova as métricas com uma frequência que cai com a idade do vídeo;
  - cada vídeo recebe uma **pontuação explicável** de 0 a 100 (velocidade relativa ao próprio
    canal, engajamento, recência e duração) e um motivo em uma linha;
  - a cota diária fica registrada numa tabela, com aviso em 80% e pausa em 95%;
  - as miniaturas do YouTube passam pelo imgproxy (fontes remotas numa lista fechada), porque a
    CSP não aceita origens externas.
- **Envio ao OpenShorts (US3, P1):**
  - a **seleção é um envio em rascunho** (`envios.status = selecionado`);
  - os padrões de corte do perfil preenchem a configuração;
  - o aviso de direito é exigido pela API (`confirmarAviso`) quando o canal é `sem_acordo` ou o
    envio é avulso. O envio vai para o histórico com o status de direito do momento;
  - o `agendador` envia a URL do vídeo ao OpenShorts (quem baixa é o yt-dlp dele) ou, no caso de
    arquivo avulso, faz o upload pelo `POST /api/uploads` + `PUT`;
  - o acompanhamento é por polling a cada 10 s e é retomado depois de reinícios. Com o OpenShorts
    fora do ar, o envio fica em `aguardando_openshorts`, com backoff.
- **Clipes → cortes (US4, P1):**
  - cada clipe recebe a legenda no estilo do kit (`POST /api/subtitle`, com a seção `openshorts`
    da 004) e é baixado pelo `video_url`, conferido com o ffprobe e guardado no bucket
    `sociman-videos` (HD);
  - vira um `Corte` da 004 em `revisao`, com origem, trecho, gancho (`viral_hook_text`), textos do
    OpenShorts e transcrição;
  - "Aplicar marca" usa a **fila da 004 sem mudanças no worker** (`revisao → na_fila`), e o perfil
    pode ligar a marca automática.
- **Postagem (US5, P2):**
  - sugestão de título, descrição e hashtags com o **Claude Sonnet 5.5** (`claude-sonnet-5-5`), em
    saída estruturada (`messages.parse` com Pydantic), a partir do perfil, do kit e do clipe;
  - `postagens` por corte e conta, com data e hora planejadas, estados `rascunho`, `agendado` e
    `postado` (este só marcado à mão) e histórico;
  - calendário próprio (grade CSS e arrastar nativo, sem biblioteca);
  - o `agendador` cria a notificação "Hora de postar";
  - notificações in-app numa tabela, lidas por polling, com a Notification API do navegador
    enquanto o app está aberto.

Detalhes em [research.md](research.md), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md) e [quickstart.md](quickstart.md). As perguntas de
alto impacto estão em [open-questions.md](open-questions.md). O dono respondeu **Q1 A, Q2 A, Q3 A,
Q4 A** em 2026-09-29 (registrado nas Clarifications da spec), e o plano já seguia essas opções.

## Technical Context

**Language/Version**: Python 3.12 (API, worker e agendador) · TypeScript 5 / React 19 (SPA)

**Primary Dependencies**:
- **Python, novas:**
  - `httpx`, que passa do grupo dev para as dependências, como cliente HTTP da YouTube Data API
    e do OpenShorts. Nada de `google-api-python-client`, que o teste-guarda do princípio I
    proíbe;
  - `anthropic`, o SDK oficial, para a sugestão de textos (R9).
- **Na imagem:** nada novo. O ffmpeg e o ffprobe já vieram com a 004.
- **No SPA:** nada novo. O calendário é feito com CSS grid, o arrastar usa o HTML5 nativo e os
  diálogos e tabelas vêm de shadcn e TanStack.

**Storage**:
- PostgreSQL, no NVMe: `canais_fonte`, `canal_perfis`, `videos_fonte`, `video_metricas`,
  `youtube_cota`, `padroes_corte`, `envios`, `cortes` (ampliada), `postagens`, `sugestoes_texto`
  e `notificacoes`;
- MinIO no HD: os clipes importados e os arquivos avulsos no bucket `sociman-videos`;
- `work/` no HD: download dos clipes e spool do upload avulso;
- as miniaturas do YouTube **não são guardadas**: o imgproxy as busca na origem, a partir de uma
  lista fechada.

**Testing**:
- pytest na stack efêmera, com **mocks HTTP** (`httpx.MockTransport`) de YouTube, OpenShorts e
  Anthropic, e ffmpeg real para os clipes sintéticos importados;
- um teste de ponta a ponta do agendador com um OpenShorts falso, que sobe e cai;
- ruff; `check:web` com o contrato regenerado e o `check:secrets` (os padrões `AIza…` e
  `sk-ant-…` já existem em `scripts/check-secrets.mjs`; a 006 só confere);
- Playwright `e2e/cortes-openshorts.spec.ts` com o agendador apontando para um **OpenShorts falso**
  (serviço `openshorts-fake` na stack e2e, `e2e/fakes/server.py`). O mesmo stub responde
  `/youtube/v3/*` (config `YOUTUBE_API_URL`), para que o e2e **nunca** chame o Google nem precise
  de chave real; a sugestão de textos fica sem chave no e2e (caminho `claude_unconfigured`) e é
  coberta pelo pytest com o mock do Anthropic;
- roteiro opcional com o OpenShorts real no quickstart §7.

**Target Platform**: a mesma stack. Entra o serviço novo `agendador`; `api` e `agendador` ganham
`extra_hosts: host.docker.internal:host-gateway`, e o imgproxy aceita fontes remotas do YouTube.

**Project Type**: web application (SPA + API + worker + agendador)

**Performance Goals**:
- SC-001: canal de 500 vídeos listado em menos de 2 min. São 20 unidades e cerca de 20
  requisições; o gargalo esperado é a latência do Google, e não passa de 30 s;
- SC-003: fim do processamento → notificação em menos de 1 min (polling de 10 s no agendador +
  20 s no SPA). Com a legenda do kit (Q4 = A), o processamento inclui o `/api/subtitle` de cada
  clipe (+30 a 60 s de CPU por clipe) e a importação, e a notificação `envio_pronto` sai no fim da
  importação; falhas do OpenShorts notificam em menos de 1 min. A importação roda numa trilha
  própria (R1), para não segurar o polling;
- SC-005: sugestão em menos de 15 s (Sonnet 5.5 com esforço `low`, saída de cerca de 400 tokens e
  timeout de 20 s);
- descoberta: filtros no servidor com índice, resposta p95 abaixo de 300 ms para cerca de 10 mil
  vídeos.

**Constraints**:
- nada publica (princípio I). Os clientes HTTP têm lista fechada de caminhos, verificada por teste;
- a CSP não muda: miniaturas via `/img` (imgproxy) e notificações sem SSE;
- cota do YouTube de 10.000 unidades por dia, que zera à meia-noite do horário do Pacífico;
- o OpenShorts guarda um job por **24 h** (`JOB_RETENTION_SECONDS` no self-host), então a
  importação precisa acontecer dentro desse prazo;
- `MAX_CONCURRENT_JOBS=1` no OpenShorts: um job por vez, e a fila fica lá;
- fonte com no mínimo 45 s (`MIN_SOURCE_SECONDS`) e no máximo 2 GB por arquivo;
- disco: clipes e arquivos avulsos no HD (sentinela e piso da 004); o OpenShorts guarda os
  trabalhos dele no NVMe (`openshorts/output`, limite de 25 GB e 24 h), o que fica **fora** do
  SociMan (risco registrado em R5);
- fuso de exibição e agendamento `America/Sao_Paulo`, com tudo guardado em `timestamptz`.

**Scale/Scope**:
- 2 perfis hoje (até cerca de 10) e cerca de 10 canais-fonte de até 5 mil vídeos;
- 5 a 20 envios e cerca de 60 clipes por dia;
- cerca de 40 endpoints;
- telas: Fontes, Descobrir, Envios, revisão do envio, Calendário, o sino, a aba "Padrões de corte"
  no perfil e a seção "Postagem" no corte.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|---|---|---|
| I. Nenhum agente publica | ✅ | Não há credencial nem cliente de rede social. O cliente do YouTube só faz GET em `channels`, `playlistItems` e `videos` (e `search` como último recurso para `/c/`). O cliente do OpenShorts tem lista fechada de caminhos (`/health`, `/api/process`, `/api/uploads`, `/api/status`, `/api/subtitle`, `/api/clip/*/transcript`, `/videos/*`), **sem `/api/social/*`**. `postado` só muda por rota humana. O teste-guarda da 001 é ampliado (R12) |
| II. Direito é responsabilidade do dono | ✅ | O status do canal é informativo, e só o dono o muda (`RequireOwner`, 403 para membro). O aviso é exigido pela API: `enviar` responde 409 `aviso_direito` sem `confirmarAviso: true` para `sem_acordo` e avulso, então vale também para o MCP da 009. Todo envio grava uma versão no histórico com autor, data, fonte e `direitoNoEnvio`. Nada bloqueia; dono e membro enviam depois de confirmar o aviso (Q3 = A). **Decisão do dono (2026-09-29):** evidência por link ou nota nesta spec; upload de print fica para depois da 007 |
| III. Marca em tokens | ✅ | O estilo da legenda sai da seção `openshorts.subtitle` da 004. O gancho do OpenShorts fica desligado (`auto_hook: false`), e quem queima o gancho é o worker da 004. Os padrões de corte são campos validados, não texto |
| IV. Contrato é a fonte única | ✅ | Todas as rotas novas entram no OpenAPI → `gen:contract`. Os nomes de rota evitam os termos do guarda (`youtube`, `tiktok`, `share`…): `/api/canais`, `/api/videos-fonte`, `/api/envios`, `/api/postagens` |
| V. Segurança e segredos | ✅ | `YOUTUBE_API_KEY` e `ANTHROPIC_API_KEY` só no `.env` da raiz (gitignored) → compose. `check:secrets` já cobre os padrões `AIza…` e `sk-ant-…`. A chave nunca vai para log nem para mensagem de erro (redação no cliente). O imgproxy aceita só `https://i.ytimg.com/`, `https://yt3.ggpht.com/` e `https://yt3.googleusercontent.com/`. A transcrição vai ao Claude como dado delimitado, sem tools. A CSP não muda |
| VI. Testes antes de pronto | ✅ | Mocks HTTP das três integrações, agendador com OpenShorts falso (queda, retorno, 404 depois da retenção), importação com ffmpeg real, testes do II (403, 409 do aviso, histórico) e do I (guarda ampliado), e2e com stub |
| VII. Humano no controle | ✅ com exceção justificada | Canal, padrões, envio e postagem guardam versão, autor e antes/depois (`GET …/versions`). **Reversão pelo dono** (`POST …/revert`, `RequireOwner`) em canal, padrões de corte e postagem. **Exceção (aprovada pelo dono em 2026-09-29):** envio e corte não têm `revert`, porque as transições disparam efeitos fora do banco (job no OpenShorts, render no worker) que um snapshot não desfaz; a reversão deles é arquivar/restaurar o corte e fazer um envio novo, e o histórico continua visível. Envios descartados são arquivados, e cortes arquivados nunca são apagados. As mudanças do sistema (sincronização, progresso) são estado de job, sem versão, como na 004. Teste em `tests/integration/test_historico_006.py` |
| VIII. Simplicidade | ✅ com justificativa | Um serviço novo (`agendador`) e duas dependências Python, justificados abaixo. O `agendador` não é componente novo da stack (restrição "stack fixa"): é a mesma imagem, linguagem e banco da API, como o `worker` da 004. Não entram SSE, Web Push, biblioteca de calendário, Redis/RQ, cópia local das miniaturas nem download do vídeo pelo SociMan |

**Reavaliação pós-design:** mantida. O design só acrescentou o que está na tabela de
complexidade.

Fora do escopo, de propósito:
- publicar ou mandar rascunho para o TikTok (spec futura, que exige emendar o princípio I);
- TikTok e Instagram como canais-fonte;
- Web Push com o app fechado (Q1 = A, decisão do dono em 2026-09-29);
- editar os cortes no editor do OpenShorts;
- reprocessar um envio com outra configuração (é um envio novo);
- GPU.

## Project Structure

### Documentation (this feature)

```text
specs/006-cortes-openshorts/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── open-questions.md
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── pyproject.toml                         # + httpx (sai do dev), + anthropic
├── migrations/versions/0006_cortes_openshorts.py
├── src/sociman_api/
│   ├── config.py                          # + YOUTUBE_API_KEY, YOUTUBE_API_URL, OPENSHORTS_URL, ANTHROPIC_API_KEY, TEXTOS_MODEL,
│   │                                      #   APP_TZ, YT_QUOTA_DAILY, AGENDADOR_* (intervalos)
│   ├── cli.py                             # + comando `agendador`
│   ├── imaging.py                         # + remote_url() para miniaturas (imgproxy, fontes permitidas)
│   ├── agendador.py                       # laço com trilhas (sync, openshorts, importação, lembretes), advisory lock
│   ├── notificacoes/                      # models, service (criar com dedupe, fan-out), schemas, router
│   ├── canais/                            # "fontes" já nomeia as fontes tipográficas (marca/fontes.py)
│   │   ├── models.py                      # CanalFonte, CanalPerfil, VideoFonte, VideoMetrica, YoutubeCota
│   │   ├── youtube.py                     # cliente httpx só GET (channels, playlistItems, videos, search), cota, redação da chave
│   │   ├── resolve.py                     # link/@/UC → consulta; puro e testável
│   │   ├── sync.py                        # completa, incremental, métricas por faixa de idade, disponibilidade
│   │   ├── score.py                       # pontuação e motivo (puro)
│   │   ├── service_canais.py              # CRUD + direito (dono) + perfis + histórico
│   │   ├── service_videos.py              # descoberta (filtros, paginação, "já cortado")
│   │   ├── schemas.py
│   │   └── router.py
│   ├── envios/
│   │   ├── models.py                      # PadroesCorte, Envio (+ enums)
│   │   ├── openshorts.py                  # cliente httpx com lista fechada de caminhos
│   │   ├── service_padroes.py             # get/put/versões (padrão preguiçoso, como o kit)
│   │   ├── service_envios.py              # selecionar, avulso, enviar (aviso), descartar, retry, lista
│   │   ├── acompanhamento.py              # submit, poll, backoff, needs_confirmation, 404 depois da retenção
│   │   ├── importacao.py                  # legenda do kit, download, ffprobe, MinIO, Corte em revisão, marca auto
│   │   ├── upload.py                      # recebimento do avulso (reusa o streaming de cortes.service, limite de 2 GB)
│   │   ├── schemas.py
│   │   └── router.py
│   ├── cortes/
│   │   ├── models.py                      # + status revisao, origem, envio_id, clip_index, trecho, textos do OpenShorts,
│   │   │                                  #   transcrição, archived_*; kit_* anuláveis
│   │   ├── service.py                     # + aplicar marca (revisao → na_fila), editar gancho, arquivar/restaurar
│   │   └── router.py                      # + rotas acima (lote)
│   ├── postagem/
│   │   ├── models.py                      # Postagem, SugestaoTexto
│   │   ├── textos.py                      # prompt, messages.parse (Pydantic), validação e normalização das hashtags
│   │   ├── service.py                     # sugerir, CRUD, agendar/remarcar, marcar postado, calendário
│   │   ├── schemas.py
│   │   └── router.py
│   └── main.py                            # inclui routers
└── tests/
    ├── fixtures/{youtube,openshorts,anthropic}/   # respostas JSON gravadas (sem chave)
    ├── unit/                              # resolve, score, youtube (cota, redação), openshorts (caminhos), textos, guards
    └── integration/                       # canais (II), descoberta, envios (aviso, duplicado), agendador + OpenShorts falso,
                                           #   importação (ffmpeg real), postagens, calendário, notificações

apps/web/src/
├── pages/canais/{CanaisList,CanalDetalhe}.tsx
├── pages/descobrir/Descobrir.tsx          # DataTable com paginação no servidor, filtros, seleção em lote
├── pages/envios/{EnviosList,EnvioDetalhe}.tsx   # Selecionados + envios; revisão dos clipes lado a lado
├── pages/calendario/Calendario.tsx        # semana/mês, arrastar nativo, diálogo "Remarcar" no toque
├── pages/perfis/tabs/PadroesCorteTab.tsx
├── pages/cortes/CorteDetalhe.tsx          # + seção Postagem (sugerir, editar, agendar, copiar, baixar, "Postado")
├── components/canais/{DireitoBadge,CanalForm,VideoCard,ScoreReason}.tsx
├── components/envios/{EnviarDialog,AvisoDireito,EnvioStatus,ClipReview}.tsx
├── components/notificacoes/{Sino,useNotificacoes}.tsx   # polling, contagem, Notification API
└── lib/{canais,envios,postagem,notificacoes,tz}.ts

docker-compose.yml       # + serviço agendador (mesma imagem, `sociman agendador`, binds do HD);
                         #   api/agendador: extra_hosts host.docker.internal:host-gateway, YOUTUBE_API_KEY,
                         #   ANTHROPIC_API_KEY, OPENSHORTS_URL; imgproxy: IMGPROXY_ALLOWED_SOURCES + fontes do YouTube
docker-compose.e2e.yml   # + openshorts-fake (stub) e agendador apontando para ele
docker/nginx/default.conf.template   # location do upload avulso (2100m, sem buffering)
scripts/check-secrets.mjs            # + padrões AIza… e sk-ant-…
e2e/cortes-openshorts.spec.ts
```

**Structure Decision:**
- três pacotes de domínio novos: `canais/` (canais, vídeos e YouTube), `envios/` (padrões, envio,
  OpenShorts e importação) e `postagem/` (textos, agenda e calendário), mais `notificacoes/`, que
  as specs futuras vão reusar;
- `cortes/` da 004 é **ampliado, não duplicado**: o clipe importado é um `Corte`, e a aplicação da
  marca é a mesma fila;
- `agendador.py` fica na raiz do pacote, como `datadir.py`, porque orquestra tarefas de vários
  domínios;
- o SPA segue a 005 (DataTable, shadcn), com as rotas novas no menu lateral: "Canais-fonte",
  "Descobrir", "Envios" e "Calendário".

**Migration:** `0006_cortes_openshorts`, com `down_revision = "0005_assets"` (a migration da
007, que vem depois de `0004_fundo_imagem`). A 006 só é aplicada depois da 007. Se a 006 for
implementada primeiro, o encadeamento é refeito no `/speckit-tasks` (a `down_revision` passa a
ser `0004_fundo_imagem`, e a 007 passa a vir depois dela).

### Pontos de integração com a 007 (assets do perfil, planejada em paralelo)
A 006 fica o máximo possível em módulos e páginas **novos**: `canais/`, `envios/`, `postagem/`,
`notificacoes/`, `agendador.py` e `pages/{canais,descobrir,envios,calendario}`. Os arquivos que
as duas specs tocam são estes, e quem implementar por último faz o merge:

| Arquivo | 007 | 006 | Como evitar conflito |
|---|---|---|---|
| `midia.py`, `router_midia.py` | novo kind `imagem` | **nenhuma mudança** (o download para postar usa o kind `corte_marcado` da 004, e a importação usa `storage.py`) | nada a fazer |
| `pages/perfis/PerfilDetalhe.tsx` | aba "Assets" | aba "Padrões de corte" | uma linha no array de abas; o conteúdo fica em `tabs/PadroesCorteTab.tsx` |
| `docker/nginx/default.conf.template` | `location` de 21m para assets | `location` do upload avulso (2100m) | blocos `location` independentes, cada um com regex próprio; `docker compose restart edge` depois |
| `docker-compose.yml` | imgproxy (se mudar algo) | serviço `agendador`, `extra_hosts` e env em `api`, `IMGPROXY_ALLOWED_SOURCES` no imgproxy | a 006 só **acrescenta** fontes a `IMGPROXY_ALLOWED_SOURCES` (lista separada por vírgula), sem trocar o valor da 007 |
| `imaging.py` | (verificar no plano da 007) | nova função `remote_url()`, sem alterar as existentes | só acréscimo |
| `apps/web/src/components/shell/nav.ts` | (se a 007 tiver item de menu) | itens Fontes, Descobrir, Envios e Calendário | só acréscimo |
| `docker-compose.e2e.yml` | – | `openshorts-fake` e `agendador` | coordenar com quem mantém a stack e2e |

**Ordem sugerida para o `/speckit-tasks`:**
0. infra: `httpx` e `anthropic`, config, `.env` e `check:secrets`, compose (`agendador`,
   `extra_hosts`, imgproxy), `sociman agendador` com advisory lock e trilhas vazias;
1. notificações (tabela, rotas e sino). Tudo depois delas notifica;
2. canais (resolve, cliente do YouTube com cota, direito só do dono, perfis);
3. sincronização e pontuação no agendador;
4. descoberta no SPA;
5. padrões de corte;
6. envios (seleção, avulso, aviso, duplicado);
7. cliente do OpenShorts, acompanhamento e OpenShorts falso;
8. importação, `Corte` ampliado e marca automática;
9. revisão dos clipes no SPA;
10. textos com o Claude;
11. postagens, lembretes e calendário;
12. guardas I e II ampliados e e2e.

As fases 0 a 9 fecham as US P1 e podem ir ao dono antes da US5.

## Complexity Tracking

| Item | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| Serviço `agendador` no compose (mesma imagem) | tarefas periódicas que sobrevivem a reinício (FR-004, FR-010, FR-017) e não podem esperar o ffmpeg (SC-003) | pôr no laço do `worker`: um corte da 004 segura o laço por até 10 min, e a notificação passaria de 1 min; `BackgroundTasks` na API: morre com o `--reload`; cron do host: fora do compose e sem estado |
| Trilhas (threads) dentro do agendador | a importação (legenda e download de 6 clipes, alguns minutos) e a primeira sincronização de um canal grande não podem atrasar o polling de 10 s | um processo por tarefa: quatro serviços no compose; asyncio: reescrever o acesso ao banco, que é síncrono |
| `httpx` como dependência de runtime | cliente HTTP com timeout, streaming (download dos clipes e upload avulso) e `MockTransport` para os testes | `urllib`: sem streaming confortável nem transporte de teste; `google-api-python-client`: proibido pelo guarda do princípio I e pesado |
| SDK `anthropic` | FR-014 com saída estruturada validada (`messages.parse` + Pydantic), retries e erros tipados | HTTP à mão: reimplementa o que o SDK faz (contra a orientação da Anthropic) e perde a validação do schema |
| Tabela `youtube_cota` | a cota é diária e compartilhada entre API (cadastro) e agendador (sync). O aviso perto do fim (edge case) precisa de contagem durável | contar no Redis: não é banco de registro; não contar: a cota estoura em silêncio e a descoberta para |
| Fontes remotas no imgproxy | miniaturas e avatares são externos, e a CSP proíbe origens externas em `img-src` | copiar as miniaturas para o MinIO: milhares de objetos para manter; relaxar a CSP: contra o princípio V |
| `location` do upload avulso (2100m) | vídeo inteiro de até 2 GB (limite do OpenShorts) | reusar a rota de cortes de 520 MB: pequena demais para vídeos longos; limite alto em toda a `/api/`: aumenta a superfície de todas as rotas |
