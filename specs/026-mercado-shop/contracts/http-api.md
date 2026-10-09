# Contrato HTTP: 026-mercado-shop

Rotas da API do SociMan (FastAPI). O OpenAPI gerado é a fonte única (princípio IV): depois de
implementar, `npm run gen:contract` atualiza `packages/contract` (inclusive `mcp-tools.json`), e o
`check:contract` acusa divergência. JSON em camelCase (`CamelModel`). **Nenhuma rota nem `operationId`
contém "tiktok"** (guarda do princípio I e FR-057): a rede é um valor (`rede: "tiktok"`), nunca um nome.
Erros no envelope `{"error": {"code", "message", "details?"}}`, mensagens em pt-BR.

Famílias: **`coleta_*`** (o coletor e a gestão da coleta) e **`mercado_*`** (leitura do lago e interesse).

## Permissões e atores

| Sigla | Dependência | Quem passa |
|---|---|---|
| **C** | `RequireColetor` (`auth/deps.py`) | só `Actor(kind="coletor")`, isto é, Bearer `scol_…` válido que passou pelo portão; qualquer outro ator → 401 `unauthorized` |
| **U** | `RequireUser` | dono, membro e cliente MCP com escopo `leitura` (tool) |
| **Hu** | `RequireHuman` | dono ou membro humano; MCP, `coletor` e `system:*` → 403 `somente_humano` + evento `publicacao_recusada` |
| **HO** | `RequireHumanOwner` | só dono humano; membro → 403 `forbidden`; outro ator → 403 `somente_humano` + evento |

O token `scol_` **só vale em `/api/coleta/*` marcadas C**. O portão `coleta/portao.py` é dependência
global do app (molde `mcp/portao.py`): qualquer Bearer `scol_` passa por ele, em qualquer rota, nesta
ordem (FR-025):

1. credencial inválida (formato, `token_id` desconhecido, hash não confere) → 401 `unauthorized`;
2. interruptor: `COLETA_HABILITADA` falso **ou** `coleta_config.habilitada` falso → `GET /api/coleta/fila`
   responde 200 com `habilitada: false` e `tarefas: []`; as demais rotas C respondem 503 `coleta_desligada`
   ("A coleta está desligada no servidor"); gestão e leitura (U/HO) não passam pelo portão;
