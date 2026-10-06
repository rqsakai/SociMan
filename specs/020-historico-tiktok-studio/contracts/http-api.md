# Contrato HTTP: Histórico do TikTok Studio (020)

Prefixos `/api/contas/{contaId}/studio/*` e `/api/studio/*`, `operationId` `studio_*` e respostas em
camelCase (aliases Pydantic). Não há "tiktok" nas rotas nem nos `operationId` (guarda do princípio I). O
contrato tipado sai do OpenAPI (`npm run gen:contract`); este arquivo descreve a forma e as regras.

**Rotas H** (só dono humano, `RequireHumanOwner`): um não humano recebe 403 `somente_humano` e deixa o
evento `publicacao_recusada`; um membro recebe 403 `somente_dono`. As demais rotas usam `RequireUser`
(dono ou membro).

## Rotas

| operationId | Método e rota | Quem | Corpo / resposta |
|---|---|---|---|
| `studio_previa` | `POST /api/contas/{contaId}/studio/previa` | **H** | multipart `arquivos` (de 1 a 2 arquivos `.zip`/`.csv`, ≤ 5 MB no total) → **201** `Previa` |
| `studio_confirmar` | `POST /api/contas/{contaId}/studio/importacoes` | **H** | `{ "previaId": uuid, "confirmoConta": bool }` → **201** `Importacao` (criada), ou **200** `Importacao` com `gravados = 0` quando tudo já estava importado (idempotente) |
| `studio_desfazer` | `POST /api/studio/importacoes/{id}/desfazer` | **H** | `{ "version": int }` → **200** `Importacao` (`estado = "desfeita"`) |
| `studio_importacoes` | `GET /api/contas/{contaId}/studio/importacoes` | dono e membro | → **200** `{ "items": Importacao[] }` (mais recentes primeiro, com as desfeitas) |
| `studio_cobertura` | `GET /api/contas/{contaId}/studio/cobertura` | dono e membro | → **200** `Cobertura` |

## Schemas

### `Previa`
```json
{
  "previaId": "uuid", "expiraEm": "2026-10-02T15:30:00-03:00",
  "conta": { "id": "uuid", "handle": "contateste", "perfil": "Taverna" },
  "arquivos": [
    { "nome": "Overview_2026-09-25_1790891174_contateste.zip", "tipo": "zip",
      "secao": "visao_geral", "handle": "contateste",
      "ignorados": [] },
    { "nome": "Followers_contateste.zip", "tipo": "zip", "secao": "seguidores", "handle": "contateste",
      "ignorados": ["FollowerActivity.csv", "FollowerGender.csv", "FollowerTopTerritories.csv"] }
  ],
  "periodo": { "de": "2026-09-25", "ate": "2026-10-01", "anoOrigem": "nome_zip" },
  "secoes": [
    { "secao": "visao_geral", "jaImportada": null,
      "contagens": { "gravados": 7, "iguais": 0, "divergentes": 0, "coletados": 1,
                     "faltando": [], "ignorados": [] },
      "totais": { "views": 2076, "visitasPerfil": 12, "likes": 127, "comments": 0, "shares": 0 },
      "colunas": { "reconhecidas": ["Date", "Video Views", "Profile Views", "Likes", "Comments", "Shares"],
                   "ausentes": [], "ignoradas": [] },
      "amostra": [ { "dia": "2026-09-25", "views": 118, "visitasPerfil": 0, "likes": 5, "comments": 0,
                     "shares": 0, "situacao": "novo" } ] },
    { "secao": "seguidores", "jaImportada": null, "contagens": { "…": "…" },
      "totais": { "seguidoresInicio": 0, "seguidoresFim": 4, "ganhos": 4 },
      "colunas": { "…": "…" }, "amostra": [ { "dia": "2026-09-25", "seguidores": 0, "seguidoresDif": 0,
                                               "situacao": "novo" } ] }
  ],
  "avisos": [ { "codigo": "diverge_da_coleta", "mensagem": "…", "detalhes": { "diferencaPct": 0.42 } } ],
  "exigeConfirmacaoConta": false,
  "podeConfirmar": true
}
```
- `periodo.anoOrigem`: `nome_zip`, `deduzido` ou `misto` (uma seção de cada jeito).
- `situacao` de cada linha da amostra: `novo`, `igual`, `divergente`, `coletado` ou `ignorado` (hoje).
- `jaImportada` (seção cujo hash é igual ao de uma importação ativa):
  `{ "importacaoId", "em", "por": "Nome do dono" }`. A seção não grava nada.
- `podeConfirmar = false` quando todas as seções têm `jaImportada`. O SPA mostra "já importado" e não
  oferece confirmar. O confirmar continua idempotente.
- Códigos de `avisos`: `diverge_da_coleta`, `dia_incompleto`, `dias_faltando`, `periodo_longo` (mais de
  366 dias), `ano_deduzido`, `colunas_ausentes` e `cabecalho_provisorio` (cabeçalho lido por um sinônimo
  pt-BR ainda não confirmado, R15).
- A amostra traz no máximo 10 linhas por seção (as primeiras 5 e as últimas 5).

