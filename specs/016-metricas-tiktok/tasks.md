---

description: "Tarefas da feature 016-metricas-tiktok"
---

# Tasks: Métricas do TikTok para análise e machine learning (016-metricas-tiktok)

**Input**: `specs/016-metricas-tiktok/` (spec, plan, research R1–R20, data-model, contracts/http-api.md, quickstart, open-questions resolvidas)

**Pré-requisito:** a **015 concluída** (`specs/015-tiktok-rascunho/tasks.md` fechado; `alembic heads` = `0010_publicacao_tiktok`). A 016 altera arquivos da 015 (`publicacao/{conexoes,schemas,router,executor,registro,limites}.py`, `publicacao/tiktok/{cliente,executor}.py`, `components/publicacao/ConexaoCard.tsx`) e da 014 (`postagem/service.py`, `components/conteudos/DestinoPanel.tsx`), então nenhuma tarefa daqui começa antes do T001.

**Decisões do dono (2026-09-30, spec → Clarifications; todas A):** Q1 = A (a anonimização guarda só características não textuais: origem, modo, nota, status do canal, duração, hora e dia, intervalo desde o post anterior, seguidores na publicação, **tamanho** do gancho e **número** de hashtags), Q2 = A (vídeos com mais de 1 ano entram com uma foto, a da descoberta, e param), Q3 = A (lembrete: liga sozinho só depois de "Marcar como postado", com a âncora na hora do clique — post até 24 h antes ou 1 h depois — e a mesma regra de duração, legenda e candidato único; antes do clique, candidatos para o dono escolher em 1 clique), Q4 = A (só PostgreSQL, sem banco novo; pausa da coleta por `METRICAS_COLETA_HABILITADA=false` no `.env`).

**Nomes canônicos** (valem os documentos do plano): pacote novo `sociman_api/metricas/` (`models`, `agenda`, `coleta`, `vinculos`, `casamento`, `anonimizar`, `consulta`, `dicionario`, `export`, `schemas`, `router`), genérico e sem HTTP; leitor da rede em `publicacao/tiktok/leitor.py` (`LeitorTikTok`), alcançado **só** por `publicacao/registro.py::leitor_para`; `LEITURA_016` em `publicacao/tiktok/cliente.py`; migration `0011_metricas_tiktok` (`down_revision = "0010_publicacao_tiktok"`); enum novo `vinculo_metodo`; `actor_kind` novo `system:metricas`; trilha do agendador `metricas`; notificações `post_detectado`, `vinculo_a_confirmar`; `details.acao` novos `ampliada`, `metricas_anonimizadas` (conexão) e `vinculo_feito`, `vinculo_desfeito` (destino); função `postagem/service.py::publicacao_pelo_vinculo`; `operationId` com prefixos `metricas_*`, `destinos_*`, `conexoes_*`; SPA `/app/metricas`, `/app/metricas/videos/:id`, componentes em `components/metricas/`.

**Tests**: OBRIGATÓRIOS (constitution, princípios I, VI e VII):
- pytest na stack efêmera (`npm run test:api [-- args]`), **sempre com a TikTok falsa** (`tests/fakes/tiktok_fake.py`);
- `docker compose exec api uv run ruff check .`;
- `npm run gen:contract && npm run check:web` (contrato regenerado, CSP igual, `check:secrets`);
- e2e na stack isolada, **sempre com trava**: `flock /tmp/sociman-e2e.lock npm run test:e2e [-- e2e/metricas.spec.ts]` (armadilha 18: nunca dois e2e ao mesmo tempo, nem com outra spec);
- **nenhum teste automatizado chama a TikTok real**; o teste real é com o dono (Phase 7).

**Segredos (princípio V):** nenhum agente roda `cat .env` nem imprime valores. Para conferir se uma variável existe, só o nome: `grep -oE '^(TIKTOK_SCOPES|METRICAS_COLETA_HABILITADA|AGENDADOR_METRICAS_S)=' .env`. O `TIKTOK_SCOPES` não é segredo e pode ser lido (`grep -E '^TIKTOK_SCOPES=' .env`). As consultas ao banco de dev só imprimem contagens, nunca `rede_video_id`, `share_url`, `legenda` nem `post_id`.

**Restrições do data-model (citadas literalmente; valem na migration, nos modelos e nos serviços):**
- Geral: "As tabelas `metricas_*` são observações da rede, escritas pela trilha `metricas` (`system:metricas`) e, no vínculo manual, pelas rotas **H**. Não têm `version`/`history` próprios (exceção justificada no plan, princípio VII). O histórico do vínculo fica no **destino** (`entity_type = "postagem"`), e o da anonimização fica na **conexão** (`entity_type = "conexao"`)"; "As fotos são **só de inserção**, com trigger no banco (research R7)"; "`actor_kind` novo: **`system:metricas`**".
- Enum: "`vinculo_metodo`: `envio` (post id do `status/fetch` ou do post direto da 015) · `casamento` (lista: data, duração e legenda) · `link` (link colado pelo dono) · `escolha` (o dono escolheu um candidato)".
- `metricas_series`: "`ck_metricas_series_anonima`: `(anonimizada_em IS NULL) = (conta_id IS NOT NULL)`, e `anonimizada_em IS NULL OR (rotulo IS NOT NULL AND anonima_n IS NOT NULL)`"; "`uq_metricas_series_conta_viva (conta_id) WHERE anonimizada_em IS NULL`: uma série viva por conta"; "`ix_metricas_series_ativas (lista_proxima_em) WHERE anonimizada_em IS NULL`"; "sequência `metricas_anonima_seq`". "**Série ativa** (derivado): `anonimizada_em IS NULL`, a conta com conexão `conectada`, `metricas_liberadas(conexao)`, `sem_permissao_desde IS NULL` e `METRICAS_COLETA_HABILITADA`".
- `metricas_videos`: `rede_video_id` "o `id` da TikTok como texto (pode passar de 2^53); `NULL` depois de anonimizado"; `publicado_em` "`create_time`; truncado para a hora ao anonimizar"; `proxima_coleta_em` "a fila (R4); `NULL` = parou (mais de 365 d ou anonimizado)"; `vinculado_por` "`NULL` quando foi automático (`system:metricas`)"; `vinculo_automatico` "false depois que o dono desfaz (R11): não se liga mais sozinho"; `features` "características **congeladas** na anonimização (R13); `NULL` antes dela". Regras: "`uq_metricas_videos_rede_id (serie_id, rede_video_id) WHERE rede_video_id IS NOT NULL`"; "`uq_metricas_videos_destino (destino_id) WHERE destino_id IS NOT NULL`: um vídeo por destino"; "`ck_metricas_videos_vinculo`: `(destino_id IS NULL) = (vinculo_metodo IS NULL)` e `destino_id IS NULL OR vinculado_em IS NOT NULL`"; "`ck_metricas_videos_anonimo`: `anonimizado_em IS NULL OR (rede_video_id IS NULL AND share_url IS NULL AND legenda IS NULL AND titulo IS NULL AND destino_id IS NULL AND vinculado_por IS NULL AND proxima_coleta_em IS NULL AND features IS NOT NULL)`"; "`ck_metricas_videos_indisponivel`: `disponivel OR indisponivel_desde IS NOT NULL`"; "`ix_metricas_videos_fila (proxima_coleta_em) WHERE proxima_coleta_em IS NOT NULL`"; "`ix_metricas_videos_serie_pub (serie_id, publicado_em DESC, id DESC)` (ranking e casamento)"; "o vínculo só pode ligar a um destino **da mesma conta** da série. Um CHECK não cruza tabelas, então isso é conferido no service, com teste".
- `features` (Q1 = A): "`origem` (`corte`, `video_proprio` ou `fora`) e `modo_envio` (`lembrete`, `criar_rascunho`, `publicar` ou null); `vinculo_metodo` e `score` (int ou null); `canal_status_direito` (`proprio`, `parceiro`, `programa_de_cortes`, `sem_acordo` ou null); `duracao_s`, `hora_local` e `dia_semana` (0 = segunda); `intervalo_post_anterior_h` e `seguidores_na_publicacao`; `gancho_caracteres` e `hashtags_n`".
- `metricas_video_fotos`: `idade_s` "`coletado_em − publicado_em` real (≥ 0)"; `fonte` "`display` (a 016); `business` fica reservado para a etapa 2". Regras: "`uq_metricas_video_fotos_janela (video_id, alvo_idade_min)`: uma foto por vídeo por janela (`ON CONFLICT DO NOTHING`)"; "`ix_metricas_video_fotos_idade (video_id, idade_s)`"; "`ix_metricas_video_fotos_coletado (coletado_em)`"; "`ck_metricas_video_fotos_idade`: `idade_s >= 0 AND alvo_idade_min >= 0`"; "`ck_metricas_video_fotos_fonte`: `fonte IN ('display','business')`"; "os contadores ficam `NULL` quando a TikTok omite o campo, e são gravados como vieram, inclusive quando caem"; "**trigger `metricas_so_insercao`** (`BEFORE UPDATE OR DELETE ... FOR EACH ROW EXECUTE FUNCTION metricas_recusa_mudanca()`), que levanta `'metricas: fotos são só de inserção'`".
- `metricas_conta_fotos`: `janela_em` "a hora cheia (modo horário) ou 00:00 de SP (diário), R6"; "`uq_metricas_conta_fotos_janela (serie_id, janela_em)`"; "o mesmo trigger `metricas_so_insercao`".
- `metricas_buscas_post`: `tentativa_id` "a tentativa `entregue` (o `publish_id` fica lá e não é copiado)"; `post_id` "`publicaly_available_post_id`; `NULL` depois de anonimizada"; "`ck_metricas_buscas_fim`: `(encerrada_em IS NULL) = (fim IS NULL)` e `encerrada_em IS NULL OR proxima_em IS NULL`"; "`ck_metricas_buscas_fim_valor`: `fim IS NULL OR fim IN ('vinculado','prazo','falhou','desfeito','anonimizada','cancelada')`"; "`ix_metricas_buscas_fila (proxima_em) WHERE encerrada_em IS NULL`".
- Tabelas existentes: `notificacao_tipo` "+ `post_detectado` (rascunho virou post e foi vinculado) e `vinculo_a_confirmar` (casamento ambíguo), para os donos ativos, com `dedupe_key` por destino"; `postagens` "**nenhuma coluna**. O vínculo mora em `metricas_videos.destino_id`"; `conexoes` "nenhuma coluna; `details.acao` ganha `ampliada` e `metricas_anonimizadas`".
- Âncora e bloqueio (Q3 = A): "`criar_rascunho` com busca (`rascunho_criado` ou `postado`) | `metricas_buscas_post.entregue_em` | `−5 min` a `+14 d`"; "`lembrete` em `postado` | `postagens.posted_at` (o clique \"Marcar como postado\") | `−24 h` a `+1 h`"; "`lembrete` em `aprovado`/`agendado` | nenhuma (só candidatos para o dono)"; "**Bloqueio do destino:** existe versão do destino com `details.acao = \"vinculo_desfeito\"`".
- Histórico: "vínculo feito (auto ou dono) | `postagem`, `action = \"updated\"` (before/after com o estado) | `{acao: \"vinculo_feito\", metodo, automatico}`, **sem** id nem link da TikTok"; "vínculo desfeito | `postagem`, `\"updated\"` | `{acao: \"vinculo_desfeito\", metodo_anterior}`"; "escopos ampliados | `conexao`, `\"updated\"` | `{acao: \"ampliada\"}`"; "métricas anonimizadas | `conexao`, `\"updated\"` | `{acao: \"metricas_anonimizadas\", videos, fotos}`"; "A reversão genérica do destino **não** restaura o vínculo nem os estados de execução (regra da 015)".
- Migration: upgrade "`CREATE TYPE vinculo_metodo`; `ALTER TYPE notificacao_tipo ADD VALUE IF NOT EXISTS` `'post_detectado'` e `'vinculo_a_confirmar'`; `CREATE SEQUENCE metricas_anonima_seq`; as 5 tabelas, com CHECKs e índices; `CREATE FUNCTION metricas_recusa_mudanca() RETURNS trigger` (`RAISE EXCEPTION`) e os 2 triggers"; "Não há backfill"; downgrade "`DROP TRIGGER`/`DROP FUNCTION`; `DROP TABLE` das 5 tabelas, na ordem das FKs; `DROP SEQUENCE` e `DROP TYPE vinculo_metodo`; `notificacao_tipo` recriado sem os 2 valores, no padrão da 0007 e da 0010".

