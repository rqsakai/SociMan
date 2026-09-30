# Pesquisa (Fase 0): 014-central-de-conteudos

Fontes consultadas:
- a spec com as Clarifications de 2026-09-29 (inclusive as respostas Q1 a Q4 do dono) e a
  constitution 4.0.0 (princípio I: "Publicação só com decisão humana");
- `docs/pesquisa/publicacao-redes.md` (capacidades por rede, desenho da 015 e emenda do princípio I);
- o código que a 014 evolui:
  - `postagem/` (`models.py`, `service.py`, `router.py`, `schemas.py`, `lembretes.py`, `textos.py`);
  - `cortes/` (`models.py`, `service.py`, `probe.py`, `compose.py`, `worker.py`);
  - `envios/` (`importacao.py`, `upload.py`);
  - `ia/` (`service.py`, `aplicacao.py`, `contexto.py`, `schemas.py`, `tipos.py`);
  - `notificacoes/`, `agendador.py`, `history.py`, `midia.py`, `perfis/models.py`;
  - o guarda `tests/unit/test_constitution_guards.py`;
- as migrations `0006_cortes_openshorts` e `0008_assistente_ia`;
- no SPA: `pages/calendario/Calendario.tsx`, `components/postagem/PostagemSection.tsx`,
  `pages/cortes/CorteDetalhe.tsx`, `pages/perfis/tabs/CortesTab.tsx`, `components/data-table/*` e
  `components/shell/nav.ts`;
- o formato da 006 (`specs/006-cortes-openshorts/*`).

Nomes usados daqui em diante:
- **conteúdo**: um vídeo publicável de um perfil (tabela nova `conteudos`);
- **destino**: um conteúdo × uma conta. É a linha de `postagens` da 006, ampliada (R2);
- **agendamento**: os campos de agenda do destino (data e hora, modo, antecedência), e não uma
  tabela à parte (R6);
- **estado gravado** é a coluna `postagens.estado`. **Estado efetivo** é o que a tela mostra,
  calculado a partir do estado gravado, do conteúdo, da conta e do relógio (R3).

---

## R1. O "conteúdo": tabela polimórfica ou view sobre cortes (FR-001, FR-011)

- **Decisão:** uma tabela nova, **`conteudos`**, como eixo da central. Cada linha tem uma origem e
  aponta para ela:
  - `origem = corte`: `conteudos.id` **é o próprio `cortes.id`** (e `corte_id = id`, com FK e
    UNIQUE). O corte continua sendo a fonte da verdade do arquivo, do status da marca, da miniatura
    e do arquivamento. O conteúdo guarda só o que é da central: `titulo` editável, `perfil_id`,
    `origem`, `created_at` e o histórico `conteudo`;
  - `origem = video_proprio`: o conteúdo **é dono do arquivo**. As colunas `video_key`,
    `poster_key`, `duration_ms`, `width`, `height`, `video_bytes`, `video_sha256` e
    `original_filename` são preenchidas no envio (R9), e o `archived_at` é do próprio conteúdo;
  - avatar e afiliado (specs 010 a 012) entram depois como **novos valores de `conteudo_origem`**
    (`ALTER TYPE … ADD VALUE`), com a mesma regra: ou apontam para a linha de origem, ou são
    donos do arquivo.
- **Sem estado copiado.** Para a origem corte, a situação (`em_revisao`, `processando`, `pronto`,
  `erro_marca`), a miniatura, a duração, o vídeo final e o arquivamento vêm de um `LEFT JOIN
  cortes` com `COALESCE`/`CASE`, num único módulo (`conteudos/consulta.py`). O worker da 004 não
  muda, e não há sincronização a manter.
- **Quando nasce a linha:** no mesmo `flush` em que nasce o corte, nos dois únicos pontos que criam
  `Corte` (`cortes/service.py:create_corte`, o upload da 004, e `envios/importacao.py`, a
  importação do OpenShorts), por `conteudos.service.criar_para_corte(db, corte)`. A migration cria
  as linhas dos cortes existentes (R2). Um teste de invariante garante que todo corte tem conteúdo.
- **Por quê:**
  - o destino (R2) precisa de **uma FK só** (`postagens.conteudo_id`), qualquer que seja a
    origem. Com uma view, o destino teria uma FK por origem (`corte_id`, `video_proprio_id`,
    `avatar_id`…) e um CHECK de "exatamente uma", e o IA, o calendário e a lista repetiriam o
    `CASE` em todo lugar;
  - `id = corte.id` deixa a migração trivial (o `conteudo_id` de cada postagem é o `corte_id` dela),
    mantém válidos os links `/app/cortes/{id}` e as notificações já criadas, e o assistente de IA
    (008) casa conteúdo e corte sem tabela de tradução;
  - não copiar o estado do corte evita o risco clássico de desnormalização: o worker muda o status
    do corte em sessões próprias, e uma cópia ficaria errada a cada falha no meio.
