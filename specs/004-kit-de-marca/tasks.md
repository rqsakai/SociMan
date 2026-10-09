---

description: "Tarefas da feature 004-kit-de-marca"
---

# Tasks: Kit de marca por perfil e aplicação nos cortes (004-kit-de-marca)

**Input**: `specs/004-kit-de-marca/` (spec, plan, research R1–R12, data-model, contracts/http-api.md, quickstart)

**Nomes canônicos** (valem os documentos do plano): `SOCIMAN_DATA_DIR`, `DATA_MIN_FREE_GB`, `scripts/data-setup.sh`, `datadir.py`; erros 503 `storage_unavailable` e 507 `storage_full`.

**Tests**: OBRIGATÓRIOS (princípio VI):
- pytest na stack efêmera (`./scripts/test-api.sh`), com ffmpeg real;
- `npm run check:web`;
- e2e de dev (`npm run test:e2e`, que zera o banco de dev);
- a migração do MinIO para o HD verificada (SC-008).

**Organization**: fase 0 (infra do HD), fundação, US1 (kit), US2 (fontes), US3 (exportação),
marca d'água, US4 (cortes) e polish.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 0: Infra do HD (constitution 2.1.0, research R5 e R12). Bloqueia tudo que grava arquivo

- [X] T001 Criar `scripts/data-setup.sh` (POSIX sh, +x) com os subcomandos:
  - `check`: confere que `SOCIMAN_DATA_DIR`, com padrão `/media/sakai/BACKUP/tiktok/sociman`, fica num filesystem diferente de `/` e que o sentinela existe;
  - `init`: cria `minio/`, `work/tmp/`, `work/cortes/` e o sentinela `.sociman-volume`, com dono 1000:1000;
  - `count`: conta os objetos e os bytes de um diretório de dados do MinIO;
  - `migrate`: com o MinIO parado, copia o conteúdo do volume `sociman_minio-data` para `$SOCIMAN_DATA_DIR/minio` com `docker run --rm -v sociman_minio-data:/from:ro -v …:/to alpine cp -a /from/. /to/` e aplica `chown -R 1000:1000`; **nunca apaga o volume antigo**;
  - `verify`: conta antes e depois e checa o `/img` de uma imagem existente.

  Mensagens em pt-BR.
- [X] T002 Criar `apps/api/src/sociman_api/datadir.py` (R5):
  - `status()`: sentinela, total, livre e usado via `os.statvfs` em `settings.data_dir`;
  - `ensure_writable(min_free_gb=settings.data_min_free_gb)`, que levanta `ApiError(503, "storage_unavailable")` sem sentinela e `ApiError(507, "storage_full")` abaixo do piso.

  No `config.py`, acrescentar `hd_path`, `data_min_free_gb` (20), `s3_fonts_bucket` (`sociman-fonts`), `s3_videos_bucket` (`sociman-videos`), `worker_poll_s` e o que mais o plano citar. O `/api/health` ganha `storage: ok|unavailable|full`, sem derrubar o status 200 da API se só o HD estiver fora: o status geral passa a ser `degraded`, mas a API responde. Criar também os testes unitários, com `tmp_path` fazendo o papel de HD.
- [X] T003 Adaptar `apps/api/src/sociman_api/storage.py`:
  - um bucket por tipo (`images` | `fonts` | `videos`);
  - `put_file` (streaming de arquivo), `get_to_file`, `stat`, `get_range`;
  - `ensure_bucket` dos três;
  - **toda escrita passa por `datadir.ensure_writable`**;
  - sem delete.

  As chamadas da 003 (logo e banner) continuam funcionando e passam a responder 503/507 quando o HD falha.
- [X] T004 Compose:
  - `minio`: sai o volume `minio-data`; entra o bind `${SOCIMAN_DATA_DIR:-/media/sakai/BACKUP/tiktok/sociman}` → `/vol` em sintaxe longa com `bind.create_host_path: false`, `user: "1000:1000"` e um entrypoint que falha sem `/vol/.sociman-volume` e roda `minio server /vol/minio --console-address :9001`. A tag da imagem fica fixa, igual à que gerou os dados.
  - `minio-init`: cria `sociman`, `sociman-fonts` e `sociman-videos`.
  - `api`: bind de `/media/sakai` no mesmo caminho com `propagation: rslave` (a API sobe sem o HD e nunca cria a pasta de dados) e `TMPDIR=${SOCIMAN_DATA_DIR}/work/tmp`.
  - O volume `minio-data` continua declarado, mas sem uso, para não ser apagado por `down -v`, com um comentário.
  - `docker-compose.test.yml`: MinIO em tmpfs com os três buckets, e o pytest com tmpfs no caminho de dados mais o sentinela criado no comando.

  Validar com `docker compose config -q`.