**Arquivos compartilhados: SÓ ACRÉSCIMO** (bloco novo ao lado dos vizinhos, sem reordenar): `apps/api/src/sociman_api/main.py`, `apps/api/migrations/env.py`, `apps/api/tests/conftest.py`, `apps/api/src/sociman_api/agendador.py`, `apps/api/src/sociman_api/config.py`, `apps/web/src/App.tsx`, `apps/web/src/components/shell/nav.ts`, `apps/web/src/lib/notificacoes.ts`, `e2e/helpers.ts`, `CLAUDE.md`, `docs/visao.md`. `packages/contract/**` é **gerado** (armadilha 6): em conflito, rebase e `npm run gen:contract` de novo.

**Não mexer:** `specs/014-central-de-conteudos/**` e `specs/015-tiktok-rascunho/**` (só leitura). Não rodar `setup-tasks.sh`; `.specify/feature.json` já aponta para a 016.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1–US5 da spec
- **[DONO]**: passo manual do dono (o agente mostra o comando e espera)

---

## Phase 1: Setup (pré-requisito, linha de base, backup e variáveis)

- [ ] T001 **Gate da 015:** conferir que `docker compose exec api uv run alembic heads` mostra `0010_publicacao_tiktok`, que o `git status` não tem trabalho da 015 pendente e que `.specify/feature.json` aponta para `specs/016-metricas-tiktok`. Só então o líder cria o branch `016-metricas-tiktok` a partir do branch com a 015 (commit só quando o dono pedir).
- [X] T002 Linha de base no dev, **antes** de subir código novo (só contagens): `select modo, estado, count(*) from postagens group by 1,2;`, `select estado, count(*) from conexoes group by 1;`, `select count(*), md5(string_agg(id::text, ',' order by id)) from entity_versions;` e `select tipo, count(*) from notificacoes group by 1;`. Guardar a saída no relatório da tarefa (não no repositório).
- [X] T003 **Backup do banco de dev antes da migration `0011_metricas_tiktok`** (a 0011 cria 5 tabelas e mexe em `notificacao_tipo`; quickstart §0.1): `mkdir -p /media/sakai/BACKUP/tiktok/sociman/backups` e `docker compose exec -T postgres pg_dump -U sociman -Fc sociman > /media/sakai/BACKUP/tiktok/sociman/backups/pre-0011.dump` (HD, fora do git e do MinIO; sem o sentinela `.sociman-volume`, usar o scratchpad da sessão). Conferir tamanho > 0 e `docker compose exec -T postgres pg_restore -l < /media/sakai/BACKUP/tiktok/sociman/backups/pre-0011.dump | grep -c "TABLE DATA"` > 0. **Nunca no repositório.** Apagar só no T094.
- [X] T004 [P] `apps/api/src/sociman_api/config.py` (acréscimo): `metricas_coleta_habilitada` (bool, padrão `true`), `agendador_metricas_s` (int, padrão `60`) e o padrão de `tiktok_scopes` com `user.info.stats,video.list` no fim (`user.info.basic,user.info.profile,video.upload,video.publish,user.info.stats,video.list`; contrato, "Variáveis de ambiente").
- [X] T005 [P] `docker-compose.yml`: `METRICAS_COLETA_HABILITADA` e `AGENDADOR_METRICAS_S` em `api` e `agendador` (nada no `worker`); `docker-compose.test.yml`: `METRICAS_COLETA_HABILITADA=true` (os testes desligam por override de `Settings`).
- [ ] T006 [DONO] **Portal e escopos** (quickstart §0.2 e §0.3): o dono confere no portal da TikTok (app no Sandbox) que `user.info.stats` e `video.list` estão ligados; o agente mostra `grep -E '^TIKTOK_SCOPES=' .env || echo "sem TIKTOK_SCOPES no .env (vale o padrão)"`. Se a linha existir sem os dois escopos, **o dono** acrescenta os dois na mesma linha. **Registrar** em `quickstart.md` (Resultado): escopos no sandbox `sim/não` e a linha do `.env` conferida. Não bloqueia as fases 2 a 6 (usam o fake).

---

## Phase 2: Foundational (modelo, migration, trigger, leitor, fake e guardas)

**⚠️ Bloqueia todas as histórias.**

