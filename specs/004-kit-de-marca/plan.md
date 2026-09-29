# Implementation Plan: Kit de marca por perfil e aplicação nos cortes (004-kit-de-marca)

**Branch**: `004-kit-de-marca` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-kit-de-marca/spec.md`

## Summary

Segunda spec de domínio, precedida de uma tarefa de infra e dividida em duas metades:
- **Infra: o MinIO único vai para o HD** (FR-018, SC-007, SC-008; primeira tarefa):
  - os dados do serviço `minio` existente saem do volume nomeado `minio-data` (NVMe) e vão para
    um bind mount no HD de 4 TB (`/media/sakai/BACKUP/tiktok/sociman/minio`), com os buckets
    `sociman` (imagens), `sociman-fonts` e `sociman-videos`;
  - temporários de upload e do worker/ffmpeg em `…/sociman/work`; no NVMe ficam só código,
    containers, PostgreSQL e Redis;
  - sentinela `.sociman-volume` e piso de espaço livre para toda gravação no HD;
  - `scripts/hd-setup.sh` cria a estrutura, migra os objetos da 003 e verifica (R12).
- **Kit de marca em tokens** (US1–US3, P1):
  - um kit por perfil (paleta, legenda, gancho, marca d'água, card final, bordões e séries),
    validado por schema Pydantic e guardado em JSONB por seção;
  - histórico, reversão e controle otimista pelo `entity_versions` da 003;
  - fontes próprias TTF/OTF no bucket `sociman-fonts`, validadas com Pillow, arquivadas e nunca apagadas;
  - prévia só no navegador (CSS), com a mesma geometria do gerador de cortes;
  - exportação `sociman.kit/1`, com a seção `openshorts` (parâmetros de legenda exatos e o
    gancho desligado, com o preset mais próximo por distância de cor em CIELAB só como
    referência) e links de fonte e marca d'água assinados sem validade.
- **Aplicação da marca num corte** (US4, P2):
  - upload de até 500 MB por uma rota própria no edge, com spool em `work/` e streaming para o
    bucket `sociman-videos`, tudo no HD;
  - validação com ffprobe;
  - fila na tabela `cortes` (`FOR UPDATE SKIP LOCKED`), processada por um serviço `worker` com a
    mesma imagem da API;
  - camadas renderizadas como PNG com Pillow e compostas num único `ffmpeg` com `overlay`, com o
    card final por cima dos últimos segundos (18 s para 60 s de vídeo em 1080×1920, medido no
    host);
  - resultado em MP4 H.264/AAC, visto e baixado por links assinados com suporte a `Range`.

Detalhes em [research.md](research.md), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md) e [quickstart.md](quickstart.md). As quatro
perguntas ao dono foram respondidas em 2026-09-29 e estão nas Clarifications da spec.

## Technical Context

**Language/Version**: Python 3.12 (API e worker) · TypeScript 5 / React 19 (SPA)

**Primary Dependencies**:
- **nenhuma dependência Python nova:** Pillow (fontes, camadas PNG), minio (upload multipart,
  `get_object` com offset) e python-multipart já estão na 003;
- **na imagem da API:** o pacote `ffmpeg` do Debian (`apt-get install --no-install-recommends
  ffmpeg`), que traz também o `ffprobe`;
- **no SPA:** nenhuma nova (shadcn/ui e TanStack Query da 005; `FontFace` e `<video>` são do
  navegador).

**Storage**: PostgreSQL (`brand_kits`, `brand_fonts`, `cortes`, `images` com o novo kind
`watermark`, `entity_versions`), no NVMe; **MinIO único com os dados no HD** (`SOCIMAN_HD_DIR` =
`/media/sakai/BACKUP/tiktok/sociman`, pasta `minio/`), com os buckets `sociman` (logos, banners,
marca d'água, pôsteres), `sociman-fonts` e `sociman-videos`; temporários em `work/` no mesmo HD
(R5)

**Testing**:
- pytest na stack efêmera, com **ffmpeg real** e vídeos sintéticos `lavfi` gerados no teste;
- amostragem de quadros para a SC-004; teste de faixas para a SC-002;
- ruff; `check:web` (contrato regenerado);
- Playwright `e2e/marca.spec.ts` (modo dev, com o worker).

**Target Platform**: a mesma stack, com o serviço novo `worker` e o `minio` com os dados no HD; o SPA também no modo casa (PWA)

**Project Type**: web application (SPA + API + worker)

**Performance Goals**:
- SC-003: corte de 60 s em menos de 2 min em CPU (medido: 18 s em vídeo sintético, com arquivos
  no NVMe; refazer a medição com `work/` e o MinIO no HD);
- prévia do kit a cada tecla sem requisição;
- upload de 500 MB limitado só pela rede de casa.

**Constraints**:
- sem DELETE e sem apagar objeto (SC-005);
- um corte por vez (FR-014);
- a CSP não muda (`media-src` e `font-src` herdam `'self'`; nada de `blob:`);
- o limite de 520 MB vale só na rota de envio de cortes;
- a porta S3 do MinIO continua fechada (o console 9101 segue só para dev);
- **disco (regra da constitution 2.1.0):** tudo o que é pesado ou cresce sem parar fica no HD
  (2,1 TB livres); o NVMe (101 GB livres) fica só com código, containers, PostgreSQL e Redis.
  Nada de vídeo no `/tmp` dos containers. Sem o sentinela `.sociman-volume`, nada é gravado, e
  gravações são recusadas com menos de `HD_MIN_FREE_GB` (20) livres (FR-018);
- **HD fora = mídia fora:** sem o HD, `minio`, `api` e `worker` não sobem (`create_host_path:
  false`); risco aceito pelo dono ao ficar com um MinIO só;
- nada publica em rede social (princípio I).

**Scale/Scope**: 2 perfis hoje (até ~10); ~15 cortes por dia; 23 endpoints; 3 abas novas no
detalhe do perfil (Marca, Fontes, Cortes) e a tela do corte

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|---|---|---|
| I. Nenhum agente publica | ✅ | o resultado só vai para o MinIO e para download; nenhuma credencial ou rota de rede social; o teste-guarda da 001 passa a cobrir `cortes` e `marca` |
| II. Direito primeiro | n/a (registrado) | o corte chega por upload do dono, sem vínculo com canal-fonte. A verificação de direito do canal entra quando o corte vier do fluxo dos agentes (specs 008/009). **Risco:** até lá, o SociMan aceita qualquer vídeo que o usuário enviar; a responsabilidade é de quem envia, como no fluxo manual de hoje |
| III. Marca em tokens | ✅ **núcleo desta spec** | todo item do kit é campo validado (faixas, enums, cores hex ou referência à paleta, fontes por referência); texto livre só em bordões, séries e CTA; o worker e a exportação consomem os mesmos tokens resolvidos; a SC-004 confere o resultado por máquina |
| IV. Contrato é a fonte única | ✅ | rotas novas regeneram o contrato (`check:contract`); o JSON de exportação tem schema Pydantic no OpenAPI |
| V. Segurança e segredos | ✅ | vídeo e fonte validados pelo conteúdo (ffprobe com `-protocol_whitelist file`, assinatura + FreeType); texto do usuário nunca vai para a linha de comando do ffmpeg (vira PNG); links de mídia assinados com HMAC (1 h na interface; sem validade só para fonte e marca d'água na exportação, nunca para vídeo); os buckets continuam privados; o limite de 520 MB só numa `location`; a CSP não muda |
| VI. Testes antes de pronto | ✅ | quickstart §0, §5 e §6: migração verificada (SC-008), ffmpeg real, amostragem de quadros, faixas do gerador, fila com worker morto, sentinela e espaço mínimo (SC-007), e2e |
| VII. Humano no controle | ✅ | kit e fontes com versão, autor e antes/depois; reversão do kit só pelo dono; fontes arquivadas, nunca apagadas; corte com autor e versão no envio e no "tentar de novo"; nenhum vídeo apagado |
| VIII. Simplicidade | ✅ com justificativa | um serviço novo (`worker`), o ffmpeg na imagem e o `minio` existente movido para o HD, sem segundo MinIO (tabela abaixo); fila no Postgres sem Redis/RQ; nenhuma dependência Python nova; prévia em CSS sem render no servidor |

**Constitution 2.1.0:** a regra "pesado no HD, NVMe só com código, PostgreSQL e Redis" entra
na constitution 2.1.0 (emenda do dono). Este plano já a segue; o check deve ser refeito contra a
2.1.0 quando ela for ratificada.

**Reavaliação pós-design:** mantida. O design não introduziu nada além da tabela de
complexidade. Fora do escopo, de propósito: stickers, reprocessar um corte com outro gancho sem
reenviar, paralelismo, aceleração por GPU e busca automática de cortes no OpenShorts.

## Project Structure

### Documentation (this feature)

```text
specs/004-kit-de-marca/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── Dockerfile                             # + apt-get install --no-install-recommends ffmpeg
├── migrations/versions/0003_kit_de_marca.py
├── src/sociman_api/
│   ├── config.py                          # + S3_FONTS_BUCKET, S3_VIDEOS_BUCKET, HD_PATH (/hd), HD_MIN_FREE_GB, WORKER_POLL_S, MIDIA_LINK_TTL_S
│   ├── storage.py                         # bucket por tipo (imagens | fontes | videos) + put_file, get_to_file, stat, get_range; toda escrita passa por hd.ensure_writable (sem delete)
│   ├── imaging.py                         # + kind "watermark" (exige alfa, mínimo 64×64)
│   ├── midia.py                           # links assinados (HMAC) + streaming com Range (R6)
│   ├── hd.py                              # sentinela + os.statvfs + piso; usado pelo storage, pelo envio, pelo worker e pelo /api/health
│   ├── cli.py                             # + comando `worker`
│   ├── marca/
│   │   ├── fonts/                         # Anton, NotoSerif-Bold, LiberationSans/Serif-Bold + licenças OFL
│   │   ├── models.py                      # BrandKit, BrandFont
│   │   ├── tokens.py                      # schema KitTokens, kit padrão, resolução de CorRef/FonteRef
│   │   ├── openshorts.py                  # SubtitleRequest, preset mais próximo (CIELAB), aproximações
│   │   ├── fontes.py                      # validação (assinatura + Pillow) e serviço de fontes
│   │   ├── service_kit.py                 # get/put/revert/export (history.py)
│   │   ├── schemas.py
│   │   └── router.py
│   ├── cortes/
│   │   ├── models.py                      # Corte (+ enum corte_status)
│   │   ├── probe.py                       # ffprobe → metadados ou invalid_video
│   │   ├── render.py                      # Pillow: PNG do gancho (quebra ≤ 3 linhas), marca d'água, card
│   │   ├── compose.py                     # filter_complex, execução do ffmpeg, progresso, timeout
│   │   ├── queue.py                       # claim (SKIP LOCKED), heartbeat, requeue, retry
│   │   ├── worker.py                      # laço do worker
│   │   ├── service.py                     # envio (HD, probe, bucket sociman-videos, linha), lista, retry
│   │   ├── schemas.py
│   │   └── router.py
│   └── main.py                            # inclui routers
└── tests/
    ├── unit/                              # tokens, openshorts (SC-002), render, compose (string), midia
    └── integration/                       # kit, fontes, marca d'água, cortes (ffmpeg real, SC-004), fila, Range

