# Contrato HTTP: Público (022)

Este contrato **amplia** o da 020 ([../../020-historico-tiktok-studio/contracts/http-api.md](../../020-historico-tiktok-studio/contracts/http-api.md)):
- as respostas continuam em camelCase;
- não há "tiktok" nas rotas nem nos `operationId`;
- o contrato tipado sai do OpenAPI (`npm run gen:contract`);
- **todas as mudanças nos schemas que já existem são aditivas**: um campo novo, ou um `Literal` com mais
  valores.

## Rotas

| operationId | Método e rota | Quem | Mudança |
|---|---|---|---|
| `studio_previa` | `POST /api/contas/{contaId}/studio/previa` | **H** | multipart `arquivos`: de **1 a 3** arquivos `.zip`, `.csv` ou **`.xlsx`** (≤ 5 MB no total); resposta `Previa` com `publico[]` |
| `studio_confirmar` | `POST /api/contas/{contaId}/studio/importacoes` | **H** | sem mudança no corpo; `Importacao` com os campos novos |
| `studio_desfazer` | `POST /api/studio/importacoes/{id}/desfazer` | **H** | sem mudança (desfaz todas as seções) |
| `studio_importacoes` | `GET /api/contas/{contaId}/studio/importacoes` | dono e membro | `Importacao` com os campos novos |
| `studio_cobertura` | `GET /api/contas/{contaId}/studio/cobertura` | dono e membro | `Cobertura` com `publico` |
| **`analytics_publico`** (nova) | `GET /api/analytics/publico` | dono e membro | os parâmetros do analytics da 019 (período, perfil, conta, rede) → **200** `PublicoOut` |
| `analytics_quando_postar` | `GET /api/analytics/quando-postar` | dono e membro | `QuandoPostarOut.atividadeSeguidores` (aditivo) |

As rotas H continuam como na 020: um não humano recebe 403 `somente_humano` e deixa o evento
`publicacao_recusada`; um membro recebe 403 `somente_dono`. No MCP, `analytics_publico` é uma tool de
**leitura**, e as 3 rotas H continuam em `PROIBIDAS`.

## Schemas

### `Previa` (aditivo)
```json
{
  "…": "campos da 020 (previaId, expiraEm, conta, arquivos, periodo, secoes, avisos…)",
  "arquivos": [
    { "nome": "Followers_contateste.zip", "tipo": "zip", "secao": "seguidores", "handle": "contateste",
      "ignorados": [] },
    { "nome": "Viewers_contateste.zip", "tipo": "zip", "secao": "espectadores", "handle": "contateste",
      "ignorados": [] }
  ],
  "publico": [
    { "secao": "genero", "vazia": false, "jaImportada": null,
      "dataFoto": "2026-10-02", "dataFotoOrigem": "historico", "situacao": "novo",
      "itens": [ { "rotulo": "feminino", "rotuloExibicao": "Feminino", "pct": 61.0 },
                 { "rotulo": "masculino", "rotuloExibicao": "Masculino", "pct": 37.5 },
                 { "rotulo": "outro", "rotuloExibicao": "Outro", "pct": 1.5 } ],
      "contagens": { "gravados": 3, "iguais": 0, "divergentes": 0, "semDado": 0 } },
    { "secao": "territorios", "vazia": true, "mensagem": "Ainda sem dados de público: a TikTok libera esses dados quando a conta tem mais seguidores (cerca de 100)." },
    { "secao": "atividade", "vazia": false, "jaImportada": null,
      "periodo": { "de": "2026-09-25", "ate": "2026-10-01", "anoOrigem": "deduzido" },
      "pico": { "dia": "2026-09-30", "hora": 20, "ativos": 41 },
      "contagens": { "gravados": 168, "iguais": 0, "divergentes": 0, "ignorados": 0, "semDado": 0 } },
    { "secao": "espectadores", "vazia": false, "jaImportada": null,
      "periodo": { "de": "2026-09-25", "ate": "2026-10-01", "anoOrigem": "deduzido" },
      "totais": { "novos": 913, "mediaTotal": 159.0, "mediaRecorrentes": 5.9 },
      "contagens": { "gravados": 7, "iguais": 0, "divergentes": 0, "faltando": [], "ignorados": [],
                     "semDado": 1 },
      "amostra": [ { "dia": "2026-09-25", "total": null, "novos": 0, "recorrentes": 0, "situacao": "novo" } ] }
  ]
}
```
- **`arquivos[].secao`:** passa a aceitar também `espectadores`. Num ZIP de Seguidores, `secao` continua
  `seguidores`, e as seções de público lidas dele aparecem em `publico[]`. O `ignorados` deixa de listar os 3
  CSVs de público.
