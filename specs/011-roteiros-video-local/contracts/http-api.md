# Contrato HTTP: 011-roteiros-video-local

As rotas do SociMan. O OpenAPI é **gerado** (`npm run gen:contract`); este arquivo descreve a intenção. Os
`operationId` começam com `roteiros_`, `roteiro_padroes_` e `pronuncias_`. Nenhuma rota tem "youtube" ou
"tiktok" no nome.

As regras de acesso são estas:
- **Leitura:** `RequireUser` (dono e membro), em `FORA` no MCP.
- **Escrita:** `RequireHuman` (dono e membro humanos; outro ator recebe 403 `somente_humano` e gera o evento
  `publicacao_recusada`), em `PROIBIDAS`.
- **Reverter:** `RequireHumanOwner`.
- **Edição:** toda escrita leva `version` (409 `version_conflict` com `details.versaoAtual`).

## Roteiros

| Método e caminho | operationId | Corpo / resposta |
|---|---|---|
| `GET /api/perfis/{perfilId}/roteiros` | `roteiros_listar` | filtros `status`, `produtoId`, `arquivados`, `q`; cursor → `{itens: RoteiroResumo[], proximo}` |
| `POST /api/perfis/{perfilId}/roteiros` | `roteiros_criar` | `{nome, brief, avatarId?, vozId?, produtos: [{produtoId, varianteId?}]}` → `RoteiroDetalhe` (voz padrão do avatar, portões do padrão do perfil) |
| `GET /api/roteiros/{id}` | `roteiros_detalhe` | `RoteiroDetalhe` |
| `PATCH /api/roteiros/{id}` | `roteiros_editar` | `{version, nome?, brief?, avatarId?, vozId?, velocidade?, frases?, produtos?, posicoes?: [{cenaId, frases: int[], tomadaId?}]}`; aplica as invalidações (FR-035/036) e devolve o detalhe |
| `POST /api/roteiros/{id}/planejar` | `roteiros_planejar` | `{version}`; `rascunho`/`aguardando_texto`/`falhou(plano)` → `planejando` |
| `POST /api/roteiros/{id}/aprovar` | `roteiros_aprovar` | `{version, portao: "texto"\|"narracao"\|"keyframes"\|"clipes"\|"final"}`; só no `aguardando_<portao>` correspondente (senão 409 `portao_fora_de_hora`) |
| `PUT /api/roteiros/{id}/controle` | `roteiros_controle` | `{version, modo, portoes}`; FR-009 (desligar o portão em que está parado = aprovar) |
| `POST /api/roteiros/{id}/tentar-de-novo` | `roteiros_tentar_de_novo` | `{version}`; só em `falhou` |
| `POST /api/roteiros/{id}/arquivar` · `…/restaurar` | `roteiros_arquivar` · `roteiros_restaurar` | `{version}`; arquivar cancela as gerações abertas |
| `GET /api/roteiros/{id}/versoes` | `roteiros_versoes` | lista com `autor: {tipo, id, nome}` ("sistema (automático)" para `system:roteiro`) |
| `POST /api/roteiros/{id}/versoes/{versao}/reverter` | `roteiros_reverter` | só dono humano |

## Por posição

| Método e caminho | operationId | Corpo / resposta |
|---|---|---|
| `POST /api/roteiros/{id}/posicoes/{ordem}/keyframe/regerar` | `roteiros_regerar_keyframe` | `{version, instrucao?, referencias?: uuid[]}`; grava a instrução e as referências na cena (409 `cena_usada` em cena usada) e pede `cena.keyframe` (a aberta anterior vira `descartada`) |
| `POST /api/roteiros/{id}/posicoes/{ordem}/keyframe` | `roteiros_enviar_keyframe` | multipart `arquivo` (PNG/JPG/WebP, ≤ 20 MB), `version`; vira o keyframe sem geração |
| `POST /api/roteiros/{id}/posicoes/{ordem}/clipe/regerar` | `roteiros_regerar_clipe` | `{version, motor?}`; pede `cena.clipe` com o motor (e grava `cenas.motor` se a cena não estiver usada) |
| `PUT /api/roteiros/{id}/posicoes/{ordem}/tomada` | `roteiros_escolher_tomada` | `{version, tomadaId}`; tomada da cena, com duração suficiente (400 `tomada_curta`) |