- **Alternativas rejeitadas:**
  - **view `UNION ALL` de cortes e vídeos próprios:** exige FK polimórfica no destino e no IA; a
    ordenação e o cursor sobre um `UNION` ficam mais caros; cada origem nova mexe na view e em
    todas as FKs;
  - **vídeo próprio como `Corte` com `origem = proprio`:** reaproveitaria tudo, mas força o
    `ck_cortes_kit` (kit obrigatório fora de `revisao`), mistura "vídeo com marca aplicada pelo
    SociMan" com "arquivo pronto do dono" e deixa avatar e afiliado sem lugar natural;
  - **copiar status, miniatura e duração do corte para `conteudos`:** lista mais simples, mas
    exige gravar em cada transição do worker e da fila (cinco pontos), com risco de divergência.

## R2. Da Postagem da 006 ao destino, sem perder dados (FR-002, Assumptions)

- **Decisão:** a tabela **`postagens` continua**, e a classe `Postagem` também. Ela passa a ser o
  **destino** (conteúdo × conta). Na API e na UI o recurso se chama `destino` (`/api/destinos`). A
  migration `0009_central_conteudos` (down_revision `0008_assistente_ia`) faz, numa transação:
  1. cria `conteudo_origem` e `conteudos`; insere **uma linha por corte** (`id = corte_id = cortes.id`,
     `perfil_id`, `titulo = COALESCE(NULLIF(openshorts_title,''), NULLIF(hook_text,''),
     original_filename)` cortado em 100, `created_at`/`created_by` do corte);
  2. `postagens.conteudo_id` = `corte_id`, `NOT NULL`, FK → `conteudos.id`; o índice único vira
     `uq_postagens_conteudo_conta_ativa (conteudo_id, conta_id) WHERE archived_at IS NULL`; a
     coluna `corte_id` sai (o corte se alcança por `conteudos.corte_id`);
  3. o estado muda de tipo: `postagem_estado` → `destino_estado` por `ALTER COLUMN … TYPE …
     USING CASE` (um tipo novo evita o `ALTER TYPE ADD VALUE`, que não pode ser usado na mesma
     transação em que é criado):

     | 006 | 014 | Aprovação preenchida |
     |---|---|---|
     | `rascunho` | `pendente` | não (ninguém aprovou na 006) |
     | `agendado` | `agendado` | `aprovado_em = updated_at`, `aprovado_por = COALESCE(updated_by, created_by)` |
     | `postado` | `postado` | idem |

  4. as colunas novas (aprovação, pedido, recusa, `modo`, `antecedencia_min`, `falha_motivo`)
     entram com os padrões do data-model; `modo = lembrete` em todas;
  5. `ia_chamadas.conteudo_id` (FK, preenchida a partir de `corte_id`);
  6. `notificacao_tipo` ganha `aprovacao_pedida` e `aprovacao_respondida`.
- **Downgrade:** recusa se existir conteúdo `video_proprio` (não há corte para onde voltar);
  senão volta `corte_id`, mapeia `pendente`/`aprovacao_pedida`/`aprovado` → `rascunho` e remove o
  resto. O teste `tests/integration/test_migration_0009.py` sobe com dados da 006 (rascunho,
  agendado, postado e arquivada), confere o mapa acima e desce de volta, como os testes das
  migrations 0006 e 0008.
- **Por quê manter `postagens` e o `entity_type = "postagem"`:**
  - `entity_versions` é só INSERT, e já guarda as versões com `entity_type = 'postagem'`. Renomear
    a tabela exigiria reescrever o histórico ou conviver com dois nomes;
  - o assistente de IA (008) usa `postagem` como entidade dos tipos `postagem.*`, e as
    notificações `hora_de_postar` usam `entidade = ("postagem", id)`;
  - o guarda de `postado` (`test_postado_so_por_acao_humana`) aponta para
    `postagem/service.py::marcar_postado`; a função fica onde está.
- **Por quê "destino" na API:** a spec (Key Entities) e a tela falam de destino, e a palavra
  "postagem" sugere que o SociMan posta. Um docstring em `postagem/models.py` registra a
  equivalência.
- **As rotas da 006 saem.** `POST/GET /api/cortes/{id}/postagens` e `/api/postagens/*` são
  substituídas pelas rotas de destino e agendamento (contrato). Motivos:
  - o `PATCH` da 006 agenda com `plannedAt` sem aprovação, o que furaria o FR-004 (um membro
    agendaria sem dono);
  - o único cliente é o SPA (o MCP da 009 ainda não existe), e o contrato é gerado (princípio
    IV), então o `check:contract` aponta cada uso a trocar.
  As rotas deprecated de sugestão da 006 (`/api/cortes/{id}/sugestoes`) ficam como estão.
- **Alternativas rejeitadas:**
  - **renomear `postagens` → `destinos`** (como a 0008 fez com `sugestoes_texto`): nome melhor,
    mas o histórico, o IA e as notificações carregam `postagem` como texto; a troca é só cosmética;
  - **manter as rotas da 006 como aliases:** dobra a superfície e exige reproduzir a regra de
    aprovação nelas;
  - **tabela `destinos` nova, deixando `postagens` só para leitura:** duplica textos e histórico.

## R3. Máquina de estados por conta: o que é gravado e o que é derivado (FR-002, FR-007)