- **`publico[].secao`:** `genero`, `territorios`, `atividade` ou `espectadores`. Com `vazia: true`, vem só
  `secao`, `vazia` e `mensagem`.
- **`situacao`:**
  - nas fotos, `novo`, `igual` ou `divergente`, contra a foto efetiva da mesma data;
  - nas linhas de atividade e espectadores, a da 020, sem `coletado`.
- **`periodo`** (raiz): passa a cobrir também os dias e as datas de foto de público.
- **`podeConfirmar`:** verdadeiro se alguma seção (da 020 ou de público) é nova e tem linhas.
- **Avisos novos:**
  - `data_foto_importacao`: a foto usa o dia da importação;
  - `espectadores_soma`: dias com total ≠ novos + recorrentes (`detalhes.dias`);
  - `sem_dado`: valores `undefined` por seção (`detalhes.secao`, `detalhes.quantidade`);
  - `secao_vazia`.

  `dia_incompleto`, `dias_faltando`, `ano_deduzido` e `cabecalho_provisorio` valem também para as seções
  diárias de público.
- **Amostra:** até 10 linhas por seção diária. Na atividade, a amostra é o `pico` (não vem `amostra`).

### `Importacao` (aditivo)
```json
{
  "…": "campos da 020",
  "secoes": ["seguidores", "genero", "atividade", "espectadores"],
  "dataFoto": "2026-10-02", "dataFotoOrigem": "historico",
  "secoesVazias": ["territorios"],
  "contagens": { "seguidores": { "…": "…" },
                 "genero": { "gravados": 3, "iguais": 0, "divergentes": 0 },
                 "atividade": { "gravados": 168, "iguais": 0, "divergentes": 0, "ignorados": 0, "semDado": 0 },
                 "espectadores": { "gravados": 7, "iguais": 0, "divergentes": 0, "faltando": 0, "ignorados": 0, "semDado": 1 } },
  "gravados": 185
}
```
`gravados` é o número de **linhas** inseridas em todas as tabelas por esta confirmação. No
`ContagensImportacao`, entra `semDado` (padrão 0), e `coletados` e `faltando` passam a ter padrão 0 (as
seções de público não têm coleta da API). A mudança é aditiva.

### `Cobertura` (aditivo)
```json
{
  "…": "campos da 020",
  "publico": {
    "fotos": [ { "tipo": "genero", "dataFoto": "2026-10-02", "importacaoId": "uuid" } ],
    "atividade":    { "faixas": [ { "de": "2026-09-25", "ate": "2026-10-01" } ], "buracos": [] },
    "espectadores": { "faixas": [ { "de": "2026-09-25", "ate": "2026-10-01" } ], "buracos": [] },
    "vazias": [ { "secao": "territorios", "em": "2026-10-02T10:00:00-03:00" } ]
  }
}
```
- `buracos`: os dias sem dado efetivo entre o primeiro e o último dia da seção.
- `vazias`: a regra "veio vazia" (data-model).

