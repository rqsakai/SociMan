# Contrato HTTP: 008-assistente-ia

Este arquivo é a fonte de desenho. Na implementação, a fonte vira o OpenAPI do FastAPI (princípio
IV), gerado com `npm run gen:contract`.
- Tudo fica sob `/api`, com o envelope de erro da 001 e JSON em camelCase.
- **Não existe rota DELETE.**
- **Nenhum caminho nem `operationId` contém** `publish`, `share`, `post-to`, `upload-to`,
  `tiktok`, `youtube` ou `instagram` (guarda do princípio I). As rotas ficam em `/api/ia/…` e os
  `operationId` seguem `ia_*`.
- Salvo indicação, as rotas pedem `RequireUser` (dono ou membro).

## Tipos

```text
TipoCampoId   "avatar.descricao_prompt"|"avatar.tom_de_voz"|"avatar.regras_imagem"
              |"cenario.prompt_ambiente"|"asset.nome"|"asset.descricao"|"perfil.bio"
              |"kit.bordoes"|"kit.series"|"postagem.titulo"|"postagem.descricao"
              |"postagem.hashtags"|"postagem.textos"
Limites       { maxChars|null, minChars|null, umaLinha: bool, maxItens|null, minItens|null,
                maxCharsItem|null, maxSugestoes|null }   # maxSugestoes = 10 só em "sugestoes"
TipoCampo     { id: TipoCampoId, rotulo, onde, entidade: "asset"|"perfil"|"kit"|"postagem",
                idioma: "en"|"perfil",                   # "en" só em avatar.descricao_prompt e cenario.prompt_ambiente
                formato: "texto"|"lista"|"sugestoes"|"textos_postagem",
                limites: Limites, regras: Regras }       # "sugestoes" = kit.bordoes e kit.series (Q3)
Regras        { texto,                  # o texto em vigor (personalizado ou padrão)
                padrao,                 # o texto que vem com o SociMan
                personalizada: bool,    # false = usando o padrão
                padraoAtualizado: bool, # true = o padrão mudou depois da última edição
                version,                # 0 = nunca editada
                updatedAt|null, updatedBy: UserRef|null }
Alvo          { entityType: "asset"|"perfil"|"kit"|"postagem"|"corte", entityId: uuid|null,
                contaId: uuid|null }    # corte + conta quando a postagem ainda não existe
Valor         { texto?: string, itens?: string[],
                titulo?: string, descricao?: string, hashtags?: string[] }   # um formato por tipo
Proposta      Valor                     # em "sugestoes": { itens } com as sugestões (≤ 10)
Selecao       { aceitos: string[] (0..20), rejeitados: string[] (0..100) }   # só em "sugestoes"
IaChamada     { id, tipoCampo, perfil: PerfilRef, alvo: Alvo, sessaoId|null, instrucao,
                aceitos: string[], rejeitados: string[], itensAplicados: string[]|null,
                entrada: Valor|null, proposta: Proposta|null, explicacao, avisos: string[],
                excede: bool, contextoFaltante: string[], desfecho: Desfecho,
                desfechoEm|null, desfechoPor: UserRef|null, aplicadaVersao|null,
                model, modelServido|null, regrasVersion, erroCode|null,
                inputTokens|null, outputTokens|null, cacheReadTokens|null,
                cacheCreationTokens|null, custoUsd: number|null, durationMs,
                createdAt, createdBy: UserRef|null }
Desfecho      "sem_acao"|"aplicada"|"editada"|"descartada"|"erro"
IaAplicacao   { tipoCampo: TipoCampoId, chamadaId: uuid,
                itens?: string[] (1..20) }   # no corpo dos saves (R10); itens só nas sugestoes
```

## Tipos de campo e regras

| Método e caminho | operationId | Quem | Resposta / erros |
|---|---|---|---|
| `GET /api/ia/tipos` | `ia_tipos_list` | todos | `{ items: TipoCampo[] }` na ordem do registro |
| `GET /api/ia/tipos/{tipo}` | `ia_tipos_get` | todos | `{ tipo: TipoCampo }` · 404 `ia_tipo_not_found` |
| `PUT /api/ia/tipos/{tipo}/regras` | `ia_regras_update` | **dono** | corpo `{ version, texto (1..8.000) }` → `{ tipo }` · 400 · 403 · 409 `version_conflict` |
| `POST /api/ia/tipos/{tipo}/padrao` | `ia_regras_padrao` | **dono** | corpo `{ version }` → `{ tipo }` (texto volta ao padrão; nova versão) · 403 · 409 |
| `GET /api/ia/tipos/{tipo}/versions` | `ia_regras_versions` | todos | `VersionsList` (vazio se nunca editada) |
| `POST /api/ia/tipos/{tipo}/revert` | `ia_regras_revert` | **dono** | `RevertIn` → `{ tipo }` · 403 · 409 |

`version` do `PUT` e do `padrao` é `0` quando a regra nunca foi editada (cria a linha).

## Gerar e descartar

`POST /api/ia/gerar` · `ia_gerar` · dono e membro

```text
corpo { tipoCampo: TipoCampoId, perfilId: uuid, alvo: Alvo,
        valorAtual: Valor,          # o que está no formulário agora (salvo ou não)
        instrucao: string (0..1.000),
        sessaoId: uuid,             # gerado pelo painel ao abrir
        anteriores: uuid[] (0..5),  # "Outra versão" / "Gerar mais": chamadas da mesma sessão
        selecao?: Selecao }         # só "sugestoes": aceitos (marcados, não aplicados) e rejeitados da sessão
→ 200 { chamada: IaChamada }        # proposta, explicação, avisos, excede
```

