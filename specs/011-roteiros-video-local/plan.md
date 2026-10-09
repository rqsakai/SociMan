# Implementation Plan: Roteiros com vídeo local

**Branch**: `011-roteiros-video-local` (trabalho na `004-kit-de-marca-poc`, como as specs anteriores) |
**Date**: 2026-10-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-roteiros-video-local/spec.md`

## Summary

O SociMan ganha o **roteiro**: brief, produtos, avatar e voz viram um vídeo voice over 1080×1920, em seis
passos novos do motor de geração da 021:
1. `roteiro.plano`: Claude escreve as frases e as cenas, preferindo reaproveitar;
2. `roteiro.narracao`: shop-tts gera um take contínuo, com as pronúncias do perfil e a velocidade
   aplicada pelo SociMan;
3. `cena.keyframe`: Qwen Edit gera 2 opções;
4. `cena.clipe`: MiniMax, Wan ou LTX, conforme a cena; o clipe vira tomada da cena;
5. `roteiro.montagem`: ffmpeg, sem GPU, na prévia;
6. `roteiro.acabamento`: SeedVR2 + ffmpeg; o resultado vira conteúdo da 014 marcado como gerado por IA,
   sem destino.

Como o roteiro é conduzido:
- **Sem serviço novo.** Uma máquina de estados (`roteiros/maquina.py`) roda nas ações humanas e nos
  ganchos dos aplicadores da 021 (R1).
- **Montagem fora da GPU.** A montagem ganha uma 3ª linha no `gerador`, com o motor `ffmpeg`, fora da trava
  de GPU (R2).
- **Vídeo como candidato.** Os candidatos ganham colunas de vídeo, e a tomada aponta o mesmo objeto (R3).
- **Portões e automático.** Os cinco portões podem ser ligados ou desligados, ou o modo pode ser
  automático. A escolha automática da opção 1 do keyframe é a única exceção à "escolha humana" da 021: ela
  acontece só dentro do roteiro, com o ator `system:roteiro`, e uma guarda AST a protege (R9).
- **Nada se apaga nas invalidações.** As invalidações só marcam. A limpeza de 90 dias passa a cobrir os
  intermediários sem uso num vídeo final, com a emenda **4.4.0** (R12).

Nada publica: o conteúdo nasce sem destino, e aprovar e agendar continuam na 014/015 (princípio I).

## Technical Context

**Language/Version**: Python 3.12 (API, uv) · TypeScript 5 / React 19 (SPA, Vite)

**Primary Dependencies**: as da 021, sem nada novo:
- FastAPI, SQLAlchemy 2, Pydantic 2, httpx, Pillow;
- ffmpeg e ffprobe, já na imagem;
- SDK `anthropic`.

Na SPA: TanStack Query, shadcn/ui, `<video>`/`<audio>` nativos. **Nenhuma dependência nova.**

**Storage**:
- **PostgreSQL** (NVMe): 7 tabelas novas, colunas em `cenas`, `cena_tomadas`, `geracoes`,
  `geracao_candidatos` e `conteudos`.
- **MinIO** (HD): vídeos dos candidatos e das tomadas em `sociman-videos`, keyframes e miniaturas em
  `sociman`, narrações em `sociman-audios`.
- **Temporários** de montagem e acabamento em `${SOCIMAN_DATA_DIR}/work/tmp/roteiros/<geracao>/`, apagados
  no `finally`.

**Testing**:
- pytest na stack efêmera, com os fakes estendidos: o `comfyui_fake` devolve mp4 sintético pelo `ffmpeg
  testsrc2`, e o `shoptts_fake` atende `/v2/tts_paragraph` com tempos;
- regressão `test_tempos_bia_vo`;
- guardas AST da seção 011;
- `test_migration_0024`;
- Playwright `e2e/roteiros.spec.ts`, em que o `geracao_fake` devolve um mp4 fixo de 8 s e um wav.

Nenhum teste chama a GPU real. O teste real é com o dono (quickstart §2–§4).

**Target Platform**: Linux (host `sakai-desktop`), Docker. A SPA roda no desktop e no celular (modo casa).

**Project Type**: web (apps/api + apps/web). Sem serviço novo: o `gerador` ganha uma linha.

**Performance Goals**:
- Telas: ações do roteiro < 300 ms; `avancar` < 100 ms (só banco).
- Montagem de 20 s < 30 s de CPU.
- Na GPU real: 4 cenas do zero ≤ 75 min (SC-002).

**Constraints**:
- trava de GPU e RAM de 28 GB da 021 em keyframe, clipe e acabamento;
- montagem fora da trava;
- resolução nativa 736×1280;
- vídeo final 1080×1920 a 24 fps, sem interpolação;
- −14 LUFS;
- upload de keyframe ≤ 20 MB (edge 21m);
- CSP inalterada.

**Scale/Scope**:
- dezenas de roteiros por mês, até 8 cenas cada (configurável);
- cerca de 20 rotas novas e 4 aditivas;
- 3 telas novas (lista, novo, detalhe) e 1 aba no perfil.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.* A constitution é a **4.3.0**,
com a emenda **4.4.0** decidida pelo dono no clarify (2026-10-08) e **aplicada na 1ª tarefa** da
implementação. Texto proposto para a exceção (1):

> (1) candidatos de geração não escolhidos e artefatos intermediários de roteiro (tomadas, narrações e
> prévias) que não entraram num vídeo final entregue, 90 dias depois de deixarem de ser usados (o
> escolhido e o que está num vídeo entregue, nunca).

| Princípio | Situação | Como |
|---|---|---|
| **I. Publicação só com decisão humana** | ✅ | O roteiro só cria conteúdo da 014 **sem destino**. O `roteiros/` não importa `publicacao` (guarda). O modo automático não alcança aprovar, agendar nem publicar (SC-005). A marca `conteudoIa` só muda o **padrão** do formulário do destino, que continua humano |
| **II. Direito é responsabilidade do dono** | ✅ (não afetado) | Não há envio para corte. O consentimento de pessoa real vem da 025, e o FR-048 só proíbe gerar coisa nova com voz ou avatar revogados |
| **III. Marca em tokens** | ✅ (não afetado) | |
| **IV. Contrato é a fonte única** | ✅ | Rotas e schemas Pydantic → `npm run gen:contract`; códigos novos no `errors.ts`. Os contratos externos (blocos do ComfyUI, campo `pronuncias` do shop-tts) ficam em `contracts/*.md` e nos fakes |
| **V. Segurança e segredos** | ✅ | Nenhum segredo novo. O `dockerctl` da 021 não muda (as mesmas 3 ações). Upload de keyframe validado pelo conteúdo (Pillow) e limitado a 20 MB. Links de vídeo por HMAC com validade (`geracao_video`) |
| **VI. Testes antes de pronto** | ✅ | Unitários (tempos, prompt local, pronúncia/hash, máquina), integração (fluxo com portões, automático, invalidações, reuso, entrega, limpeza, revogação, permissões, migration), guardas e e2e |
| **VII. Humano no controle** | ✅ com a 4.4.0 | Roteiro, padrões e pronúncias versionados. As ações humanas têm `history.record`; a escolha automática gera versão com o ator `system:roteiro`, à vista. Invalidar nunca apaga. A limpeza dos intermediários é a exceção (1) ampliada, com evento `eliminacao_intermediarios`, nunca disparada por IA, agente ou MCP (só a trilha e o CLI) |
| **VIII. Simplicidade** | ⚠️ justificado | Uma linha a mais no `gerador` e 7 tabelas. Nenhum serviço, dependência ou fila nova (a fila é a `geracoes`). Ver Complexity Tracking |
| Restrições: NVMe × HD | ✅ | Mídia e temporários no HD, com o sentinela e o piso; o PG só com metadados |
| Restrições: banco | ✅ | `0024_roteiros_video_local` (provisória), com upgrade/downgrade e teste |
| Restrições: portas | ✅ | Nenhuma porta nova |

**Reavaliação pós-design:** mantida.
- A escolha automática ficou num módulo só, coberto por uma guarda AST, e confere passo, roteiro e modo na
  mesma transação.
- A emenda 4.4.0 é a única mudança de governança, e o dono a pediu.
- Todas as rotas novas estão classificadas no `mcp/mapa.py`: as escritas em `PROIBIDAS`, as leituras em
  `FORA`.

## Decisões do plano (recomendadas; o dono pode trocar na revisão)

| # | Decisão | Escolha | Alternativa descartada |
|---|---|---|---|
| P1 | Quem conduz o roteiro | Máquina nos ganchos da 021 (R1) | Trilha de polling ou serviço novo |
| P2 | Onde roda a montagem | 3ª linha do `gerador`, motor `ffmpeg` (R2) | Worker de cortes (fila presa a `cortes`) |
| P3 | Vídeo do clipe × tomada | Mesmo objeto, sem cópia (R3) | Copiar para `cenas/<cena>/tomadas/` (dobra o HD) |
| P4 | Velocidade da narração | `atempo` no SociMan, depois do shop-tts (R5) | Mudar o shop-tts para aceitar velocidade |
| P5 | Limpeza da tomada | A linha fica sem mídia (`limpa_em`), como a 021 e a 025 (R12) | Apagar a linha (quebraria histórico e FKs) |
| P6 | O que "usado num vídeo final" protege | O vídeo final, mais as tomadas, os keyframes e a narração dele, porque assim o reuso funciona (R12) | Só o vídeo final (cada reuso pagaria GPU de novo) |
| P7 | Resolução do acabamento | A da cena, 736×1280, como no vídeo aprovado (R11) | 720×1248, o padrão do script |

## Dependências externas e de ordem

| # | O quê | Quem | Bloqueia |
|---|---|---|---|
| — | 012 e 025 implementadas (produtos, variantes, kit do avatar, vozes, `assets.voz_id`) | sessões de implementação | o início da 011 |
| X1 | Rede `gpu-local` no `../comfyui-docker` (021) | dono | quickstart §2 |
| X2 | shop-tts contrato v2 (021/025) | dono | quickstart §2 |
| **X3** | Campo `pronuncias` no `/v2/tts_paragraph` ([contracts/shop-tts-pronuncias.md](contracts/shop-tts-pronuncias.md)) | dono | quickstart §2 (a narração real) |

## Project Structure

### Documentation (this feature)

```text
specs/011-roteiros-video-local/
├── plan.md              # este arquivo
├── research.md          # R1–R20
├── data-model.md        # 7 tabelas, extensões da 010/021/014, máquina, migration 0024
├── quickstart.md        # automático + manual com o dono (GPU real)
├── contracts/
│   ├── http-api.md            # rotas do SociMan (OpenAPI gerado)
│   ├── comfyui-blocos.md      # blocos de vídeo copiados (sem mudança externa)
│   └── shop-tts-pronuncias.md # DEPENDÊNCIA EXTERNA X3
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
.specify/memory/constitution.md                 # T001: emenda 4.4.0 (via /speckit-constitution)
apps/api/src/sociman_api/roteiros/
├── __init__.py
├── models.py          # Roteiro, RoteiroProduto, RoteiroCena, RoteiroNarracao, RoteiroEntrega, RoteiroPadroes, Pronuncia
├── tempos.py          # limites() puro (R6)
├── pronuncia.py       # aplicar() e hash_atual() puros (R10)
├── maquina.py         # avancar(): etapas, portões, invalidações, cancelamentos (R1)
├── automatico.py      # único chamador de geracao.service.escolher_automatico (R9)
├── aplicadores.py     # 6 aplicadores registrados no APLICADORES da 021
├── montagem.py        # comandos ffmpeg puros + execução (R2, R11)
├── entrega.py         # conteúdo 014, roteiro_entregas, cenas.usos (R13)
├── retencao.py        # seleção pura dos intermediários protegidos/elegíveis (R12)
├── service.py         # criar, editar, planejar, aprovar, controle, posições, tentar de novo, arquivar
├── service_pronuncias.py, service_padroes.py
├── schemas.py
└── router.py, router_perfil.py
apps/api/src/sociman_api/
├── geracao/passos.py, models.py, comfyui.py (BLOCOS + vídeo), gerador.py (LinhaMontagem, vídeo, narração),
│   fila.py (claim ffmpeg), limpeza.py (fase 2), service.py (escolher_automatico), workflows/ (+5 blocos, MANIFEST)
├── cenas/models.py, service.py (CAMPOS_LOCAIS, marcar_pronta, duplicar), tomadas.py (prompt_usado, geracao_local),
│   prompt_local.py (R7)
├── conteudos/models.py (gerado_ia), video_proprio.py (create_de_objeto)
├── publicacao/…        # só o padrão de conteudoIa (sem nova chamada de rede)
├── storage.py (Excecao intermediarios_90d), midia.py (MidiaKind geracao_video), imaging.py (keyframe)
├── auth/deps.py (ator system:roteiro), history.py ("sistema (automático)")
├── ia/tipos.py (roteiro.plano), mcp/mapa.py, config.py (ROTEIRO_MAX_CENAS), main.py
apps/api/migrations/versions/0024_roteiros_video_local.py
apps/api/tests/
├── fakes/comfyui_fake.py (+vídeo), shoptts_fake.py (+tts_paragraph), fixtures/bia_vo_timings.json
├── unit/test_roteiro_tempos.py, test_roteiro_pronuncia.py, test_prompt_local.py, test_roteiro_maquina.py,
│   test_montagem_comandos.py, test_constitution_guards.py (+011), test_workflows_manifest.py
└── integration/roteiro_helpers.py, test_roteiro_fluxo.py, test_roteiro_automatico.py,
    test_roteiro_invalidacoes.py, test_roteiro_reuso.py, test_roteiro_entrega.py, test_roteiro_limpeza.py,
    test_roteiro_revogacao.py, test_roteiro_permissoes.py, test_pronuncias.py, test_migration_0024.py
docker/nginx/default.conf.template              # location do upload de keyframe (21m)
docker-compose.yml, docker-compose.e2e.yml      # ROTEIRO_MAX_CENAS em api e gerador
e2e/fakes/geracao_fake.py, e2e/fixtures/geracao/clipe_8s.mp4, narracao.wav, e2e/roteiros.spec.ts
apps/web/src/
├── pages/roteiros/RoteirosList.tsx, RoteiroNovo.tsx, RoteiroDetalhe.tsx, etapas/{Texto,Narracao,Keyframes,Clipes,Final}.tsx
├── pages/perfis/tabs/VideoLocalTab.tsx         # padrão de portões + pronúncias
├── components/roteiro/Portoes.tsx, PlayerVideo.tsx, LinhaTempos.tsx
├── components/shell/nav.ts                     # item "Roteiros"
└── lib/roteiros.ts                             # hooks (polling 2 s com geração aberta)
```

**Structure Decision**: o web app que já existe, com o pacote novo `roteiros/`. As setas:
- `roteiros → geracao.service`, `cenas.service`, `conteudos.video_proprio`, `produtos`, `vozes`;
- `geracao` não importa `roteiros`: os aplicadores entram pelo registro, como os da 025 e da 012;
- `roteiros` não importa `publicacao` nem `mcp`.

## Complexity Tracking

| Violação | Por que precisa | Alternativa mais simples rejeitada porque |
|---|---|---|
| 3ª linha (thread) no `gerador` | A montagem não pode esperar a GPU (FR-043), e o gerador já tem o MinIO e o `work/tmp` | Rodar a montagem na linha GPU segura a GPU à toa; o worker de cortes tem a fila presa a `cortes` |
| Escolha automática (exceção à regra da 021) | Decisão do dono (modo automático) | Não há alternativa; fica contida num módulo, com guarda AST e conferência na transação |
| Limpeza que apaga mídia de tomada e narração | Decisão do dono no clarify (90 dias) | Guardar tudo enche o HD com clipes de 3 a 20 MB por tentativa; exige a emenda 4.4.0 |
| 7 tabelas | Cada uma tem ciclo de vida próprio: posições, narrações (várias por roteiro), entregas (só inserção, protege da limpeza), padrões e pronúncias (versionados) | Colocar tudo em jsonb do roteiro perderia as FKs que a limpeza e a proteção precisam |