- [X] T007 Criar `apps/api/src/sociman_api/metricas/__init__.py` (docstring: "métricas das redes, só leitura (princípio I); genérico, sem HTTP; chega ao leitor só por `publicacao.registro.leitor_para`") e `metricas/models.py` com `VinculoMetodo`, `Serie`, `VideoRede`, `FotoVideo`, `FotoConta`, `BuscaPost`: todas as colunas, CHECKs, índices únicos, índices parciais e a sequência citados acima. Nenhum `__versioned_fields__` (exceção do princípio VII no plan).
- [X] T008 [P] `apps/api/src/sociman_api/notificacoes/models.py`: os tipos `post_detectado` e `vinculo_a_confirmar`.
- [X] T009 Criar `apps/api/migrations/versions/0011_metricas_tiktok.py` (`revision = "0011_metricas_tiktok"`, `down_revision = "0010_publicacao_tiktok"`) na ordem do data-model ("Migration `0011_metricas_tiktok`", upgrade 1 a 4): `ADD VALUE IF NOT EXISTS` em bloco `autocommit` do Alembic (como na 0010); `vinculo_metodo`; sequência; as 5 tabelas; função `metricas_recusa_mudanca()` + trigger `metricas_so_insercao` `BEFORE UPDATE OR DELETE ... FOR EACH ROW` nas duas tabelas de fotos. `downgrade` (docstring "só dev") na ordem inversa, com `DELETE FROM notificacoes WHERE tipo::text IN ('post_detectado','vinculo_a_confirmar')` e o tipo recriado sem os 2 valores (padrão da 0007/0010).
- [X] T010 Acréscimos: `apps/api/migrations/env.py` (import de `metricas.models`); `apps/api/tests/conftest.py` (bloco "Spec 016": `TRUNCATE` das 5 tabelas `metricas_*` na limpeza, na ordem das FKs — o trigger de linha não dispara no `TRUNCATE`, research R7); `apps/api/src/sociman_api/agendador.py::_registrar_modelos` (import de `metricas.models`).
- [X] T011 Criar `apps/api/tests/integration/test_migration_0011.py` (como `test_migration_0010.py`): descer a `0010_publicacao_tiktok`, semear conexões (`conectada`, `precisa_reconectar`, `desconectada`) e destinos em todos os estados da 015 com versões; subir e conferir: nenhum destino nem conexão mudou, `entity_versions` idêntica (contagem e hash); cada CHECK recusa com `INSERT`/`UPDATE` direto (`ck_metricas_series_anonima`, `ck_metricas_videos_vinculo`, `ck_metricas_videos_anonimo`, `ck_metricas_videos_indisponivel`, `ck_metricas_video_fotos_idade`, `ck_metricas_video_fotos_fonte`, `ck_metricas_buscas_fim`, `ck_metricas_buscas_fim_valor`, os dois `UNIQUE` de janela, `uq_metricas_series_conta_viva`, `uq_metricas_videos_destino`); **o trigger recusa `UPDATE` e `DELETE`** nas duas tabelas de fotos com a mensagem `metricas: fotos são só de inserção`, e o `TRUNCATE` continua funcionando. Descer (as notificações dos 2 tipos saem, o resto fica) e **subir de novo** (`IF NOT EXISTS`). Ajustar os testes de migration anteriores que sobem para `head`, sem mudar o que verificam.
- [X] T012 [P] `apps/api/src/sociman_api/publicacao/tiktok/cliente.py`: `LEITURA_016 = frozenset({("POST", "/v2/video/list/"), ("POST", "/v2/video/query/")})` e `ALLOWED = <R21> | LEITURA_016` (as listas só crescem por spec). Ajustar `apps/api/tests/unit/test_tiktok_cliente.py` (os dois caminhos novos passam; qualquer outro continua recusado) e `apps/api/tests/integration/test_trilha_publicacao.py` só onde ele compara o `ALLOWED`.
- [X] T013 [P] `apps/api/src/sociman_api/publicacao/executor.py`: `Protocol LeitorRede` (`stats_conta`, `listar`, `consultar`, `post_publicado`) e os tipos `VideoLido` (`id: str`, `criado_em`, `url`, `legenda`, `titulo`, `duracao_s`, `largura`, `altura`, contadores opcionais), `StatsConta`, `PostId`/`Pendente`/`Falhou`, `SemPermissaoLeitura` (erro tipado para `scope_not_authorized`); `publicacao/registro.py`: `leitor_para(platform) -> LeitorRede | None` (acréscimo, sem mexer em `executor_para`).
- [X] T014 Criar `apps/api/src/sociman_api/publicacao/tiktok/leitor.py` (`LeitorTikTok`, research R2): 4 métodos pelo cliente com `ALLOWED`; `user/info` com `fields=open_id,follower_count,following_count,likes_count,video_count`; `video/list` e `video/query` com `fields=id,create_time,share_url,video_description,title,duration,width,height,view_count,like_count,comment_count,share_count` (**sem** `cover_image_url` e `embed_html`); `video/query` com no máximo 20 ids; `status/fetch` → `PostId(publicaly_available_post_id)` / `Pendente(status)` / `Falhou(codigo)`; `id` sempre convertido para `str`; `scope_not_authorized` (e `access_token_invalid` só num endpoint de leitura) → `SemPermissaoLeitura`, sem mudar a conexão (R1). Logs só com método, caminho e status (nunca legenda, link nem token). `publicacao/tiktok/executor.py`: atributo `leitor` (nada muda no envio).
- [X] T015 [P] `apps/api/src/sociman_api/publicacao/limites.py`: `TAXAS["leitura"] = 120` por minuto, por token e por endpoint (`user_info`, `video_list`, `video_query`); o `status/fetch` usa a chave `"status"` da 015, compartilhada (R18). Caso novo em `apps/api/tests/integration/test_limites.py`.
- [X] T016 [P] `apps/api/src/sociman_api/publicacao/conexoes.py`: `ESCOPOS_METRICAS = frozenset({"user.info.stats", "video.list"})` e `metricas_liberadas(conexao) -> bool` (`ESCOPOS_METRICAS ⊆ conexao.escopos`), a **única** regra, usada pela coleta, pelo `EstadoColeta` e pelo `iniciar` (R1). `ESCOPO_OBRIGATORIO` continua `video.upload`.
- [X] T017 **TikTok falsa (pytest)** em `apps/api/tests/fakes/tiktok_fake.py` e `apps/api/tests/fixtures/tiktok/video_*.json` (R17): `user_info` com os campos de stats quando pedidos (`seguidores(handle, n)`); `video_list` com cursor em ms, `max_count ≤ 20`, `has_more` e só os públicos, do mais novo ao mais antigo; `video_query` com até 20 ids, **só os da conta do token**; controles `video(handle, id, criado_em, duracao, legenda, publico=True)`, `contadores(id, views=…, likes=…)` (aceita cair), `tornar_privado(id)`, `publicar_rascunho(publish_id, post_id)` (o próximo `status` devolve `PUBLISH_COMPLETE` com `publicaly_available_post_id`); falhas pelo `falhar_proximo` de sempre + `scope_not_authorized`; `requests` registra `video_list`, `video_query`, `user_info`, `status` e `token`. Ids de teste acima de 2^53.
- [X] T018 [P] Criar `apps/api/tests/unit/test_leitor_tiktok.py` (contra o fake): campos pedidos exatos, id como `str` acima de 2^53, lote de 20, `scope_not_authorized` → `SemPermissaoLeitura`, `status` → os 3 resultados, nenhum log com legenda ou link.
- [X] T019 **Guardas 1 a 3 do princípio I** em `apps/api/tests/unit/test_constitution_guards.py`, seção "spec 016" (plan, "Guardas"): (1) **ajustar o teste existente** `test_cliente_da_tiktok_com_lista_fechada_do_r21` para `set(cliente.ALLOWED) == TIKTOK_ALLOWED_R21 | LEITURA_016_ESPERADA` (o `TIKTOK_ALLOWED_R21` do teste **não muda**; `LEITURA_016_ESPERADA` é a constante do teste com exatamente `video/list` e `video/query`, e `cliente.LEITURA_016` é comparada com ela); (2) `metricas/*.py` não importa `publicacao.tiktok`, `publicacao.trilha`, `publicacao.service` nem `publicacao.executor` (só `registro`, `conexoes`, `models` e `limites` de `publicacao/`), e `httpx` não aparece em `metricas/`; (3) AST: `put_parte`, `.iniciar(` e `.enviar_parte(` não aparecem em `metricas/` nem em `publicacao/tiktok/leitor.py`, e o leitor só cita caminhos de `LEITURA_016 ∪ {"/v2/user/info/", "/v2/post/publish/status/fetch/"}`. Continuam verdes **sem mudança**: `test_listas_do_guarda_nao_encolheram`, `test_so_o_registro_importa_o_executor_da_rede` (o `metricas/` chega ao leitor só por `registro`), `test_permitido_em_so_libera_a_pasta_da_rede` (o host `open.tiktokapis.com` só aparece no `cliente.py`; o `leitor.py` não o cita) e `test_config_sem_url_da_tiktok`.
- [X] T020 [P] Criar `apps/api/src/sociman_api/metricas/schemas.py` com `EstadoColeta`, `Contadores`, `FotoVideo`, `FotoConta`, `MarcoValor`, `Marcos`, `VideoResumo`, `VideoDetalhe`, `Ancora`, `Candidato`, `Vinculo` e os corpos de entrada, em camelCase, exatamente como o contrato ("Tipos"). Nenhum campo com `tiktok`/`share` no nome (o link é `url`).

**Checkpoint:** `npm run test:api -- tests/integration/test_migration_0011.py tests/unit/test_constitution_guards.py tests/unit/test_leitor_tiktok.py tests/unit/test_tiktok_cliente.py` verde; `alembic upgrade head` no dev (depois do T003) mostra `0011_metricas_tiktok (head)`.

---

## Phase 3: User Story 1 - Liberar a coleta numa conta (Priority: P1) 🎯 MVP

**Goal**: o login pede os escopos de métricas; uma conexão da 015 sem eles mostra "Reconectar para liberar métricas", e reconectar amplia a mesma conexão (FR-001).

