# Data Model: 031-video-guiado

A migration **`0028_video_guiado`** entra sobre a `0027_roteiros_video_local`, com upgrade e downgrade e com o
teste `test_migration_0028`. Tudo é **aditivo**: os roteiros da 011 continuam iguais (`tipo_video IS NULL`).
O histórico segue o `history.py` (princípio VII). Não há DELETE.

**Glossário:** "quadro" é o keyframe da cena. A spec usa "keyframe", e o código usa `cena_quadros`.

## `roteiros` (colunas novas)

| Coluna | Tipo | Regra |
|---|---|---|
| `tipo_video` | enum `roteiro_tipo_video` (`avatar_pov`), nulo | Preenchida = roteiro guiado. Nula = roteiro da 011 (abre no avançado) |
| `cenario_id` | FK `assets` (tipo `cenario`), nulo | Obrigatória no guiado. Mesma regra de uso da 029: qualquer perfil base, não arquivado |
| `duracao_alvo_s` | smallint, nulo | No guiado: múltiplo de `trecho_base_s`, entre 1× e `grade_max`× (CHECK) |
| `trecho_base_s` | smallint, nulo | Cópia da grade no momento da criação (FR-033). Mudar o `.env` depois não mexe |
| `conversa_estado` | enum `conversa_estado` (`sem_perguntas`, `perguntando`, `respondida`), nulo | Só no guiado |
| `avisos` (existente) | JSONB | Novo código `fala_nao_cabe` com a `ordem` |

Entram em `__versioned_fields__`: `tipo_video`, `cenario_id`, `duracao_alvo_s` e `trecho_base_s`. Só o
`trecho_base_s` é imutável depois de criado (`__immutable_fields__`). A `duracao_alvo_s` pode mudar dentro
da grade guardada, e a mudança reposiciona o roteiro em `planejando` (refaz o plano). O `conversa_estado` é técnico, fora do
snapshot. O CHECK `ck_roteiros_guiado` exige que `tipo_video`, `cenario_id`, `duracao_alvo_s` e
`trecho_base_s` estejam todos preenchidos ou todos nulos.

## `roteiro_conversa` (nova, só inserção)

Uma linha por mensagem do chat. O trigger `roteiro_conversa_so_insercao` bloqueia UPDATE e DELETE.

| Coluna | Tipo | Regra |
|---|---|---|
| `id` | uuid PK | |
| `roteiro_id` | FK `roteiros` | |
| `seq` | int | UNIQUE (`roteiro_id`, `seq`) |
| `tipo` | enum `conversa_tipo` (`pergunta`, `resposta`, `pedido_troca`, `esclarecimento`, `aviso`) | |
| `pergunta_id` | text, nulo | O `id` da pergunta (vindo da IA) a que a resposta se refere |
| `conteudo` | JSONB | `pergunta`: `{texto, multipla, opcoes[{id,rotulo}], exemplos[]}`. `resposta`: `{opcoes[], texto?}`. `pedido_troca`: `{alvo, opcoes[], texto?}` |
| `alvo` | JSONB, nulo | `{tipo: narracao|quadros|trecho|posicao|final, ordem?, quadro?, trecho?}` |
| `ia_chamada_id` | FK `ia_chamadas`, nulo | A chamada que gerou a pergunta ou o esclarecimento |
| `autor_tipo`, `autor_id` | | O humano ou `system:roteiro` |
| `created_at` | timestamptz | |

Limites:
- `texto` com até 500 caracteres;
- de 2 a 6 opções por pergunta;
- até 5 perguntas na rodada inicial (FR-009);
- até 3 esclarecimentos por pedido de troca, sem contar para as 5.

## `roteiro_cenas` (posições; colunas novas)

| Coluna | Tipo | Regra |
|---|---|---|
| `trechos` | smallint, nulo | No guiado: 1..3 (CHECK). `duracao_s` passa a ser `trechos × trecho_base_s`, fixo, e não mais tirado da fala |
| `reuso` | enum `posicao_reuso` (`total`, `plano`, `nova`), nulo | A decisão do modal (FR-019) |
| `motivo` | text ≤ 300, nulo | A frase do motivo da proposta |
| `aprovado_keyframes_em`, `aprovado_keyframes_por` | | Aprovação da sequência da posição (R9). Zerados quando um quadro muda |
| `aprovado_clipe_em`, `aprovado_clipe_por` | | Idem, para os trechos |
| `orcamento_chars` | smallint, nulo | O orçamento de fala da posição (R4), derivado de `duracao_s` |

Regra: no guiado, a soma de `duracao_s` das posições é `duracao_alvo_s`. Quem confere é o aplicador do plano e
o `PUT` de posições, que devolve 422 `duracao_nao_fecha` com a soma.

## `roteiro_trechos` (nova)

A tomada escolhida para cada trecho de cada posição, no lugar do `roteiro_cenas.tomada_id` (que continua para
a 011).

| Coluna | Tipo | Regra |
|---|---|---|
| `roteiro_id`, `ordem`, `trecho` | PK | `trecho` 0..2, `< roteiro_cenas.trechos` |
| `tomada_id` | FK `cena_tomadas`, nulo | Nulo = a gerar |

Faz parte do snapshot do roteiro (campo `posicoes`), como as posições.

## `cenas` (colunas novas)