- **Decisão:** gravar só o que é **decisão humana ou resultado de execução**; derivar o resto.

  **Gravado** em `postagens.estado` (enum `destino_estado`):

  | Valor | Quem grava | Significado |
  |---|---|---|
  | `pendente` | criação, recusa, cancelamento de aprovação | conta escolhida, sem aprovação |
  | `aprovacao_pedida` | pedir aprovação (dono ou membro) | aguardando um dono |
  | `aprovado` | aprovar (dono); cancelar o agendamento | "pode ir para esta conta" |
  | `agendado` | agendar (dono ou membro, com aprovação) | tem data, hora e modo |
  | `postado` | **só** `marcar_postado` (humano) | alguém postou à mão |
  | `rascunho_criado`, `publicado`, `falhou` | **ninguém na 014** | reservados ao executor da 015 |

  **Derivado** (estado efetivo, calculado em SQL por uma expressão só, usada no filtro e na
  saída):

  | Estado efetivo | Regra (em ordem) |
  |---|---|
  | `arquivado` | destino arquivado ou conteúdo arquivado |
  | `em_revisao` | a situação do conteúdo não é `pronto` (corte em `revisao`, `na_fila`, `processando` ou com erro na marca) |
  | `atencao` | `agendado` e a conta arquivada, `pausada` ou `encerrada` (não executa; motivo na saída) |
  | `atrasado` | `agendado`, `modo = lembrete` e `planned_at <= now() - 24 h` |
  | `a_postar` | `agendado`, `modo = lembrete` e `planned_at <= now()` |
  | `agendado`, `aprovado`, `aprovacao_pedida`, `postado`, `rascunho_criado`, `publicado`, `falhou` | o estado gravado |
  | `pronto` | `pendente` com o conteúdo pronto |

  Um conteúdo **sem destino** aparece como `sem_conta` na lista (estado do conteúdo, não do
  destino).
- **Por quê derivar `a_postar`, `atrasado`, `em_revisao` e `atencao`:**
  - dependem só do relógio ou de outra entidade; gravá-los exigiria um job reescrevendo linhas a
    cada volta, com histórico poluído e risco de o job ficar para trás;
  - a trilha `lembretes` continua só **avisando** (princípio I), sem mudar estado;
  - `em_revisao` vem do corte, que já é a fonte da verdade (R1).
- **Por quê gravar `aprovado` separado de `agendado`:** a spec separa "pode ir" de "quando"
  (Clarifications), e o atalho "Aprovados sem data" é uma consulta direta ao estado.
- **Por quê `postado` e `publicado` são valores diferentes:** `postado` é a marcação humana da 006,
  protegida pelo guarda de AST; `publicado` será gravado pelo executor da 015, que precisará do
  próprio guarda. A lista mostra os dois no filtro "Publicados".
- **`pendente` em vez de `rascunho`:** "rascunho" passa a significar o rascunho **na rede**
  (`rascunho_criado`, modo `criar_rascunho`); manter a palavra para "sem aprovação" confundiria.