**Independent Test**: com uma conexão sem os escopos (fake), ver o aviso, reconectar como dono e ver "Coletando métricas"; membro vê o estado sem os botões.

### Tests for User Story 1

- [X] T021 [P] [US1] Criar `apps/api/tests/integration/test_reconectar_escopos.py` (R1; contrato, "Rotas da 015 que mudam"): `iniciar` numa conexão `conectada` sem os escopos → 200 (URL de login com os 6 escopos); com todos → 409 `ja_conectada`; com destino `enviando` na conta → 409 `envio_em_andamento`; `retorno` com o **mesmo `open_id`** reusa a linha, grava os escopos novos, troca a credencial sob `FOR UPDATE` e registra versão da conexão com `details.acao = "ampliada"`; `open_id` diferente → `conta_diferente`; o dono desmarca `video.list` na TikTok → a conexão fica com os escopos que vieram e o `EstadoColeta.escoposFaltando = ["video.list"]`; `sem_permissao_desde` da série é limpo na ampliação; membro e `Actor(kind="mcp_client")` → 403 `somente_humano` + evento `publicacao_recusada`.
- [X] T022 [P] [US1] Criar `apps/api/tests/unit/test_estado_coleta.py`: `permissao` `ok`/`faltando`/`sem_conexao`, `coletando` só com a série ativa (as 5 condições citadas acima), `habilitada` espelha `METRICAS_COLETA_HABILITADA`, erro em pt-BR.

### Implementation for User Story 1

- [X] T023 [US1] `apps/api/src/sociman_api/publicacao/conexoes.py`: `iniciar` aceita `conectada` sem `metricas_liberadas` (409 `envio_em_andamento` com destino `enviando` na conta; 409 `ja_conectada` com todos os escopos); `_validar_e_gravar` aceita `conectada` + mesmo `open_id` (reusa a linha, `details.acao = "ampliada"`, credencial sob `FOR UPDATE`) e limpa `sem_permissao_desde` da série viva da conta (import local de `metricas.models`, para não criar ciclo).
- [X] T024 [US1] `apps/api/src/sociman_api/metricas/consulta.py` (criar): `estado_coleta(db, conta, conexao, settings) -> EstadoColeta` (derivado; usa `metricas_liberadas` e a série viva; contagens de vídeos e fotos).
- [X] T025 [US1] `apps/api/src/sociman_api/publicacao/schemas.py` e `publicacao/router.py`: `Conexao.metricas: EstadoColeta | None` (`null` em rede sem leitor), preenchido em `GET /api/contas/{id}/conexao`, no retorno do login e no `ContaRef` do `ConexaoCard` (import de `metricas.schemas`/`metricas.consulta` só dentro da função).
- [X] T026 [US1] `npm run gen:contract` (trilha A) e conferir `npm run check:contract`.
- [X] T027 [P] [US1] SPA: `apps/web/src/lib/metricas.ts` (tipos do contrato, rótulos pt-BR, formatação em `America/Sao_Paulo` com `lib/tz.ts`) e `apps/web/src/components/metricas/ColetaStatus.tsx` ("Coletando métricas · última coleta há 12 min", "Coleta pausada no servidor", "Faltam permissões: …", o erro com a hora da próxima tentativa).
- [X] T028 [US1] SPA: `apps/web/src/components/publicacao/ConexaoCard.tsx`: `ColetaStatus` e o botão **"Reconectar para liberar métricas"** (só dono, chama o `iniciar` da 015); membro vê o estado sem o botão (US1, cenário 3).

**Checkpoint**: US1 verde no pytest; o `ConexaoCard` mostra o aviso e reconecta no fake.

---

## Phase 4: User Story 2 - Série temporal da conta e dos vídeos (Priority: P1)

**Goal**: a trilha `metricas` descobre os vídeos, tira as fotos na cadência por idade e fotografa a conta, só com inserção e com idempotência (FR-002, FR-003, FR-004).

**Independent Test**: com uma conta liberada no fake e um vídeo novo, avançar o relógio (`agora`) e ver as fotos horárias do vídeo com os números subindo e as fotos da conta.

### Tests for User Story 2

- [X] T029 [P] [US2] Criar `apps/api/tests/unit/test_agenda_metricas.py` (R4, R6): `agenda.alvos()` gera 48 + 28 + 9 + 10 alvos (1 h … 48 h; 3 d … 30 d; 37 d … 86 d, 90 d; 120 d … 360 d, 365 d); `proxima_coleta_em` = `publicado_em + menor alvo > idade da última foto`; tolerância `min(15 min, passo/4)`; atraso pula para **o alvo mais recente já vencido** (nada inventado); depois de 365 d → `None`; foto de descoberta no alvo cuja tolerância contém a idade (R5); janela da conta horária com vídeo < 48 h, senão 00:00 de SP (inclusive na virada do horário de verão, se houver).
- [X] T030 [P] [US2] Criar `apps/api/tests/integration/test_coleta_metricas.py` (R3 a R7, relógio injetado por `agora`, sem sleep): 1ª volta cria a série e a **1ª foto da conta** (SC-001); varredura inicial segue o `cursor` até 10 páginas por volta e continua na seguinte (`varredura_cursor`, `varredura_concluida_em`); **vídeo com mais de 365 d entra com uma foto e `proxima_coleta_em = NULL`** (Q2 = A); fila em lotes de 20 no `video/query`; vídeo que some → `disponivel = false` + `indisponivel_desde`, fotos antigas intactas, e volta limpa a marca; contagem que cai é gravada como veio; `rate_limit_exceeded`/taxa local → `adiar_ate = agora + 60 s` sem erro visível; `ConexaoIndisponivel` → `adiar_ate = agora + 5 min` e `ultimo_erro`; `scope_not_authorized` → `sem_permissao_desde` e a conexão **não muda**; `ConexaoPerdida` → nada na série (a 015 cuida da conexão); **isolamento**: erro numa conta não atrasa a outra; **idempotência**: volta repetida e queda injetada depois do pedido e antes do commit não duplicam foto (`ON CONFLICT DO NOTHING`); série anonimizada ou conta sem escopos não é coletada; `METRICAS_COLETA_HABILITADA=false` → nenhum pedido; nenhum `UPDATE`/`DELETE` em tabela de fotos (o trigger acusaria).
- [X] T031 [P] [US2] Acréscimo em `apps/api/tests/integration/test_agendador.py`: trilha `metricas` ociosa com `METRICAS_COLETA_HABILITADA=false`, sem app da TikTok ou sem a chave dos tokens; **ativa** com `PUBLICACAO_HABILITADA=false` e o botão "Envios automáticos" desligado (R3).

### Implementation for User Story 2

- [X] T032 [US2] Criar `apps/api/src/sociman_api/metricas/agenda.py` (funções puras, constantes de cadência numa linha cada; R4, R6; o ajuste depois do R19 é uma linha com teste).
- [X] T033 [US2] Criar `apps/api/src/sociman_api/metricas/coleta.py`: `rodar(db, client=None, agora=None)` na ordem de R3 (séries → descoberta → fila → conta → buscas → estado), **sessão curta por conta e commit por passo**, ordem **pedido → INSERT das fotos + UPDATE da agenda do vídeo → commit** (R7), token por `conexoes.token_valido`, leitor por `registro.leitor_para`, tabela de erros de R3, `ultima_coleta_em`. Deixa os pontos de chamada do vínculo (`vinculos.ao_descobrir`, `vinculos.rodar_buscas`, `vinculos.varrer_lembretes`) atrás de um import que a US3 preenche (T046).
- [X] T034 [US2] Acréscimo em `apps/api/src/sociman_api/agendador.py`: `Trilha("metricas", s.agendador_metricas_s, metricas.coleta.rodar, _metricas_ociosa)` com o motivo ocioso no log ("trilha metricas ociosa: …"; ativa: "trilha metricas ativa").
- [X] T035 [US2] **Guarda 5** em `apps/api/tests/unit/test_constitution_guards.py`: **ajustar o teste existente** `test_agendador_sem_trilha_nova` para `{sync, openshorts, importacao, lembretes, publicacao, metricas}` (docstring: "a lista só cresce por spec; `metricas` é da 016").
- [X] T036 [US2] Criar `apps/api/tests/integration/test_guardas_016.py` com o **guarda 6, parte da coleta** (`test_coleta_so_le_com_interruptor_desligado`): ciclo completo de coleta contra o fake com `PUBLICACAO_HABILITADA=false` **e** o botão desligado → o fake registra só `token`, `user_info`, `video_list`, `video_query` e `status`; nenhum destino vai a `enviando`; nenhuma `publicacao_tentativas` é criada.

**Checkpoint**: US2 verde; `docker compose logs agendador | grep -i "trilha metricas"` mostra a trilha no dev.

---

## Phase 5: User Story 3 - Ligar o vídeo da TikTok ao conteúdo do SociMan (Priority: P1)

