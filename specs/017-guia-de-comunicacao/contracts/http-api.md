# Contrato HTTP: 017-guia-de-comunicacao

Este arquivo é a fonte de desenho. Na implementação, a fonte vira o OpenAPI do FastAPI (princípio
IV), gerado com `npm run gen:contract`.
- Tudo fica sob `/api`, com o envelope de erro da 001 e JSON em camelCase.
- **Não existe rota DELETE** (limpar o guia = salvar vazio).
- **Nenhum caminho nem `operationId` contém** `publish`, `share`, `post-to`, `upload-to`,
  `tiktok`, `youtube` ou `instagram` (guarda do princípio I). As rotas do guia usam `guias_*`; as
  do assistente, `ia_guia_*`.
- GET e `versions`: `RequireUser` (dono e membro). PUT, `revert`, montar e testar: **dono**
  (`RequireOwner`, 403 `forbidden` para o membro).

## Tipos

```text
GuiaEmojis    "nao"|"moderado"|"livre"
Exemplo       { tipo: "titulo"|"legenda"|"bordao", texto (1..500) }
GuiaCampos    { tom (0..500), faca: string[] (0..10, 1..200 cada), naoFaca: string[] (0..10, 1..200),
                vocabulario: string[] (0..30, 1..60), proibidas: string[] (0..30, 1..60),
                emojis: GuiaEmojis|null,            # null = não definido (na conta: herda do perfil)
                emojisPreferidos: string[] (0..10, 1..16),
                hashtagsFixas: string[],            # perfil 0..5, conta 0..8; normalizadas na resposta (#sem-acento)
                maxHashtagsFixas: int|null,         # só na conta: 0..8, null = 5 (Q3); no perfil, sempre null
                exemplos: Exemplo[] (0..5) }        # soma de todos os textos ≤ 4.000
GuiaLimites   { tomMax: 500, regrasItens: 10, regraMax: 200, vocabularioItens: 30, termoMax: 60,
                proibidasItens: 30, emojisItens: 10, emojiMax: 16,
                hashtagsFixasPerfil: 5,             # teto das fixas do perfil (= o padrão)
                hashtagsFixasPadrao: 5,             # máximo da conta quando maxHashtagsFixas é null
                hashtagsFixasTeto: 8,               # limite de hashtags da postagem (textos.HASHTAGS_MAX)
                exemplos: 5, exemploMax: 500, totalMax: 4000 }
Guia          { id: uuid|null,                      # null = nunca editado
                perfilId, contaId: uuid|null,
                campos: GuiaCampos,
                tamanho: int,                       # a soma de caracteres (R2)
                version,                            # 0 = nunca editado
                updatedAt|null, updatedBy: UserRef|null,
                limites: GuiaLimites }
GuiaEfetivo   { proibidas: string[], hashtagsFixas: string[], emojis: GuiaEmojis|null,
                emojisPreferidos: string[],
                maxHashtagsFixas: int }             # conta.maxHashtagsFixas ?? 5
Conflito      { campo: "emojis"|"faca"|"naoFaca"|"hashtagsFixas", perfil: string, conta: string, mensagem }
                                                    # "hashtagsFixas" só no estado inválido herdado (research R6)
GuiaIn        { version: int ≥ 0, campos: GuiaCampos,
                ia?: IaAplicacao[] }                # só { tipoCampo: "guia.montar", chamadaId } (008 R10)
```

Na 008, mudam:

```text
TipoCampoId   + "guia.montar" | "guia.testar"
TipoCampo     + usaGuia: "completo"|"so_proibidas"   # entidade + "guia"; formato + "guia" | "variacoes"
                                                     # so_proibidas: avatar.descricao_prompt, cenario.prompt_ambiente,
                                                     #   avatar.regras_imagem (Q1)
Alvo          entityType + "guia"
Valor         + guia?: GuiaCampos,                   # proposta/entrada do guia.montar; entrada do guia.testar
                variacoes?: { titulo, descricao, hashtags[] }[]   # proposta do guia.testar (3)
IaChamada     + guiaPerfilVersion: int|null, guiaContaVersion: int|null,
                guiaRascunho: "perfil"|"conta"|null, proibidas: string[]
```

`GET /api/ia/tipos` lista `guia.montar` (regra editável) e **não** lista `guia.testar` (usa as
regras de `postagem.textos`).

## Guia do perfil

| Método e caminho | operationId | Quem | Resposta / erros |
|---|---|---|---|
| `GET /api/perfis/{id}/guia` | `guias_perfil_get` | todos | `{ guia: Guia }` (version 0 e campos vazios se nunca editado) · 404 |
| `PUT /api/perfis/{id}/guia` | `guias_perfil_update` | **dono** | `GuiaIn` → `{ guia: Guia }` · 400 `validation_error` (`details.fields`, `details.contas`) · 403 · 404 · 409 `version_conflict` / perfil arquivado |
| `GET /api/perfis/{id}/guia/versions` | `guias_perfil_versions` | todos | `VersionsList` (vazio se nunca editado) |
| `POST /api/perfis/{id}/guia/revert` | `guias_perfil_revert` | **dono** | `RevertIn` → `{ guia: Guia }` · 400 (a versão alvo não passa na validação de hoje) · 403 · 404 · 409 |

