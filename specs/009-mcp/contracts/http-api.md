# Contrato HTTP: gestão do MCP e anotações (009)

As rotas REST novas ou alteradas pela 009 seguem algumas regras comuns:

- JSON em camelCase (aliases Pydantic);
- erros no formato `ApiError` (`{code, message}`);
- `version` no corpo das mutações (409 `version_conflict`);
- histórico via `history.record`.

O cliente tipado sai do OpenAPI (`npm run gen:contract`); este arquivo descreve só a forma e as regras.
O endpoint MCP (`/mcp`) fica em [mcp.md](mcp.md).

Legenda de acesso:

- **H**: `RequireHumanOwner`, ou seja, dono com sessão humana (outro ator → 403 `somente_humano` +
  evento);
- **Hu**: `RequireHuman`, qualquer usuário humano (ator MCP → 403 `somente_humano`);
- **U**: `RequireUser` (humano ou cliente MCP, conforme o mapa).

## Clientes MCP (`/api/mcp/…`, todas **H**, todas em `PROIBIDAS` no mapa)

| operationId | Método e rota | Corpo | Resposta |
|---|---|---|---|
| `mcp_clientes_list` | `GET /api/mcp/clientes?situacao=` | — | `{clientes: ClienteMcp[]}` (inclui revogados; ordem: ativos, suspensos, revogados, depois nome) |
| `mcp_clientes_create` | `POST /api/mcp/clientes` | `{nome, descricao?, escopo, expiraEm?, limitePorMinuto?, limiteEscritasDia?}` | 201 `{cliente: ClienteMcp, token}` + `Cache-Control: no-store` |
| `mcp_clientes_get` | `GET /api/mcp/clientes/{cliente_id}` | — | `{cliente: ClienteMcp}` |
| `mcp_clientes_update` | `PATCH /api/mcp/clientes/{cliente_id}` | `{version, nome?, descricao?, escopo?, expiraEm?, limitePorMinuto?, limiteEscritasDia?}` | `{cliente}`; 409 `mcp_cliente_revogado` |
| `mcp_clientes_suspender` | `POST …/{cliente_id}/suspender` | `{version}` | `{cliente}` |
| `mcp_clientes_reativar` | `POST …/{cliente_id}/reativar` | `{version}` | `{cliente}` |
| `mcp_clientes_rotacionar` | `POST …/{cliente_id}/rotacionar` | `{version}` | `{cliente, token}` + `no-store` |
| `mcp_clientes_revogar` | `POST …/{cliente_id}/revogar` | `{version}` | `{cliente}` (final) |
| `mcp_clientes_versions` | `GET …/{cliente_id}/versions` | — | `VersionsOut` padrão (sem hash) |
| `mcp_config_get` | `GET /api/mcp/config` | — | `{habilitado, servidorHabilitado, version}` (`servidorHabilitado` = `MCP_HABILITADO`) |
| `mcp_config_update` | `PUT /api/mcp/config` | `{habilitado, version}` | idem |
| `mcp_config_versions` | `GET /api/mcp/config/versions` | — | `VersionsOut` |
| `mcp_chamadas_list` | `GET /api/mcp/chamadas?clienteId=&tool=&resultado=&via=&de=&ate=&cursor=&limit=` | — | `{chamadas: ChamadaMcp[], nextCursor}` (mais nova primeiro; `limit` ≤ 200) |

`ClienteMcp`:

```json
{
  "id": "uuid", "nome": "Caçador", "descricao": "agente cacador do OpenClaw",
  "escopo": "leitura", "situacao": "ativo", "tokenId": "k3j9x2ab",
  "tokenEmitidoEm": "2026-10-02T15:00:00Z", "expiraEm": null, "venceEmBreve": false,
  "limitePorMinuto": 60, "limiteEscritasDia": 200,
  "ultimoUsoEm": "2026-10-02T15:10:00Z",
  "uso24h": { "chamadas": 120, "recusas": 2, "escritas": 0 }, "noLimite": false,
  "revogadoEm": null, "revogadoPor": null,
  "createdAt": "…", "createdBy": {"id": "…", "nome": "Raul"}, "version": 3
}
```

`token` (somente na criação e na rotação): `smcp_<8 base32>_<43 base64url>`. Nenhuma outra resposta, histórico
ou evento contém o token ou o hash.

`ChamadaMcp`: `{id, ocorreuEm, cliente: {id, nome} | null, via, tool, metodo, rota, argsResumo, resultado,
statusHttp, codigoErro, duracaoMs, escrita, entidade: {tipo, id, link} | null}`. O `link` é a rota do
SPA do item.

Validações:

- `nome`: 1–60 caracteres, único sem caixa nem acento (409 `nome_em_uso`);
- `limitePorMinuto`: 1–600;
- `limiteEscritasDia`: 0–5000;
- `expiraEm`: no futuro (400 `expira_no_passado`).

## Anotações e propostas (`/api/anotacoes…`)

| operationId | Método e rota | Acesso | Mapa |
|---|---|---|---|
| `anotacoes_list` | `GET /api/anotacoes?alvoTipo=&alvoId=&perfilId=&situacao=&tipo=&autorClienteId=&cursor=&limit=` | U | tool (leitura) |
| `anotacoes_get` | `GET /api/anotacoes/{anotacao_id}` | U | tool (leitura) |
| `anotacoes_create` | `POST /api/anotacoes` `{alvoTipo, alvoId, tipo, texto, campos?}` | U (ator MCP precisa do escopo `propostas`) | tool (propostas, escrita) |
| `anotacoes_update` | `PATCH /api/anotacoes/{anotacao_id}` `{version, texto?, campos?}` | U, só o autor, só `aberta` (403 `nao_e_o_autor`, 409 `anotacao_fechada`) | tool (propostas, escrita) |
| `anotacoes_archive` | `POST …/{anotacao_id}/archive` `{version}` | U, o autor ou um dono, só `aberta` | tool (propostas, escrita) |
| `anotacoes_descartar` | `POST …/{anotacao_id}/descartar` `{version, motivo?}` | Hu | proibida |
| `anotacoes_revert` | `POST …/{anotacao_id}/revert` `{version, toVersion}` | H | proibida |
| `anotacoes_versions` | `GET …/{anotacao_id}/versions` | U | tool (leitura) |
| `anotacoes_resumo` | `GET /api/anotacoes/resumo?perfilId=` | U | fora (contador do menu) |

`Anotacao`:

```json
{
  "id": "uuid", "alvo": {"tipo": "destino", "id": "uuid", "titulo": "…", "link": "/app/conteudos/…", "arquivado": false},
  "perfilId": "uuid", "tipo": "proposta_texto", "texto": "Sugestão de legenda mais curta",
  "campos": {"titulo": null, "descricao": "…", "hashtags": ["receita", "airfryer"]},
  "situacao": "aberta",
  "autor": {"tipo": "mcp_client", "id": "uuid", "nome": "Planejador"},
  "resolvidaPor": null, "resolvidaEm": null, "motivoDescarte": null,
  "createdAt": "…", "version": 1
}
```

Erros da criação:

- 404 se o alvo não existe;
- 409 `alvo_arquivado`;
- 400 `proposta_so_em_destino` (`proposta_texto` com alvo que não é `destino`);
- 400 `campos_vazios`;
- 400 de validação dos campos (mesmos limites do destino: título, descrição e hashtags).

## Rotas existentes alteradas

| operationId | Mudança |
|---|---|
| `destinos_update` (`PATCH /api/destinos/{destino_id}`) | Ganha o campo opcional `propostaId` no corpo. Se vier, o service confere que a proposta é `proposta_texto` do **mesmo** destino, está `aberta` e que o ator é humano (ator MCP → 403 `somente_humano`). Ao salvar, marca a proposta `aplicada` e grava `details.proposta = {id, clienteId}` no histórico do destino. **Ator MCP** sem `propostaId`: só nos estados `pendente` e `aprovacao_pedida`; nos demais, 409 `destino_aprovado` ("destino aprovado: só o dono altera; grave uma proposta"). |
| todas as `*_versions` | Cada versão ganha `autor: {tipo: "usuario" \| "mcp_client" \| "sistema", id, nome}`. Os campos antigos continuam, por compatibilidade. |
| `security_events_list` | Os eventos ganham `actorMcpClient: {id, nome} \| null`. |

## Recusas do portão (qualquer rota, ator `mcp_client`)

| Situação | Status | `code` |
|---|---|---|
| Token ausente, inválido, revogado ou vencido | 401 | `unauthorized` (mensagem neutra) |
| Interruptor desligado (`.env` ou tela) | 403 | `mcp_desligado` |
| Cliente suspenso | 403 | `mcp_suspenso` |
| `Origin` presente | 403 | `mcp_origem` |
| Operação em `PROIBIDAS` | 403 | `somente_humano` (+ evento `publicacao_recusada` com o cliente) |
| Operação fora de `TOOLS` ou do escopo do cliente | 403 | `escopo_mcp` |
| Limite por minuto ou de escritas por dia | 429 | `mcp_limite` + `Retry-After` |
| Redis indisponível | 503 | `mcp_indisponivel` |

Toda recusa (menos o token sem `<id>` reconhecível) gera uma linha em `mcp_chamadas`.