### `Importacao`
```json
{
  "id": "uuid", "contaId": "uuid", "serieId": "uuid", "version": 1,
  "estado": "ativa", "secoes": ["visao_geral", "seguidores"],
  "periodoDe": "2026-09-25", "periodoAte": "2026-10-01", "anoOrigem": "nome_zip",
  "contagens": { "visao_geral": { "gravados": 7, "iguais": 0, "divergentes": 0, "coletados": 1,
                                  "faltando": 0, "ignorados": 0 },
                 "seguidores": { "…": "…" } },
  "nomesArquivos": ["Overview_…_contateste.zip", "Followers_contateste.zip"],
  "criadaEm": "…", "criadaPor": { "id": "uuid", "nome": "…" },
  "desfeitaEm": null, "desfeitaPor": null,
  "gravados": 14
}
```
`nomesArquivos` vem `null` numa série anonimizada. `gravados` é o número de linhas desta confirmação
(0 no caso idempotente).

### `Cobertura`
```json
{
  "contaId": "uuid", "hoje": "2026-10-02",
  "coleta": { "primeiroDia": "2026-09-30", "primeiroDiaCoberto": "2026-10-01" },
  "secoes": [
    { "secao": "visao_geral",
      "faixas": [ { "de": "2026-09-25", "ate": "2026-10-01", "fonte": "studio" } ],
      "sobreposicao": [ { "de": "2026-10-01", "ate": "2026-10-01" } ],
      "buracos": [] },
    { "secao": "seguidores", "faixas": [ … ], "sobreposicao": [ … ], "buracos": [] }
  ],
  "importacoesAtivas": 1
}
```
- `faixas`: os dias com dado efetivo do Studio (importações ativas), agrupados em intervalos contínuos.
- `buracos`: dias entre o 1º dia importado e o dia anterior a `primeiroDiaCoberto` sem dado efetivo.
- Uma série sem coleta tem `coleta: null`, e os buracos vão até ontem.

## Mudanças nas rotas da 019 (`/api/analytics/*`, só leitura)

| Schema | Campo novo | Regra |
|---|---|---|
| `Contexto` | `studio: { dias: int, series: int }` | dias distintos do período em que alguma série usou o Studio |
| `Indicador` | `diasStudio: int` | para `views`, `likes`, `engajamento` e `seguidores`; 0 nos demais |
| `ViewsConta` (série diária) | `fonte: "coletado" \| "studio"`, `comparacao: int \| null`, `visitasPerfil: int \| null` | data-model, "Fonte do dia" |
| `DiaCalendario` | `fonte: "coletado" \| "studio" \| "misto"`, `contasStudio: int` | `misto` quando há contas de fontes diferentes no dia |
| tabela de contas e perfis (`analytics_contas`) | `diasStudio` em cada `Indicador` | idem |

Os campos são **aditivos**: um cliente que os ignora vê os mesmos números de antes quando não há
importação (regressão zero, R6).

## Mudança na exportação da 016

`GET /api/metricas/export` (só dono) devolve o mesmo ZIP, mais `studio_dias.csv` (ou `.jsonl`) e as linhas
novas em `dicionario.csv` (`versao = 2`). Colunas em data-model e research R10.

## Erros

`ErrorEnvelope` padrão (`code`, `message`, `details`):

| Código | Status | Quando | `details` |
|---|---|---|---|
| `arquivo_grande` | 413 | envio acima de 5 MB | `{ limiteBytes }` |
| `studio_arquivos` | 400 | 0 ou mais de 2 arquivos, ou a mesma seção 2 vezes | `{ recebidos }` |
| `studio_zip_inseguro` | 400 | R2 (entradas, tamanho expandido, razão, caminho, link, cifrado, aninhado, método) | `{ arquivo, motivo }` |
| `studio_secao_nao_importada` | 400 | Conteúdo, Espectadores, demografia, XLSX, "Baixar seus dados" | `{ arquivo, secaoReconhecida? , orientacao }` |
| `studio_formato` | 400 | cabeçalho não reconhecido, coluna obrigatória faltando, vazio, codificação | `{ arquivo, esperadas, encontradas }` |
| `studio_invalido` | 400 | problemas por linha (FR-006) | `{ problemas: [{ arquivo, linha, coluna, valor, motivo }] (até 50), total }` |
| `studio_datas` | 400 | ordem, ano impossível, nome do ZIP que não bate com as datas | `{ arquivo, motivo }` |
| `studio_conta_diferente` | 400 | o @ do ZIP é diferente da conta, ou os ZIPs têm @ diferentes | `{ arquivo, handleArquivo, handleConta }` |
| `serie_indisponivel` | 409 | a conta não é TikTok ou não tem série viva | `{ contaId }` |
| `confirmar_conta` | 400 | `exigeConfirmacaoConta` e `confirmoConta != true` | — |
| `previa_indisponivel` | 410 | prévia expirada, já usada ou de outro usuário ou conta | — |
| `previa_desatualizada` | 409 | a base da série mudou (outra importação ou desfazer) | — |
| `ja_desfeita` | 409 | desfazer uma importação já desfeita | — |
| `version_conflict` | 409 | `version` diferente no desfazer | `{ atual }` |
| `somente_humano` / `somente_dono` | 403 | rotas H | — |
| `not_found` | 404 | conta ou importação inexistente | — |
