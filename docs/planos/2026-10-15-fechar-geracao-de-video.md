# Fechar a geração de vídeo inicial: estado em 2026-10-15 e plano em paralelo

Ponto de parada pedido pelo dono às 17:23. Branch `031-video-guiado`, **nada commitado** desde o PR #8 (main =
`47bbc6f`). Este arquivo é o quadro de trabalho; os detalhes técnicos estão nos arquivos citados, não aqui.

## 1. O que está feito (na branch, sem commit)

| Item | Onde | Estado |
|---|---|---|
| Spec 031 (vídeo guiado) implementada contra os fakes | `specs/031-video-guiado/`, migration `0028` | T001–T058 ✅ |
| T059 §2: primeiro vídeo real (15 s, 3 cenas) | research R13 | ✅ medido; §3 pendente |
| Composição do quadro 0 (fundo do cenário, não do corpo-base) | `roteiros/pedidos.composicao_do_quadro` + teste | ✅ |
| MALLOC no ComfyUI (RAM não voltava a 12 GB) | `../comfyui-docker/docker-compose.yml` (autorizado) | ✅ no ar; falta nota no CLAUDE.md da raiz |
| Gerador sem teto de tempo nos blocos de vídeo | `geracao/comfyui.SEM_TETO` | ✅ |
| Plano sempre no MiniMax | `roteiros/plano.MOTOR_DO_PLANO` | ✅ |
| Motor do regerar de trecho fica na cena | `roteiros/service._regerar_trecho` + teste | ✅ |
| Acabamento `leve` padrão, `hd` opcional | `roteiros.acabamento_modo`, migration `0029`, wizard e avançado | ✅ + 2 testes |
| Regras do quadro (fixas) e enquadramento fixo do clipe | `pedidos.REGRAS_QUADRO`, `prompt_local.AMBIENTE_FIXO` | ✅ |
| Controles de regerar visíveis durante a geração | `etapas/Guiado.tsx` | ✅ |
| Estudo Voomi × SociMan e proposta da 030 | `docs/pesquisa/030-movimentos-ux.md` (§4.4 = regras e checagem) | ✅ |
| Grill da 030 | sessão `movimentos-030`, Q1–Q5 fechadas | ⏸ Q6–Q10 |

Verificações feitas hoje: ruff ok; `test:api -k` dos testes tocados (acabamento, regerar, duração, prompt, passos,
guardas) ok; `tsc` ok; `gen:contract` ok. **Não rodados:** `test:api` inteiro, `check:web`, e2e.

## 2. O que está em aberto

### 2.1 Para fechar a 031 (bloqueia o resto)
- [x] 2026-10-16: `test:api` inteiro (3819 passaram em 1 h 09; dois testes de tempo falharam sob carga da GPU e
      passaram isolados), `check:web` ok, e2e inteiro (119 passaram em 45 min).
- [x] 2026-10-16: branch movida para a main (`47bbc6f`, fix da memória do ComfyUI já estava na árvore). Falta:
      commit em pt-BR e PR, **quando o dono pedir**.
- [x] 2026-10-16: nota do MALLOC no `tiktok-shop/CLAUDE.md` (linha da memória do ComfyUI).
- [ ] Pergunta sem resposta do dono: o wizard deve continuar ligando todos os portões ao abrir?

### 2.2 Qualidade do vídeo guiado (lições da T059, research R13)
- [x] 2026-10-16: **o motivo da recusa da IA fica gravado** (`ia_chamadas.explicacao`, log e mensagem da
      geração) e **a `<grade>` do plano faz a conta dos trechos** (regras padrão v2): no 2º vídeo real (10 s)
      o plano falhou duas vezes, uma "fora do formato" sem motivo e outra com 3 cenas para 2 trechos.
- [ ] **Biblioteca de cenas com lixo**: candidatas repetidas e uma com "8 seconds" na ação entram no
      `<cenas>` do plano (6 mil tokens de entrada). Filtrar/arquivar as do pipeline antigo.
- [ ] **Fallback genérico das cenas reaproveitadas** (`plano_guiado.GENERICAS`): o plano deve pedir os quadros da
      cena derivada como faz na `nova`. Hoje = quadros iguais = zoom.
- [ ] **Locomoção não cabe em 5 s**: regra do plano (sem "walks across"; giro, gesto, mão no produto).
- [ ] **Ação do clipe editável no avançado** (hoje só pelo "Não aprovo", 500 caracteres).
- [ ] **"Na fila" × "Gerando…"** no wizard, com tempo estimado por etapa (medidas em R13).
- [ ] **Deriva de identidade** entre quadros: testar `rosto_34` nas âncoras (R3).
- [ ] T059 §3: trecho de 5 s × 8 s, emenda de 3 trechos, SC-006 (precisa da GPU e do dono).

