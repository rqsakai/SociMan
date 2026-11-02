# Implementation Plan: Vídeo guiado

**Branch**: `031-video-guiado` | **Date**: 2026-10-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/031-video-guiado/spec.md`

## Summary

O plano amplia o roteiro da 011 em vez de criar um sistema novo. Um **roteiro guiado** tem tipo de vídeo,
cenário, duração-alvo e uma cópia da grade.

O "Novo vídeo" passa a ser uma sequência de blocos com cartões de imagem. Ao fim dos blocos, a IA gera **numa
chamada só** as até 5 perguntas fechadas (passo `roteiro.perguntas`). As respostas vão ao planejador da 011,
que tem uma saída v2 com estas regras:
- cada posição ocupa de 1 a 3 trechos-base;
- cada cena tem uma instrução por quadro;
- o reuso tem nível `total` ou `plano`;
- a fala de cada posição tem um orçamento de caracteres.

O resto da geração funciona assim:
- **Quadros:** cada um nasce do anterior (Qwen Edit com `base_image` = quadro anterior). No wizard, a cadeia
  segue com a opção única, de forma provisória, e o operador aprova a sequência da cena.
- **Trechos:** cada trecho é um clipe com quadro inicial e final, um recurso que os 4 blocos de clipe já
  aceitam. Os trechos são ajustados para exatamente o trecho-base e colados.
- **Narração:** continua contínua, mas cada bloco de fala é posto no início do seu slot. O vídeo tem
  exatamente a duração escolhida.
- **"Não aprovo":** vira um pedido ao passo `roteiro.ajuste`. A IA devolve um esclarecimento com opções ou uma
  mudança, que é aplicada pelo save normal do roteiro, com o humano como autor, e só o que mudou é refeito.

O wizard e o avançado são duas apresentações do mesmo roteiro. Os roteiros da 011 abrem no avançado.

## Technical Context

**Language/Version**: Python 3.12 (API, uv) · TypeScript 5 / React 19 (SPA, Vite)

**Primary Dependencies**: as da 011, **sem nada novo**:
- API: FastAPI, SQLAlchemy 2, Pydantic 2, SDK `anthropic`, ffmpeg/ffprobe;
- SPA: TanStack Query, shadcn/ui, `<audio>`/`<video>`.

**Storage**:
- **PostgreSQL (NVMe):**
  - 3 tabelas novas: `roteiro_conversa` (só inserção), `roteiro_trechos` e `cena_quadros`;
  - colunas novas em `roteiros`, `roteiro_cenas`, `cenas` e `cena_tomadas`;
  - migration `0028_video_guiado`.
- **MinIO (HD):** quadros no bucket de imagens, trechos no de vídeos, sem prefixo novo.
- **Temporários** da montagem: os da 011.

**Testing**:
- pytest na stack efêmera: unitários de grade, orçamento, plano v2, encadeamento e `setpts`; integração do
  fluxo guiado com fakes; `test_migration_0028`; guardas;
- Playwright: `e2e/video-guiado.spec.ts` novo, e `e2e/roteiros.spec.ts` ajustado (cria pela API e abre no
  avançado);
- nenhum teste chama a GPU real.

**Target Platform**: Linux (`sakai-desktop`), Docker; SPA no desktop e no celular (modo casa).

**Project Type**: web (apps/api + apps/web). Nenhum serviço novo.

**Performance Goals**:
- ações do roteiro < 300 ms; responder pergunta < 150 ms (só banco);
- montagem de 30 s < 40 s de CPU;
- GPU real: 20 s em ~1 h, 30 s em ~1 h 30 (R11);
- reuso total = 0 GPU.

**Constraints**:
- trava de GPU e RAM de 28 GB da 021 (com a correção de 2026-10-13);
- resolução nativa 736×1280;
- trecho = trecho-base exato (`setpts`);
- −14 LUFS;
- wizard sem prompt nem fala **na tela** (FR-015). A API é a mesma nos dois modos;
- CSP inalterada.

**Scale/Scope**:
- até 8 posições e até 3 trechos por posição (≤ 24 trechos e ≤ 32 quadros por vídeo);
- 9 rotas novas e 5 aditivas;
- 1 tela nova (blocos e chat), o detalhe ganha o wizard e o modal.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.* Constitution **4.5.0**.

| Princípio | Situação | Como |
|---|---|---|
| **I. Publicação só com decisão humana** | ✅ | O vídeo final continua sendo um conteúdo da 014 sem destino. `roteiros/` não importa `publicacao` (guarda da 011) |
| **II. Direito é do dono** | ✅ (não afetado) | Sem corte de fonte. O consentimento da 025 continua barrando avatar e voz revogados |
| **III. Marca em tokens** | ✅ (não afetado) | |
| **IV. Contrato é a fonte única** | ✅ | `gen:contract`; os formatos da IA ficam em `contracts/http-api.md` e nos fakes |
| **V. Segurança e segredos** | ✅ | Nenhum segredo novo. Textos livres limitados a 500 caracteres. Links de mídia com HMAC |
| **VI. Testes antes de pronto** | ✅ | Ver Testing e quickstart §1 |
| **VII. Humano no controle** | ✅ com nota | Toda escolha, resposta e recusa é humana, com histórico. Duas ações da máquina, à vista e com ator `system:roteiro`: (a) a opção única de um quadro aplicada **provisoriamente** para seguir a cadeia (R3), que não passa do portão sem a aprovação humana da sequência; (b) a mudança do `roteiro.ajuste`, aplicada **em nome do humano que pediu** (autor = ele, `details.ia`), cujo resultado volta para aprovação. Nenhuma delas aprova portão. A escolha automática continua num módulo só (`automatico.py`, guarda AST ampliada) |
| **VIII. Simplicidade** | ⚠️ justificado | 3 tabelas e 2 passos. Nenhum serviço, fila ou dependência nova. As perguntas saem numa chamada só (sem multi-turn). Ver Complexity Tracking |
| **IX. Coleta de mercado** | ✅ (não afetado) | |
| Restrições: NVMe × HD | ✅ | Mídia no HD com o sentinela; o PG só com metadados |
| Restrições: banco | ✅ | `0028_video_guiado` com upgrade, downgrade e teste; backup antes, no dev |
| Restrições: portas | ✅ | Nenhuma |

**Reavaliação pós-design:** mantida. A extensão do `automatico.py` (opção única do guiado) é a única mudança em
área sensível, e a guarda AST continua sendo a que restringe quem chama `escolher_automatico`.

## Decisões do plano (recomendadas; o dono pode trocar na revisão)

| # | Decisão | Escolha | Alternativa descartada |
|---|---|---|---|
| P1 | Trecho-base | 5 s, grade 5–30 s, no `.env`; medir 8 s com o dono (R1) | Grade por motor (quebra a 032) |
| P2 | Perguntas do chat | 1 chamada gera as até 5 (R5) | Conversa multi-turn (cara e imprevisível) |
| P3 | Narração na grade | Contínua, cortada por bloco e posta no slot, com `atempo` por bloco até 1,20 (R4) | 1 TTS por bloco (prosódia quebrada) |
| P4 | Duração exata do trecho | `setpts` para o trecho-base, sem o 1º quadro repetido (R2) | `trim` (cortaria o quadro final) |
| P5 | Cadeia de quadros no wizard | Opção única aplicada provisoriamente, aprovação da sequência (R3) | Aprovar quadro a quadro (descartado no clarify 2) |
| P6 | "Não aprovo" | Passo `roteiro.ajuste` aplica em nome do humano (R6) | Mostrar a proposta para confirmar (expõe o prompt) |
| P7 | Modo lembrado | `localStorage` por roteiro (R9) | Coluna no banco (é preferência de quem vê) |
| P8 | Roteiros da 011 | Abrem no avançado; criar da 011 `deprecated` (R10) | Migrar para o guiado (sem cenário nem grade) |

## Dependências externas e de ordem

| # | O quê | Quem | Bloqueia |
|---|---|---|---|
| — | PR da correção de memória do ComfyUI (2026-10-13) mesclado | dono | quickstart §2 |
| — | Reboot do host (driver NVIDIA 595.99) | dono | quickstart §2 |
| — | Pelo menos 1 cenário com a imagem `cena` (025) e 1 produto aprovado | dono (cadastro) | quickstart §2 |

Não é preciso mexer no `../comfyui-docker`: os blocos de clipe já aceitam `end_image`, e as cópias em
`geracao/workflows/` batem com as de lá (cmp).

## Project Structure

### Documentation (this feature)

```text
specs/031-video-guiado/
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
├── migrations/versions/0028_video_guiado.py
├── src/sociman_api/
│   ├── config.py                       # ROTEIRO_TRECHO_BASE_S, ROTEIRO_GRADE_MAX
│   ├── roteiros/
│   │   ├── grade.py                    # novo, puro: opções, orçamento de caracteres, soma das posições
│   │   ├── conversa.py                 # novo: perguntas, respostas, estado, esclarecimentos
│   │   ├── guiado.py                   # novo: criar guiado, definir cena (modal), aprovar posição, recusar
│   │   ├── plano.py                    # v2 (quadros, trechos, nível, orçamento) ao lado da v1
│   │   ├── aplicadores.py              # perguntas, ajuste, plano v2, quadro (cadeia), trecho
│   │   ├── pedidos.py                  # keyframe por quadro (base = cenário/quadro anterior), clipe por trecho
│   │   ├── maquina.py / estado.py      # cadeia de quadros, trechos, portões por posição, reposicionar
│   │   ├── automatico.py               # + opção única do guiado (provisória)
│   │   ├── montagem.py / tempos.py     # setpts por trecho, fala por slot, atempo por bloco
│   │   ├── models.py, schemas.py, router.py
│   ├── cenas/
│   │   ├── models.py                   # trechos, origem_cena_id, CenaQuadro; tomada.trecho/keyframe_fim
│   │   └── quadros.py                  # novo: quadros da cena, espelho em keyframe_inicial/final
│   ├── geracao/passos.py               # roteiro.perguntas, roteiro.ajuste; keyframe n_max 4
│   ├── ia/tipos.py, ia/saida.py        # perguntas_roteiro, ajuste_roteiro, plano_roteiro v2
│   └── mcp/mapa.py                     # rotas novas classificadas
└── tests/
    ├── unit/test_roteiro_grade.py, test_plano_v2.py, test_montagem_trechos.py
    ├── integration/test_video_guiado.py, test_quadros_cadeia.py, test_reuso_niveis.py,
    │   test_conversa.py, test_recusar_ajuste.py, test_migration_0028.py
    └── fakes/ (anthropic_fake + comfyui_fake estendidos)

