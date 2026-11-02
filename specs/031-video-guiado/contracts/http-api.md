# Contrato HTTP: 031-video-guiado

O que está aqui é o rascunho. A fonte da verdade continua sendo o OpenAPI do FastAPI, gerado pelo `npm run
gen:contract` (princípio IV). As rotas não citam rede (guarda da 006).

Regras de acesso:
- todas as escritas são `RequireHuman` (dono ou membro), com `history.record`;
- as leituras são `RequireUser`;
- no `mcp/mapa.py`, as escritas ficam em `PROIBIDAS` e as leituras em `FORA` (mesma regra da 011).

## Novas

| Método e caminho | operationId | Corpo | Resposta | Erros |
|---|---|---|---|---|
| `GET /api/roteiros/grade` | `roteiros_grade` | — | `{trechoBaseS, opcoes: [5,10,…], maxTrechosPorCena: 3}` | — |
| `POST /api/roteiros` | `roteiros_criar_guiado` | `{perfilId, tipoVideo:"avatar_pov", avatarId, vozId, cenarioId, produtoId, varianteId?, duracaoS, nome?}` | `Roteiro` (201), já com `conversaEstado` e a geração `roteiro.perguntas` pedida | 400 `perfil_invalido`, 409 `perfil_base_arquivado`, 422 `cena_invalida` (field), 422 `duracao_fora_da_grade`, 400 `voz_invalida`, 409 `consentimento_revogado` |
| `GET /api/roteiros/{id}/conversa` | `roteiros_conversa` | — | `{estado, mensagens: [Mensagem], perguntaAtual?: Pergunta, geracaoAberta?}` | 404 |
| `POST /api/roteiros/{id}/conversa/respostas` | `roteiros_responder` | `{perguntaId, opcoes: string[], texto?: string≤500, version}` | `Conversa` | 409 `pergunta_respondida`, 422 `opcao_invalida`, 409 `version_conflict` |
| `POST /api/roteiros/{id}/conversa/refazer-perguntas` | `roteiros_refazer_perguntas` | `{version}` | `Conversa` | 409 `geracao_em_andamento` |
| `POST /api/roteiros/{id}/recusar` | `roteiros_recusar` | `{alvo: {tipo, ordem?, quadro?, trecho?}, opcoes: string[], texto?: string≤500, version}` | `Roteiro`, com a geração `roteiro.ajuste` pedida | 409 `etapa_errada` (alvo fora da etapa atual), 409 `geracao_em_andamento` |
| `PUT /api/roteiros/{id}/posicoes/{ordem}/cena` | `roteiros_definir_cena` | `{reuso: "total"\|"plano"\|"nova", cenaId?, version}` | `Roteiro` | 422 `reuso_invalido` (`total` com cena que não casa), 409 `etapa_errada` (depois do texto, só no avançado) |
| `POST /api/roteiros/{id}/posicoes/{ordem}/aprovar` | `roteiros_aprovar_posicao` | `{etapa: "keyframes"\|"clipe", version}` | `Roteiro` | 409 `nada_a_aprovar` (quadro provisório faltando ou geração aberta) |
| `GET /api/roteiros/{id}/posicoes/{ordem}/quadros` | `roteiros_quadros` | — | `[{ordem, papel, imageUrl?, provisorio, geracaoId?, instrucao}]`. Esconder o texto no wizard é regra da tela (FR-015), não da API | 404 |

## Alteradas (aditivas)

- **`GET /api/roteiros/{id}`** (`Roteiro`) ganha:
  - `tipoVideo`, `cenarioId`, `duracaoAlvoS`, `trechoBaseS` e `conversaEstado`;
  - em cada posição: `trechos`, `reuso`, `motivo`, `aprovadoKeyframesEm`, `aprovadoClipeEm`,
    `quadros[]` (resumo) e `tomadasTrechos[]`;
  - o aviso `fala_nao_cabe` (com `ordem`).
- **`PATCH /api/roteiros/{id}`** aceita `duracaoS` no guiado (dentro da grade; 422 `duracao_fora_da_grade`). A mudança refaz o plano.
- **`POST …/posicoes/{ordem}/keyframe/regerar`** ganha `quadro?` (padrão 0) e `nOpcoes?` (1..4; no wizard,
  sempre 1). Refaz o quadro e arquiva os seguintes.
- **`POST …/posicoes/{ordem}/clipe/regerar`** ganha `trecho?` e `nOpcoes?` (1..2, cada opção uma tomada;
  quem escolhe é o `PUT …/tomada` com `trecho`).
- **`PUT …/posicoes/{ordem}/tomada`** ganha `trecho?`.
- **`POST /api/roteiros/{id}/planejar`**: no guiado, exige `conversaEstado = respondida` (409
  `conversa_incompleta`) e manda as respostas ao planejador.
- **`POST /api/perfis/{id}/roteiros`** (criar da 011) fica `deprecated`. A SPA deixa de usar.

## Formatos da IA (saída estruturada)

**`perguntas_roteiro`**:

```json
{"perguntas": [{"id": "foco", "texto": "…", "multipla": true,
  "opcoes": [{"id": "caimento", "rotulo": "Caimento"}], "exemplos": ["…"]}]}
```

Regras: de 1 a 5 perguntas, de 2 a 6 opções, rótulo com até 60 caracteres, texto com até 200.

**`ajuste_roteiro`**:

```json
{"tipo": "pergunta", "pergunta": {…}}
```

ou

```json
{"tipo": "mudanca", "mudanca": {"alvo": {…}, "quadros": [{"ordem": 1, "instrucao": "…"}],
  "acao": "…", "motor": "wan", "velocidade": 1.1, "frases": {"0": "…"}, "trechos": 2},
  "resumo": "…"}
```

Só os campos do alvo podem mudar, e o aplicador confere.

**`plano_roteiro` v2**: está no data-model.

## Fakes

- **Claude falso** (`tests/fakes/anthropic_fake.py` e o `e2e/fakes/server.py`) responde os 3 formatos.
  Palavras na instrução ativam os modos de erro: "ambíguo" faz o ajuste devolver uma `pergunta`, e "não cabe"
  faz o plano estourar o orçamento na 1ª tentativa.
- **`comfyui_fake`** grava o `end_image` recebido (inspeção no teste do encadeamento) e devolve um mp4 de
  124 quadros a 24 fps.