apps/web/src/
├── pages/perfis/tabs/{MarcaTab,FontesTab,CortesTab}.tsx
├── pages/cortes/CorteDetalhe.tsx
├── components/marca/{KitPreview,ColorTokenInput,FontSelect,PaletteEditor,SectionCard}.tsx
├── components/cortes/{CorteUpload,CorteStatusBadge}.tsx
└── lib/{marca,cortes,fontFaces}.ts        # rótulos, formulários, registro de FontFace, upload com XHR

docker/nginx/default.conf.template         # location da rota de cortes (520m, sem buffering) e /api/midia/ (streaming)
docker-compose.yml                         # minio: sai o volume minio-data; bind SOCIMAN_HD_DIR → /vol (create_host_path: false),
                                           #   user 1000, entrypoint confere o sentinela e roda `minio server /vol/minio`;
                                           #   minio-init cria sociman, sociman-fonts e sociman-videos;
                                           #   api e worker: bind SOCIMAN_HD_DIR → /hd (create_host_path: false), TMPDIR=/hd/work/tmp;
                                           #   worker novo (mesma imagem, `sociman worker`)
docker-compose.test.yml                    # MinIO em tmpfs com os 3 buckets de teste + tmpfs em /hd no pytest
scripts/hd-setup.sh                        # R12: confere o HD, cria minio/ work/ e o sentinela, migra minio-data, verifica
e2e/marca.spec.ts
```

**Structure Decision**: dois pacotes de domínio, `marca/` (kit, fontes, exportação) e `cortes/`
(envio, fila, processamento), porque a segunda metade tem ciclo de vida e testes próprios e pode
ser entregue depois (P2). `midia.py` fica na raiz do pacote, como `storage.py` e `imaging.py`,
porque vídeos, fontes e, no futuro, avatares e cenas (specs futuras) usam os mesmos links
assinados. O SPA segue a estrutura da 005 (`components/ui` do shadcn, DataTable para a lista de
cortes); as abas novas entram no detalhe do perfil da 003.

**Ordem sugerida para o `/speckit-tasks`:** (0) **infra, antes de tudo:** `hd-setup.sh`,
migração do `minio-data` para o HD, troca do compose, `hd.py` no `storage.py` e verificação
(imagens da 003 abrindo em `/img`, contagem de objetos igual, `test:api` e `test:e2e` verdes,
R12); (1) tokens, kit e histórico; (2) fontes; (3) exportação; (4) prévia no SPA; (5) ffmpeg na
imagem, worker e fila; (6) render e compose com
amostragem de quadros; (7) upload no edge e links de mídia; (8) telas de cortes e e2e. As fases
1 a 4 fecham as US P1 e podem ir para o dono antes da US4.

## Complexity Tracking

| Item | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| Serviço `worker` no compose | FR-014: processamento em segundo plano, um por vez, que sobrevive a reinício; isola ~1 GB de RAM e CPU do ffmpeg da API | thread ou `BackgroundTasks` na API: morrem com o processo e com o `--reload`; RQ/Celery: dependência nova e Redis como dado de registro |
| `ffmpeg` na imagem da API | compor o vídeo (FR-015) e validá-lo (ffprobe, US4-4) | usar o OpenShorts: sem marca d'água por perfil, sem card final e só 6 ganchos fixos |
| Fila em tabela Postgres | durável, na mesma transação do corte, sem dependência | Redis: não é banco de registro (constitution) |
| Links de mídia assinados (`midia.py`) | `<video>`, download e `@font-face` não mandam o Bearer | cookie de sessão: quebra o padrão cookieless; `blob:`: 500 MB em memória e muda a CSP |
| `location` própria no edge (520m, sem buffering) | aceitar 500 MB só onde precisa | limite alto em toda a `/api/`: aumenta a superfície de todas as rotas |
| Dados do `minio` no HD (bind mount) + migração | FR-016 proíbe apagar; o NVMe tem 101 GB livres e ~1,5 GB/dia de vídeo o encheria em ~2 meses (decisão do dono) | segundo MinIO só para vídeos: duas instâncias e dois clientes; cota no NVMe: rejeitada pelo dono |
| Sentinela + piso de espaço (`hd.py`) | com o HD desmontado, o Docker criaria a pasta no NVMe e encheria o disco do sistema (FR-018, SC-007) | só `create_host_path: false`: não cobre uma pasta vazia deixada no ponto de montagem |