Validações e erros:
- 400 `invalid_ia`: tipo incompatível com o alvo (ex.: `avatar.tom_de_voz` num cenário), alvo de
  outro perfil, `valorAtual` fora do formato do tipo ou acima de 1,5 × o limite, `selecao` num
  tipo que não é `sugestoes` ou fora dos limites (quantidade, tamanho do item);
- 400 `ia_anteriores_invalidas`: anterior de outro autor, sessão, tipo ou alvo;
- 404: perfil, entidade, corte ou conta inexistente;
- 409 `conflict`: entidade arquivada;
- 503 `claude_unconfigured` (sem `ANTHROPIC_API_KEY`);
- 504 `ia_timeout`; 502 `ia_recusa`, `ia_invalida`, `claude_error`.
Toda falha a partir do Claude (504/502) **grava a chamada** com `desfecho = erro` antes de
responder. O 503 também grava (`erro_code = unconfigured`), para o registro mostrar a tentativa.

Nas `sugestoes`, a proposta nunca repete (casefold) um item de `valorAtual.itens`, de
`selecao.aceitos` ou de `selecao.rejeitados`: o servidor remove as repetidas e avisa em `avisos`.
Quantas cabem no kit (20 − itens atuais − aceitos) é conta do painel.

`POST /api/ia/chamadas/{id}/descartar` · `ia_chamadas_descartar` · só o autor da chamada
- corpo vazio → 204. Idempotente. Chamada já `aplicada`/`editada`/`erro` → 204 sem mudar nada;
  de outro autor → 403.

## Registro e resumo (dono)

`GET /api/ia/chamadas` · `ia_chamadas_list` · **dono**
- query: `perfilId`, `tipoCampo`, `desfecho`, `de`, `ate` (datas em `APP_TZ`), `sessaoId`,
  `cursor`, `limit` (≤ 100, padrão 50);
- → `{ items: IaChamada[], nextCursor|null }`, mais recentes primeiro. Inclui as linhas da 006
  (`postagem.textos`).

`GET /api/ia/chamadas/{id}` · `ia_chamadas_get` · **dono** → `{ chamada: IaChamada }`

`GET /api/ia/resumo` · `ia_resumo` · **dono**
- query: `mes=YYYY-MM` (padrão: mês corrente em `APP_TZ`);
- → `{ mes, chamadas, erros, aplicadas, editadas, descartadas, custoUsd,
       porTipo: { tipoCampo, chamadas, custoUsd }[], porPerfil: { perfil: PerfilRef, chamadas,
       custoUsd }[], precosVersao }`.

## Saves existentes (campo aditivo `ia`)
Mesmas rotas, mesmos códigos e mesma validação. O único acréscimo é o campo opcional
`ia: IaAplicacao[]` (até 10). Com Q1 = B, o **Aplicar** do painel chama estas rotas na hora, com
só aquele campo (`PATCH` parcial; `POST` de criação quando a postagem não existe; no `PUT` do kit,
os tokens salvos com só aquele campo trocado). Um 409 `version_conflict` ou um 400 voltam ao painel
como em qualquer save, e nada é gravado:

| Rota | Tipos aceitos em `ia` |
|---|---|
| `PATCH /api/assets/{id}` (`assets_update`) | `avatar.*`, `cenario.prompt_ambiente`, `asset.nome`, `asset.descricao` |
| `PATCH /api/perfis/{id}` (`perfis_update`) | `perfil.bio` |
| `PUT /api/perfis/{id}/kit` (`kit_update`) | `kit.bordoes`, `kit.series` |
| `POST /api/cortes/{id}/postagens` (`postagens_create`) | `postagem.*` com alvo `corte` + a mesma conta |
| `PATCH /api/postagens/{id}` (`postagens_update`) | `postagem.*` com alvo nesta postagem ou no corte + conta dela |

Itens que não casam (outro perfil, outro alvo, campo que não mudou, chamada `texto`/`lista`/
`textos_postagem` já aplicada, `itens` que não entraram na lista nesta versão) são **ignorados**;
o save nunca falha por causa deles. Numa chamada `sugestoes`, uma nova aplicação com outros itens
acumula em `itensAplicados`. A versão gravada leva `details.ia` (data-model)
e a resposta é a mesma de antes. `sugestaoId` de `postagens_create/update` fica `deprecated`.

## Rotas da 006 (deprecated)
- `POST /api/cortes/{id}/sugestoes` (`postagens_sugerir`): passa a chamar o serviço novo com
  `tipoCampo = "postagem.textos"`, alvo `corte` + `contaId`, sem sessão; `outraVersao: true` manda
  as últimas propostas do corte e da plataforma como anteriores (comportamento da 006). A resposta
  continua `{ sugestao: Sugestao }`. Códigos de erro novos (`ia_timeout`…) substituem
  `textos_timeout`/`textos_invalidos`.
- `GET /api/cortes/{id}/sugestoes` (`postagens_sugestoes`): lê de `ia_chamadas` com
  `tipo_campo = 'postagem.textos'`.

## Integrações
`GET /api/integracoes` não muda: `claude: "ok" | "ausente"` já habilita ou desabilita o botão.

## Rotas do SPA
- `/app/assistente-ia` (abas `?aba=regras|registro|resumo`; registro e resumo só para o dono);
- `/app/assistente-ia/regras/:tipo` (detalhe da regra, com histórico);
- o painel `IaAssist` aparece dentro de `/app/assets/:id`, `/app/perfis/:id` (edição e
  `?aba=marca`) e `/app/cortes/:id` (seção Postagem).