**Goal**: vínculo em 3 níveis (envio → casamento → link/escolha), com a âncora do lembrete no "Marcar como postado" (Q3 = A), desfazer com histórico e `publicado` só pela função guardada (FR-005, FR-006).

**Independent Test**: no fake, entregar um rascunho, `publicar_rascunho` e ver o destino virar `publicado` com o link; num lembrete, marcar postado e ver o vínculo automático; desfazer e ver o histórico.

### Tests for User Story 3

- [X] T037 [P] [US3] Criar `apps/api/tests/unit/test_casamento.py` (R10): normalização (minúsculas, sem acento, sem `#tags`, sem emoji, sem pontuação, sem espaço repetido); Jaccard ≥ 0,5 ou contém → `compativel`; `L(V)` < 3 tokens → `neutra`; resto → `incompativel`; `L(D) = publicacao.legenda.legenda_tiktok(destino)`; duração ±1 s; **as duas âncoras**: entrega (`−5 min` a `+14 d`) e `posted_at` do lembrete (`−24 h` a `+1 h`, bordas incluídas e 1 s fora); **unicidade nos dois sentidos** com destinos de rascunho e de lembrete disputando o mesmo vídeo; neutra só com candidato único.
- [X] T038 [P] [US3] Criar `apps/api/tests/unit/test_link_tiktok.py` (R11): aceita `https://www.tiktok.com/@<handle>/video/<id>` com ou sem query; recusa encurtado (`vm.`/`vt.tiktok.com`) → "Abra o link e copie o endereço completo"; sem `/video/<id>` → `link_invalido`; `@` diferente → `link_outra_conta` com os dois `@`; id acima de 2^53 preservado.
- [X] T039 [P] [US3] Criar `apps/api/tests/integration/test_vinculo.py` (R9 a R12; contrato, "Métricas e vínculo do destino"): **nível 1** — a busca nasce na 1ª volta depois da entrega, agenda de consultas (10 min até 2 h, 30 min até 24 h, 3 h até 3 d, 12 h até 14 d), `PUBLISH_COMPLETE` + `video/query [post_id]` → vínculo `envio` e `rascunho_criado → publicado` com `post_detectado` (dedupe por destino), `FAILED` → `fim = falhou`, 14 d → `fim = prazo`, vídeo não devolvido → só `video/query` a cada 12 h; a tentativa da 015 **não muda**; modo `publicar` liga pelo `rede_post_id` sem busca; **nível 2** — único candidato liga (`casamento`, `system:metricas`, `vinculado_por = NULL`), ambíguo não liga e gera 1 `vinculo_a_confirmar`; **lembrete (Q3 = A)** — em `aprovado`/`agendado` nada é ligado sozinho e o `GET .../vinculo` lista os candidatos (vídeos sem vínculo dos últimos 14 dias, duração ±1 s, legenda não incompatível, ordenados pela distância ao `planned_at`), `POST .../vinculo {videoId}` → `escolha` e o destino vai a `postado` pelo `marcar_postado` (posted_url `null`); depois de "Marcar como postado" sem link, um post único dentro de `posted_at −24 h/+1 h` liga sozinho na volta seguinte e o destino **continua** `postado`; fora da janela, não liga; **nível 3** — link válido liga (`link`; num lembrete antes do clique, → `postado` com `posted_url = link`), outra conta → 409 `link_outra_conta`, `video/query` sem o id → 404 `post_nao_encontrado`, TikTok fora → 502 `rede_indisponivel`, vídeo já ligado → 409 `video_ja_vinculado` com `details.destinoId`, destino já ligado → 409 `destino_ja_vinculado`, estado fora de R12 → 409 `destino_sem_post`, conta sem série ativa → 409 `metricas_indisponiveis`; **desfazer** — `destino_id`, `vinculo_metodo`, `vinculado_por`, `vinculado_em` nulos, `vinculo_automatico = false`, busca `fim = desfeito`, `publicado → rascunho_criado` **só** se o vínculo o moveu (um `publicado` da 015 nunca volta), lembrete continua `postado`, e o destino fica **bloqueado** para o automático (inclusive lembrete, pelo `vinculo_desfeito` no histórico); refazer pelo mesmo `POST`; **histórico** no destino com `details` citados acima e **sem** id nem link da TikTok; `version` do destino → 409 `version_conflict`; vínculo só com destino da **mesma conta** da série; destino arquivado encerra a busca com `fim = cancelada`.
- [X] T040 [P] [US3] **Guarda 4** em `apps/api/tests/unit/test_constitution_guards.py`: `ESTADOS_015_PERMITIDOS` ganha `("postagem/service.py", "publicacao_pelo_vinculo")` e o guarda continua vivo; teste de que `publicacao_pelo_vinculo` só aceita `rascunho_criado → publicado` / `falhou (incerta) → publicado` ao ligar e o caminho inverso ao desfazer, só com vídeo da mesma conta.
- [X] T041 [P] [US3] Acréscimo em `apps/api/tests/integration/test_guardas_016.py` (**guardas 6 e 7, parte do vínculo**): ciclo de vínculo (níveis 1 e 2, lembrete depois do clique) com os dois níveis do interruptor desligados → só pedidos de leitura; `Actor(kind="mcp_client")` e membro em `POST .../vinculo` e `.../vinculo/desfazer` → 403 `somente_humano`, nada muda e o evento `publicacao_recusada` é gravado.

### Implementation for User Story 3

- [X] T042 [US3] `apps/api/src/sociman_api/postagem/service.py` (acréscimo): `publicacao_pelo_vinculo(db, actor, destino, vinculado: bool)` (R12), com `history.record` no destino e a conferência de que a última ida a `publicado` veio de `vinculo_feito` antes de desfazer.
- [X] T043 [US3] Criar `apps/api/src/sociman_api/metricas/casamento.py` (R10): normalização, Jaccard, classificação da legenda, âncora do destino (tabela do data-model, Q3 = A), bloqueio pelo histórico e a regra de unicidade nos dois sentidos.
- [X] T044 [US3] Criar `apps/api/src/sociman_api/metricas/vinculos.py` (R9 a R12): buscas do nível 1 (criação, agenda de consultas, `post_publicado`, `consultar`), `ao_descobrir(video)` (liga `publicar` pelo `rede_post_id` e roda o casamento), `varrer_lembretes(agora)` (lembretes `postado` nas últimas 25 h, sem vínculo e sem bloqueio), `candidatos(destino)` (inclusive o lembrete antes do clique), `ligar(destino, video_id | link, actor)` (lembrete antes do clique → `postagem.service.marcar_postado`; rascunho → `publicacao_pelo_vinculo`), `desfazer`, parser do link, notificações `post_detectado`/`vinculo_a_confirmar` com `dedupe_key` por destino e `history.record` com `details` citados acima. Autor automático: `Actor(kind="system:metricas")`. **Nunca atribui `postado`** fora de `marcar_postado` (o guarda `test_postado_so_por_acao_humana` continua sem exceção) e só muda `rascunho_criado`/`publicado`/`falhou` por `publicacao_pelo_vinculo`.
- [X] T045 [US3] Criar `apps/api/src/sociman_api/metricas/router.py` com `GET /api/destinos/{id}/vinculo` (`destinos_vinculo_get`, User), `POST /api/destinos/{id}/vinculo` (`destinos_vinculo_criar`, **H**) e `POST /api/destinos/{id}/vinculo/desfazer` (`destinos_vinculo_desfazer`, **H**), com os erros do contrato; acréscimo em `apps/api/src/sociman_api/main.py` (inclui o router). Conferir que `test_nenhuma_rota_de_publicacao` continua **sem exceção**.
- [X] T046 [US3] Acréscimo em `apps/api/src/sociman_api/metricas/coleta.py` (trilha B, a pedido da C): chamar `vinculos.ao_descobrir`, `vinculos.rodar_buscas` e `vinculos.varrer_lembretes` na volta (R3, passo 3).
- [X] T047 [US3] `npm run gen:contract` (trilha A).
- [X] T048 [P] [US3] SPA: `apps/web/src/components/metricas/VinculoPanel.tsx`: estado (`vinculado` com o link e o método "pelo envio"/"pela lista"/"pelo link"/"escolhido"; `buscando` "Procurando o post"; `a_confirmar` "Escolha o post"; `sem_vinculo`; `indisponivel`), candidatos com a diferença de duração, a legenda e os minutos da âncora, **escolha em 1 clique** (no lembrete antes do clique: "Este é o post" marca como postado), "Ligar a um post" (colar link) e **Desfazer vínculo** em AlertDialog — tudo só para o dono.
- [X] T049 [US3] SPA: seção **"Desempenho"** em `apps/web/src/components/conteudos/DestinoPanel.tsx` com o `VinculoPanel` (a curva entra na US4) e invalidação das queries do destino, do conteúdo e da conexão depois de ligar e desfazer.
- [X] T050 [P] [US3] SPA: rótulos e links dos avisos `post_detectado` e `vinculo_a_confirmar` em `apps/web/src/lib/notificacoes.ts` (acréscimo; link `/app/conteudos/{conteudoId}?conta={contaId}`).