- **Transições:** a tabela completa está no data-model. Regras que valem sempre:
  - aprovar exige o conteúdo `pronto` (409 `conteudo_nao_pronto`, "Aplique a marca antes de
    aprovar");
  - agendar exige `aprovado` ou `agendado` (reagendar), ou um **dono** agendando direto (aprova e
    agenda na mesma transação, com duas versões no histórico: `aprovado` e `agendado`);
  - `postado` só a partir de `aprovado` ou `agendado`;
  - recusar só a partir de `aprovacao_pedida` ou `aprovado`. Um destino `agendado` precisa ter o
    agendamento cancelado antes (409 `conflict`, com a mensagem);
  - nada sai de `postado` (como na 006), e a reversão nunca desfaz nem refaz `postado`.
- **Alternativas rejeitadas:**
  - **gravar todos os estados da esteira** (inclusive `a_postar`/`atrasado`): job de transição,
    histórico com versões do sistema e divergência entre relógio e banco;
  - **um enum só para conteúdo e destino:** o conteúdo tem estados próprios (revisão, marca), e o
    destino é por conta (US3-6).

## R4. Capacidades por rede em código, com motivo (FR-006, FR-013)

- **Decisão:** um registro em código, `conteudos/capacidades.py`, sem tabela:
  ```text
  Modo = lembrete | criar_rascunho | publicar | rascunho_e_publicar
  CAPACIDADES: dict[Platform, dict[Modo, Capacidade]]   # Capacidade(existe: bool, motivo: str)
  modos_da_conta(conta) -> list[ModoInfo]               # {modo, disponivel, motivo|null}
  ```
  `modos_da_conta` combina três camadas, e o primeiro "não" dá o motivo:
  1. **a rede oferece o modo?** (fato da pesquisa, permanente);
  2. **existe integração para a rede?** Na 014, nunca: "Aguardando a spec de integração (015)";
  3. **a conta está conectada e em condição?** Na 014 não existe conexão: "Conta não conectada".
     Conta arquivada, `pausada` ou `encerrada` → nenhum modo, nem o lembrete (motivo "Conta
     pausada" etc.).

  `lembrete` existe em todas as redes e é o único disponível na 014. A tabela de motivos (textos
  da tela) vem de `docs/pesquisa/publicacao-redes.md`:

  | Rede | `criar_rascunho` | `publicar` | `rascunho_e_publicar` |
  |---|---|---|---|
  | TikTok | existe (caixa de entrada) → "Aguardando a spec de integração" | existe, mas "sem auditoria a rede só publica como privado" | **não existe**: "O TikTok não permite publicar um rascunho pela API" |
  | YouTube | existe (envio privado) → aguardando | existe (`publishAt`), "privado até a auditoria do Google" | existe (privado + horário) → aguardando |
  | Instagram | **não existe**: "O Instagram não tem rascunho pela API" | existe → aguardando | **não existe** |
  | Kwai, Facebook, X, outra | "Sem integração prevista" | idem | idem |

- **Por quê em código:** as capacidades são fatos das APIs das redes, mudam com o código da 015
  (não com o uso) e precisam de revisão; uma tabela editável sugeriria que o dono pode "ligar" um
  modo que não tem executor.
- **A mesma função valida a escrita.** `agendar`, `reagendar` e `sequencia` chamam
  `modos_da_conta` e respondem 409 `modo_indisponivel` (com `details.motivo`) para um modo
  indisponível; a tela usa o mesmo resultado (`GET /api/contas/{id}/modos`) para desabilitar as
  opções com o motivo.
- **Três camadas de defesa do princípio I na 014** (R13 e plan):
  1. a função acima (nenhum modo automático disponível);
  2. o CHECK `ck_postagens_modo_014` (`modo = 'lembrete' AND antecedencia_min IS NULL`) e o CHECK
     `ck_postagens_estados_015` (`estado NOT IN ('rascunho_criado','publicado','falhou')`), que a
     migration da 015 remove depois da emenda;
  3. os testes-guarda (plan, "Guardas").
- **Alternativas rejeitadas:**
  - **tabela `capacidades_rede`:** dado de configuração sem dono humano, editável sem código que o
    execute;
  - **esconder os modos indisponíveis:** a spec pede que apareçam desabilitados, com o motivo
    (FR-006, US3-2);
  - **só o CHECK no banco:** a mensagem para o usuário viria de um `IntegrityError`.

## R5. Aprovação, pedido de aprovação e avisos (FR-004, US2)

- **Decisão:**
  - **aprovar** (`RequireOwner`): `pendente|aprovacao_pedida → aprovado`, com `aprovado_por`,
    `aprovado_em` e `aprovado_video_ref` (a chave do vídeo final no momento: `cortes.result_key`
    ou `conteudos.video_key`). Limpa o pedido e a recusa anteriores;
  - **pedir aprovação** (`RequireUser`): `pendente → aprovacao_pedida`, com `pedido_por`,
    `pedido_em` e uma nota opcional (até 500). Notifica **os donos ativos** (tipo novo
    `aprovacao_pedida`, `dedupe_key = aprovacao_pedida:<destino>:<version>`), com link para o
    conteúdo na aba da conta;
  - **recusar** (`RequireOwner`, motivo obrigatório de 1 a 500 caracteres): `aprovacao_pedida|
    aprovado → pendente`, com `recusado_por`, `recusado_em` e `recusa_motivo` visível no destino
    até a próxima aprovação. Notifica quem pediu (tipo novo `aprovacao_respondida`); a aprovação
    também notifica quem pediu, com o mesmo tipo;
  - tudo com `history.record` na mesma transação (`details.acao`: `aprovado`, `aprovacao_pedida`,
    `recusado`), `check_version` e 409 `version_conflict`;
  - **"o vídeo mudou desde a aprovação":** o destino devolve `videoMudou = aprovado_video_ref <>
    vídeo atual`. A aprovação continua valendo (edge case da spec); a tela mostra o aviso.
- **Em lote** (US2-5): `POST /api/destinos/lote/aprovar` e `/lote/pedir-aprovacao` com `{contaId,
  conteudoIds[]}` (até 100). Cria o destino que faltar, trava as linhas (`FOR UPDATE`, em ordem de
  id, para não criar deadlock) e processa cada item num `SAVEPOINT` (`db.begin_nested()`): um item
  inelegível entra em `falhas` com o código e a mensagem, e os outros seguem. O lote não leva
  `version` por item: as pré-condições de estado protegem a corrida, e cada item gera a própria
  versão no histórico.
- **Por quê notificar só no pedido e na resposta:** o sino da 006 já é o canal de avisos; notificar
  cada aprovação feita pelo próprio dono seria ruído.
- **Alternativas rejeitadas:**
  - **tabela `pedidos_aprovacao` (1:N):** a spec não pede múltiplos pedidos simultâneos por destino,
    e o histórico já guarda cada pedido e recusa;
  - **aprovação no conteúdo (e não por conta):** a spec define aprovação por conta
    (Clarifications, US3-6).

## R6. Agendar, reagendar e cancelar; agendamento no destino (FR-005, FR-008, FR-010)

- **Decisão:** o agendamento são **campos do destino** (`planned_at`, `modo`, `antecedencia_min`,
  `lembrado_em`), com uma ação dedicada para cada mudança:
  - `POST /api/agendamentos` (**agendar direto**, FR-010): `{conteudoId, contaId, plannedAt, modo,
    antecedenciaMin?, textos?, ia?}`. Cria o destino se faltar; se o destino não está aprovado,
    um **dono** aprova no mesmo passo e um **membro** recebe 403 `aprovacao_necessaria` ("Peça
    aprovação a um dono"); grava os textos (com o campo `ia` da 008) e agenda;
  - `PATCH /api/destinos/{id}/agendamento`: reagendar (data, hora, modo). Mudar a data zera
    `lembrado_em`, como na 006;
  - `POST /api/destinos/{id}/agendamento/cancelar`: `agendado → aprovado`, `planned_at = null`;
  - `POST /api/agendamentos/lote/reagendar` e `/lote/cancelar`: vários destinos com `version`
    cada (arrastar no calendário, trocar horários na lista, cancelar em lote), com `SAVEPOINT` por
    item.
  Validações: horário no futuro (tolerância de 1 min da 006, 400 `planned_in_past`), destino
  aprovado (409 `nao_aprovado`), conteúdo pronto (409 `conteudo_nao_pronto`), modo disponível
  (409 `modo_indisponivel`), conta sem atenção (409 `conta_em_atencao`).
- **Arquivar** o conteúdo (ou o corte, pela rota da 006) **cancela** os agendamentos ativos dele,
  na mesma transação, com versão `details.acao = "cancelado_por_arquivo"` em cada destino (edge
  case). Restaurar não reagenda.
- **Os textos continuam no destino** (título, descrição e hashtags, com os limites da 006) e são
  editáveis em qualquer estado, menos `postado` e arquivado. Editar os textos **não** desfaz a
  aprovação (Clarifications, Q2 = A); cada mudança fica no histórico do destino.
- **Quem agenda** (Clarifications, Q1 = A): dono e membro agendam, reagendam e cancelam destinos já
  aprovados; aprovar, recusar e "aprovar e agendar" são só do dono. Na 015, os modos automáticos
  exigem dono (constitution 4.0.0, princípio I): `agendamentos_create`, `agendamentos_update` e
  `sequencia` com `modo <> lembrete` passarão a responder 403 para membro. Na 014 esses modos já
  respondem 409 `modo_indisponivel` para todos.
- **Intervalo mínimo no agendamento individual** (Clarifications, Q3): `agendar`, `reagendar`,
  `lote/reagendar` (arrastar no calendário, "Trocar horários") conferem o intervalo mínimo da conta
  (R7). Em conflito, e sem `ignorarIntervalo: true`, respondem 409 `intervalo_conflito` com
  `details.intervaloMin` e `details.conflitos` (`destinoId`, `conteudoId`, `titulo`, `plannedAt`);
  nada é gravado. O SPA mostra o aviso com "Manter mesmo assim" (reenvia com `ignorarIntervalo:
  true`) ou "Escolher outro horário". Mantido, a versão do destino leva
  `details.intervaloIgnorado = true`. É um aviso, não um bloqueio: o 409 só garante que o humano viu
  o conflito antes de gravar.
- **Por quê no destino e não numa tabela `agendamentos`:** há no máximo um agendamento ativo por
  destino; reagendar e cancelar já ficam no histórico do destino; e o resultado de cada execução
  automática (015) vai para uma tabela própria só-INSERT (`tentativas`, pesquisa §4.1), não para
  uma "linha de agendamento".
- **Alternativas rejeitadas:**
  - **tabela `agendamentos` 1:N:** exigiria "um ativo por destino" com índice parcial, e o
    histórico passaria a ter duas entidades para o mesmo fato;
  - **manter o `PATCH plannedAt` da 006:** misturaria textos e agenda numa rota sem a regra de
    aprovação (R2).

## R7. Agendar em sequência: prévia, conflitos e confirmação (FR-009, US4, SC-003)

- **Decisão:**
  - um planejador **puro** (`conteudos/sequencia.py`, sem banco):
    `planejar(itens, inicio, horarios, ocupados, agora, janela) -> (slots, pulados)`. Gera os
    horários dia a dia a partir de `inicio` (data local, APP_TZ), em cada `HH:MM` de `horarios`
    (1 a 6 por dia, ordenados), pula os que já passaram e os que ficam a menos de `janela` de um
    horário **ocupado** da mesma conta (agendamentos ativos e os já atribuídos na própria
    sequência), e atribui os itens na ordem recebida. Limites: 100 itens, 180 dias;
  - **janela de conflito = intervalo mínimo da conta** (Clarifications, Q3 = C): coluna nova
    `contas.intervalo_min_minutos` (smallint, padrão 30, CHECK 0..1.440), editável só por dono
    pelo `PATCH /api/contas/{id}` (membro que muda o valor recebe 403 `forbidden`), versionada no
    histórico da conta. Há conflito quando `|Δ| < max(intervalo, 1 min)`: com 0, só o mesmo minuto
    conflita. A **sequência pula** o horário em conflito (`pulados`, motivo `conflito`); o
    **individual avisa** (R6). Mudar o intervalo não remarca nada: vale para as próximas
    verificações. A prévia devolve o `intervaloMin` usado;
  - `POST /api/agendamentos/sequencia/previa` devolve `slots` (conteúdo → horário), `pulados`
    (horário, motivo e o destino que ocupa) e `inelegiveis` (conteúdo com o motivo: não pronto, não
    aprovado para um membro, arquivado). Não grava nada;
  - `POST /api/agendamentos/sequencia` recebe os mesmos parâmetros e o `esperado` (a lista
    `{conteudoId, plannedAt}` mostrada na prévia). O servidor **recalcula** com as linhas travadas:
    se o resultado for diferente (alguém agendou no meio), responde 409 `previa_desatualizada` com a
    prévia nova em `details`. Se for igual, aplica item a item com `SAVEPOINT` (uma falha não
    desfaz os outros, US4-2) e devolve `{ok, falhas}`;
  - um **dono** aprova e agenda no mesmo passo os itens não aprovados; para um membro, só entram os
    já aprovados (os outros vão para `inelegiveis`).
- **Textos pela IA "para os que não têm":** quem gera é o **SPA**, depois da confirmação: para
  cada destino sem título, chama `POST /api/ia/gerar` (`postagem.textos`, alvo `postagem`) com no
  máximo 3 chamadas ao mesmo tempo, e salva com `PATCH /api/destinos/{id}` e o campo `ia`. Uma
  barra mostra o progresso, e o destino que ficar sem texto aparece com o selo "sem textos".
- **Por quê:** a prévia sem estado e o `esperado` na confirmação evitam guardar prévias no banco
  e ainda pegam a corrida. Gerar os textos no SPA reaproveita a rota da 008 com o registro de
  custo e a marca "com ajuda da IA", sem segurar uma requisição por 10 chamadas ao Claude (cerca
  de 100 s em série), e o lembrete só precisa dos textos na hora de postar.
- **Reordenar** (US4-3): na lista, "Trocar horários" entre dois selecionados; no calendário,
  arrastar. Os dois usam `lote/reagendar`, que muda só os itens mexidos.
- **Alternativas rejeitadas:**
  - **gravar a prévia (`sequencias` com id):** tabela para um estado de minutos;
  - **gerar os textos no servidor, na confirmação:** requisição de minutos, timeout do edge e
    falha parcial difícil de explicar;
  - **trilha nova no agendador para gerar textos:** um job para algo que o usuário acompanha com a
    tela aberta.

## R8. Lembrete, "a postar" e "atrasado" no agendador (FR-007)

- **Decisão:** a trilha `lembretes` da 006 continua, com três ajustes:
  - o filtro passa a exigir `modo = 'lembrete'` (os outros modos nunca existem na 014, mas a 015
    terá a própria trilha) e a conta sem atenção (não arquivada, não `pausada` nem `encerrada`),
    junta `conteudos` em vez de `cortes`, e o link vai para `/app/conteudos/{conteudoId}?conta=
    {contaId}`;
  - o título usa `postagens.titulo`, depois `conteudos.titulo`;
  - continua **sem mudar estado**: `a_postar` e `atrasado` são derivados (R3). Nenhuma
    notificação nova de atraso: o atalho "Atrasados" basta (VIII).
- **Por quê:** a trilha já é idempotente (`dedupe_key` com o horário, `lembrado_em`, `SKIP
  LOCKED`) e é o único job que toca destinos. Derivar os estados mantém o agendador sem escrita
  de estado, o que o guarda do princípio I verifica (plan).
- **Alternativa rejeitada:** uma trilha `atrasos` gravando `atrasado`: job, histórico e divergência
  para uma informação que um `WHERE` responde.

## R9. Vídeo próprio: upload, miniatura e duração (FR-011, US5)

- **Decisão:** `POST /api/perfis/{id}/conteudos/arquivo` (multipart, campos `arquivo` e
  `titulo?`), com o recebimento em streaming da 004/006:
  1. `cortes.service.precheck` e `receive` com `max_bytes = 2 GB` e prefixo `proprio-` (HD,
     sentinela, piso de espaço, sha256 enquanto chega; 413/503/507);
  2. `cortes.probe.probe` com duração de 1 s a 10 min (o teto da API do TikTok; Clarifications,
     Q4 = A);
     formato aceito como na 004 (MP4, MOV, WebM); vídeo não vertical é aceito, com o aviso
     `naoVertical` na resposta;
  3. o arquivo vai para o bucket `sociman-videos` em `conteudos/{id}/video.<ext>`;
  4. a miniatura é extraída **na própria requisição** com `cortes.compose.extract_frame` (1 frame
     em `min(1 s, duração/2)`, menos de 1 s de CPU) e gravada no bucket `sociman` como a do
     worker, para o imgproxy;
  5. só então a linha `conteudos` (`origem = video_proprio`) e a versão `created`. Um envio
     interrompido não cria linha.
  - O player e o "Baixar vídeo" usam um `MidiaKind` novo, `conteudo_video` (com validade, como os
    vídeos da 004), em `midia.py` e `router_midia.py`.
  - O edge ganha a `location ~ ^/api/perfis/[^/]+/conteudos/arquivo$` com `client_max_body_size
    2100m`, sem buffering, igual à do envio avulso (e `docker compose restart edge`).
- **Por quê síncrono:** o probe já é síncrono na 004 e na 006, e a miniatura de um frame custa
  menos que o próprio upload; uma fila só para isso seria peça a mais (VIII). Sem transcodificar:
  o arquivo já vem pronto do dono, e o `Range` da rota de mídia toca MP4 sem `faststart`.
- **O princípio II não se aplica:** vídeo próprio não é envio para corte; não há canal-fonte nem
  aviso de direito. A versão `created` registra autor e arquivo.
- **Alternativas rejeitadas:**
  - **passar pelo worker da 004 (fila):** o worker aplica a marca; o vídeo próprio já vem pronto;
  - **aproveitar a rota de cortes (520 MB):** limite pequeno e cria um `Corte` (R1).

## R10. Lista com filtros na URL e paginação por cursor (FR-003, SC-001, SC-006)

- **Decisão:**
  - `GET /api/conteudos` com filtros no servidor: `perfilId` (repetível), `contaId`,
    `plataforma`, `estado` (repetível, estado efetivo de algum destino, ou `sem_conta`), `origem`,
    `agendadoDe`/`agendadoAte` (datas locais sobre `planned_at`), `criadoDe`/`criadoAte`, `q`
    (busca `ILIKE` em `conteudos.titulo`, nos títulos dos destinos e, na origem corte, no gancho e
    no título do OpenShorts), `atalho` e `ordem` (`recentes`, padrão, ou `agenda`, pelo próximo
    `planned_at`);
  - **cursor opaco** (base64 de `[chave de ordenação, id]`), `limit` de 1 a 100 (padrão 50) e
    `nextCursor`; o `total` do filtro vem num `COUNT` da mesma consulta sem o cursor;
  - cada linha traz os **destinos resumidos** (conta, plataforma, `@`, estado efetivo,
    `plannedAt`, modo, `semTextos`, `videoMudou`), numa segunda consulta `WHERE conteudo_id IN
    (…)` (sem N+1);
  - `GET /api/conteudos/resumo` (mesmos `perfilId`/`contaId`) devolve as contagens dos atalhos:
    `prontosSemAgendamento`, `aprovadosSemData`, `aprovacaoPedida`, `agendadosHoje`, `estaSemana`,
    `aPostar`, `atrasados` e `falharam`;
  - **índices:** `conteudos (perfil_id, created_at DESC, id DESC)` e `(created_at DESC, id DESC)`;
    `postagens (conteudo_id)`; `postagens (conta_id, planned_at) WHERE archived_at IS NULL AND
    estado = 'agendado'` (conflitos, agenda e atalhos); o `ix_postagens_estado_planned` da 006
    continua. Sem `pg_trgm`: com centenas a poucos milhares de linhas, `ILIKE` responde em
    milissegundos (VIII);
  - no SPA, os filtros vivem em `useSearchParams` (voltar, recarregar e compartilhar o link), a
    query do TanStack usa os parâmetros como chave, e a tabela usa o `DataTable` da 005 **sem a
    paginação local** (um prop `manual` que desliga os modelos de ordenação, filtro e paginação do
    cliente) mais um componente `CursorPagination` ("Carregar mais").
- **Meta de desempenho:** p95 abaixo de 200 ms no servidor com 500 conteúdos e 1.000 destinos
  (seed do teste de escala, como o `assets-escala` da 007), o que deixa a tela abaixo de 1 s
  (SC-006).
- **Alternativas rejeitadas:**
  - **offset/limit:** repete ou pula linhas quando entram cortes novos durante a navegação (a
    importação cria cortes em rajada);
  - **filtrar no cliente (como as tabelas atuais):** carrega tudo, e a lista cresce todo dia;
  - **full-text (`tsvector`) ou `pg_trgm`:** extensão e índice para um volume que não precisa.

## R11. Integração com o calendário da 006 (FR-012)

- **Decisão:** `GET /api/calendario` continua (mesmo caminho, mesmo `operationId`), com os itens
  vindos de `postagens` + `conteudos` (não mais de `cortes`):
  - cada item ganha `modo`, `estadoEfetivo` e `conteudo` (id, origem, título, miniatura, duração,
    situação) no lugar de `corte`;
  - `semData` passa a listar primeiro os **destinos aprovados sem data** e depois os conteúdos
    prontos sem destino agendado, com `conteudoId` e, quando houver, `destinoId`/`contaId`;
  - arrastar um item agendado usa `lote/reagendar` com um item; soltar um "sem data" num dia abre o
    `AgendarDialog` comum (R12), que para um membro diante de um item não aprovado mostra "Pedir
    aprovação";
  - o cartão mostra o modo (ícone "lembrete" na 014) e o estado efetivo (`a_postar`/`atrasado` em
    destaque).
- **Por quê:** o calendário é a outra metade da central (SC-001, "o que está agendado esta
  semana"); reaproveitar a rota evita duas agendas.

## R12. Integração com o assistente de IA (008)

- **Decisão:**
  - o alvo do assistente ganha `entityType = "conteudo"` (`{entityType: "conteudo", entityId,
    contaId}`) para gerar textos antes de o destino existir (o "Agendar" num corte pronto). O alvo
    `"corte"` continua aceito (o `id` é o mesmo, R1), e o alvo `"postagem"` continua para destinos
    existentes;
  - `ia/service.py::_resolver_postagem` passa a resolver pelo conteúdo: carrega o `Conteudo` e, na
    origem corte, o `Corte` (para a transcrição e o gancho do contexto); `ia/contexto.py::montar`
    ganha o parâmetro `conteudo` (título, origem, duração), e sem corte o contexto não tem
    transcrição (o prompt já trata campos ausentes);
  - `ia_chamadas.conteudo_id` (nova FK) passa a ser gravada em toda chamada de `postagem.*`; o
    `corte_id` continua gravado na origem corte;
  - `ia/aplicacao.py::_Alvo` compara `conteudo_id` no lugar de `corte_id`;
  - o `AgendarDialog` e o painel do destino usam o `IaAssist` da 008 como o `PostagemSection` faz
    hoje (a sessão sobrevive à criação do destino).
- **Por quê:** o assistente já cobre gerar, registrar custo e marcar "com ajuda da IA"; a 014 só
  troca a chave de corte para conteúdo.

## R13. Como a 015 vai plugar um executor por rede

A 014 **não cria** executor, registro de executores, conexão de conta nem credencial (princípio I e
VIII). Ela deixa o modelo pronto, e a 015 (depois da emenda MAJOR do princípio I) faz:
1. **migration da 015:** remove `ck_postagens_modo_014` e `ck_postagens_estados_015`; cria
   `contas_conectadas`, `credenciais` (cifradas) e `tentativas` (só INSERT), como na pesquisa §4.1;
2. **capacidades:** a camada 2 de `modos_da_conta` passa a consultar "existe executor para a rede"
   e a camada 3, "a conta está conectada, com o escopo certo". A tabela de fatos da rede não muda;
3. **executor:** um módulo por rede (`publicacao/tiktok.py`…) implementa
   `executar(db, destino, conta, conexao) -> Resultado`, chamado por uma **trilha nova**
   (`execucao`) no agendador, que pega `agendado AND modo <> 'lembrete' AND momento <= now()` com
   `SKIP LOCKED` (o momento é `planned_at` ou `planned_at - antecedencia_min` no rascunho
   antecipado) e grava `rascunho_criado`, `publicado` ou `falhou` + `falha_motivo`;
4. **guardas:** a lista de trilhas conhecidas ganha `execucao`; o guarda de AST dos estados
   `rascunho_criado`/`publicado`/`falhou` ganha o módulo da 015 como único lugar permitido; o
   guarda de termos passa a valer "exceto em `publicacao/`", como a pesquisa §5 propõe;
5. **textos aprovados:** o dono decidiu (Q2 = A) que, na 014, editar textos não desfaz a aprovação.
   Com modos automáticos, o princípio I (4.0.0) pede "postagem aprovada e agendada por um dono";
   a 015 precisa decidir se texto editado por membro depois da aprovação exige nova aprovação de
   dono (por exemplo, com `aprovado_textos_hash`). A 014 não antecipa isso;
6. **só donos nos modos automáticos:** a 015 restringe a dono a escolha de `modo <> lembrete`
   (agendar, reagendar, sequência) **e o reagendamento de um destino que já está em modo
   automático** ("reagendar para envio automático", princípio I), como registrado em Clarifications
   Q1. Cancelar continua aberto a dono e membro (cancelar nunca envia).

**Por quê não antecipar mais:** cada peça acima depende da emenda e de testes no sandbox da
TikTok; qualquer código que a 014 escrevesse para isso seria código morto sujeito ao guarda.

## R14. Onde aparece o "Agendar" e a navegação (FR-010, SC-002)

- **Decisão:**
  - menu lateral: item **"Conteúdos"** (`/app/conteudos`), entre "Envios" e "Calendário";
  - `/app/conteudos/:id`: detalhe com player, título editável, origem (link para o corte ou o
    envio), uma **aba por conta de destino** (textos com o IA, aprovação, agendamento e "Postado"),
    "Adicionar conta" e o histórico;
  - o botão **Agendar** (abre o `AgendarDialog`: conta, data e hora, modo com motivos, textos com
    IA) aparece no detalhe do conteúdo, nas linhas da lista, no detalhe do corte pronto
    (`CorteDetalhe`, no lugar da seção Postagem da 006, que vira o mesmo painel de destinos) e na
    aba Cortes do perfil (`CortesTab`, só nos prontos);
  - "Enviar vídeo próprio" fica no topo de Conteúdos (escolhe o perfil) e na aba do perfil.
- **Por quê:** a spec pede o agendar "direto no clipe" (FR-010) e um lugar só para tudo (US1). O
  `PostagemSection` da 006 vira o `DestinoPanel`, usado pelo corte e pelo conteúdo, para não haver
  duas telas de postagem.