## Guia da conta

| Método e caminho | operationId | Quem | Resposta / erros |
|---|---|---|---|
| `GET /api/contas/{id}/guia` | `guias_conta_get` | todos | `GuiaContaOut` · 404 |
| `PUT /api/contas/{id}/guia` | `guias_conta_update` | **dono** | `GuiaIn` → `GuiaContaOut` · 400 · 403 · 404 · 409 (versão ou conta/perfil arquivado) |
| `GET /api/contas/{id}/guia/versions` | `guias_conta_versions` | todos | `VersionsList` |
| `POST /api/contas/{id}/guia/revert` | `guias_conta_revert` | **dono** | `RevertIn` → `GuiaContaOut` · 400 · 403 · 404 · 409 |

```text
GuiaContaOut  { guia: Guia,                 # o da conta
                perfil: Guia,               # o do perfil (só leitura nesta tela; "o que vem do perfil")
                efetivo: GuiaEfetivo,       # o que o assistente usa de fato nas garantias
                conflitos: Conflito[] }     # avisos; não bloqueiam
```

### Erros de validação (US1-4)

```json
{ "error": { "code": "validation_error",
             "message": "O guia tem 2 problemas",
             "details": { "fields": { "exemplos.2.texto": "usa a palavra proibida 'clickbait'",
                                      "hashtagsFixas": "perfil e conta somam 6 hashtags fixas; o máximo desta conta é 5" },
                          "contas": [ { "contaId": "…", "rotulo": "TikTok @atavernanerd",
                                        "campos": ["vocabulario"] },
                                      { "contaId": "…", "rotulo": "YouTube @atavernanerd",
                                        "campos": ["hashtagsFixas"] } ] } } }
```
`contas` só aparece no PUT/revert do perfil (validação cruzada, data-model): uma conta entra se
usa uma proibida nova do perfil (só contas com guia) ou se `|fixas(perfil) ∪ fixas(conta)|` passa do
máximo dela (todas as contas não arquivadas, com ou sem guia). `maxHashtagsFixas` não nulo no PUT
do perfil → 400 em `maxHashtagsFixas`.

## Montar e testar (assistente)

`POST /api/ia/guia/montar` · `ia_guia_montar` · **dono**

```text
corpo { perfilId: uuid, contaId?: uuid,          # contaId = montar o guia da conta
        descricao (1..1000),                     # vira a <instrucao>
        guiaAtual: GuiaCampos,                   # o formulário agora (salvo ou não)
        sessaoId: uuid, anteriores: uuid[] (0..5) }
→ 200 { chamada: IaChamada }                     # proposta = { guia: GuiaCampos } (sem hashtagsFixas, maxHashtagsFixas e exemplos)
erros 400 invalid_ia · 403 · 404 · 409 (arquivado) · 502 ia_invalida|ia_recusa|claude_error · 503 claude_unconfigured · 504 ia_timeout
```
A proposta **não salva nada**: a tela preenche o formulário, e o dono salva com
`PUT …/guia` e `ia: [{ tipoCampo: "guia.montar", chamadaId }]` (desfecho `aplicada`/`editada`).
Descartar: `POST /api/ia/chamadas/{id}/descartar` da 008.

`POST /api/ia/guia/testar` · `ia_guia_testar` · **dono**

```text
corpo { perfilId: uuid,
        nivel: "perfil"|"conta",                 # qual nível vem do formulário
        contaId: uuid,                           # obrigatório (texto de postagem é de uma plataforma)
        alvo: { entityType: "corte"|"conteudo", entityId: uuid },
        guia: GuiaCampos }                       # o do formulário, não salvo
→ 200 { chamada: IaChamada }                     # proposta = { variacoes: [3 × {titulo, descricao, hashtags}] }
erros 400 validation_error (guia do formulário, campo a campo, sem chamar o Claude) · 400 invalid_ia
      · 403 · 404 · 409 · 502 · 503 · 504
```
Grava só a chamada (`tipoCampo = "guia.testar"`, `guiaRascunho = nivel`, `entrada.guia`), com
desfecho `sem_acao`. Nenhuma entidade muda; nenhuma versão é criada.

## Mudanças em rotas existentes

| Rota | Mudança |
|---|---|
| `POST /api/ia/gerar` (008) | corpo igual; a resposta traz `guiaPerfilVersion`, `guiaContaVersion` e `proibidas`; hashtags fixas já incluídas na proposta (até o máximo da conta); avisos novos (proibida, emoji com "não usar", fixas cortadas no estado inválido herdado). Nos tipos `so_proibidas`, só as proibidas do perfil entram no pedido |
| saves com `ia` (008: asset, perfil, kit, postagem) | **400 `ia_proibida`** (`details.palavras: string[]`, `details.campos: string[]`) quando um item `ia` casa com uma chamada com `proibidas` e **algum campo salvo é igual ao da proposta e contém a proibida** (aplicar sem editar; Q2 = A: campo editado passa). Vale também nos 3 campos visuais (`so_proibidas`). Qualquer outro problema do campo `ia` continua ignorado |
| `GET /api/ia/chamadas`, `GET /api/ia/chamadas/{id}` (008) | campos novos em `IaChamada` |
| `GET /api/ia/tipos` (008) | `usaGuia`; `guia.montar` na lista |