- [X] T005 Executar a migração:
  1. `data-setup.sh check`, que deve falhar antes do `init`;
  2. `init`;
  3. `count` no volume antigo;
  4. `docker compose stop minio imgproxy api`;
  5. `migrate`;
  6. `docker compose up -d`;
  7. `count` no HD, que precisa ser igual (SC-008);
  8. `verify`.

  Depois, no banco de dev, recriar dados se precisar e confirmar que um logo da 003 enviado depois abre em `/img` e que o objeto está em `/media/sakai/BACKUP/tiktok/sociman/minio/`. Registrar a saída em `specs/004-kit-de-marca/quickstart.md` (resultado §0).
- [X] T006 Rodar `./scripts/test-api.sh -q` (verde) e `npm run test:e2e` (13/13). Testar à mão a proteção: renomear o sentinela temporariamente faz `docker compose restart minio` falhar e o envio de logo responder 503. Depois restaurar o sentinela

---

## Phase 1: Foundational (DB, tokens, mídia)

- [X] T007 Criar os modelos de `apps/api/src/sociman_api/marca/models.py` (`BrandKit`, `BrandFont`) e de `cortes/models.py` (`Corte` e o enum `corte_status`), conforme data-model.md. O enum `image_kind` ganha `watermark`. Criar a migration `0003_kit_de_marca`, testar downgrade e upgrade no banco de teste, importar em `migrations/env.py` e acrescentar as tabelas novas ao TRUNCATE do `tests/conftest.py`
- [X] T008 [P] Criar `marca/tokens.py`:
  - schema Pydantic `KitTokens`, exatamente com as faixas da spec FR-001–FR-006 e do data-model;
  - `default_kit()`;
  - resolução de `CorRef`/`FonteRef`, que valida as referências à paleta e às fontes.

  Criar os testes unitários.
- [X] T009 [P] Fontes padrão:
  - copiar Anton, NotoSerif-Bold e LiberationSans/Serif-Bold, com as licenças OFL, para `marca/fonts/`, pegando os arquivos de `../openshorts/fonts` e dos pacotes do sistema com as licenças; se algum faltar, baixar de fonte oficial do Google Fonts ou do repositório da fonte e registrar a origem;
  - criar as rotas `GET /api/fontes-padrao` e `GET /api/fontes-padrao/{key}` (sem login, com `Cache-Control`).