### `PublicoOut` (novo)
```json
{
  "contexto": { "…": "Contexto da 019" },
  "contas": [
    { "conta": { "serieId": "uuid", "contaId": "uuid", "rotulo": "@contateste", "ordem": 0 },
      "genero": {
        "dataFoto": "2026-10-02", "anteriorAoPeriodo": true, "importacaoId": "uuid",
        "dataFotoComparacao": "2026-09-15", "seguidoresNaData": 128,
        "itens": [ { "rotulo": "feminino", "rotuloExibicao": "Feminino", "pct": 61.0,
                     "pctComparacao": 58.0, "difPp": 3.0, "marca": null } ],
        "outrosPct": null },
      "territorios": null,
      "atividade": {
        "celulas": [ { "dia": 0, "hora": 20, "valor": 38.5, "n": 2, "amostraPequena": false } ],
        "diasComDado": 7, "ultimoDiaComDado": "2026-10-01" },
      "espectadores": {
        "serie": [ { "dia": "2026-09-25", "total": null, "novos": 0, "recorrentes": 0 } ],
        "novos": { "valor": 913, "anterior": null, "variacaoPct": null, "n": 7 },
        "mediaTotal": { "valor": 159.0, "anterior": null, "variacaoPct": null, "n": 6 },
        "mediaRecorrentes": { "valor": 5.9, "anterior": null, "variacaoPct": null, "n": 7 },
        "diasSemDado": 1 },
      "motivos": { "genero": null, "territorios": "veio_vazia", "atividade": null, "espectadores": null } }
  ]
}
```
- **`genero`/`territorios`:** `null` quando não há foto até o fim do período; o motivo vai em `motivos`.
  `marca` é `"novo"` (o rótulo não estava na foto de comparação), `"saiu"` (estava e não está; vem com
  `pct = null`) ou `null`.
- **`atividade.celulas`:** sempre 168 (7 × 24; `dia` 0 = segunda, como o `CelulaMapa` da 019). `valor`
  vem `null` quando `n = 0`.
- **`motivos`:** `sem_importacao`, `veio_vazia`, `sem_dado_no_periodo` ou `null` (o card tem dado).
- **Conta anonimizada:** o `rotulo` vem como "Conta anônima N" (019), e `contaId` vem `null`.

### `QuandoPostarOut.atividadeSeguidores` (aditivo)
```json
{ "contas": [ { "conta": { "…": "…" }, "atividade": { "…": "como em PublicoOut" }, "motivo": null } ] }
```

## Exportação (016/020, só dono)

O ZIP de `GET /api/metricas/export` ganha `studio_distribuicoes.csv`, `studio_atividade.csv` e
`studio_espectadores.csv` (ou `.jsonl`), só das importações ativas, com `importacao_id` e `efetivo`. O
`dicionario.csv` vai para a `versao = 3`.

## Erros (novos ou ampliados)

| Código | Status | Quando | `details` |
|---|---|---|---|
| `studio_arquivos` | 400 | 0 ou mais de **3** arquivos, ou a mesma seção 2 vezes | `{ recebidos }` |
| `studio_sem_dados` (novo) | 400 | todas as seções do envio vieram só com o cabeçalho (R5) | `{ secoes: [...] }` |
| `studio_planilha` (novo) | 400 | XLSX com macro, fórmula, link externo, protegido, DOCTYPE/ENTITY, sem a aba `Viewers` (com mais de uma aba), `.xls` antigo ou cifrado | `{ arquivo, motivo, celula? }` |
| `studio_zip_inseguro` | 400 | os limites da 020, aplicados também ao XLSX por dentro (entradas, tamanho, razão, caminho, link, cifrado, aninhado de 2º nível) | `{ arquivo, motivo }` |
| `studio_secao_nao_importada` | 400 | **só** Conteúdo e "Baixar seus dados" (Espectadores, demografia e XLSX deixam de cair aqui) | `{ arquivo, secaoReconhecida?, orientacao }` |
| `studio_invalido` | 400 | os problemas de FR-008 por linha ou célula | `{ problemas: [{ arquivo, linha, coluna, valor, motivo, celula? }], total }` |

Os demais códigos da 020 não mudam.