apps/web/src/
├── pages/roteiros/
│   ├── VideoNovo.tsx                   # novo: blocos (substitui RoteiroNovo)
│   ├── RoteiroDetalhe.tsx              # switch wizard/avançado
│   └── wizard/                         # novo: Conversa, ModalCenas, NarracaoWizard, QuadrosWizard,
│                                       #       ClipesWizard, FinalWizard, NaoAprovo
├── components/video-guiado/            # novo: BlocoEscolha (radiogroup de cartões), ResumoEscolhas, Chat
└── lib/roteiros.ts, lib/videoGuiado.ts # hooks e chaves

e2e/video-guiado.spec.ts (novo) · e2e/roteiros.spec.ts (ajustado) · e2e/fakes/server.py (formatos novos)
```

**Structure Decision**: o web app que já existe. O código novo fica dentro de `roteiros/` e `cenas/`, sem
pacote novo. A SPA ganha `pages/roteiros/wizard/` e `components/video-guiado/`.

## Complexity Tracking

| Violação | Por que é preciso | Alternativa mais simples descartada porque |
|---|---|---|
| 3 tabelas novas | Os quadros (até 4 por cena, com histórico de recusas), a tomada por trecho e o chat (que retoma de onde parou e fica no histórico) não cabem nas colunas da 011 | Um JSONB no roteiro: perderia FKs para `images`/`cena_tomadas`, a proteção da limpeza e a consulta por cena para o reuso |
| 2 passos novos na 021 | As perguntas e o ajuste são chamadas ao Claude com registro e custo, como todas as outras (008) | Chamar o Claude direto na rota: travaria a requisição até 120 s e ficaria sem registro |
| Ampliar o `automatico.py` | Sem a opção única provisória, a cadeia de quadros exigiria aprovação quadro a quadro (descartado no clarify 2) | Aprovar quadro a quadro: até 4 idas e vindas por cena |