3. `revogado` ou `expira_em` vencido → 401 `unauthorized`; `suspenso` → 403 `coleta_suspensa`;
4. cabeçalho `Origin` presente (veio de navegador) → 403 `escopo_coleta`;
5. rota fora de `/api/coleta/*` marcada C → 403 `escopo_coleta` ("Este token só vale para o serviço do
   coletor");
6. `X-Sociman-Coleta-Protocolo` ausente ou ≠ `1` → 426 `protocolo_coleta` (`details.esperado = 1`,
   mensagem "Atualize o sociman-coletor: o servidor fala o protocolo 1");
7. limite no Redis (`limite_por_minuto` do cliente) → 429 `coleta_limite` (`Retry-After`); Redis fora →
   503 `coleta_indisponivel`.

Toda recusa do portão grava `security_events` (`coleta_recusada`, `actor_kind = "coletor"`, `details =
{motivo, tokenId, rota}`), sem o token. Toda passagem atualiza `coleta_clientes.ultimo_contato_em`,
`versao_coletor` (cabeçalho `X-Sociman-Coletor-Versao`) e `chrome_versao` (`X-Sociman-Chrome-Versao`).

## Rotas do coletor (**C**; `X-Sociman-Coleta-Protocolo: 1` obrigatório)

### `GET /api/coleta/fila?limite=40` · `coleta_fila` · **C**
Entrega e **reserva** (lease de `FILA_LEASE_MIN = 30` min, estado `reservada`, `cliente_id` = o cliente)
até `min(limite, coleta_config.itens_por_coleta)` tarefas `pendente` do dia local, em ordem `(nivel,
prioridade)`, só do `mercado` do cliente. **200**:
```json
{
  "habilitada": true, "desligadaNoServidor": false,
  "pausadaAte": null, "continuarEm": null,
  "agoraServidor": "2026-10-09T11:02:10-03:00", "dataLocal": "2026-10-09", "fuso": "America/Sao_Paulo",
  "janela": { "inicio": 8, "fim": 23, "dentro": true },
  "limites": { "paginasDia": 300, "imagensDia": 1500, "imagensPorProduto": 9,
               "itensPorColeta": 40, "pausaMinS": 5, "pausaMaxS": 40, "leaseMin": 30 },
  "orcamento": { "paginasHoje": 112, "paginasRestantes": 188, "imagensHoje": 640, "imagensRestantes": 860 },
  "tarefas": [
    { "tarefaId": "uuid", "tipo": "produto", "rede": "tiktok", "mercado": "BR", "fonte": "ambas",
      "chave": "produto:7291…", "url": "https://…/product/7291…", "nivel": 1, "prioridade": 3,
      "turno": "manha", "reservadaAte": "2026-10-09T11:32:10-03:00",
      "extra": { "baixarImagens": true, "imagensMax": 9 } },
    { "tarefaId": "uuid", "tipo": "ranking", "fonte": "affiliate", "chave": "ranking:cat123:mais_vendidos:7d",
      "url": "https://…", "nivel": 3, "prioridade": 0, "turno": null, "reservadaAte": "…",
      "extra": { "rankingTipo": "mais_vendidos", "janela": "7d", "categoriaRedeId": "cat123" } },
    { "tarefaId": "uuid", "tipo": "avaliacoes", "fonte": "pagina_publica", "chave": "avaliacoes:7291…:1",
      "url": "https://…", "nivel": 8, "prioridade": 2, "turno": null, "reservadaAte": "…",
      "extra": { "paginas": 2 } }
  ]
}
```
- Com o interruptor desligado, fora da janela, com `pausadaAte` no futuro, orçamento esgotado ou nada a
  coletar: `tarefas: []` e os campos de estado preenchidos (o coletor dorme; o motivo vai no `motivoVazia`:
  `desligada | fora_da_janela | pausada | orcamento | nada_a_coletar | aguardando_continuar`).
- O coletor **só pode abrir a `url` entregue** (FR-023); o servidor confere no item que a URL canônica do
  resultado é a da tarefa (senão `invalido`, `url_divergente`).
- Erros: 503 `coleta_desligada` só se o cliente também não puder saber o estado (Redis fora); 429.

### `POST /api/coleta/coletas` · `coleta_coletas_abrir` · **C**
Abre a rodada. Corpo:
```json
{ "versaoColetor": "0.1.0", "chromeVersao": "131.0.6778.85", "protocolo": 1,
  "limitesLocais": { "paginasDia": 300, "imagensDia": 1500 }, "iniciadaEm": "2026-10-09T11:02:12-03:00" }
```
**201** `Coleta` (estado `ativa`). Erros: 409 `coleta_em_andamento` (já há rodada aberta deste cliente;
`details.coletaId`, `details.batimentoEm`; o 2º coletor com o mesmo token não coleta, Edge); 503
`coleta_desligada`; 409 `risco_nao_aceito` não ocorre aqui (sem aceite o botão nunca liga).

### `POST /api/coleta/coletas/{coleta_id}/itens` · `coleta_itens_enviar` · **C**
Lote de **1 a 50 itens**, corpo ≤ 6 MB na API (o edge aceita 10m nesta `location`). Corpo:
```json
{ "itens": [
  { "tarefaId": "uuid", "status": "ok", "coletadoEm": "2026-10-09T11:05:40-03:00", "duracaoMs": 18340,
    "esquemaVersao": "tiktok_shop/1", "fonte": "pagina_publica",
    "campos": { "...payload normalizado do tipo (contracts/coletor.md)..." },
    "bruto": "H4sIAAAAAAAA/…",          // gzip + base64 do JSON interceptado, já podado; ≤ 2 MB descomprimido
    "imagens": ["<sha256>", "<sha256>"],  // referências; os arquivos vão em …/imagens
    "reprocessadoDe": null },
  { "tarefaId": "uuid", "status": "erro", "coletadoEm": "…", "duracaoMs": 4021,
    "erroCodigo": "pagina_sem_campos", "campos": null, "bruto": null }
] }
```
`status` do item enviado: `ok | erro | captcha` (`captcha` fecha o item e dispara o mesmo efeito do evento
`captcha`). Para cada item o servidor, numa **transação por item** (SAVEPOINT; um inválido não derruba o
lote, FR-028):
1. confere `tarefaId` (existe, `reservada` por este cliente, não vencida → senão `invalido`
   `tarefa_desconhecida | tarefa_de_outro_cliente | reserva_vencida`);
2. calcula `dataLocal` e `turno` pelo `coletadoEm` no fuso do mercado (FR-027);
3. valida e normaliza pelo adaptador `fontes/tiktok_shop.py` (`esquemaVersao` desconhecido → `invalido`
   `esquema_desconhecido`); URL canônica ≠ `url` da tarefa → `invalido` `url_divergente`;
4. **poda** o bruto com a lista fechada de chaves pessoais e recusa se ainda houver (`invalido`
   `bruto_pessoal`, FR-029); bruto > 2 MB → `invalido` `bruto_grande`;
5. grava `INSERT … ON CONFLICT DO NOTHING`: ficha (nova versão só se `hash_conteudo` mudou), foto(s) por
   fonte, vínculos de imagem (só para shas já recebidos em `…/imagens`; os demais ficam pendentes),
   itens de ranking, avaliações, vídeos, loja e categorias conforme o tipo; `0 linhas` em tudo →
   `repetido`;
6. grava o bruto em `sociman-mercado` (`bruto/<dataLocal>/<coletaId>/<tarefaId>.json.gz`); HD indisponível
   → grava a parte numérica e marca `brutoPendente: true` (FR-030; nunca falha o item por isso);
7. insere `mercado_coleta_itens`, fecha a tarefa (`recebida` ou `pendente`/`falhou` nas tentativas) e
   atualiza o estado técnico do produto e os contadores da rodada (e o `batimento_em`).

**200**:
```json
{ "coletaId": "uuid", "resultados": [
  { "tarefaId": "uuid", "status": "gravado", "dataLocal": "2026-10-09", "turno": "manha",
    "imagensPendentes": ["<sha256>"], "brutoPendente": false, "fichaNova": true },
  { "tarefaId": "uuid", "status": "repetido", "dataLocal": "2026-10-09", "turno": "manha" },
  { "tarefaId": "uuid", "status": "invalido", "erroCodigo": "bruto_pessoal", "erroCampo": "bruto.reviews[0].user_name" },
  { "tarefaId": "uuid", "status": "erro", "erroCodigo": "pagina_sem_campos", "tentativas": 1, "voltaParaFila": true }
 ],
 "orcamento": { "paginasHoje": 115, "paginasRestantes": 185, "imagensHoje": 640, "imagensRestantes": 860 },
 "pausadaAte": null, "parar": false }
```
`parar: true` quando o interruptor desligou, a rodada foi abortada ou o orçamento acabou: o coletor fecha a
rodada depois deste lote. Erros do lote inteiro: 404 `coleta_nao_encontrada`; 409 `coleta_fechada`
(rodada em estado final); 400 `entrada_invalida` (lote vazio ou > 50; `details.field`); 413
`lote_grande` (> 6 MB).

### `POST /api/coleta/coletas/{coleta_id}/imagens` · `coleta_imagens_enviar` · **C**
`multipart/form-data`: até **10 arquivos** (`arquivos`), cada um ≤ 5 MB, mais o campo `manifesto` (JSON:
`[{sha256, tarefaId, origem: "produto"|"avaliacao", contentType}]`). O edge tem `location` própria com
`client_max_body_size 60m` e sem buffering. Para cada arquivo: sha256 recalculado no servidor (≠ do
manifesto → `recusada` `sha_divergente`), validado pelo conteúdo (`imaging.py`; não é imagem →
`imagem_invalida`), gravado em `imagens` sob `mercado/<sha[:2]>/<sha>.<ext>` e em `mercado_imagens`
(`ON CONFLICT DO NOTHING` → `repetida`); vínculos pendentes (`mercado_produto_imagens`,
`mercado_avaliacoes.imagens_sha`) são materializados. **200**:
```json
{ "aceitas": ["<sha256>"], "repetidas": ["<sha256>"],
  "recusadas": [{ "sha256": "<sha256>", "motivo": "imagem_invalida" }],
  "orcamento": { "imagensHoje": 652, "imagensRestantes": 848 } }
```
Erros: 404 `coleta_nao_encontrada`; 409 `coleta_fechada`; 413 `arquivo_grande` (> 5 MB em um arquivo) ou
`lote_grande` (> 10 arquivos); 503 `storage_unavailable` / 507 `storage_full` (HD, `datadir.py`; o
coletor guarda os arquivos e tenta no próximo batimento). Com `imagensRestantes = 0`, o servidor responde
`recusadas` com motivo `orcamento` e o coletor para de baixar (produto fica `imagens_pendentes`).

### `POST /api/coleta/coletas/{coleta_id}/batimento` · `coleta_batimento` · **C**
A cada 60 s (FR-023). Corpo:
```json
{ "estado": "ativa", "tarefaAtualId": "uuid", "paginasHoje": 115, "imagensHoje": 652,
  "proximaAcaoEm": "2026-10-09T11:07:02-03:00", "memoriaMb": 512 }
```
**200** `{ "parar": false, "pausadaAte": null, "continuarEm": null, "limites": {…}, "orcamento": {…} }`.
É aqui que o coletor pausado descobre o clique "Continuar" (`continuarEm` preenchido) e que a rodada
`pausada_*` foi encerrada por `CAPTCHA_ESPERA_MAX_H` (`parar: true`, `motivo: "pausa_vencida"`). Erros:
404, 409 `coleta_fechada`.

### `POST /api/coleta/coletas/{coleta_id}/fim` · `coleta_coletas_fechar` · **C**
```json
{ "motivo": "fila_vazia", "terminadaEm": "…", "paginas": 38, "imagens": 212,
  "porTipo": { "produto": 30, "ranking": 5, "avaliacoes": 3 } }
```
`motivo`: `fila_vazia | orcamento | fora_da_janela | parar_local | servico_parado | erro_interno |
pausa_vencida`. **200** `Coleta` (`encerrada`, ou `interrompida` quando o motivo é `parar_local` ou
`servico_parado`). As tarefas ainda `reservada` voltam a `pendente`. 409 `coleta_fechada` se já estava
fechada (idempotente: devolve a rodada).

### `POST /api/coleta/eventos` · `coleta_eventos_enviar` · **C**
```json
{ "tipo": "captcha", "coletaId": "uuid", "tarefaId": "uuid", "ocorreuEm": "…",
  "detalhe": { "codigoHttp": null, "contagem": 1, "urlSemParametros": "https://…/product/7291…", "tipoTarefa": "produto" } }
```
`tipo`: `captcha | login_perdido | bloqueio_suspeito | layout_mudou | parar_local | retomou | iniciado |
parado`. **201** `{ "eventoId": 123, "coleta": Coleta|null, "pausadaAte": "…"|null, "notificado": true }`.
Efeitos (data-model, `coleta_eventos`): muda o estado da rodada, grava `coleta_config.pausada_ate` nos
recuos de 24 h e notifica os donos (uma vez por tipo por dia). `detalhe` com chave da lista de poda
(`nome`, `nickname`, `avatar`, `bio`, `cookie`, `token`, `email`, `telefone`, URL com `?`) → 400
`bruto_pessoal`. Erros: 404 `coleta_nao_encontrada` (quando `coletaId` vem e não existe).

### `GET /api/coleta/coletas/{coleta_id}/bruto/{tarefa_id}` · `coleta_bruto_link` · **C**
Para o `reprocessar --desde` do coletor (FR-012). **200** `{ "link": { "url": "/api/midia/<token>",
"expiresAt": "…" }, "bytes": 48213, "esquemaVersao": "tiktok_shop/1", "dataLocal": "…", "turno": "…" }`
(`MidiaKind "mercado_bruto"`, com validade de 1 h, `Content-Encoding: gzip`). Erros: 404
`bruto_nao_encontrado` (item sem `bruto_ref`: "bruto pendente"); 503 `hd_indisponivel`. O reenvio do bruto
renormalizado volta por `…/itens` com `reprocessadoDe` e só **insere** o que faltava (ficha nova se o
conteúdo mudou; vínculos de imagem; fotos de outra fonte que o parser antigo não lia); fotos existentes
respondem `repetido`. O reenvio vai para a **rodada original, já fechada**: `…/itens` aceita a rodada
fechada quando **todos** os itens do lote trazem `reprocessadoDe` (senão 409 `coleta_fechada`), e a
tarefa já `recebida` não responde "repetido" de saída, é regravada de forma idempotente. Para listar
o período, o token do coletor pode chamar `coleta_coletas_listar` e `coleta_coletas_detalhe`
(rotas **U** que também aceitam o ator `coletor`, restrito às **próprias** rodadas; a de outro
cliente é 404). Implementado em 2026-10-09, a pedido da US2.

## Gestão da coleta (**HO**: só dono humano)

### Clientes (`/api/coleta/clientes`)
| operationId | Rota | Corpo | Resposta |
|---|---|---|---|
| `coleta_clientes_listar` | `GET /api/coleta/clientes` | — | `{ itens: ColetaCliente[] }` (sem hash; só `tokenId` como prefixo) |
| `coleta_clientes_criar` | `POST /api/coleta/clientes` | `{ nome, descricao?, mercado: "BR", rede?: "tiktok", expiraEm?, limitePorMinuto? }` | **201** `{ cliente: ColetaCliente, token: "scol_…" }` com `Cache-Control: no-store`; o token **só aparece aqui** |
| `coleta_clientes_detalhe` | `GET …/{cliente_id}` | — | `ColetaCliente` |
| `coleta_clientes_editar` | `PATCH …/{cliente_id}` | `{ nome?, descricao?, expiraEm?, limitePorMinuto?, version }` | `ColetaCliente` |
| `coleta_clientes_rotacionar` | `POST …/{cliente_id}/rotacionar` | `{ version }` | `{ cliente, token }` + `no-store` (novo `tokenId`; o antigo deixa de valer na hora e as rodadas abertas dele são `interrompida`) |
| `coleta_clientes_suspender` | `POST …/{cliente_id}/suspender` | `{ version }` | `ColetaCliente` (`suspenso`; a rodada aberta vira `interrompida`) |
| `coleta_clientes_reativar` | `POST …/{cliente_id}/reativar` | `{ version }` | `ColetaCliente` (`ativo`) |
| `coleta_clientes_revogar` | `POST …/{cliente_id}/revogar` | `{ version }` | `ColetaCliente` (`revogado`, **final**; 409 `cliente_revogado` em qualquer ação posterior) |
| `coleta_clientes_versions` | `GET …/{cliente_id}/versions` | — | `VersionsList` padrão (sem hash; `tokenId` mostra a rotação) |

Erros: 400 `entrada_invalida`; 409 `nome_em_uso`; 409 `version_conflict`; 409 `cliente_revogado`.
Não existe revert de cliente (molde da 009).

### Configuração (`/api/coleta/config`)
| operationId | Rota | Corpo | Resposta |
|---|---|---|---|
| `coleta_config_get` | `GET /api/coleta/config` | — | `ColetaConfig` + `servidorHabilitado` (= `COLETA_HABILITADO` do `.env`) e `textoRisco` (o resumo e o link para `docs/decisoes/coleta-mercado.md`, FR-034). **HO**; o membro usa `GET /api/coleta/estado` |
| `coleta_config_put` | `PUT /api/coleta/config` | `{ habilitada, janelaInicio, janelaFim, paginasDia, imagensDia, imagensPorProduto, itensPorColeta, pausaMinS, pausaMaxS, version }` | `ColetaConfig`. `habilitada: true` sem aceite → **409 `risco_nao_aceito`** ("Aceite de risco pendente: leia o aviso e confirme antes de ligar"); ligar com `servidorHabilitado: false` é aceito e a tela mostra "desligada no servidor" |
| `coleta_config_aceitar_risco` | `POST /api/coleta/config/aceitar-risco` | `{ textoVersao: "2026-10-08", confirmo: true, version }` | `ColetaConfig` (`riscoAceitoEm`, `riscoAceitoPor`); grava versão e `security_events.coleta_aceite_risco`. Aceitar de novo renova a data (histórico) |
| `coleta_config_pausar` | `POST /api/coleta/config/pausar` | `{ horas: 1..168, version }` | `ColetaConfig` (`pausadaAte`); a rodada aberta recebe `parar: true` no próximo batimento |
| `coleta_config_continuar` | `POST /api/coleta/config/continuar` | `{ version }` | `ColetaConfig` (`continuarEm = agora`); só faz sentido com rodada `pausada_*` (senão 409 `nada_a_continuar`); o coletor retoma em `continuarEm + CAPTCHA_ESFRIAR_MIN` (FR-018) |
| `coleta_config_versions` | `GET /api/coleta/config/versions` | — | `VersionsList` |
| `coleta_config_revert` | `POST /api/coleta/config/revert` | `{ toVersion, version }` | `ColetaConfig`; reverter para uma versão `habilitada` sem aceite → 409 `risco_nao_aceito` |

### Leitura da coleta (**U**: dono e membro; tool MCP só `coleta_estado`)
| operationId | Rota | Resposta |
|---|---|---|
| `coleta_estado` | `GET /api/coleta/estado` | `EstadoColeta` (abaixo): o que o membro vê e o bloco "Estado da coleta" do cockpit |
| `coleta_coletas_listar` | `GET /api/coleta/coletas?estado=&de=&ate=&limite=&cursor=` | `{ itens: ColetaResumo[], proximo }` (cursor `(iniciada_em desc, id)`, ≤ 50) |
| `coleta_coletas_detalhe` | `GET /api/coleta/coletas/{coleta_id}` | `Coleta` + `itens: ColetaItem[]` (paginados, `?itensLimite=200`) + `eventos: ColetaEvento[]` |
| `coleta_eventos_listar` | `GET /api/coleta/eventos?tipo=&de=&ate=&limite=` | `{ itens: ColetaEvento[], proximo }` |
| `coleta_fila_hoje` | `GET /api/coleta/fila/hoje?estado=&tipo=&perfilId=` | `{ itens: TarefaFila[], porNivel: {...}, porEstado: {...} }` (a fila do dia, para a tela; `perfilId` aqui é o operacional da tarefa) |

```text
EstadoColeta {
  servidorHabilitado: bool, habilitada: bool, riscoAceito: bool,
  situacao: "desligada_no_servidor"|"desligada"|"aceite_pendente"|"pausada"|"aguardando_continuar"|"fora_da_janela"|"ociosa"|"coletando"|"pausada_captcha"|"pausada_login"|"sem_cliente"|"parada",
  pausadaAte, continuarEm, janela: {inicio, fim, dentro}, dataLocal, fuso,
  orcamento: {paginasHoje, paginasRestantes, imagensHoje, imagensRestantes},
  hoje: {tarefas, pendentes, recebidas, falhadas, expiradas, gravados, repetidos, invalidos},
  clientes: [{id, nome, tokenId, situacao, mercado, ultimoContatoEm, versaoColetor, chromeVersao}],
  rodadaAtual: ColetaResumo | null, ultimoResultadoEm: datetime|null,
  eventosRecentes: ColetaEvento[] (10)
}
```
`parada` = coleta ligada e sem item `gravado` há `COLETA_PARADA_H = 48` (FR-041).

## Leitura do mercado (**U**: dono, membro e tools MCP de leitura)

### Filtro comum (`mercado/filtros.py`; FR-043)
| Parâmetro | Regra |
|---|---|
| `de`, `ate` | datas no fuso do mercado; padrão `hoje − 29 … hoje` (`PERIODO_PADRAO_DIAS = 30`); até `PERIODO_MAX_DIAS = 400` → 400 `periodo_invalido`; o período anterior tem a mesma duração e termina na véspera de `de` |
| `perfilId` | **só restringe**: produtos com interesse do perfil (ativo ou pausado) ou com `categoria_id` nas categorias do perfil; perfil inexistente → 404 |
| `mercado` | padrão `BR`; `^[A-Z]{2}$` |
| `rede` | `platform`; padrão todas |
| `categoriaId` | a categoria e as filhas (pelo `caminho`) |
| `lojaId` | |
| `origem` | `mercado_interesse_origem` (repetível) |
| `soAcompanhados` | `true` = só produtos com interesse ativo (de qualquer perfil, ou do `perfilId`) |
| `q` | busca em `titulo_atual` (tsquery `portuguese`, prefixo) e `rede_produto_id` exato |
| `ordenar` | `vendasPeriodo` (padrão, desc), `gmvPeriodo`, `crescimento`, `vendasTotais`, `gmvTotal`, `preco`, `comissaoBp`, `comissaoPorVenda`, `retornoAfiliado`, `nCriadores`, `primeiraVezEm`, `ultimaFotoEm`, `titulo`; sufixo `:asc`; nulos por último |
| `limite`, `cursor` | ≤ 100; cursor opaco `(ordenar, id)` |

### `GET /api/mercado/produtos` · `mercado_produtos_listar` · **U**
**200** `{ itens: CartaoProdutoOut[], proximo: string|null, total: int, contexto: ContextoMercado }`.
```text
Numero { valor: number|null, estimado: bool, motivos: string[], amostraPequena: bool, nFotos: int,
         min?: number|null, max?: number|null }      # motivos: "estimado", "incerteza", "inconsistente",
                                                      #   "grosseiro", "cupons_nao_descontados", "sem_dado_afiliado",
                                                      #   "fonte_affiliate", "fonte_pagina_publica", "interpolado"
CartaoProdutoOut {
  id, rede, mercado, redeProdutoId, titulo, urlCanonica, imagemUrl (/img da 1ª imagem) | null,
  loja: { id, nome, oficial } | null, categoria: { id, nome, caminho } | null,
  estado: "coletando" | "amostra_pequena" | "ok", calor, fotosPorDia, primeiraVezEm, lancadoEm, ultimaFotoEm, ultimaFotoAffiliateEm, indisponivelDesde,
  preco: { minCentavos, maxCentavos, originalCentavos, moeda, dataLocal } | null,
  comissaoBp: Numero, comissaoPorVendaCentavos: Numero,       # "sem_dado_afiliado" quando não há foto affiliate
  nCriadores: Numero, retornoAfiliadoCentavosDia: Numero, saturacao: Numero,
  vendasPeriodo: Numero, gmvPeriodoCentavos: Numero, crescimento: Numero,
  vendasDia: Numero, vendasTotais: Numero, gmvTotalCentavos: Numero,
  novoEmAlta: bool, altoRetornoPoucosAfiliados: bool, poucosAfiliados: bool,
  rankings: [{ categoriaId, tipo, janela, posicao, variacao7d, dataLocal }],   # posições atuais (último dia)
  interesses: [{ id, perfilId, origem, situacao }]                              # resumo (vazio para quem só filtra)
}
ContextoMercado { de, ate, anteriorDe, anteriorAte, fuso, mercado, perfilId, geradoEm, constantes: {…} }
```
A projeção de lucro para 10, 100 e 1.000 vendas é calculada **na tela** (comissão por venda × N). O
membro recebe os mesmos números do dono (FR-054).

### `GET /api/mercado/produtos/{produto_id}` · `mercado_produtos_detalhe` · **U**
**200** `ProdutoMercadoOut` = `CartaoProdutoOut` + `ficha: FichaOut` (a atual) + `galeria: ImagemOut[]`
(ordem da ficha atual; `url` do imgproxy e `original: Link` sem validade) + `nFichas` + `interessesDoUsuario`
(por perfil do usuário: `{perfilId, interesseId|null}` para a ação "Acompanhar neste perfil") +
`adotadoEm: [{perfilId, produtoId}]` (012, quando existe). Erros: 404 `produto_nao_encontrado`.
```text
FichaOut { id, hashConteudo, titulo, descricao, atributos: [{nome, valor}], variantes: [...], argumentos: string[],
           selos: string[], categoria: {id, nome, caminho}|null, loja: {id, nome, oficial}|null,
           imagens: ImagemOut[], esquemaVersao, coletadoEm, createdAt }
ImagemOut { id, sha256, url (/img), original: Link, width, height, bytes, contentType, posicao }
```

### `GET /api/mercado/produtos/{produto_id}/serie?de&ate&fonte` · `mercado_produtos_serie` · **U**
**200**:
```json
{ "produtoId": "uuid", "de": "…", "ate": "…",
  "fotos": [ { "dataLocal": "2026-10-01", "turno": "manha", "fonte": "pagina_publica", "vendidos": 12400,
               "vendidosMin": 12350, "vendidosMax": 12449, "vendidosExato": false,
               "precoMinCentavos": 4990, "precoMaxCentavos": 5990, "precoOriginalCentavos": 7990, "moeda": "BRL",
               "nota": 4.8, "nAvaliacoes": 311, "comissaoBp": null, "nCriadores": null, "vendas7d": null, "vendas30d": null,
               "estoqueVisivel": 230, "disponivel": true, "brutoPendente": false } ],
  "diaria": [ { "dataLocal": "2026-10-01", "vendidos": {"valor": 12400, "estimado": true, "...": "Numero"},
                "vendasDia": {"...": "Numero"}, "precoMinCentavos": 4990, "nCriadores": {"...": "Numero"}, "comissaoBp": {"...": "Numero"} } ],
  "resumo": { "vendasPeriodo": {"...": "Numero"}, "gmvPeriodoCentavos": {"...": "Numero"}, "crescimento": {"...": "Numero"} } }
```
`diaria` é a série para os gráficos (vendidos, vendas/dia, preço, criadores), um ponto por dia local com
foto; dias sem foto não aparecem (nunca interpolados, salvo o marcador `interpolado` quando a última foto
anterior ao período foi usada como base).

### `GET /api/mercado/produtos/{produto_id}/rankings?de&ate` · `mercado_produtos_rankings` · **U**
**200** `{ itens: [{ rankingFotoId, dataLocal, fonte, categoria: {id, nome, caminho}|null, tipo, janela,
posicao, valorExibido, valorNum }], resumo: [{ categoriaId, tipo, janela, posicaoAtual, melhorPosicao,
diasNoTopo, variacao7d, entrouEm, saiuEm|null }] }`.

### `GET /api/mercado/produtos/{produto_id}/videos?de&ate&limite&cursor` · `mercado_produtos_videos` · **U**
**200** `{ itens: [{ redeVideoId, autorHandle, views, likes, comentarios, compartilhamentos, legenda,
publicadoEm, dataLocal, posicao, url (montada pelo servidor a partir do handle e do id, sem parâmetros)
}], proximo }`. Só o @ público e contadores (FR-011): nada mais sobre a pessoa. A última observação de
cada vídeo no período; `?todasObservacoes=true` traz a série.

### `GET /api/mercado/produtos/{produto_id}/avaliacoes?nota&comFotos&limite&cursor` · `mercado_produtos_avaliacoes` · **U**
**200** `{ itens: [{ id, texto, nota, dataAvaliacao, variante, imagens: ImagemOut[], curtidas, coletadoEm
}], proximo, resumo: { total, porNota: {1..5}, comTexto, comFotos } }`. **Nunca** `autor_hash`, nome, @ ou
foto de perfil (FR-010): o hash fica no banco para dedup e não sai na API.

### `GET /api/mercado/produtos/{produto_id}/fichas` · `mercado_produtos_fichas` · **U**
**200** `{ itens: FichaOut[] }` em ordem decrescente de `createdAt`, com `diff: { campos: ["titulo",
"argumentos"] }` em relação à anterior (US5, cenário 2).

### `GET /api/mercado/rankings?de&ate&categoriaId&tipo&janela&fonte&mercado&rede` · `mercado_rankings_listar` · **U**
**200** `{ fotos: [{ id, dataLocal, fonte, categoria, tipo, janela, nItens }], atual: { rankingFotoId,
dataLocal, itens: [{ posicao, produto: CartaoProdutoOut (resumido), valorExibido, valorNum, variacao:
"subiu"|"caiu"|"igual"|"novo", delta: int|null }] , sairam: [{ produto, ultimaPosicao }] } }`. Sem
`categoriaId`, lista as fotos de todas as categorias dos perfis ativos (ou do `perfilId`) e `atual` vem
nulo. `variacao` compara com a foto anterior do mesmo ranking (US5, cenário 3).

### `GET /api/mercado/lojas?de&ate&q&oficial&seguidaPor&ordenar&limite&cursor` · `mercado_lojas_listar` · **U**
**200** `{ itens: CartaoLojaOut[], proximo }`.
```text
CartaoLojaOut { id, rede, mercado, redeLojaId, nome, oficial, url, primeiraVezEm, ultimoVistoEm, ultimaFotoEm,
                nota: Numero, seguidores: Numero, envioNoPrazoPct: Numero, nProdutos: Numero, vendidosTotal: Numero,
                nProdutosAcompanhados: int, gmvEstimadoCentavos: Numero, concentracaoTop1: Numero,
                lancamentos30d: int, comissaoMediaBp: Numero,
                seguidaPor: uuid[] (perfis que seguem) }
```

### `GET /api/mercado/lojas/{loja_id}?de&ate` · `mercado_lojas_detalhe` · **U**
**200** `CartaoLojaOut` + `fotos: [{dataLocal, fonte, nota, seguidores, envioNoPrazoPct, nProdutos,
vendidosTotal…}]` + `produtos: CartaoProdutoOut[]` (os do lago desta loja, ordenados por `gmvPeriodo`) +
`novos30d: CartaoProdutoOut[]`. 404 `loja_nao_encontrada`.

### `GET /api/mercado/categorias?mercado&rede&nivel&paiId&ativas&q` · `mercado_categorias_listar` · **U**
**200** `{ itens: [{ id, redeCategoriaId, nome, nivel, paiId, caminho, ativa, ultimoVistoEm, nProdutos,
indicadores: { medianaComissaoBp: Numero, medianaPrecoCentavos: Numero, nNovosEmAlta: int, espacoEmBranco:
bool } | null }], atualizadaEm: datetime|null }`. `indicadores` só com `?comIndicadores=true` e `de/ate`
(FR-049; nulo com menos de `MIN_PRODUTOS_CATEGORIA` produtos). É a lista do seletor "categorias do nicho".

### `GET /api/mercado/resumo?filtro comum` · `mercado_resumo` · **U**
Os cards do Cockpit (FR-051), todos com os mesmos dados que a tabela e o CSV da tela:
```json
{ "contexto": { "...": "ContextoMercado" },
  "maisVendidos": { "itens": ["CartaoProdutoOut × 10"], "total": 143 },
  "novosEmAlta": { "itens": ["CartaoProdutoOut × 10"], "total": 7 },
  "altoRetornoPoucosAfiliados": { "itens": ["CartaoProdutoOut × 10"], "total": 12, "criterio": { "porCategoria": true, "p25Criadores": 18, "p75Retorno": 4210 } },
  "estadoColeta": { "...": "EstadoColeta (resumido)" },
  "totais": { "produtos": 412, "acompanhados": 230, "coletando": 18, "amostraPequena": 40, "ok": 354,
              "vendasPeriodo": {"...": "Numero"}, "gmvPeriodoCentavos": {"...": "Numero"} } }
```

## Interesse e configuração do perfil

### `GET /api/perfis/{perfil_id}/mercado/interesses?situacao&origem&limite&cursor` · `mercado_interesses_listar` · **U**
**200** `{ itens: InteresseOut[], proximo }`. Inclui os de `perfilId` nulo (vitrine) marcados
`todosOsPerfis: true`.
```text
InteresseOut { id, perfilId: uuid|null, todosOsPerfis: bool, mercadoProdutoId, produto: CartaoProdutoOut (resumido),
               origem, situacao, motivo: object, nota, produtoId: uuid|null (012), temaId: uuid|null,
               pausadoEm, encerradoEm, version, createdAt, createdBy: UserRef|null (null = automático), updatedAt }
```

### `POST /api/perfis/{perfil_id}/mercado/interesses` · `mercado_interesses_criar` · **Hu**
Por link **ou** por produto já no lago:
```json
{ "url": "https://…/product/7291…", "nota": "visto no vídeo da fulana" }
{ "mercadoProdutoId": "uuid", "nota": "" }
```
Com `url`: o adaptador extrai `(rede, mercado, redeProdutoId)` e a URL canônica (400 `url_invalida` se
não reconhece a rede ou o mercado ≠ o da config do perfil); produto inexistente no lago é criado "pela
cara" (`fonte_descoberta = manual`, `calor = quente`, `fotos_por_dia = 2`) e uma tarefa `produto` nível 1
entra na fila de hoje (se a coleta estiver ligada). **201** `InteresseOut` (`origem = manual`). Erros: 409
`interesse_duplicado` (`details.interesseId`; se o existente está `pausado`, a mensagem sugere retomar);
404 `produto_nao_encontrado`; 404 perfil.

### `PATCH /api/mercado/interesses/{interesse_id}` · `mercado_interesses_editar` · **Hu**
```json
{ "situacao": "pausado", "nota": "esperando o preço cair", "version": 2 }
```
`situacao` ∈ `ativo | pausado | encerrado` (de `encerrado` não se sai: 409 `interesse_encerrado`; crie
outro). Qualquer humano, dono ou membro, inclusive nos automáticos (Clarification 4). **200**
`InteresseOut`. Erros: 409 `version_conflict`; 400 `entrada_invalida`.

### `GET /api/mercado/interesses/{interesse_id}/versions` · `mercado_interesses_versions` · **U**
**200** `VersionsList`.

### `POST /api/mercado/interesses/{interesse_id}/revert` · `mercado_interesses_revert` · **HO**
`{ "toVersion": 1, "version": 3 }` → **200** `InteresseOut`. 409 `interesse_duplicado` se a versão alvo
violar a UQ; 409 `version_conflict`.

### `GET /api/perfis/{perfil_id}/mercado/config` · `mercado_perfil_config_get` · **U**
**200** `MercadoPerfilConfigOut { perfilId, mercado, categorias: [{id, nome, caminho, ativa}],
lojasSeguidas: [{id, nome, oficial}], maxRelacionadosDia, avisarNovoEmAlta, version (0 sem linha),
updatedAt, updatedBy }`.

### `PUT /api/perfis/{perfil_id}/mercado/config` · `mercado_perfil_config_put` · **HO**
```json
{ "mercado": "BR", "categoriaIds": ["uuid", "uuid"], "maxRelacionadosDia": 10, "avisarNovoEmAlta": true, "version": 0 }
```
(`lojasSeguidas` **não** entra aqui: muda por seguir/deixar de seguir.) **200** `MercadoPerfilConfigOut`.
Erros: 400 `categorias_maximo` ("No máximo 5 categorias por perfil"); 400 `categoria_desconhecida`
(`details.categoriaId`); 409 `version_conflict`. A próxima volta da trilha inclui os rankings das
categorias novas (US4, cenário 1).

### `GET /api/perfis/{perfil_id}/mercado/config/versions` · `mercado_perfil_config_versions` · **U**
### `POST /api/perfis/{perfil_id}/mercado/config/revert` · `mercado_perfil_config_revert` · **HO**

### `POST /api/perfis/{perfil_id}/mercado/lojas/{loja_id}/seguir` · `mercado_lojas_seguir` · **Hu**
`{ "version": 2 }` (da config do perfil) → **200** `MercadoPerfilConfigOut` (versão com `details.loja =
{lojaId, acao: "seguir"}`). Idempotente (já seguida → 200 sem nova versão). 404 `loja_nao_encontrada`.

### `POST /api/perfis/{perfil_id}/mercado/lojas/{loja_id}/deixar-de-seguir` · `mercado_lojas_deixar_de_seguir` · **Hu**
`{ "version": 3 }` → **200** `MercadoPerfilConfigOut`. Os interesses `loja` já criados **não** mudam
(pausar ou encerrar é ação à parte).

### `POST /api/mercado/produtos/{produto_id}/adotar` · `mercado_produtos_adotar` · **Hu**
```json
{ "perfilId": "uuid", "name": "shorts linho bege", "confirmoImagens": true }
```
Cria o produto do catálogo (012) pelo `produtos.service.create` na mesma transação: `name` (ou o título
truncado a 80), `nome_comercial` = título (≤ 120), `categoria` = `caminho` da categoria, `url_loja` =
`urlCanonica`, `descricao_venda` = os argumentos (≤ 600), `obs` com a origem; as imagens da ficha atual
são **copiadas** para `images` do perfil (`kind = produto`) e viram variantes/originais da 012;
`produtos.mercado_produto_id` = este produto; versão com `details.origem = "mercado_026"` e
`details.mercadoProdutoId`; cria o interesse `manual` do perfil se não existir (FR-055). **201** `{
produto: ProdutoOut (012), interesse: InteresseOut }`. Erros: **409 `ja_adotado`** (`details.produtoId`
do existente; a tela oferece "Abrir o produto"); 409 `passo_indisponivel` ("Este passo chega com o
cadastro de produtos (012)") enquanto a 012 não estiver no banco; 404 `produto_nao_encontrado` /
perfil; 503 `storage_unavailable` / 507 `storage_full`.

## Integrações (aditivo)
`GET /api/integracoes` ganha, sem expor valores:
```json
{ "coleta": { "servidorHabilitado": true, "habilitada": true, "riscoAceito": true,
              "situacao": "coletando", "clientes": 1, "ultimoContatoEm": "…",
              "paginasHoje": 115, "imagensHoje": 652, "rodadaAtual": "ativa|null", "hd": "ok|indisponivel" } }
```

## Mídia (aditivo)
- `MidiaKind` ganha `"mercado_imagem"` (link **sem validade**, como `imagem`, para a galeria e o CSV
  apontarem para o original) e `"mercado_bruto"` (com validade de 1 h, `Content-Encoding: gzip`, só pela
  rota do coletor). As miniaturas vêm pelo imgproxy (`/img`), com as mesmas URLs assinadas das outras
  imagens, porque o objeto está no bucket `imagens`.

## Erros (resumo)
| Código | HTTP | Mensagem |
|---|---|---|
| `entrada_invalida` | 400 | por campo (`details.field`) |
| `url_invalida` | 400 | "Não reconheci um produto do TikTok Shop neste link" (a mensagem pode citar a rede; a rota não) |
| `categorias_maximo` | 400 | "No máximo 5 categorias por perfil" |
| `categoria_desconhecida` | 400 | "Esta categoria não está na taxonomia coletada" |
| `periodo_invalido` | 400 | "Período inválido (até 400 dias, no fuso do mercado)" |
| `bruto_pessoal` | 400 (eventos) / item `invalido` | "O bruto ainda traz dado pessoal de terceiros: <campo>" |
| `unauthorized` | 401 | "Não autenticado" |
| `somente_humano` | 403 | "Só uma pessoa, pela interface, pode fazer isto" (texto da 015) |
| `forbidden` | 403 | "Só o dono pode fazer isto" |
| `escopo_coleta` | 403 | "Este token só vale para o serviço do coletor" |
| `coleta_suspensa` | 403 | "Este token está suspenso" |
| `produto_nao_encontrado`, `loja_nao_encontrada`, `coleta_nao_encontrada`, `bruto_nao_encontrado` | 404 | |
| `coleta_em_andamento` | 409 | "Já existe uma rodada aberta para este token" |
| `coleta_fechada` | 409 | "Esta rodada já foi encerrada" |
| `risco_nao_aceito` | 409 | "Aceite de risco pendente: leia o aviso e confirme antes de ligar" |
| `nada_a_continuar` | 409 | "Nenhuma rodada está pausada" |
| `cliente_revogado` | 409 | "Este token foi revogado (definitivo)" |
| `nome_em_uso` | 409 | "Já existe um cliente com este nome" |
| `interesse_duplicado` | 409 | "Este perfil já acompanha este produto por esta origem" (`details.interesseId`) |
| `interesse_encerrado` | 409 | "Acompanhamento encerrado: crie outro" |
| `ja_adotado` | 409 | "Este produto já foi adotado neste perfil" (`details.produtoId`) |
| `passo_indisponivel` | 409 | "Este passo chega com o cadastro de produtos (012)" |
| `version_conflict` | 409 | "Recarregue e tente de novo" (`details.versaoAtual`) |
| `arquivo_grande` | 413 | "Imagem grande demais (máximo 5 MB)" |
| `lote_grande` | 413 | "Lote grande demais (máximo 50 itens e 6 MB; 10 imagens)" |
| `protocolo_coleta` | 426 | "Atualize o sociman-coletor: o servidor fala o protocolo 1" (`details.esperado`) |
| `coleta_limite` | 429 | "Muitas requisições do coletor" (`Retry-After`) |
| `coleta_desligada` | 503 | "A coleta está desligada no servidor" |
| `coleta_indisponivel` | 503 | "Serviço da coleta indisponível (Redis)" |
| `hd_indisponivel` / `storage_unavailable` | 503 | "O HD de dados não está montado" |
| `storage_full` | 507 | "Sem espaço no HD de dados" |

`conta_fora_do_perfil` da 019 **não se aplica**: o mercado não filtra por conta.

## Classificação em `mcp/mapa.py`
| Grupo | operationIds | Classe |
|---|---|---|
| Coletor | `coleta_fila`, `coleta_coletas_abrir`, `coleta_itens_enviar`, `coleta_imagens_enviar`, `coleta_batimento`, `coleta_coletas_fechar`, `coleta_eventos_enviar`, `coleta_bruto_link` | **FORA** ("serviço do coletor") |
| Gestão | `coleta_clientes_*`, `coleta_config_*` | **PROIBIDAS** (`RequireHumanOwner`) |
| Leitura da coleta | `coleta_estado` | **TOOLS** escopo `leitura` ("Coleta: estado") |
| | `coleta_coletas_listar`, `coleta_coletas_detalhe`, `coleta_eventos_listar`, `coleta_fila_hoje` | **FORA** (operacional, sem valor para o agente) |
| Leitura do mercado | `mercado_produtos_listar`, `mercado_produtos_detalhe`, `mercado_produtos_serie`, `mercado_produtos_rankings`, `mercado_produtos_videos`, `mercado_produtos_avaliacoes`, `mercado_produtos_fichas`, `mercado_rankings_listar`, `mercado_lojas_listar`, `mercado_lojas_detalhe`, `mercado_categorias_listar`, `mercado_resumo`, `mercado_interesses_listar`, `mercado_perfil_config_get` | **TOOLS** escopo `leitura` (prontas para a 028) |
| Versions | `mercado_interesses_versions`, `mercado_perfil_config_versions` | **FORA** |
| Escritas de interesse e ponte | `mercado_interesses_criar`, `mercado_interesses_editar`, `mercado_interesses_revert`, `mercado_perfil_config_put`, `mercado_perfil_config_revert`, `mercado_lojas_seguir`, `mercado_lojas_deixar_de_seguir`, `mercado_produtos_adotar` | **PROIBIDAS** (`RequireHuman*` → 403 `somente_humano` + `publicacao_recusada`) |

Rota nova sem classificação quebra o `test_mcp_mapa.py`. O `gen:contract` regenera `mcp-tools.json`.

## Edge (`docker/nginx/default.conf.template`)
| `location` | Limites |
|---|---|
| `~ ^/api/coleta/coletas/[^/]+/imagens$` | `client_max_body_size 60m`, `proxy_request_buffering off` |
| `~ ^/api/coleta/coletas/[^/]+/itens$` | `client_max_body_size 10m` |
| demais `/api/coleta/*` e `/api/mercado/*` | o padrão de `/api/` (8m) |

`X-Sociman-Via` continua apagado em toda location da API. Depois de mudar o template: `docker compose
restart edge`.

## Tela (SPA), resumo
- Menu Analytics ganha **"Mercado de produtos"** → `/app/mercado?aba=cockpit|produtos|rankings|lojas|
  acompanhamentos` (`FilterBar` + `useFiltroUrl("mercado")`, `ServerPagination`, cards com "Ver tabela" e
  "CSV" gerados dos mesmos dados, ECharts no chunk `graficos`, tooltip em texto escapado). A aba
  "Mercado" de `/app/metricas` passa a se chamar **"Fontes"** (FR-051).
- `/app/mercado/produtos/:id`: ficha, galeria, série, rankings, vídeos, avaliações (sem autor),
  "Acompanhar neste perfil" (Hu) e "Adotar no catálogo" (Hu; 409 `ja_adotado` → "Abrir o produto").
- Perfil `?aba=mercado`: categorias do nicho (PUT só dono), lojas seguidas, acompanhamentos com origem,
  situação e ações (pausar, retomar, encerrar: qualquer humano).
- `/app/configuracoes/coleta` (só dono; o membro vê o `EstadoColeta`): aviso e aceite de risco,
  interruptor (desabilitado sem aceite, com "aceite de risco pendente"), janela, tetos, pausas, "Pausar
  N h", "Continuar", tokens mostrados 1 vez, rodadas, eventos e guia de instalação do coletor.
