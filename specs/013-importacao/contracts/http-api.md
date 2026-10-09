# Contrato HTTP: Importação da agência (013)

Prefixo `/api/agencia/*`, `operationId` `agencia_*` e respostas em camelCase (aliases Pydantic). Sem
"youtube" nem "tiktok" nas rotas e nos `operationId` (guarda do princípio I). O contrato tipado sai do
OpenAPI (`npm run gen:contract`); este arquivo descreve a forma e as regras.

**Rotas H** (só dono humano, `RequireHumanOwner`): um não humano recebe 403 `somente_humano` e deixa o
evento `publicacao_recusada`; um membro recebe 403 `somente_dono`. As demais usam `RequireUser`.

## Rotas

| operationId | Método e rota | Quem | Corpo / resposta |
|---|---|---|---|
| `agencia_estado` | `GET /api/agencia/estado` | dono e membro | → **200** `Estado` |
| `agencia_previa` | `POST /api/agencia/previa` | **H** | sem corpo → **201** `Previa` |
| `agencia_confirmar` | `POST /api/agencia/importacoes` | **H** | `Confirmar` → **202** `Importacao` (`estado = "processando"`) |
| `agencia_importacoes_list` | `GET /api/agencia/importacoes` | dono e membro | → **200** `{ "items": ImportacaoResumo[] }` (mais recentes primeiro) |
| `agencia_importacoes_get` | `GET /api/agencia/importacoes/{id}` | dono e membro | `?situacao=&tipo=&perfil=` → **200** `Importacao` (com `itens`) |
| `agencia_desfazer` | `POST /api/agencia/importacoes/{id}/desfazer` | **H** | `{ "version": int }` → **200** `Importacao` (`estado = "desfeita"`) |

## Schemas

### `Estado`
```json
{
  "raizes": { "shared": { "disponivel": true }, "clipes": { "disponivel": true } },
  "ultima": { "id": "uuid", "estado": "concluida", "criadaEm": "…", "criadaPor": { "id": "uuid", "name": "Dono" } },
  "perfis": [ { "slug": "queridinhos", "ultimaImportacaoEm": "…", "arquivosMudaram": true } ],
  "emAndamento": null
}
```
`arquivosMudaram` compara as impressões digitais dos arquivos usados na última importação `concluida` com as
atuais (só leitura dos bytes; nada é montado). Sem raiz disponível, `disponivel = false` e `motivo`.

### `Previa`

Os números do exemplo são ilustrativos.
```json
{
  "previaId": "uuid", "expiraEm": "2026-10-06T15:30:00-03:00",
  "contagens": { "novo": 52, "igual": 39, "diverge": 3, "fora": 47, "aguardandoCota": 0, "naoReconhecido": 0 },
  "bytesNovos": 943718400,
  "arquivosNaoReconhecidos": [ { "arquivo": "shared:perfis/x/fontes.md", "faltou": ["coluna status"] } ],
  "itens": [
    { "n": 17, "tipo": "canal", "perfilSlug": "queridinhos",
      "origem": { "arquivo": "shared:perfis/queridinhos/fontes.md", "trecho": "Fofocalizando", "linha": 20 },
      "situacao": "diverge", "motivo": "direito",
      "atual": { "direito": "parceiro", "titulo": "Fofocalizando" },
      "proposto": { "direito": "sem_acordo", "statusMarkdown": "pendente" },
      "escolhaPadrao": { "usar": "sociman" }, "direitosAceitos": ["sem_acordo"] },
    { "n": 61, "tipo": "clipe", "perfilSlug": "atavernanerd",
      "origem": { "arquivo": "clipes:atavernanerd/2026-09-25/atavernanerd-20260925-4.mp4", "trecho": "atavernanerd-20260925-4" },
      "situacao": "novo", "proposto": { "titulo": "Como o eBay comprou secretamente 49% do Magento em 2010" },
      "bytes": 17825792, "escolhaPadrao": { "marcado": true } }
  ]
}
```
`atual` e `proposto` trazem só os campos comparados; textos longos vêm cortados em 300 caracteres com
`"cortado": true`. Erros: 503 `agencia_pasta_indisponivel`; 413 `agencia_pasta_grande`; 409
`importacao_em_andamento`.

### `Confirmar`
```json
{ "previaId": "uuid",
  "escolhas": [ { "n": 17, "usar": "markdown", "direito": "sem_acordo" },
                { "n": 61, "marcado": false } ] }
```
Só os itens que mudam o padrão precisam vir. Erros: 409 `previa_expirada` (expirou ou já usada); 422
`escolha_invalida` (item sem escolha, `direito` fora dos 4, `usar` em item que não diverge, perfil da
persona não informado quando obrigatório); 409 `importacao_em_andamento`.

### `Importacao` / `ImportacaoResumo`
```json
{
  "id": "uuid", "version": 3, "estado": "concluida",
  "criadaEm": "…", "criadaPor": { "id": "uuid", "name": "Dono" }, "concluidaEm": "…",
  "desfeitaEm": null, "desfeitaPor": null, "erro": null,
  "progresso": { "etapa": "fim", "feitos": 70, "total": 70, "bytes": 943718400 },
  "contagens": { "criado": 52, "atualizado": 3, "mantido": 0, "igual": 39, "fora": 47, "naoGravado": 0 },
  "itens": [ { "n": 17, "tipo": "canal", "perfilSlug": "queridinhos", "origem": { "…": "…" },
               "situacao": "diverge", "escolha": { "usar": "markdown", "direito": "sem_acordo" },
               "resultado": "atualizado", "resultadoMotivo": null,
               "entidade": { "tipo": "canal", "id": "uuid", "version": 4, "titulo": "Fofocalizando" },
               "desfeitoEm": null, "desfazerMotivo": null } ]
}
```
O resumo não traz `itens`. Erros do desfazer: 409 `version_conflict`; 409 `importacao_nao_desfazivel`
(estado diferente de `concluida`).