| Coluna | Tipo | Regra |
|---|---|---|
| `trechos` | smallint, nulo | 1..3 nas cenas criadas pelo guiado. Nulo = cena da 010/011 (1 keyframe) |
| `cenario_id` (existente) | FK `assets` | Sem mudança de tipo. Nas cenas do guiado é obrigatório, com o cenário do roteiro (validação no service) |
| `origem_cena_id` | FK `cenas`, nulo | A cena de onde esta derivou (reuso do plano ou ajuste, FR-022). Imutável |

`keyframe_inicial_id` e `keyframe_final_id` passam a ser **espelhos** do quadro 0 e do último quadro, para a 010,
o `tomada_serve` antigo e o prompt do Flow. Quem os grava é o `cenas/quadros.py`, na mesma transação.

## `cena_quadros` (nova)

| Coluna | Tipo | Regra |
|---|---|---|
| `id` | uuid PK | |
| `cena_id` | FK `cenas` | UNIQUE (`cena_id`, `ordem`) entre os não arquivados |
| `ordem` | smallint 0..3 | 0 = início; o último (`= cenas.trechos`) = fim |
| `papel` | enum `quadro_papel` (`inicio`, `meio1`, `meio2`, `fim`) | Derivado da ordem e do total. Fica gravado para leitura |
| `instrucao` | text ≤ 2000 | Estado final do quadro, em inglês (vem do plano ou do ajuste) |
| `image_id` | FK `images`, nulo | Nulo = a gerar |
| `geracao_id` | FK `geracoes`, nulo | A geração aberta ou a última |
| `provisorio` | bool | `true` = opção única aplicada pela máquina para seguir a cadeia (R3), ainda sem aprovação humana |
| `archived_at` | | Recusa ou mudança arquiva o quadro (nunca apaga) e cria outro na mesma ordem |

Não tem `version` próprio: mudar um quadro gera uma versão da **cena** (como `produto_variantes` faz com o
produto), com `details.quadro` = ordem.

## `cena_tomadas` (colunas novas)

| Coluna | Tipo | Regra |
|---|---|---|
| `trecho` | smallint, nulo | 0..2. Nulo = tomada inteira da 010/011 |
| `keyframe_fim_image_id` | FK `images`, nulo | O quadro final usado. Faz parte da chave do reuso (R8) |

## `geracoes` / passos

| Passo novo | Motor | n | Sem escolha | Aplicador |
|---|---|---|---|---|
| `roteiro.perguntas` | claude | 1/1 | sim | Grava as perguntas em `roteiro_conversa`; `conversa_estado = perguntando` |
| `roteiro.ajuste` | claude | 1/1 | sim | Grava um `esclarecimento` (pergunta) **ou** aplica a mudança pelo `service.editar`, com o autor = quem pediu |

Passos alterados:
- **`cena.keyframe`:** `extras.quadro` e `n_max` 4. O guiado pede n = 1 (wizard) ou o n pedido no avançado.
- **`cena.clipe`:** `extras.trecho`, com refs `[quadro[t], quadro[t+1]]`.

O CHECK `ck_geracoes_passo` ganha os 2 passos. Em `ia/tipos.py`, entram os formatos `perguntas_roteiro` e
`ajuste_roteiro`, e o `plano_roteiro` ganha a v2 (abaixo).

## Plano v2 (`plano_roteiro`, só no guiado)

Por posição, o plano traz:
- `cena_id` + `nivel` (`total`/`plano`) **ou** `nova`;
- `trechos` (1..3);
- `frases` (índices);
- `motivo` (≤ 300).

A `nova` traz os campos da 011 mais `quadros[]` (de `trechos + 1` instruções, em inglês) e `trechos`.

A validação (`problemas()`) confere:
- a soma `Σ trechos × base` igual à `duracao_alvo_s`;
- o orçamento de caracteres por posição;
- que o reuso `total` só seja usado com uma cena candidata `total`;
- que cena com outro produto não apareça.

A v1 continua para os roteiros da 011.

## Estados

A máquina da 011 não ganha estados. O guiado usa os mesmos, com 3 diferenças:
- `aguardando_texto` mostra o **modal de cenas** no wizard;
- `gerando_keyframes` encadeia os quadros por posição (R3);
- `gerando_clipes` pede um clipe por trecho.

O portão `keyframes` passa quando **todas** as posições têm `aprovado_keyframes_em`, e o `clipes` quando todas
têm `aprovado_clipe_em`. O `aprovar` global da 011 preenche todas.

`reposicionar` ganha duas checagens:
- um quadro sem `image_id`, ou provisório sem aprovação, volta a `gerando_keyframes`;
- um trecho sem tomada que sirva volta a `gerando_clipes`.

## Limpeza e revogação

- **Limpeza:** quadros arquivados e tomadas de trecho sem uso entram na fase 2 da limpeza da 011 (exceção
  1, 4.5.0), pelo `desuso_em`. O quadro e as tomadas de um vídeo entregue ficam protegidos.
- **Revogação (025):** pedir quadro ou trecho novo com avatar ou voz revogados dá 409
  `consentimento_revogado`.
- **Conversa:** a revogação da 025 **não** mexe na `roteiro_conversa`. A tabela é só de inserção, e as
  respostas são sobre o produto e o vídeo, não sobre a pessoa. A tela do chat avisa para não escrever dados
  pessoais.