- [X] T010 [P] Criar `apps/api/src/sociman_api/midia.py` (R6):
  - links HMAC `/api/midia/{token}` com `exp` opcional (sem validade para fonte e marca d'água; com validade curta para vídeo);
  - streaming com `Range` (206), a partir do MinIO;
  - `POST /api/midia/links` (`RequireUser`);
  - 503 quando o HD falha.

  O edge ganha `location /api/midia/` com `proxy_buffering off`. Criar os testes.

## Phase 2: US1 (P1), kit de marca

- [X] T011 [P] [US1] Criar `tests/integration/test_kit.py`:
  - GET padrão (version 0);
  - PUT válido e inválido (400 no campo certo);
  - `version_conflict`;
  - histórico por seção;
  - revert só pelo dono (403 membro);
  - referência à paleta.
- [X] T012 [US1] Criar `marca/service_kit.py` (get, put, revert e versões com `history.py`) e `marca/router.py` (rotas de kit do contrato, incluindo o export da T019), incluídos em `main.py`. Exportar o OpenAPI
- [X] T013 [US1] SPA: aba **Marca** no detalhe do perfil (`pages/perfis/tabs/MarcaTab.tsx`), com:
  - editor de paleta;
  - seções Legenda, Gancho, Marca d'água, Card final, Bordões e Séries em `SectionCard`;
  - `ColorTokenInput` (hex ou cor da paleta);
  - `KitPreview` em CSS sobre um quadro vertical 9:16 (R7), com legenda, gancho, marca d'água e card, usando as fontes via `FontFace`;
  - salvar com `version`, conflito, e histórico com `VersionHistory` (reverter só dono).

  Regenerar o contrato. `npm run check:web` verde.

## Phase 3: US2 (P1), fontes próprias

- [X] T014 [P] [US2] Criar `tests/integration/test_fontes.py`:
  - TTF e OTF válidos (gerados ou copiados das fontes padrão);
  - `.ttf` falso;
  - mais de 10 MB;
  - nome repetido;
  - `archive` com a fonte em uso dá 409 `font_in_use` com os campos;
  - `restore`;
  - objeto no bucket `sociman-fonts`;
  - 503 sem HD.
- [X] T015 [US2] Criar `marca/fontes.py` (validação pela assinatura mais Pillow `ImageFont.truetype`) e as rotas de fontes do contrato
- [X] T016 [US2] SPA: aba ou seção **Fontes** (lista com amostra "Os achadinhos que você queria", upload, arquivar e restaurar) e o `FontSelect` no kit, com as padrão mais as ativas

## Phase 4: US3 (P1), exportação

- [X] T017 [P] [US3] Testes:
  - `tests/unit/test_openshorts.py`, com o mapeamento dentro das faixas do `SubtitleRequest` (SC-002, parametrizado com kits extremos) e o preset mais próximo por CIELAB;
  - `test_export`: `sociman.kit/1`, `hook.enabled=false`, links sem `exp`, fallback de fonte própria na legenda com aviso.
- [X] T018 [US3] Criar `marca/openshorts.py` e `GET /api/perfis/{id}/kit/export` (`download=1` com `Content-Disposition kit-<slug>-v<n>.json`)
- [X] T019 [US3] SPA: botão "Exportar kit (JSON)" na aba Marca

## Phase 5: Marca d'água (parte de US1/US4)

- [X] T020 [P] Adaptar `imaging.py` com o kind `watermark` (PNG ou WebP com alfa, mínimo 64×64) e criar as rotas `POST`/`GET /api/perfis/{id}/marca-dagua`, com testes. O SPA ganha, na seção Marca d'água do kit, o upload e a escolha entre logo do perfil, imagem própria e texto @

## Phase 6: US4 (P2), aplicar a marca nos cortes

- [X] T021 `apps/api/Dockerfile` ganha o `ffmpeg` (apt, `--no-install-recommends`). O compose ganha o serviço `worker` (mesma imagem, `command: sociman worker`, bind de `/media/sakai` com rslave, `TMPDIR`, depends_on postgres, minio e redis). O `docker-compose.test.yml` ganha o ffmpeg na imagem de teste, que é a mesma do Dockerfile. Rebuild
- [X] T022 [P] [US4] Criar `cortes/probe.py` (ffprobe: duração até 180 s, stream de vídeo, codecs, dimensões; senão `invalid_video` com a razão) e os testes, com vídeos sintéticos gerados por ffmpeg lavfi num fixture
- [X] T023 [P] [US4] Criar `cortes/render.py` (Pillow: PNG do gancho com quebra em até 3 linhas, contorno e fundo com opacidade; marca d'água de logo, imagem ou texto; card final com CTA e logo opcional), com geometria relativa ao tamanho do vídeo, e os testes (dimensões, alfa, texto longo recusado)
- [X] T024 [US4] Criar `cortes/compose.py`: `filter_complex` com `overlay` e `enable='between(t,…)'` para o gancho (0..duração do kit), a marca d'água (o vídeo todo) e o card (os últimos N s, **por cima**, com a duração inalterada); saída MP4 H.264/AAC `+faststart` com a resolução preservada e o áudio copiado ou recodificado; progresso via `-progress pipe:1`; timeout. O texto do usuário nunca vai para a linha de comando. Criar `tests/integration/test_compose.py` com ffmpeg real, extraindo quadros em t=1 s, no meio e no fim e checando pixels nas regiões do gancho, da marca e do card (SC-004), e checar que a duração de saída é igual à de entrada
- [X] T025 [US4] Criar `cortes/queue.py` (claim com `FOR UPDATE SKIP LOCKED`, heartbeat, requeue depois de 120 s parado, até 3 tentativas), `cortes/worker.py` (laço: claim → baixar do MinIO para `${SOCIMAN_DATA_DIR}/work/cortes/{id}` → probe → render → compose → upload do resultado e do pôster → pronto; limpar o work; exigir 3× o tamanho livre no HD) e o comando `sociman worker` na CLI. Testes: fila, requeue e um processamento completo com o worker rodando em thread no teste
- [X] T026 [US4] Criar `cortes/service.py` e `cortes/router.py`:
  - `POST /api/perfis/{id}/cortes` (multipart em streaming: confere o HD e o `Content-Length` antes de ler o corpo; spool em `${SOCIMAN_DATA_DIR}/work/tmp`; probe; `put_file` no bucket de vídeos; grava os tokens do kit resolvidos e a `kitVersion`);
  - lista com cursor;
  - `GET /api/cortes/{id}`;
  - retry;
  - versões;
  - `GET /api/armazenamento`.

  O edge ganha uma `location` exata para o envio de cortes, com `client_max_body_size 520m` e `proxy_request_buffering off`; depois, `docker compose restart edge`. Criar os testes de integração.
- [X] T027 [US4] SPA:
  - aba **Cortes** no perfil: DataTable com data, autor, gancho, versão do kit e status em badge com percentual; uso do HD vindo de `/api/armazenamento`; envio desabilitado sem HD;
  - `CorteUpload`: arquivo e "Texto do gancho", com barra de progresso de upload por XHR e checagem de tipo e tamanho no navegador;
  - `CorteDetalhe`: status com polling de 2 s, `<video>` com link de mídia do resultado e do original, e botões "Baixar" e "Tentar de novo".

  Regenerar o contrato. `npm run check:web` verde.

## Phase 7: Polish e POC

- [X] T028 Criar `e2e/marca.spec.ts`: o dono edita o kit (gancho com cor da paleta) e salva; envia uma fonte; exporta o JSON com `enabled: false`; envia um vídeo sintético pequeno, gerado com ffmpeg no host ou fixture; espera "Pronto" (até 120 s); o `<video>` do resultado carrega
- [X] T029 Atualizar o CLAUDE.md (worker, `data-setup.sh`, buckets, `sociman worker`, `/api/midia`, rota grande no edge) e o `docs/visao.md` (004 implementada)
- [X] T030 Verificação final e POC para o dono:
  - `./scripts/test-api.sh -q`, `npm run check:web` e `npm run test:e2e`, cada um duas vezes;
  - `npm run casa:up && npm run test:e2e:pwa`, e depois voltar ao modo dev;
  - medir a SC-003 (60 s em menos de 2 min) com os arquivos no HD;
  - **POC:** recriar no dev os perfis Queridinhos e A Taverna Nerd com kits preenchidos a partir do Estilo visual de `../shared/perfis/*/perfil.md` (SC-006) e processar um corte real ou sintético de cada um;
  - capturas em `.playwright-mcp/sociman/poc-*.png` e quadros extraídos do vídeo;
  - escrever `docs/poc-004.md` com o que funciona, como testar, as capturas, as medições e as pendências.

## Phase 8: Fundo com imagem no gancho e no card final (FR-005a, FR-005b, pedido do dono depois da POC)

- [X] T031 API:
  - migration `0004_fundo_imagem` com o novo valor `fundo` no enum `image_kind`;
  - `imaging.py` com o kind `fundo` (PNG, JPG ou WebP, mínimo 540×540, sem exigir alfa);
  - rotas `POST` e `GET /api/perfis/{id}/fundos` (como as de marca d'água, 503/507 via datadir);
  - `tokens.py`: `Gancho` e `CardFinal` ganham `fundo_tipo: Literal["cor","imagem"] = "cor"` e `fundo_imagem_id: uuid | None = None`; o `CardFinal` ganha também `opacidade_fundo` (padrão 0.45, só usado com imagem). Com "imagem" e a seção ligada, o id é obrigatório e precisa ser uma imagem kind `fundo` do perfil;
  - `resolve_tokens` e a exportação incluem a imagem (link sem validade).

  Criar os testes (tokens, rotas, exportação).
- [X] T032 Render e worker:
  - `render.py`: `HookStyle` e `EndCardStyle` aceitam `bg_image_path`. A imagem é recortada em cover para a caixa do gancho (cantos arredondados como hoje) ou para o quadro inteiro do card, e a camada `cor_fundo`×opacidade vai por cima, com o texto e o logo acima dela;
  - o worker baixa a imagem de fundo para o work.

  Testes com imagem sintética (pixel da imagem visível sob a camada; texto ainda no lugar) e um compose com quadro final amostrado.
- [X] T033 SPA:
  - nas seções Gancho e Card final da aba Marca, entra o "Tipo de fundo" (Cor ou Imagem) e, com Imagem, o seletor de imagens de fundo com upload (como o `WatermarkImagePicker`) e a "Opacidade da camada";
  - o `KitPreview` mostra a imagem (cover) com a camada.

  Regenerar o contrato. `npm run check:web` verde.
- [X] T034 e2e: estender `e2e/marca.spec.ts` (ou criar `e2e/fundo.spec.ts`): enviar uma imagem de fundo, usar no card final, salvar, exportar (asset presente) e processar um corte; o quadro final mostra a imagem (via extração de quadro pela API ou pelo download).
- [X] T035 Verificação: `./scripts/test-api.sh -q`, `npm run check:web`, `npm run test:e2e` e as capturas. Depois, commit da 004.

## Dependencies
- **T001–T006 bloqueiam** tudo que grava arquivo: T009 (a rota de fontes-padrão não grava e pode andar antes), T010, T015, T020 e T024–T026.
- **T007** bloqueia os serviços; a T008 e a T017 (mapeamento puro) andam em paralelo com a infra.
- **US1:** T011–T013 dependem de T007 e T008.
- **US4:** T021 → T022 e T023 em paralelo → T024 → T025 → T026 → T027.
- **SPA:** T013, T016, T019 e T020 (parte SPA) e T027 ficam com um agente de SPA, porque são arquivos compartilhados do detalhe do perfil.