### 2.3 Regras do quadro editáveis e checagem automática (estudo da 030, §4.4)
- [ ] Regras como `ia_regras` (padrão em código, editáveis pelo dono, três níveis: global → perfil → movimento).
- [ ] Prompt negativo do bloco keyframe (contrato do bloco em `../comfyui-docker`, com autorização).
- [ ] Passo `cena.quadro_checagem` (Claude visão): nota por item, nova seed automática até N, cartão "atenção".
- [ ] Registro das reprovações com a regra violada (aprendizado das regras).

### 2.4 Spec 030 (movimentos)
- [ ] Grill Q6–Q10: modo B na 030 ou depois; como o plano escolhe movimentos; N+2 aprovações e "Montar o
      vídeo" automático; vocabulário e "na fila"; experimento antes do specify.
- [ ] Reescrever `docs/insumos/030-clonagem-movimento.md` como "Movimentos" (ficha, biblioteca curada + pessoal,
      vídeo enviado guardado com consentimento, provedores e unidades de cobrança).
- [ ] `/speckit-specify` → clarify → plan → tasks.

### 2.5 Mais adiante
- 032 variantes de vídeo (insumo pronto); provedores externos de vídeo (desenho na 030, implementação no fim);
  cópia de pose (Wan Animate / VACE) como fase 2 da 030; multi-tenant.

## 3. Plano para continuar em paralelo (multiagente)

Regras do paralelismo: **a GPU e a stack de dev são um recurso só** (um trabalho de GPU por vez; o e2e nunca em
paralelo); código em **worktrees** separadas sobre a main já com a 031; `test:api` pode rodar em paralelo (stack
efêmera); **só uma frente mexe em migration por vez**; commit e PR só quando o dono pedir.

### Fase 0 (sequencial, hoje ou amanhã cedo): fechar e mesclar a 031
Uma sessão só: 2.1 inteiro. Sem isso, as frentes abaixo não têm base comum.

### Fase 1 (em paralelo, cada uma numa worktree)

| Frente | Escopo | Entrega | Toca migration? | Precisa do dono? |
|---|---|---|---|---|
| **A. Qualidade do guiado** | 2.2 menos o §3: fallback genérico, regra de locomoção, ação editável no avançado, "na fila" + estimativa | PR `031-qualidade-guiado` com testes | não | não (revisão no fim) |
| **B. Banco de prompts e formatos de cena** | 2.3 ampliado em 2026-10-16: `033-banco-de-prompts` (`docs/insumos/033-banco-de-prompts.md`): blocos de prompt editáveis com tela, formatos `avatar`/`pov_maos`/`sem_rosto`/`espelho`/`produto_so`, checagem do quadro por visão. O passo zero (ampliar `clipe.realismo` e `REGRAS_QUADRO`, §4.4 do insumo) pode ir na frente A | spec + PR | sim (blocos e formatos) → é a migration da fase, D espera | o clarify (6 perguntas no insumo) |
| **C. Insumo e spec da 030** | 2.4: fechar o grill (Q6–Q10 com o dono), reescrever o insumo, `/speckit-specify` e clarify | insumo + `specs/030-movimentos/spec.md` | não (só spec) | sim: o grill é com o dono |
| **D. Unidades por geração** | decisão Q2 do grill: gravar `unidades` (clipes de 5 s, quadros, HD) em cada geração e mostrar o tempo estimado; base para cobrar depois | PR pequeno | sim (coluna em `geracoes`) → roda **depois** de B decidir se precisa de migration, ou vira a única migration da fase | não |

Frentes A e D são autônomas. B e C têm pontos com o dono (clarify e grill), então ficam na sessão principal,
enquanto A e D rodam em subagentes.

### Fase 2 (GPU, com o dono, sequencial)
- T059 §3 (5 s × 8 s, emenda de 3 trechos, SC-006) e o teste de `rosto_34` nas âncoras.
- Experimento das 3 fichas de movimento (Q3 do grill: genérica × texto × quadro final).
- Segundo vídeo real com a frente A mesclada (meta: zero quadro ruim e um vídeo publicável sem retoque).

### Fase 3
- Implementar a 030 (tasks) → 032 variantes → provedores externos.

## 4. Critério de "geração de vídeo inicial fechada"
1. "Novo vídeo" → vídeo publicável em ≤ 45 min de GPU para 15 s, sem retoque manual, em 3 produtos diferentes.
2. Nenhum quadro com peça extra, zoom ou reenquadramento nos 3 vídeos (ou a checagem automática pega e refaz).
3. O leigo só vê: escolhas em cartão, "na fila / gerando / pronto" com tempo, aprovar ou "não aprovo".
4. Tudo mesclado na main com e2e verde.