**Checkpoint**: US3 verde no pytest; `npm run check:web` verde.

---

## Phase 6: Desconectar anonimiza (FR-009; obrigatória antes do teste real) [US1]

**Goal**: desconectar exige confirmação e anonimiza a série por UPDATE, na mesma transação, guardando só as características não textuais (Q1 = A). Fica antes do teste real porque, com a coleta ligada, desconectar sem ela deixaria dados identificáveis.

**Independent Test**: com uma série com fotos no fake, desconectar sem confirmar (409), confirmar e ver a série como "Conta anônima N", sem nenhuma coluna identificadora e com as mesmas contagens de linhas.

- [X] T051 [P] [US1] Criar `apps/api/tests/integration/test_anonimizacao.py` (R13; **guarda 9**): série com dados + desconectar sem `confirmoAnonimizar` → 409 `confirmar_anonimizacao` com `details: {videos, fotos, conta}` e **nada muda**; com a confirmação: `conta_id`, erro e cursor nulos, `rotulo = "Conta anônima N"`, `anonimizada_em/por`; em cada vídeo `rede_video_id`, `share_url`, `legenda`, `titulo`, `destino_id`, `vinculo_metodo`, `vinculado_por`, `vinculado_em`, `proxima_coleta_em` nulos, `publicado_em` truncado para a hora e `features` **só com as chaves de Q1** (nenhum texto: gancho, legenda, hashtags, perfil, conta ou canal); buscas com `post_id` nulo e abertas encerradas com `fim = anonimizada`; **contagens de linhas iguais antes e depois** em todas as tabelas `metricas_*` (nenhum DELETE); versão da conexão com `{acao: "metricas_anonimizadas", videos, fotos}` e **sem** identificador no histórico; a série anônima não é mais coletada; reconectar depois cria **outra série**; série sem foto desconecta sem pedir confirmação; membro/MCP → 403 `somente_humano`.
- [X] T052 [US1] Criar `apps/api/src/sociman_api/metricas/anonimizar.py`: `serie(db, serie, actor)` só com UPDATE, na ordem "congelar `features` → cortar o elo" (R13), `rotulo` pela sequência `metricas_anonima_seq`.
- [X] T053 [US1] `apps/api/src/sociman_api/publicacao/conexoes.py::desconectar` + `publicacao/schemas.py` (`DesconectarIn { version, confirmoAnonimizar = false }`, resposta com `metricasAnonimizadas: {videos, fotos} | null`) + `publicacao/router.py`: anonimiza **na mesma transação**, depois de revogar e apagar a credencial (import local de `metricas.anonimizar`). Ajustar `apps/api/tests/integration/test_conexoes.py` (desconectar com série e com o corpo novo).
- [X] T054 [US1] `npm run gen:contract` (trilha A).
- [X] T055 [US1] SPA: no diálogo de desconectar do `apps/web/src/components/publicacao/ConexaoCard.tsx`, repetir com `confirmoAnonimizar: true` depois do 409 `confirmar_anonimizacao`, com o texto de R13 ("As métricas de @x (N vídeos, M fotos) serão anonimizadas… Isso não pode ser desfeito.") e o botão destrutivo em AlertDialog.

**Checkpoint**: `npm run test:api -- -k "anonimizacao or conexoes or guardas_016"` verde.

---

## Phase 7: Teste real com o dono (manual; SC-001, SC-003, R1, R9, R11, R19)

**Pré-requisito:** Phases 2 a 6 verdes, T003 e T006 feitos. Um passo por vez (quickstart §3 e §4). Nenhum agente chama a TikTok real por conta própria.

- [ ] T056 Subir o código novo no dev: `docker compose up -d --build api agendador edge`. **Verificar:** `curl -s http://localhost:8180/api/health` ok, `docker compose exec api uv run alembic current` → `0011_metricas_tiktok (head)`, `docker compose logs agendador | grep -i "trilha metricas"` → ativa. Comparar com a linha de base do T002 (nada mudou em `postagens`, `conexoes` e `entity_versions`).
- [ ] T057 [DONO] **Reconectar @atavernanerd** (quickstart §3.1 a §3.3): antes, `select count(*) from metricas_series` → `0`; o dono clica em "Reconectar para liberar métricas" e autoriza marcando tudo. **Verificar** (SC-001): em até 2 min, `fotos_conta ≥ 1`, `videos` perto dos públicos da conta, `varredura_ok = t`, sem erro (consulta do quickstart §3.3, só contagens). **Registrar:** a TikTok pediu só os escopos novos ou todos de novo (R1).
- [ ] T058 [DONO] **Reconectar @meusqueridinhos10** (quickstart §3.5) e conferir o mesmo. **Membro** abre a conta e vê "Coletando métricas" sem os botões (§3.6).
- [ ] T059 [DONO] **Vínculo de um rascunho** (quickstart §4.1 a §4.3): destino `criar_rascunho` entregue → "Procurando o post"; o dono finaliza em público com a legenda do "Copiar textos". **Verificar** (SC-003): em até 30 min, destino **Publicado** com o link, método e histórico "vínculo feito". **Registrar:** tempo, nível que ligou e se o `status/fetch` devolveu o id (consulta do §4.3, sem imprimir o id).
- [ ] T060 [DONO] **Link errado, desfazer e lembrete** (quickstart §4.4 a §4.6): link de outra conta recusado; link certo liga e o lembrete vira **Postado**; desfazer volta a "sem vínculo" com histórico; num lembrete postado à mão, os candidatos aparecem antes do clique e, depois de "Marcar como postado" (sem link), o vínculo sai sozinho em até 1 h (Q3 = A). **Registrar:** o comportamento do `video/query` com id de outra conta (R11).
- [ ] T061 [DONO] **Latência do `view_count`** (quickstart §3.4; R19): depois de 6 h de um vídeo novo, a consulta do §3.4 (só idade, contadores e hora). **Registrar:** as views mudam de hora em hora? Quantas fotos repetiram enquanto o app mostrava mais? Se a TikTok atualiza com atraso, o dono decide se a faixa de 48 h passa a 2 h ou 3 h (uma constante em `metricas/agenda.py`, com o teste do T029 ajustado).
- [ ] T062 Registrar os resultados do T057–T061 em `specs/016-metricas-tiktok/quickstart.md` (seção "Resultado", nova, no fim) e os **[não confirmado]** medidos em `docs/pesquisa/metricas-tiktok.md` (§1.4, §5.1) como **[confirmado em 2026-MM-DD]**.

---

## Phase 8: User Story 4 - Ver o desempenho (Priority: P2)

**Goal**: evolução da conta, curva de cada vídeo com os marcos 1 h/24 h/7 d/30 d e ranking ordenável e filtrável (FR-007).

**Independent Test**: com fotos semeadas, abrir o ranking da Taverna ordenado por views 7 d e abrir o 1º para ver a curva e os marcos.

### Tests for User Story 4

- [X] T063 [P] [US4] Criar `apps/api/tests/unit/test_marcos.py` (R15): interpolação linear em `idade_s`; foto exata no marco; âncora `(0, 0)`; `estimado` quando o intervalo passa de 25% de `T`; `ainda_nao` com o vídeo mais novo que `T`; `sem_dado` sem foto depois de `T` e a última a mais de 10% de `T`; contagem que cai não é forçada a subir; engajamento com views = 0 → 0; velocidade com menos e com mais de 24 h.
- [X] T064 [P] [US4] Criar `apps/api/tests/integration/test_rotas_metricas.py` (contrato, "Métricas de conta" e "Vídeos, ranking e curva"): `GET /api/metricas/videos` ordena por `views24h`, `views7d`, `engajamento`, `velocidade` e `publicadoEm` nas duas direções, com ordenação estável e cursor (50 por página, `limite ≤ 100`), filtra por perfil, conta, origem (`corte`, `video_proprio`, `fora`, `anonima`) e período de publicação; `GET /api/metricas/videos/{id}` com fotos, marcos e `coletaParadaEm`; `GET /api/contas/{id}/metricas` com `resolucao=auto|hora|dia` e as publicações marcadas; `GET /api/destinos/{id}/metricas`; membro vê tudo; `miniaturaUrl` só do SociMan (nenhuma URL da CDN da TikTok na resposta); anônimo sem `conta`, `url` nem `legenda`; ranking de 2 contas × 1 ano semeado responde em menos de 300 ms (SC-004).

### Implementation for User Story 4

