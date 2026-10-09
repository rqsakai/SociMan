# Implementation Plan: Central de conteúdos, aprovação e agendamento (014-central-de-conteudos)

**Branch**: `014-central-de-conteudos` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/014-central-de-conteudos/spec.md`

## Summary

A 014 junta num lugar só tudo o que pode ser publicado, separa **aprovar** de **agendar** e deixa o
modelo pronto para os modos automáticos da 015, **sem executar nenhum deles** (princípio I). Tem
cinco blocos:

- **Conteúdo (US1, US5):**
  - tabela nova `conteudos`, eixo da central. Na origem `corte`, o id **é o do corte** e o estado
    vem do corte por `JOIN` (nada copiado); na origem `video_proprio`, o conteúdo é dono do
    arquivo (research R1);
  - envio de **vídeo próprio** (até 2 GB, 1 s a 10 min) pelo streaming da 004/006, com ffprobe e
    miniatura extraída na própria requisição (R9).
- **Destino (US2):**
  - a `Postagem` da 006 vira o **destino** (conteúdo × conta), na mesma tabela `postagens`, com
    estados gravados `pendente → aprovacao_pedida → aprovado → agendado → postado` (e
    `rascunho_criado`/`publicado`/`falhou` reservados à 015 e bloqueados no banco) (R2, R3);
  - **aprovar e recusar** (com motivo) são do dono; **pedir aprovação** é de todos e avisa os
    donos no sino; aprovar em lote com `SAVEPOINT` por item (R5).
- **Agendamento (US3):**
  - campos do destino (`planned_at`, `modo`, `antecedencia_min`); "agendar direto" num conteúdo
    pronto aprova e agenda no mesmo passo quando quem agenda é dono (R6);
  - **capacidades por rede em código**, com o motivo de cada modo indisponível; na 014, só
    `lembrete` está disponível, e um CHECK no banco garante isso (R4);
  - a trilha `lembretes` da 006 continua só avisando; `a_postar` e `atrasado` são **derivados**
    (R3, R8).
- **Sequência (US4):** planejador puro com prévia sem estado, janela de conflito = **intervalo
  mínimo da conta** (coluna nova `contas.intervalo_min_minutos`, padrão 30, editável só por dono;
  a sequência pula, o agendamento individual avisa e deixa manter) e confirmação que recalcula e recusa se a prévia ficou velha; os textos que faltam são
  gerados pelo SPA com o assistente da 008 (R7).
- **Central no SPA (US1):** tela **Conteúdos** com filtros na URL, atalhos com contagem e cursor
  no servidor; detalhe com uma aba por conta; "Agendar" no detalhe do conteúdo, na lista, no corte
  pronto e na aba Cortes do perfil; calendário com modo e estado (R10, R11, R14).

Detalhes em [research.md](research.md), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md) e [quickstart.md](quickstart.md). As perguntas ao
dono foram respondidas em 2026-09-29 (spec, Clarifications: Q1 A, Q2 A, Q3 C com padrão de
30 min, Q4 A); [open-questions.md](open-questions.md) está resolvido.

## Technical Context

**Language/Version**: Python 3.12 (API e agendador) · TypeScript 5 / React 19 (SPA)

**Primary Dependencies**:
- **Python:** nada novo. ffmpeg/ffprobe (004), `httpx` e `anthropic` (006/008) já existem.
- **SPA:** nada novo. shadcn/ui, TanStack Query e TanStack Table v9 (005).

**Storage**:
- PostgreSQL (NVMe): `conteudos` (nova); `postagens` (ampliada: destino); `contas`
  (+`intervalo_min_minutos`); `ia_chamadas` (+`conteudo_id`); `notificacao_tipo` (+2 valores). Migration `0009_central_conteudos`
  (down_revision `0008_assistente_ia`);
- MinIO (HD): vídeo próprio em `sociman-videos` (`conteudos/{id}/video.<ext>`) e miniatura em
  `sociman`; spool do upload em `work/tmp` (sentinela e piso da 004).

**Testing**:
- pytest na stack efêmera (`npm run test:api`):
  - `test_migration_0009.py` (sobe com dados da 006 e desce);
  - `test_conteudos.py` (lista, filtros, cursor, atalhos, invariante corte ⇔ conteúdo, vídeo
    próprio com ffmpeg real);
  - `test_destinos.py` (aprovação, pedido, recusa, lote, permissões dono × membro, histórico,
    reversão, `videoMudou`);
  - `test_agendamentos.py` (direto, reagendar, cancelar, arquivar cancela, conta em atenção,
    intervalo mínimo da conta: 409 `intervalo_conflito` e `ignorarIntervalo`, sequência com prévia e
    `previa_desatualizada`);
  - `test_contas.py` ampliado (`intervaloMinMinutos`: padrão 30, limites 0..1.440, membro 403,
    histórico e reversão);
  - `unit/test_sequencia.py` (planejador puro: fuso, passado, conflito com o intervalo da conta,
    intervalo 0, horizonte) e
    `unit/test_capacidades.py`;
  - `test_lembretes.py` ampliado (modo, conta em atenção, link novo) e `test_ia_postagem.py`
    ampliado (alvo `conteudo`, vídeo próprio sem transcrição);
  - `test_escala_conteudos.py`: 500 conteúdos e 1.000 destinos, p95 < 200 ms na lista filtrada;
  - guardas do princípio I (abaixo);
- ruff; `npm run check:web` (contrato regenerado);
- Playwright `e2e/conteudos.spec.ts` (US1 a US5, com membro e dono), e o
  `e2e/cortes-openshorts.spec.ts` e o `e2e/assistente-ia.spec.ts` ajustados (a seção Postagem vira
  o painel de destinos, e as rotas `/api/cortes/{id}/postagens` e `/api/postagens/*` saem).

**Target Platform**: a mesma stack. Sem serviço novo. O edge ganha uma `location` (upload do vídeo
próprio).

**Project Type**: web application (SPA + API + worker + agendador)

**Performance Goals**:
- SC-006: lista com 500 conteúdos filtrada e paginada com p95 < 200 ms no servidor (keyset,
  índices do data-model, destinos numa segunda consulta sem N+1);
- SC-001: as duas perguntas do dono são **um clique** cada (atalhos "Esta semana" com filtro de
  conta e "Prontos sem agendamento"), com as contagens em `GET /api/conteudos/resumo`;
- SC-002: agendar um corte pronto = um diálogo (conta, data, IA, modo) e uma requisição
  (`POST /api/agendamentos`); a geração de textos leva menos de 15 s (008);
- SC-003: sequência de 10 = prévia + confirmação (< 1 s cada) + textos no SPA com 3 chamadas em
  paralelo (cerca de 40 s).

**Constraints**:
- nada executa em rede social (princípio I): só `lembrete`, com três camadas de defesa (R4);
- sem rota DELETE; toda mutação com `history.record`; reversão só pelo dono (princípio VII);
- fuso `America/Sao_Paulo` na tela, `timestamptz` no banco (como a 006);
- vídeo próprio até 2 GB no HD (sentinela e piso), sem transcodificar.

**Scale/Scope**:
- 2 perfis (até cerca de 10), 4 a 20 contas, 43 cortes hoje e cerca de 60 por dia; alvo de
  desenho: 5 mil conteúdos e 10 mil destinos;
- cerca de 30 endpoints (novos ou alterados) e 10 removidos (os de postagem da 006);
- telas: Conteúdos, detalhe do conteúdo, `AgendarDialog`, `SequenciaDialog`, painel de destinos
  (corte e conteúdo), calendário ajustado.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|---|---|---|
| I. Publicação só com decisão humana (4.0.0) | ✅ | Os modos `criar_rascunho`, `publicar` e `rascunho_e_publicar` são **só modelados**: valores de enum, textos de motivo e o registro de capacidades. **Nenhum executa.** Não entra credencial, conexão de conta, cliente HTTP de rede social, SDK nem trilha nova. Três camadas: (1) `modos_da_conta` devolve só `lembrete` disponível e o service responde 409 `modo_indisponivel`; (2) CHECKs `ck_postagens_modo_014` e `ck_postagens_estados_015` no banco; (3) testes-guarda (abaixo). `postado` continua só em `postagem/service.py::marcar_postado`. Rotas e `operationId` sem `publish`/`tiktok`/`youtube`/`share`. A trilha `lembretes` só avisa. O interruptor `PUBLICACAO_HABILITADA` e o "só dono agenda envio automático" são da 015 (na 014 não há envio); membro agenda só `lembrete`, que não envia nada (Clarifications Q1) |
| II. Direito é responsabilidade do dono | ✅ (não afetado) | Não há envio para corte nesta spec. O vídeo próprio não passa pelo OpenShorts nem tem canal-fonte; a versão `created` registra autor e arquivo. Aprovar para uma conta não bloqueia nem muda o status de direito |
| III. Marca em tokens | ✅ | "Pronto" continua exigindo a marca aplicada pelo worker da 004 (origem corte). O vídeo próprio é declarado pronto pelo dono, sem prosa de marca |
| IV. Contrato é a fonte única | ✅ | Todas as rotas no OpenAPI → `gen:contract`. As rotas de postagem da 006 saem do contrato, e o `check:contract` aponta cada uso no SPA |
| V. Segurança e segredos | ✅ | Nenhum segredo novo. CSP igual (player via `/api/midia/`, mesma origem). Upload com o `precheck` da 004 (HD, tamanho) e ffprobe pelo conteúdo. Uma `location` nova no edge, limitada ao caminho do upload |
| VI. Testes antes de pronto | ✅ | pytest (migração, domínio, permissões, escala), ruff, `check:web` e e2e; os guardas do I e do VII ampliados (abaixo) |
| VII. Humano no controle | ✅ com exceção herdada | Destino e conteúdo com `version`, `check_version` (409), `history.record` em toda mutação (inclusive cada item de lote e o cancelamento por arquivamento), autor e antes/depois; reversão pelo dono (`destinos_revert`, `conteudos_revert`), que nunca desfaz `postado` nem restaura aprovação. **Exceção herdada da 006:** o conteúdo de origem corte arquiva e restaura pelo corte e não tem `revert` de arquivamento próprio (o corte não tem `revert`). Nada é apagado |
| VIII. Simplicidade | ✅ com justificativa | Uma tabela nova, três enums e nenhuma dependência nem serviço. Estados que dependem do relógio são derivados (sem job). Prévia sem estado. Detalhes em Complexity Tracking |

**Reavaliação pós-design:** mantida.

### Guardas (testes automatizados do princípio I e do VII)
Em `apps/api/tests/unit/test_constitution_guards.py` (seção "spec 014") e
`tests/integration/test_guardas_014.py`:
1. **Rotas:** o `test_nenhuma_rota_de_publicacao` existente já cobre as rotas novas; um teste novo
   confere que toda rota de `/api/conteudos`, `/api/destinos` e `/api/agendamentos` tem
   `operationId` com o prefixo do recurso e nenhuma é DELETE.
2. **Capacidades:** para cada `Platform` e para contas em cada `ContaStatus`,
   `modos_da_conta` devolve **no máximo** `lembrete` como disponível, e todo modo indisponível tem
   motivo.
3. **Service:** `POST /api/agendamentos`, `PATCH …/agendamento` e `sequencia` com cada modo
   automático → 409 `modo_indisponivel`, e nenhuma linha muda.
4. **Banco:** `INSERT`/`UPDATE` direto com `modo <> 'lembrete'` ou com estado `rascunho_criado`,
   `publicado` ou `falhou` → `IntegrityError` (prova dos CHECKs).
5. **AST:** nenhum arquivo de `src/` atribui `rascunho_criado`, `publicado` ou `falhou` a um estado
   (mesma técnica do guarda de `postado`, com lista de lugares permitidos **vazia**); o guarda de
   `postado` continua com `postagem/service.py::marcar_postado`.
6. **Agendador:** os nomes de `trilhas_padrao()` são exatamente `{sync, openshorts, importacao,
   lembretes}`; e uma volta da trilha `lembretes` com destinos vencidos não muda `estado` nem
   `version` de nenhum destino (só cria notificações e `lembrado_em`).
7. **Listas só crescem:** `test_listas_do_guarda_nao_encolheram` inalterado.
8. **VII:** cada ação (aprovar, pedir, recusar, agendar, reagendar, cancelar, cancelar por
   arquivo, lote) grava exatamente uma versão por destino afetado, com autor; membro recebe 403 em
   aprovar, recusar, aprovar em lote e reverter.

Fora do escopo, de propósito:
- executar qualquer modo automático, conectar conta, OAuth e credenciais (015, depois da emenda do
  princípio I);
- vídeos de avatar e afiliado (specs 010 a 012; só o valor de origem futuro está previsto);
- notificação de "atrasado" (o atalho basta);
- reordenar por arrastar dentro da lista (há "Trocar horários" e o arrastar do calendário);
- exposição no MCP (009): quando existir, aprovar, recusar e agendar exigem sessão humana; o MCP
  pode ler e, no máximo, pedir aprovação (a decidir na 009).

## Project Structure

### Documentation (this feature)

```text
specs/014-central-de-conteudos/
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
├── migrations/versions/0009_central_conteudos.py      # NOVO
├── src/sociman_api/
│   ├── conteudos/                                     # NOVO pacote
│   │   ├── models.py          # Conteudo, ConteudoOrigem; enums Modo (agendamento_modo)
│   │   ├── consulta.py        # expressões derivadas (situação, estado efetivo, arquivado), filtros,
│   │   │                      #   atalhos, cursor, resumo; a ÚNICA definição do estado efetivo
│   │   ├── capacidades.py     # CAPACIDADES por rede + modos_da_conta (R4)
│   │   ├── sequencia.py       # planejador puro (R7) + conflitos(horario, ocupados, intervalo), usado
│   │   │                      #   também pelo aviso do agendamento individual
│   │   ├── video_proprio.py   # upload: precheck/receive da 004, probe, MinIO, miniatura (R9)
│   │   ├── service.py         # criar_para_corte, get/list/update/archive/restore/revert, destinos novos
│   │   ├── schemas.py
│   │   ├── router.py          # /api/conteudos (lista, resumo, detalhe, título, arquivo, histórico)
│   │   └── router_video.py    # /api/perfis/{id}/conteudos/arquivo (vídeo próprio; arquivo à parte
│   │                          #   para as trilhas paralelas não colidirem)
│   ├── postagem/              # EVOLUÍDO: destino e agendamento
│   │   ├── models.py          # Postagem = destino: conteudo_id, DestinoEstado, modo, aprovação, pedido, recusa
│   │   ├── service.py         # textos, aprovar/pedir/recusar, agendar/reagendar/cancelar, lote,
│   │   │                      #   sequência, marcar_postado (fica aqui: guarda), cancelar_por_arquivo, calendário
│   │   ├── schemas.py         # Destino, DestinoResumo, LoteResultado, Previa…
│   │   ├── router.py          # /api/destinos, /api/agendamentos, /api/calendario,
│   │   │                      #   /api/conteudos/{id}/destinos, /api/contas/{id}/modos (rotas da 006 removidas)
│   │   ├── lembretes.py       # filtro por modo e conta, JOIN conteudos, link novo
│   │   └── textos.py          # sem mudança
│   ├── cortes/
│   │   ├── models.py          # sem mudança de schema
│   │   ├── service.py         # create_corte cria o conteúdo; arquivar cancela agendamentos; corte_out com destinos
│   │   └── schemas.py         # Corte.postagens → Corte.destinos (DestinoResumo)
│   ├── envios/importacao.py   # cria o conteúdo junto com o corte importado
│   ├── ia/
│   │   ├── models.py          # IaChamada.conteudo_id
│   │   ├── schemas.py         # AlvoTipo + "conteudo"
│   │   ├── service.py         # _resolver_postagem pelo conteúdo; grava conteudo_id
│   │   ├── contexto.py        # montar(..., conteudo=...) (sem transcrição fora da origem corte)
│   │   └── aplicacao.py       # _Alvo.conteudo_id
│   ├── notificacoes/models.py # + aprovacao_pedida, aprovacao_respondida
│   ├── midia.py, router_midia.py   # + kind conteudo_video
│   ├── agendador.py           # _registrar_modelos + conteudos (sem trilha nova)
│   └── main.py                # inclui o router de conteudos
└── tests/
    ├── unit/                  # test_sequencia, test_capacidades, guardas 014
    └── integration/           # test_migration_0009, test_conteudos, test_destinos, test_agendamentos,
                               #   test_escala_conteudos, test_guardas_014; lembretes, ia_postagem,
                               #   postagens (reescrito como destinos), cortes (invariante) ampliados

apps/web/src/
├── pages/conteudos/{Conteudos,ConteudoDetalhe}.tsx               # NOVAS
├── components/conteudos/
│   ├── {EstadoBadge,DestinoChips,ModoSelect,FiltrosConteudos,AtalhosConteudos}.tsx
│   ├── {AgendarDialog,SequenciaDialog,RecusarDialog,VideoProprioDialog}.tsx
│   └── DestinoPanel.tsx       # evolução do PostagemSection (textos + IA, aprovação, agendamento, Postado)
├── components/postagem/PostagemSection.tsx   # REMOVIDO (substituído pelo DestinoPanel)
├── components/data-table/{DataTable.tsx,CursorPagination.tsx}   # prop `manual`; paginação por cursor
├── pages/cortes/CorteDetalhe.tsx             # DestinoPanel + Agendar
├── pages/perfis/tabs/CortesTab.tsx           # Agendar nas linhas prontas
├── pages/perfis/ContasTab.tsx                # campo "Intervalo mínimo entre posts" (só dono edita)
├── pages/calendario/Calendario.tsx           # modo/estado, contaId, AgendarDialog comum, sem data aprovados
├── components/shell/nav.ts                   # item "Conteúdos"
├── App.tsx                                   # rotas /app/conteudos e /app/conteudos/:id
└── lib/{conteudos,postagem}.ts               # queries, chaves e rótulos em pt-BR dos estados e modos

docker/nginx/default.conf.template   # location do upload do vídeo próprio (2100m)
e2e/conteudos.spec.ts                # NOVO; e2e/cortes-openshorts.spec.ts ajustado
```

**Structure Decision:**
- `conteudos/` é pacote novo (conteúdo, consulta, capacidades, sequência e vídeo próprio);
- `postagem/` **evolui** para destino e agendamento. O nome do pacote e da tabela ficam (histórico,
  IA, guarda de `postado`), e o recurso da API se chama `destinos` (research R2);
- `cortes/` e `envios/importacao.py` só ganham a criação do conteúdo e o cancelamento por
  arquivamento; o worker e a fila da 004 **não mudam**;
- o SPA ganha as páginas de Conteúdos e troca o `PostagemSection` pelo `DestinoPanel`, usado pelo
  corte e pelo conteúdo.

**Migration:** `0009_central_conteudos`, com `down_revision = "0008_assistente_ia"` (data-model,
"Migração dos dados da 006").

### Arquivos existentes tocados
| Arquivo | Mudança |
|---|---|
| `postagem/{models,schemas,service,router,lembretes}.py` | destino, aprovação, agendamento, lote, sequência, calendário; rotas da 006 removidas |
| `cortes/service.py`, `cortes/schemas.py` | criar conteúdo; arquivar cancela agendamentos; `destinos` no `Corte` |
| `envios/importacao.py` | criar conteúdo no mesmo flush do corte |
| `ia/{models,schemas,service,contexto,aplicacao}.py` | alvo `conteudo`, `conteudo_id` |
| `notificacoes/models.py` | 2 tipos novos |
| `perfis/{models,schemas,service_contas}.py` | `Conta.intervalo_min_minutos` (versionado), `intervaloMinMinutos` no `ContaOut` e no `UpdateContaIn` (só dono muda: 403 `forbidden`) |
| `tests/conftest.py` | `conteudos` na lista de tabelas zeradas entre testes |
| `midia.py`, `router_midia.py` | kind `conteudo_video` |
| `agendador.py`, `main.py` | registrar modelos e router |
| `tests/unit/test_constitution_guards.py` | seção "spec 014" (guardas 1 a 6) |
| `tests/integration/{test_postagens,test_lembretes,test_ia_postagem,test_cortes,test_historico_006,test_sugestoes,test_importacao,test_migration_0006,test_migration_0008,test_contas}.py` | adaptar ao destino, à cadeia de migrations com a 0009 e ao intervalo da conta |
| `docker/nginx/default.conf.template` | `location` do upload |
| SPA: `CorteDetalhe`, `CortesTab`, `Calendario`, `nav.ts`, `App.tsx`, `DataTable`, `lib/postagem.ts`, `lib/ia.ts`, `components/ia/IaAssist.tsx`, `pages/perfis/ContasTab.tsx` | ver a árvore acima; `IaAssist`/`lib/ia.ts` com o alvo `conteudo`; `ContasTab` com o campo "Intervalo mínimo entre posts" (só dono edita) |
| `e2e/cortes-openshorts.spec.ts`, `e2e/assistente-ia.spec.ts` | seção Postagem → painel de destinos; rotas de destino no lugar das da 006 |
| `CLAUDE.md` (SociMan) | seção curta "Central de conteúdos (desde a spec 014)" com os guardas e a regra "só lembrete" |

**Ordem sugerida para o `/speckit-tasks`:**
0. backup do banco de dev; migration `0009` + modelos (inclusive `contas.intervalo_min_minutos`) +
   `test_migration_0009` (sobe e desce com dados da 006);
1. `conteudos/` (criação junto com o corte, invariante, `consulta.py` com estado efetivo, lista,
   cursor, resumo) + testes;
2. destino: textos, aprovação, pedido, recusa, lote, notificações + testes de permissão e histórico;
3. capacidades + agendar/reagendar/cancelar (com o aviso do intervalo mínimo) + arquivar cancela +
   lembretes ajustados + guardas 1 a 6;
4. sequência (planejador puro com o intervalo da conta, prévia, confirmação);
5. IA com alvo `conteudo`;
6. vídeo próprio (upload, miniatura, mídia, edge);
7. `gen:contract` e SPA: Conteúdos, detalhe, `DestinoPanel`, `AgendarDialog`, corte, aba Cortes;
8. `SequenciaDialog` e calendário;
9. e2e, teste de escala e `CLAUDE.md`.

As fases 0 a 3 e 7 fecham US1 a US3 (P1) e podem ir ao dono antes de US4 e US5.

## Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| Migração de `postagens` (troca de FK, de índice único e de enum) com dados reais | perda de agendamento ou de histórico | uma transação; teste de migração com os três estados da 006 e arquivada; nenhuma linha de `entity_versions` alterada; backup do banco antes (`quickstart §0`) |
| Remoção das rotas de postagem da 006 | quebra de telas e e2e que ainda as usem | o contrato é gerado: o `check:contract` e o `typecheck` apontam cada uso; o e2e da 006 é ajustado na mesma fase |
| Conteúdo sem linha para um corte (criação esquecida num caminho novo) | corte invisível na central | só dois pontos criam `Corte`; teste de invariante em `test_cortes` e `test_importacao`; FK `postagens.conteudo_id` falha alto |
| Estado efetivo calculado em dois lugares (filtro e saída) divergir | filtro mostra uma coisa e o chip outra | uma única expressão em `consulta.py`, usada no `WHERE` e no `SELECT` |
| Versões antigas do histórico sem os campos novos | reversão quebrar ou restaurar aprovação indevida | reversão com padrões para campos ausentes e regra explícita (nunca restaura aprovação nem `postado`); teste com versão da 006 |
| Intervalo mínimo não bater com a rotina de cada conta | sequência pula horários demais ou de menos | intervalo por conta (Q3 = C), editável pelo dono; o individual só avisa |
| Lote grande com um item travado por outra pessoa | espera longa ou deadlock | travas em ordem de id, `SAVEPOINT` por item, limite de 100 |
| Upload de 2 GB com miniatura síncrona | requisição longa | a miniatura é 1 frame (< 1 s); timeouts da `location` iguais aos do envio avulso |
| O dono esperar execução automática já na 014 | frustração | modos visíveis e desabilitados com o motivo "Aguardando a spec de integração (015)" |
| Emenda do princípio I atrasar a 015 | modos automáticos ficam só modelados por mais tempo | nada na 014 depende da 015; o lembrete cobre o fluxo atual |

## Complexity Tracking

| Item | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| Tabela `conteudos` (hub polimórfico) | FR-011: origens diferentes (corte, vídeo próprio, depois avatar/afiliado) com uma FK só no destino e no IA | view `UNION`: FK polimórfica em destino e IA; vídeo próprio como `Corte`: quebra o `ck_cortes_kit` e mistura conceitos (R1) |
| Estado efetivo derivado em SQL | FR-002/FR-007 sem job que reescreva estados pelo relógio | gravar `a_postar`/`atrasado`: job, histórico poluído, divergência (R3) |
| CHECKs `ck_postagens_modo_014` e `ck_postagens_estados_015` | prova no banco de que nenhum modo automático existe na 014 (FR-013, SC-005) | só validação no service: um bug ou um script passaria por cima |
| Planejador de sequência + prévia + `esperado` | FR-009: prévia antes de confirmar e pular conflitos, sem corrida silenciosa | gravar a prévia: tabela para estado de minutos; aplicar sem prévia: contra a spec |
| Rotas em lote com `SAVEPOINT` por item | US2-5 e US4-2: falha num item não desfaz os outros | transação única: um item ruim desfaria o lote; N chamadas do SPA: lento e sem motivo agregado |
| Coluna `contas.intervalo_min_minutos` + aviso `intervalo_conflito` com `ignorarIntervalo` | Q3 = C: contas com rotinas diferentes; o individual avisa sem bloquear | constante global: o dono pediu por conta; bloquear o individual: o dono quer poder manter |
| `location` nova no edge (2100m) | vídeo próprio até 2 GB (Assumptions) | reaproveitar a de cortes (520 MB): pequena; limite alto em `/api/`: aumenta a superfície |