Escolher uma opção de keyframe usa a rota da 021 (`POST /api/geracoes/{id}/escolher`), sem mudança.

## Padrão do perfil e pronúncias

| Método e caminho | operationId | Corpo / resposta |
|---|---|---|
| `GET /api/perfis/{perfilId}/roteiro-padroes` | `roteiro_padroes_ler` | `{modo, portoes, version}` (version 0 = padrão do código) |
| `PUT /api/perfis/{perfilId}/roteiro-padroes` | `roteiro_padroes_salvar` | `{version, modo, portoes}` |
| `GET /api/perfis/{perfilId}/pronuncias` | `pronuncias_listar` | `?arquivadas` → `Pronuncia[]` |
| `POST /api/perfis/{perfilId}/pronuncias` | `pronuncias_criar` | `{escrita, falada}`; 409 `pronuncia_existe` |
| `PATCH /api/pronuncias/{id}` | `pronuncias_editar` | `{version, escrita?, falada?}` |
| `POST /api/pronuncias/{id}/arquivar` · `…/restaurar` | `pronuncias_arquivar` · `pronuncias_restaurar` | `{version}` |

## Schemas principais (nomes únicos no OpenAPI)

```text
RoteiroDetalhe {
  id, perfilId, nome, brief, avatar?: {id, nome, kitStatus}, voz?: {id, nome, origem, revogada},
  formato, frases: str[], velocidade, modo, portoes: {texto, narracao, keyframes, clipes, final},
  status, etapaFalhou?, erro?: {code, message}, avisos: [{code, message, ordem?}],
  produtos: [{produtoId, nomeComercial, varianteId?, cor?}],
  posicoes: [{ordem, cena: {id, nome, status, motor, largura, altura, keyframeUrl?, keyframeGeracaoId?},
              frases: int[], inicioS?, duracaoS?, tomada?: TomadaRoteiro, aviso?,
              geracoesAbertas: [{id, passo, status, progress, etapaMensagem}]}],
  narracao?: {id, audioUrl?, tempos, totalS, similaridade, velocidade, desatualizada, limpa},
  previa?: {geracaoId, videoUrl?, duracaoMs}, conteudoId?, version, createdAt, updatedAt
}
TomadaRoteiro { id, origem, motor?, duracaoMs, videoUrl?, miniaturaUrl?, keyframeAntigo, limpa }
RoteiroResumo { id, nome, status, etapaFalhou?, produtos: str[], cenas: int, miniaturaUrl?, updatedAt }
Pronuncia { id, escrita, falada, archived, version }
```

## Mudanças em rotas existentes (aditivas)
- `GET /api/cenas/{id}` ganha `motor`, `largura`, `altura`, `keyframeInicial?`, `keyframeFinal?`,
  `keyframeInstrucao`, `keyframeRefs`, `duracaoMaxS`, e nas tomadas `motor`, `keyframeAntigo` e `limpa`.
  O `PATCH /api/cenas/{id}` aceita os campos locais (409 `cena_usada` em cena usada).
- `GET /api/conteudos/{id}` ganha `geradoIa` e `roteiro?: {id, nome, motores, avisoAtribuicao?}`.
- `GET /api/geracoes/{id}`: o `CandidatoGeracao` ganha `video?: {url, miniaturaUrl, duracaoMs, largura,
  altura}`.
- Opções de rede do destino: `conteudoIa` passa a vir `true` por padrão quando o conteúdo é `geradoIa`.

## Erros novos
`invalid_roteiro` (400, com `field`), `portao_fora_de_hora`, `limite_cenas`, `cena_usada` (já da 010),
`consentimento_revogado`, `pronuncia_existe`, `tomada_curta` e `roteiro_arquivado` (409). Todos entram no
`errors.ts` do contrato com a mensagem em pt-BR.

## Edge
`location ~ ^/api/roteiros/[^/]+/posicoes/[0-9]+/keyframe$` com `client_max_body_size 21m` (como os
assets da 007). O resto fica no `/api/` geral.