- [X] T065 [US4] `apps/api/src/sociman_api/metricas/consulta.py` (acréscimo): curvas, marcos por `LATERAL … ORDER BY idade_s LIMIT 1` sobre `ix_metricas_video_fotos_idade`, ranking numa consulta SQL, engajamento, velocidade, origem derivada (corte, vídeo próprio, fora, anônima) e a resolução da conta.
- [X] T066 [US4] `apps/api/src/sociman_api/metricas/router.py` (acréscimo): `metricas_conta`, `metricas_videos_list`, `metricas_videos_get` e `destinos_metricas` (User).
- [X] T067 [US4] `npm run gen:contract` (trilha A).
- [X] T068 [P] [US4] SPA: `apps/web/src/components/metricas/LinhaChart.tsx` (SVG próprio, ~200 linhas, **sem dependência nova**; 1 a 4 séries, ticks "bonitos", marcadores verticais, tooltip por mouse e por teclado com setas, `role="img"` + `aria-label` e tabela `sr-only`, cores dos tokens do tema claro e escuro; R14) e `components/metricas/MarcosCard.tsx` ("ainda não", "estimado", "sem dado").
- [X] T069 [US4] SPA: `apps/web/src/components/metricas/RankingTable.tsx` (`DataTable` com `dataTableColumns<T>()` da TanStack Table v9, filtros com `NativeSelect`, clique leva ao conteúdo ou a `/app/metricas/videos/:id` quando é de fora) e `apps/web/src/pages/metricas/Metricas.tsx` (abas **Ranking** e **Contas**: seletor de conta, gráfico de seguidores e curtidas com os vídeos marcados, `ColetaStatus`).
- [X] T070 [US4] SPA: `apps/web/src/pages/metricas/VideoMetricas.tsx` (vídeo de fora: curva, marcos e link do post; ícone da rede, sem imagem da CDN) e acréscimos em `apps/web/src/App.tsx` (as 2 rotas) e `apps/web/src/components/shell/nav.ts` (item "Métricas").
- [X] T071 [US4] SPA: curva e `MarcosCard` na seção "Desempenho" do `apps/web/src/components/conteudos/DestinoPanel.tsx` (acima do `VinculoPanel`).

**Checkpoint**: US4 verde; `npm run check:web` verde (bundle, CSP igual).

---

## Phase 9: User Story 5 - Exportar o dataset (Priority: P2)

**Goal**: ZIP com `fotos_videos`, `videos`, `fotos_conta`, `dicionario.csv` e `LEIAME.txt`, em CSV ou JSON Lines, com cabeçalho estável (FR-008, SC-005).

**Independent Test**: exportar um mês de uma conta em CSV e abrir `fotos_videos.csv` numa planilha com acentos certos.

### Tests for User Story 5

- [X] T072 [P] [US5] Criar `apps/api/tests/integration/test_export_metricas.py` (R16; contrato, "Exportação"): só dono (membro e MCP → 403); `formato=csv|jsonl`; `de`/`ate` obrigatórios e até 400 dias → senão 400 `periodo_invalido`; `Content-Disposition` com `sociman-metricas-AAAAMMDD-AAAAMMDD.zip`; o ZIP tem os 5 arquivos; **cabeçalho de cada CSV igual ao `metricas/dicionario.py`** (ordem e nomes) e `DICIONARIO_VERSAO` no `LEIAME.txt`; CSV UTF-8 com BOM, vírgula, ponto decimal e datas ISO com offset de SP; JSONL com as mesmas chaves; `video_ref` = uuid do SociMan, nunca o id da TikTok; vídeo sem vínculo com as colunas do SociMan vazias e `origem = fora`; anônimas só com `incluirAnonimas`, com `serie = "Conta anônima N"`, colunas identificadoras vazias e as características de `features`; estimativa acima de 32 MB sem HD → 503 `storage_unavailable`, abaixo do piso → 507 `storage_full` (`datadir` simulado); 1 mês de 1 conta semeada sai em menos de 2 s.

### Implementation for User Story 5

- [X] T073 [US5] Criar `apps/api/src/sociman_api/metricas/dicionario.py` (constante única: arquivo, coluna, tipo, unidade, significado, origem TikTok/SociMan/calculado; `DICIONARIO_VERSAO`; colunas de R16, com os avisos "só vídeos públicos", "contagens acumuladas" e "`video_count` conta só públicos").
- [X] T074 [US5] Criar `apps/api/src/sociman_api/metricas/export.py`: streaming (`yield_per(2000)`) para `SpooledTemporaryFile(max_size=32 MB, dir=<HD>/work/exports)`, estimativa pela contagem de fotos e `datadir` (sentinela e piso) antes de montar quando passar de 32 MB (R16); características por join na hora (vídeos ligados) ou de `features` (anônimos).
- [X] T075 [US5] `apps/api/src/sociman_api/metricas/router.py` (acréscimo): `GET /api/metricas/export` (`metricas_export`, Owner) → `application/zip`.
- [X] T076 [US5] `npm run gen:contract` (trilha A).
- [X] T077 [US5] SPA: `apps/web/src/components/metricas/ExportarDialog.tsx` (período, perfil, conta, formato, "incluir anônimas"; download por `fetch` com Bearer + `Blob`, sem link público) e o botão **Exportar** (só dono) em `apps/web/src/pages/metricas/Metricas.tsx`.

**Checkpoint**: US5 verde; `npm run check:web` verde.

---

## Phase 10: e2e (TikTok falsa na stack efêmera)

- [X] T078 [P] Fake do e2e em `e2e/fakes/server.py` (R17): `/tiktok/v2/video/list/` e `/tiktok/v2/video/query/` com as mesmas regras do fake do pytest, stats no `/tiktok/v2/user/info/`, `publicaly_available_post_id` no `status/fetch` depois de `POST /tiktok-e2e/publicar-rascunho`, e controle por `POST /tiktok-e2e/videos` (criar, contadores, privado).
- [X] T079 [P] `docker-compose.e2e.yml`: `AGENDADOR_METRICAS_S: "2"` e `METRICAS_COLETA_HABILITADA: "true"` em `api` e `agendador`; acréscimo em `e2e/helpers.ts`: semear fotos por `INSERT` via `psql` pelo `compose()` (só projeto `sociman-e2e`; o trigger aceita INSERT).
- [X] T080 Criar `e2e/metricas.spec.ts` (plan, "Testing"): conta sem escopos → aviso → reconectar → "Coletando métricas" e a 1ª foto [US1]; rascunho publicado no fake → destino "Publicado" com o link [US3]; casamento ambíguo → escolher o post [US3]; lembrete: candidatos antes do clique e "Marcar como postado" → ligado sozinho (Q3 = A) [US3]; link de outra conta recusado; desfazer [US3]; ranking com fotos semeadas e curva com os marcos [US4]; exportar ZIP (dono) e membro sem os botões de dono [US5]; desconectar com confirmação → série anônima no ranking com "incluir anônimas" [US1/FR-009]. Usar `NativeSelect` e `role="alertdialog"` como nos outros e2e.
- [X] T081 Rodar `flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/metricas.spec.ts` e depois `flock /tmp/sociman-e2e.lock npm run test:e2e` inteiro (a 014 e a 015 continuam verdes). Nunca `npx playwright test` direto.

---

## Phase 11: Polish & Cross-Cutting Concerns

- [X] T082 `npm run test:api` inteiro verde (inclui `test_migration_0011`, `test_coleta_metricas`, `test_vinculo`, `test_anonimizacao`, `test_guardas_016`, `test_constitution_guards`) e `docker compose exec api uv run ruff check .` sem erros.
- [X] T083 `npm run gen:contract && npm run check:web` (contrato igual, typecheck, build, bundle sem segredo, CSP igual à de antes — nenhuma origem nova, nenhum `unsafe-eval`).
- [X] T084 Quickstart §1 e §2 completos (guardas do princípio I com o fake); **registrar** que `test_coleta_so_le_com_interruptor_desligado` passou.
- [X] T085 [P] Revisão de logs: `docker compose logs agendador api | grep -iE "video_description|share_url|access_token"` não acha nada (o leitor só loga método, caminho e status).
- [X] T086 [P] Conferir no banco de dev (só contagens) que nenhuma linha de `entity_versions` tem `rede_video_id`, `share_url` ou `post_id` nos `details` de `vinculo_feito`/`vinculo_desfeito` (R11, R13).
- [ ] T087 [DONO] **Depois de uma semana de coleta** (quickstart §5): ranking top 5 em menos de 30 s (SC-004), cadência no horário ≥ 0,95 com a consulta do §5.2 (SC-002), exportação de um mês em menos de 1 min e abrindo na planilha (SC-005), e o `UPDATE` em transação desfeita recusado pelo trigger (SC-006). **Registrar** em `quickstart.md` (Resultado).
- [ ] T088 `CLAUDE.md` (acréscimo, **só no fim**): seção "Métricas (desde a spec 016)": trilha `metricas`, `METRICAS_COLETA_HABILITADA` (pausa sem desconectar), fotos só de inserção (trigger), desconectar anonimiza (irreversível, confirmação), reconectar para ampliar escopos, vínculo em 3 níveis com a âncora do lembrete no "Marcar como postado", e a lista fechada `LEITURA_016`.
- [ ] T089 `docs/visao.md` (acréscimo, **só no fim**): marcar a 016 e registrar os resultados do T057–T061 e do T087.
- [ ] T090 Marcar `specs/016-metricas-tiktok/checklists/requirements.md` e este `tasks.md`; conferir que `open-questions.md` segue resolvido.
- [ ] T091 [DONO] Validação final do dono: o dono usa `/app/metricas` com dados reais e aprova (ou pede ajustes, que viram tarefas novas aqui).
- [ ] T092 Opcional (só se o dono pedir depois do T061): ajustar a faixa horária em `metricas/agenda.py` e o `test_agenda_metricas.py`.
- [ ] T093 Commit e push **só quando o dono pedir**, em pt-BR, no imperativo.
- [ ] T094 [DONO] Apagar o backup `pre-0011.dump` do T003, **só** com a confirmação do dono e depois do T091.

