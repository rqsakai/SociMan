# Implementation Plan: Geração local com candidatos

**Branch**: `021-geracao-local` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/021-geracao-local/spec.md`

## Summary

O SociMan ganha um **motor de geração** único para o ciclo "pedir → gerar opções → um humano escolhe →
vira o arquivo oficial":
- **3 tabelas novas** (`geracoes`, `geracao_candidatos`, `audios`) e uma coluna em `ia_chamadas`, na
  migration `0020_geracao_local` (número provisório, conferido no gate T001);
- um **serviço novo `gerador`** (mesma imagem da API, `sociman gerador`), com uma linha de GPU (um job
  `comfyui` ou `tts` por vez, garantido por índice único parcial) e uma linha `claude`;
- a fila **espera a GPU livre** (envios da 006 em `processando` e VRAM medida pelo `/system_stats` do
  ComfyUI), sem fila única com o OpenShorts;
- antes de cada job `comfyui`, a RAM do ComfyUI sobe para 28 GB e volta para 12 GB num `finally`, pelo
  **`dockerctl`**: 3 ações fixas, sem parâmetros. Fica para o dono escolher onde ele roda (D1);
- o ComfyUI é usado pela API padrão, com 4 blocos do pipeline copiados e com hash. O shop-tts é usado por
  um **contrato `v2` novo** (arquivos em vez de caminhos, mais uma rota de importar voz), que é dependência
  externa e só está descrito em `contracts/shop-tts.md`;
- **piloto de ponta a ponta:** a cena de um cenário da 007 (`cenario.cena`). Os outros passos ficam
  registrados, mas respondem `passo_indisponivel` até a 025 e a 012 trazerem os aplicadores;
- a **limpeza de 90 dias** é uma trilha do agendador e usa o único delete do `storage.py`, restrito à
  exceção 1 da emenda 4.3.0 e auditado por evento.

Nada publica: o SociMan só fala com o ComfyUI, o shop-tts, o `dockerctl` e o Claude.

## Technical Context

**Language/Version**: Python 3.12 (API, uv) · TypeScript 5 / React 19 (SPA, Vite)

**Primary Dependencies**: FastAPI, SQLAlchemy 2, Pydantic 2, httpx (já usado), Pillow (já usado:
normalizar 768×1344), ffprobe/ffmpeg (já na imagem: validar áudio), SDK `anthropic` (já usado pela 008).
**Nenhuma dependência Python ou npm nova.** O `dockerctl` usa só a stdlib (`http.server`, `http.client`
por socket Unix). Na SPA: TanStack Query, shadcn/ui, `<audio>` nativo.

**Storage**: PostgreSQL (NVMe: 3 tabelas, 1 coluna). MinIO no HD: imagens no bucket `sociman` (como hoje)
e **áudios no bucket novo `sociman-audios`**, com sentinela `.sociman-volume` e piso de espaço livre
(`datadir.ensure_writable`). Os temporários de upload ficam em `work/tmp` no HD (`TMPDIR`).

**Testing**: pytest na stack efêmera (`npm run test:api`) com os fakes novos `comfyui_fake`,
`shoptts_fake` e `dockerctl_fake`; ruff; `npm run check:web`; Playwright (`e2e/geracao.spec.ts`) com o
`openshorts-fake` atendendo `/comfyui`, `/shop-tts`, `/dockerctl` e `/geracao-e2e`. Nenhum teste chama
serviço real. Validação real só com o dono (quickstart §2–§4).

**Target Platform**: Linux (host `sakai-desktop`), Docker; SPA no desktop e no celular (modo casa)

**Project Type**: web (apps/api + apps/web) + 2 serviços novos no compose (`gerador`, `dockerctl`)

**Performance Goals**: pedir e escolher < 300 ms; claim < 50 ms; a tela vê o andamento em ≤ 2 s (polling);
cancelar para a GPU em ≤ 5 s (heartbeat)

**Constraints**:
- 1 job de GPU por vez;
- RAM do ComfyUI em 12 GB fora dos jobs `comfyui`;
- GPU de 16 GB compartilhada com o OpenShorts;
- upload de áudio ≤ 25 MB (edge com 26m);
- CSP inalterada;
- nada de `docker.sock` fora do `dockerctl`;
- ComfyUI e shop-tts só pela rede `gpu-local`.

**Scale/Scope**:
- algumas dezenas de gerações por semana, 2 a 4 opções cada;
- 10 rotas novas e 1 rota aditiva;
- 1 seção nova na tela de cenário e 6 componentes reutilizáveis.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.* (constitution **4.3.0**, emenda
aprovada pelo dono em 2026-10-06 e **aplicada na 1ª tarefa** da implementação: o princípio VII ganha as
"Exceções de eliminação (4.3.0)")

| Princípio | Situação | Como |
|---|---|---|
| **I. Publicação só com decisão humana** | ✅ | O pacote `geracao/` só fala com o ComfyUI, o shop-tts, o `dockerctl` e o Claude, cada um com lista fechada `ALLOWED` no cliente. Não importa `publicacao`. O guarda `test_constitution_guards` ganha `geracao/` (nenhum host de rede social, nada de `publicacao`). Sem "youtube" nem "tiktok" em rotas e `operationId` (`geracoes_*`, `audios_*`) |
| **II. Direito é responsabilidade do dono** | ✅ (não afetado) | Nenhum envio para corte. O consentimento de pessoa real é da 025 |
| **III. Marca em tokens** | ✅ (não afetado) | O kit não muda |
| **IV. Contrato é a fonte única** | ✅ | Rotas e schemas Pydantic → `npm run gen:contract`; `GET /api/integracoes` só ganha campos. Os contratos externos (ComfyUI, shop-tts, `dockerctl`) não entram no OpenAPI do SociMan: ficam em `contracts/*.md` e nos fakes |
| **V. Segurança e segredos** | ⚠️ justificado (D1 = A decidida) | **Risco: o `docker.sock` dá poder total no host.** Mitigação: só o `dockerctl` o monta, com 3 ações sem parâmetros e valores fixos, rede `internal` só com o gerador, token, `read_only`, `cap_drop ALL` e `no-new-privileges` (research R4). Segredo novo: `DOCKERCTL_TOKEN` (`.env` da raiz, gerado pelo dono, coberto pelo `check:secrets`). O ComfyUI e o shop-tts não ganham porta na LAN (rede `gpu-local`, D2). A CSP não muda (`<audio>` e imagens pela mesma origem). As portas da API continuam fechadas |
| **VI. Testes antes de pronto** | ✅ | Unitários (passos, seeds, erros, workflows/manifesto, áudio), integração (fila, GPU, RAM, estados, escolha, aplicador, 008, limpeza, permissões, migration), guardas (I, VII, delete restrito, "nunca auto") e e2e. As regras inegociáveis têm teste no backend: escolha só humana (SC-004), limpeza só da exceção 1 (SC-006), nenhuma rede social |
| **VII. Humano no controle** | ✅ com as exceções da 4.3.0 e ⚠️ uma justificada | Gerações versionadas (`entity_type = geracao`), com `history.record` em cada ação humana. O alvo grava a versão com `details.geracao_id`. **Exceção 1 da 4.3.0:** a limpeza apaga candidatos não escolhidos aos 90 dias (nunca o escolhido), com o evento `eliminacao_candidatos` (quem, quando, contagem, motivo) e nunca disparada por IA, agente ou MCP (não há rota nem tool; só a trilha e o CLI). A exceção 2 (LGPD) é da 025; aqui só o `storage.apagar_por_excecao` já aceita o motivo `lgpd_revogacao`. **Justificada (Complexity Tracking):** a geração não tem "reverter", como envio e corte na 006 |
| **VIII. Simplicidade** | ⚠️ justificado | Dois serviços novos no compose (`gerador`, `dockerctl`), uma rede externa e um bucket. Nenhuma dependência nova e nenhuma fila nova (a fila é a tabela, como a dos cortes). Ver Complexity Tracking |
| Restrições: armazenamento NVMe × HD | ✅ | Imagens e áudios no MinIO do HD; uploads em `work/tmp` do HD; sentinela e piso em toda gravação; o PG guarda só metadados |
| Restrições: Redis | ✅ (não usado) | A fila e o andamento ficam no PG |
| Restrições: banco | ✅ | `0020_geracao_local` (provisório), com upgrade/downgrade e `test_migration_0020` |
| Restrições: portas | ✅ | `dockerctl` e `gerador` sem porta publicada; nada em 8000/5175/18789; o ComfyUI (8188) e o shop-tts (8200) continuam só em `127.0.0.1` |
| Restrições: containers UID 1000 | ✅ | `gerador` e `dockerctl` com UID 1000 (`dockerctl` com o gid do grupo docker) |

**Reavaliação pós-design:** mantida. O design trocou a "trilha `geracao`" do insumo por um serviço próprio
(R1), para isolar o acesso à rede da GPU e ao `dockerctl`. A única peça com poder total sobre o host é o
`dockerctl`, decidida pelo dono (D1 = A), com as travas do research R4. Todas as rotas novas estão
classificadas no `mcp/mapa.py`: as escritas (`RequireHuman`) em `PROIBIDAS` e as leituras em `FORA`.

## Decisões do dono (decididas em 2026-10-07)

| # | Decisão | Escolha | Consequência |
|---|---|---|---|
| **D1** | Onde fica o acesso ao Docker para a RAM de 28 GB ↔ 12 GB (**risco: o `docker.sock` dá poder total no host**) | **A:** container `dockerctl` mínimo no compose do SociMan, o **único** com o socket: 3 ações fixas sem parâmetros, rede `internal` só com o gerador, token, `read_only`, `cap_drop ALL` e `no-new-privileges` | T036 e T037; `contracts/dockerctl.md` (a opção B, no host, fica só como registro). Guarda: nenhum outro serviço monta o socket (T010) |
| **D2** | Rede para o ComfyUI e o shop-tts (hoje em `127.0.0.1`) | **A:** rede Docker externa `gpu-local` com `comfyui`, `shop-tts` e só o `gerador` | A mudança no `../comfyui-docker/docker-compose.yml` é a dependência externa **X1**, aplicada pelo dono antes do quickstart §2 |
| **D3** | Quando muda o shop-tts (contrato `v2`) | **Antes da 025**, pelo dono ou noutra sessão, no `../comfyui-docker` | Dependência externa **X2**; não bloqueia a 021 (o motor `tts` é testado contra o fake) |

Também ficou decidido: o texto final da emenda 4.3.0, com a exceção (2) ajustada (arquivos e textos que
descrevem a pessoa, inclusive em versões antigas do histórico). Ele é aplicado na T001.

## Contradições da spec resolvidas no plano

| Contradição | Resolução |
|---|---|
| `avatar.rostos_34` gera "2 pares" × 1 imagem por candidato | Coordenado com a 025: a opção é um **par**, com a coluna nova `geracao_candidatos.image_par_id` (lado direito); uma escolha preenche os dois slots (R15) |
| "Testar" da voz sem passo na lista | Coordenado com a 025: passo novo `voz.teste` (15 passos) e estado final novo `entregue` (sem escolha, alvo intocado, entra na limpeza) (R15) |
| `geracoes` sem `version` × histórico das ações humanas | `version` e `entity_type = geracao`; as ações humanas versionam e as do gerador são estado de job (R10) |
| Upload de 25 MB × edge com 8 MB | `location ~ ^/api/perfis/[^/]+/audios$` com 26m e sem buffering (R11) |
| Links de áudio | `MidiaKind "audio"`, sempre com validade e Range; candidatos de imagem com validade (R11) |
| "Trilha `geracao`" do insumo × serviço próprio | Serviço `gerador` (R1); a limpeza é a trilha `geracao_limpeza` do agendador (R12) |
| Chave do áudio `perfis/{id}/{uuid}.wav` × upload em m4a/ogg/mp3 | `perfis/{id}/audios/{uuid}.{ext}` pelo formato detectado; o original fica como veio (R11) |
| "Blocos `cena`" × não há `cena.params.json` no pipeline | `cena` = `V3 - Imagem FLUX schnell (txt2img)`, como o `cenarios.py criar`; com foto, `keyframe` (R6) |

## Project Structure

### Documentation (this feature)

```text
specs/021-geracao-local/
├── plan.md              # este arquivo
├── research.md          # R1–R16
├── data-model.md        # 3 tabelas, 1 coluna, estados, migration 0020
├── quickstart.md        # automático + manual com o dono (GPU real)
├── contracts/
│   ├── http-api.md      # rotas do SociMan (OpenAPI gerado)
│   ├── comfyui.md       # API padrão usada + mudança externa de rede
│   ├── shop-tts.md      # DEPENDÊNCIA EXTERNA: contrato v2 (não editado aqui)
│   └── dockerctl.md     # ajuste de RAM (decisão D1)
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks: T001–T060
```

### Source Code (repository root)

```text
.specify/memory/constitution.md               # T001: emenda 4.3.0 (via /speckit-constitution)
apps/api/src/sociman_api/geracao/
├── __init__.py
├── models.py          # Geracao (versionada), GeracaoCandidato, Audio
├── passos.py          # registro dos 15 passos, sufixos REALISMO/MANTER, aplicadores (R15)
├── aplicadores.py     # cenario.cena → asset_files referencia (piloto); protocolo para 025/012
├── seeds.py           # base, próximas sem repetir (R7)
├── erros.py           # códigos, mensagens pt-BR, espera crescente (R8)
├── fila.py            # claim por motor, heartbeat, requeue_stale, fins "é meu" (R2)
├── gpu.py             # GPU livre: envios 006 + /system_stats + pisos (R3)
├── memoria.py         # cliente do dockerctl, subir/devolver/conferir (R4)
├── comfyui.py         # cliente ALLOWED + run_block portado (R6)
├── shoptts.py         # cliente ALLOWED do contrato v2 (R13; real só depois de D3)
├── motor_claude.py    # ia.cliente + ia_chamadas com geracao_id (R14)
├── gerador.py         # `sociman gerador`: lock, linha GPU, linha Claude, SIGTERM (R1)
├── audios.py          # upload em work/tmp, ffprobe, sha256, put no bucket audios (R11)
├── uso.py             # midia_em_uso (R12)
├── limpeza.py         # trilha geracao_limpeza + CLI; único usuário do delete (R12)
├── service.py         # pedir, escolher, cancelar, tentar de novo, gerar outras + history
├── schemas.py
├── router.py          # /api/perfis/{id}/geracoes, /api/geracoes/{id}/…
├── router_audios.py   # /api/perfis/{id}/audios, /api/audios/{id}
└── workflows/         # 4 blocos (*.api.json + *.params.json) + MANIFEST.json (R6)
apps/api/src/sociman_api/
├── storage.py         # Bucket "audios"; apagar_por_excecao (único delete)
├── midia.py, router_midia.py   # MidiaKind "audio"
├── ia/models.py       # ia_chamadas.geracao_id
├── integracoes.py     # bloco "geracao"
├── mcp/mapa.py        # escritas em PROIBIDAS, leituras em FORA
├── agendador.py       # trilha geracao_limpeza
├── cli.py             # `sociman gerador`, `sociman geracoes limpar [--dry-run]`
├── config.py          # COMFYUI_URL, SHOP_TTS_URL, DOCKERCTL_URL/TOKEN, S3_AUDIOS_BUCKET, pisos, intervalos
└── main.py            # include_router
apps/api/migrations/versions/0020_geracao_local.py
apps/api/tests/
├── fakes/comfyui_fake.py, shoptts_fake.py, dockerctl_fake.py
├── unit/test_geracao_passos.py, test_geracao_seeds.py, test_geracao_erros.py,
│   test_workflows_manifest.py, test_audios_probe.py, test_constitution_guards.py (+021)
└── integration/test_geracao_fila.py, test_geracao_gpu.py, test_geracao_memoria.py,
    test_geracao_estados.py, test_geracao_escolher.py, test_geracao_permissoes.py,
    test_geracao_claude.py, test_geracao_limpeza.py, test_audios.py, test_migration_0020.py
docker/dockerctl/Dockerfile, server.py        # opção A de D1 (stdlib)
docker/nginx/default.conf.template            # location de /api/perfis/{id}/audios (26m)
docker-compose.yml                            # serviços gerador e dockerctl; redes gpu-local (external) e dockerctl (internal)
docker-compose.e2e.yml                        # gerador apontando para o openshorts-fake
scripts/data-setup.sh                         # check: DOCKER_GID, rede gpu-local, bucket de áudios
e2e/fakes/server.py                           # /comfyui, /shop-tts, /dockerctl, /geracao-e2e
e2e/geracao.spec.ts

apps/web/src/
├── components/geracao/PedirGeracao.tsx, AndamentoGeracao.tsx, OpcoesGeracao.tsx,
│   ListaGeracoes.tsx, PlayerAudio.tsx
├── lib/geracoes.ts                            # hooks TanStack Query (polling de 2 s enquanto não final)
└── pages/assets/AssetDetalhe.tsx              # seção "Gerar cena" + "Gerações" no cenário (piloto)
```

**Structure Decision**: o web app que já existe (apps/api + apps/web), com o pacote novo `geracao/`. Ele
não importa nada de `publicacao/` nem de `mcp/`. O `assets/` não importa `geracao/`: a seta é
`geracao.aplicadores → assets.service`. A 025 e a 012 plugam seus aplicadores e seus provedores de
"em uso" pelo registro de `passos.py` e de `uso.py`.

**Ordem sugerida para as tasks** (o `/speckit-tasks` detalha):
1. **T001 (gate):**
   - aplicar a emenda 4.2.0 → 4.3.0 da constitution pelo `/speckit-constitution`, com o texto aprovado;
   - conferir o próximo número livre de migration (renomear `0020` se a 024 tiver ocupado).
2. Migration + models + passos + seeds + erros (unitários).
3. Fila + GPU + memória + clientes, com fakes (US2).
4. Service, rotas e aplicador do `cenario.cena` (US1, US3).
5. Áudios + `MidiaKind` + edge (US5).
6. Motor Claude + 008 (US4).
7. Limpeza + delete restrito + guarda (US6).
8. SPA + e2e.
9. Compose (`gerador`, `dockerctl` conforme D1, redes conforme D2) + quickstart com o dono.

## Complexity Tracking

| Violação | Por que é necessária | Alternativa mais simples rejeitada porque |
|---|---|---|
| Serviço novo `gerador` (VIII) | Jobs de GPU levam minutos, e só esse processo deve ter acesso à rede da GPU e ao `dockerctl` (V) | Trilha no agendador: prende uma thread por minutos e daria ao agendador (que já tem os segredos da TikTok) o acesso ao Docker. Dentro do `worker`: um corte esperaria uma geração e vice-versa |
| Serviço novo `dockerctl` com o `docker.sock` (V, VIII) — **D1 = A** | A decisão do dono exige mudar o limite de RAM do container do ComfyUI no job e devolver depois; isso só se faz pela API do Docker | Socket no gerador ou proxy genérico: dão poder total ao processo que fala com a rede. Manter 28 GB sempre: contraria a decisão do dono |
| Rede externa `gpu-local` (VIII) — **D2 = A** | O ComfyUI e o shop-tts escutam em `127.0.0.1`, e o `host.docker.internal` não alcança o loopback | Bind no bridge ou `0.0.0.0`: abre para todo container ou para a LAN, sem senha |
| Geração sem "reverter" (VII) | Os atos humanos (cancelar, escolher, gerar outras) já são o desfecho; o caminho de volta é pedir outra geração. O alvo continua reversível pelo histórico dele | Um revert genérico da geração "desescolheria" uma opção já aplicada ao alvo: dois históricos para desfazer a mesma coisa. Mesma exceção aprovada de envio e corte na 006 |
| Delete no `storage.py` (VII, exceção 1 da 4.3.0) | A emenda 4.3.0 permite apagar candidatos não escolhidos aos 90 dias | Lifecycle do MinIO: não sabe qual opção foi escolhida e não registra evento |
| Cópia de 4 workflows do `../comfyui-docker` | O SociMan não pode ler o projeto vizinho em tempo de execução; o manifesto com sha256 evita deriva silenciosa | Bind mount do projeto vizinho: acopla os dois repos e quebra o e2e |