---

## Dependencies & Execution Order

### Phase Dependencies
- Setup (T001–T006): T001 primeiro; T002 → T003 antes de subir a migration no dev; T004, T005 em paralelo; T006 com o dono (não bloqueia as fases 2 a 6).
- Foundational (T007–T020): T007 → T009 → T010 → T011; T008 com o T007; T012, T013, T015, T016, T020 em paralelo depois do T007; T013 → T014; T017 → T018; T019 depois do T012 e do T014. **Bloqueia todas as histórias.**
- US1 (T021–T028): T021, T022 depois da Foundational; T023 → T024 → T025 → T026; SPA (T027, T028) depois do T026.
- US2 (T029–T036): depende da US1 (`metricas_liberadas`, série ativa). T029 → T032; T030 → T033 → T034; T035 com o T034; T036 depois do T033.
- US3 (T037–T050): depende da US2 (a trilha e a descoberta). T042, T043 em paralelo; T044 depois dos dois; T045 depois do T044; T046 depois do T044 (trilha B); T047 depois do T045; SPA (T048–T050) depois do T047.
- Phase 6 (T051–T055): depende da US2 (há série para anonimizar); T052 → T053 → T054 → T055. Pode correr em paralelo com a US3 (arquivos diferentes, exceto `publicacao/conexoes.py`, que é da trilha B nos dois casos).
- Phase 7 (teste real): depois das Phases 2 a 6 e do T003/T006. T056 → T057 → T058 → T059 → T060; T061 em paralelo depois do T057; T062 no fim.
- US4 (T063–T071): pode começar depois da US2 (lê fotos); as telas ficam melhores com dados reais da Phase 7. T065 → T066 → T067; SPA depois do T067.
- US5 (T072–T077): depois da Phase 6 (anônimas) e da US4 (`consulta.py` dos marcos para os rótulos). T073 → T074 → T075 → T076 → T077.
- e2e (T078–T081): T078, T079 a qualquer momento depois da Foundational; T080 cresce por história; T081 no fim de cada história e no fim de tudo.
- Polish por último; T088 e T089 só no fim; T094 por último.

### Parallel Opportunities
- Setup: T004, T005.
- Foundational: T008, T012, T013, T015, T016, T018, T020 (arquivos diferentes).
- Testes de cada história marcados [P] entre si.
- US3 × Phase 6 (trilha C escreve `vinculos.py` e `anonimizar.py`; trilha B, `coleta.py` e `conexoes.py`).
- US4 × US5 na API (arquivos diferentes, `router.py` em blocos de acréscimo pela trilha C).

---

## Trilhas para agentes paralelos

Cinco agentes, sem arquivo em comum. Cada trilha só edita os arquivos listados; qualquer outro pede coordenação pelo líder. Os arquivos "só acréscimo" do topo podem receber blocos de qualquer trilha. As tarefas **[DONO]** e a Phase 7 ficam com o líder e o dono.

| Trilha | Agente sugerido | Tarefas | Arquivos (exclusivos) |
|---|---|---|---|
| **A: base, migração, cliente, guardas e contrato** | `api-016-base` | T002–T005, T007–T015, T017–T019, T026, T035, T036, T040, T041, T047, T054, T067, T076, T082–T086 | `apps/api/src/sociman_api/config.py` (acréscimo); `docker-compose.yml`, `docker-compose.test.yml`; `apps/api/migrations/versions/0011_metricas_tiktok.py`; `metricas/{__init__,models}.py`; `notificacoes/models.py`; `publicacao/{executor,registro,limites}.py`; `publicacao/tiktok/{cliente,leitor,executor}.py`; `tests/fakes/tiktok_fake.py`, `tests/fixtures/tiktok/**`; `tests/unit/{test_constitution_guards,test_tiktok_cliente,test_leitor_tiktok}.py`; `tests/integration/{test_migration_0011,test_guardas_016,test_limites,test_trilha_publicacao}.py` e os de migration anteriores. **Única trilha que roda `npm run gen:contract`** e toca `packages/contract/**` (a pedido de B, C) |
| **B: conexões, coleta, agenda, trilha e consultas** | `api-016-coleta` | T016, T021–T025, T029–T034, T046, T053, T063, T065 | `publicacao/{conexoes,schemas,router}.py`; `metricas/{agenda,coleta,consulta}.py`; acréscimo em `agendador.py`; `tests/unit/{test_estado_coleta,test_agenda_metricas,test_marcos}.py`; `tests/integration/{test_reconectar_escopos,test_coleta_metricas,test_conexoes}.py`; acréscimo em `tests/integration/test_agendador.py` |
| **C: vínculo, anonimização, rotas e exportação** | `api-016-vinculo` | T020, T037–T039, T042–T045, T051, T052, T064, T066, T072–T075 | `metricas/{schemas,casamento,vinculos,anonimizar,router,dicionario,export}.py`; `postagem/service.py` (só a função nova); acréscimo em `main.py`; `tests/unit/{test_casamento,test_link_tiktok}.py`; `tests/integration/{test_vinculo,test_anonimizacao,test_rotas_metricas,test_export_metricas}.py` |
| **D: SPA** | `spa-016` | T027, T028, T048–T050, T055, T068–T071, T077 | `apps/web/**` (novos em `pages/metricas/`, `components/metricas/`, `lib/metricas.ts`; alterações em `components/publicacao/ConexaoCard.tsx`, `components/conteudos/DestinoPanel.tsx`; acréscimos em `App.tsx`, `nav.ts`, `lib/notificacoes.ts`) |
| **E: e2e, verificação e docs** | `e2e-016` | T006 (com o líder), T056, T062, T078–T081, T087 (com o líder), T088–T090, T094 (com o líder) | `e2e/**` (`metricas.spec.ts` novo, `fakes/server.py`, acréscimos em `helpers.ts`), `docker-compose.e2e.yml`, `specs/016-metricas-tiktok/quickstart.md` (Resultado), `docs/pesquisa/metricas-tiktok.md`, `CLAUDE.md`, `docs/visao.md` |

Sincronização:
1. O líder faz o T001 e pede ao dono o T006. A faz a Setup e a Foundational; C faz o T020 em paralelo; B faz o T016.
2. Depois do checkpoint da Foundational, B faz a API da US1 (T021–T025) e A roda o T026; D faz o T027 e o T028. E começa o T078 e o T079.
3. B faz a US2 (T029–T034); A faz o T035 e o T036.
4. C faz a US3 (T037–T045) e pede a B o T046 e a A o T040, T041 e T047; D faz o T048–T050. Em paralelo, C faz o T051/T052 e B o T053; A roda o T054; D o T055.
5. O líder conduz a Phase 7 com o dono (E sobe a stack no T056 e registra no T062).
6. B faz o T063/T065 e C o T064/T066 (US4); A roda o T067; D faz o T068–T071. Depois C faz a US5 (T072–T075); A o T076; D o T077.
7. E roda o e2e **sempre** com `flock /tmp/sociman-e2e.lock` (nunca dois e2e ao mesmo tempo, nem com outra spec).
8. T088 e T089 só no fim; T094 por último.

---

## Implementation Strategy

### MVP (US1, US2, US3 e a anonimização, todas P1)
1. T001 (015 pronta) → Setup (linha de base, backup, variáveis) → Foundational (migration testada nos dois sentidos, trigger, leitor com lista fechada, fake, guardas).
2. US1 (liberar) → US2 (série temporal) → US3 (vínculo, com a Q3) → Phase 6 (desconectar anonimiza).
3. **Parar e fazer o teste real com o dono** (Phase 7): as 2 contas coletando, a 1ª foto, a latência e 1 rascunho ligado. A coleta começa cedo, que é o ponto da spec.

### Incremental
US4 (telas, sobre dados reais) → US5 (exportação) → e2e completo → Polish (uma semana de coleta, docs, backup apagado).

## Notes
- Nenhuma dependência nova, nenhum serviço novo, nenhum banco novo (Q4 = A), nenhuma `location` nova no edge, CSP igual.
- Nenhuma rota DELETE; as fotos são só de inserção (trigger); a anonimização é UPDATE, irreversível e com confirmação.
- A coleta só lê: `LEITURA_016` + `user/info` + `status/fetch`, provado pelos guardas 1 a 3 e 6.
- Commit só quando o dono pedir, em pt-BR, no imperativo.
