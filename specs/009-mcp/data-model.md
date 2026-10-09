# Data Model: Servidor MCP para os agentes (009)

Uma migração nova (`0014_mcp`, com `down_revision` = a 0013 da spec 020, confirmada no gate T001)
cria quatro tabelas e acrescenta uma coluna em duas tabelas existentes. Nada é apagado de fato: não
existe DELETE de domínio (princípio VII).

## Tabelas novas

### `mcp_clientes` (Cliente MCP) · `entity_type = "mcp_cliente"`

| Coluna | Tipo | Regra |
|---|---|---|
| `id` | uuid PK | |
| `nome` | text | obrigatório, 1–60 caracteres, único sem caixa nem acento (`uq_mcp_clientes_nome`, sobre a forma normalizada) |
| `descricao` | text | até 300 caracteres, padrão `''` |
| `escopo` | enum `mcp_escopo` (`leitura`, `propostas`) | |
| `situacao` | enum `mcp_situacao` (`ativo`, `suspenso`, `revogado`) | `revogado` é final (não volta) |
| `token_id` | text | 8 caracteres `[a-z2-7]`, único; muda a cada rotação (R4) |
| `token_hash` | bytea (32) | SHA-256 do token completo; **nunca** sai em resposta, histórico ou log |
| `token_emitido_em` | timestamptz | criação ou última rotação |
| `expira_em` | timestamptz NULL | opcional; vencido = autenticação recusada (vale como revogado) |
| `limite_por_minuto` | int | padrão 60, 1–600 |
| `limite_escritas_dia` | int | padrão 200, 0–5000 (0 = sem escrita, mesmo com escopo `propostas`) |
| `ultimo_uso_em` | timestamptz NULL | atualizado no máximo 1 vez por minuto (evita escrever a cada chamada) |
| `revogado_em`, `revogado_por` | timestamptz / uuid FK users NULL | preenchidos na revogação |
| `created_at/by`, `updated_at/by` | AuditMixin | sempre um dono humano |
| `version` | int | controle otimista |

- `__versioned_fields__`: `nome`, `descricao`, `escopo`, `situacao`, `expira_em`,
  `limite_por_minuto`, `limite_escritas_dia`, `token_id`. O `token_id` entra para a rotação aparecer no
  diff; o hash fica de fora.
- Transições de `situacao`: `ativo` ↔ `suspenso`; `ativo|suspenso` → `revogado`. Revogar ou rotacionar um
  revogado → 409 `mcp_cliente_revogado`.
- O histórico das ações usa `action`: `created`, `updated` (editar, suspender, reativar, rotacionar
  com `details.acao`) e `archived` (revogar, com `details.acao = "revogado"`; o cliente nunca é
  restaurado).
- **Eventos de segurança:** `mcp_cliente_criado`, `mcp_cliente_rotacionado`, `mcp_cliente_revogado`,
  `mcp_cliente_suspenso`, `mcp_config_alterada` e `mcp_auth_falhou` (este com `details.tokenId`
  quando o id existe).

### `mcp_config` (Interruptor) · `entity_type = "mcp_config"`

| Coluna | Tipo | Regra |
|---|---|---|
| `id` | smallint PK | `CHECK (id = 1)` |
| `habilitado` | bool | padrão `false` |
| `version` + AuditMixin | | |

O acesso só vale com `settings.mcp_habilitado` (`MCP_HABILITADO`, padrão `false`) **e**
`habilitado = true` (R11).

### `mcp_chamadas` (Registro de chamadas) · só inserção

| Coluna | Tipo | Regra |
|---|---|---|
| `id` | bigint identity PK | |
| `ocorreu_em` | timestamptz | `now()` no início da requisição |
| `cliente_id` | uuid FK `mcp_clientes` NULL | nulo só quando o token não identifica nenhum cliente |
| `via` | enum (`mcp`, `api`) | `mcp` = veio pela ponte do servidor MCP (R3) |
| `tool` | text | `operationId`, ou o nome pedido quando a tool é desconhecida |
| `metodo`, `rota` | text | método HTTP e rota-modelo (ex.: `PATCH /api/destinos/{destino_id}`) |
| `args_resumo` | jsonb | ≤ 2 KB, chaves sensíveis com `"***"`, strings ≤ 200 caracteres (R8) |
| `resultado` | enum `mcp_resultado` (`ok`, `erro`, `recusada`, `limite`, `nao_autenticado`) | |
| `status_http` | smallint NULL | |
| `codigo_erro` | text NULL | ex.: `somente_humano`, `escopo_mcp`, `version_conflict`, `destino_aprovado` |
| `duracao_ms` | int | |
| `escrita` | bool | conforme o mapa |
| `entidade_tipo`, `entidade_id` | text / uuid NULL | o item alterado nas escritas com sucesso |
| `ip` | inet NULL | de `X-Forwarded-For` (o edge) |

- O trigger `mcp_chamadas_so_insercao` recusa UPDATE e DELETE (o `TRUNCATE` do `reset-db` e dos testes
  continua valendo).
- Índices: `(cliente_id, ocorreu_em DESC)`, `(ocorreu_em DESC)` e `(resultado, ocorreu_em DESC)`.
- A tela agrega "chamadas em 24 h", "recusas em 24 h" e "no limite (429 nos últimos 5 min)" por
  cliente direto desta tabela.

### `anotacoes` (Anotação / proposta) · `entity_type = "anotacao"`

| Coluna | Tipo | Regra |
|---|---|---|
| `id` | uuid PK | |
| `alvo_tipo` | enum `anotacao_alvo` (`perfil`, `conta`, `canal`, `video_fonte`, `corte`, `conteudo`, `destino`) | |
| `alvo_id` | uuid | precisa existir e não estar arquivado na criação (senão, 404 ou 409 `alvo_arquivado`) |
| `perfil_id` | uuid FK perfis | derivado do alvo (para filtrar a caixa por perfil) |
| `tipo` | enum `anotacao_tipo` (`observacao`, `proposta_texto`) | `proposta_texto` só com `alvo_tipo = destino` |
| `texto` | text | 1–4.000 caracteres |
| `campos` | jsonb NULL | só em `proposta_texto`: `{titulo?, descricao?, hashtags?[]}`, com pelo menos um campo e os mesmos limites do destino |
| `situacao` | enum `anotacao_situacao` (`aberta`, `aplicada`, `descartada`, `arquivada`) | |
| `autor_kind` | text | `mcp_client` ou `user` |
| `autor_mcp_cliente_id` | uuid FK NULL | CHECK: preenchido se e só se `autor_kind = 'mcp_client'` |
| `autor_user_id` | uuid FK users NULL | CHECK: preenchido se e só se `autor_kind = 'user'` |
| `resolvida_por`, `resolvida_em` | uuid FK users / timestamptz NULL | quem aplicou ou descartou (sempre humano) |
| `motivo_descarte` | text NULL | opcional, ≤ 300 caracteres |
| `version` + AuditMixin | | |

- `__versioned_fields__`: `texto`, `campos`, `situacao`, `motivo_descarte`.
- Transições:

  | De | Para | Quem |
  |---|---|---|
  | `aberta` | `aberta` (editar) | só o autor |
  | `aberta` | `arquivada` | o autor ou o dono |
  | `aberta` | `aplicada` | humano, pelo save do destino com `propostaId` |
  | `aberta` | `descartada` | humano |
  | `aplicada`, `descartada`, `arquivada` | — | finais, mas o dono pode reverter pelo histórico |

- Índices: `(alvo_tipo, alvo_id)` e `(situacao, created_at DESC)`.
- Na caixa de propostas, um item arquivado depois da criação da anotação aparece com
  `alvoArquivado: true`, calculado na leitura.

## Colunas novas em tabelas existentes

| Tabela | Coluna | Regra |
|---|---|---|
| `entity_versions` | `actor_mcp_client_id uuid NULL FK mcp_clientes(id)` | CHECK `ck_entity_versions_ator`: `(actor_kind = 'mcp_client') = (actor_mcp_client_id IS NOT NULL)` |
| `security_events` | `actor_mcp_client_id uuid NULL FK mcp_clientes(id)` | mesmo CHECK |

As linhas antigas têm `actor_kind` `user`, `system:*` ou `anonymous`, e o CHECK vale para elas sem
backfill.

## Estruturas em código (sem tabela)

- **`Actor`** (`auth/deps.py`) ganha `mcp_client_id: UUID | None` e `mcp_escopo: str | None`, com
  `kind = "mcp_client"`. O `ActorLike` do `history.py` ganha `mcp_client_id`.
- **Mapa** (`mcp/mapa.py`, R2):
  - `Tool(escopo: "leitura" | "propostas", escrita: bool, descricao_extra: str | None,
    limite_padrao: int | None, entidade: str | None)`, onde `entidade` diz o tipo do item que a
    escrita altera, para o registro;
  - `FORA` e `PROIBIDAS`: `dict[str, str]` (operationId → motivo).
- **Definição de tool gerada:** `{name, title, description, inputSchema, outputSchema, annotations}`,
  derivada de `app.openapi()` e exportada em `packages/contract/mcp-tools.json` (`{"leitura": [...],
  "propostas": [...]}`).

## Regras transversais

- **Escopo:** `propostas` inclui `leitura`. O `tools/list` devolve as tools do escopo, ordenadas pelo
  `name`.
- **Escritas do primeiro corte:**
  - `envios_selecionar`;
  - `destinos_update`, com a trava para ator MCP: só nos estados `pendente` e `aprovacao_pedida`,
    senão 409 `destino_aprovado`; e o ator MCP não pode mandar `propostaId`;
  - `anotacoes_create`, `anotacoes_update` e `anotacoes_archive` (as duas últimas só nas próprias
    anotações abertas).
- **Paginação nas tools de lista:** o mapa define `limite_padrao` (padrão 50) e o teto do parâmetro
  `limit`/`limite` de cada rota que já pagina:
  - `conteudos_list`, `envios_list`, `cortes_list`, `assets_list`, `assets_images`,
    `videos_fonte_list` e `metricas_videos_list` usam o parâmetro da própria rota;
  - as listas sem paginação (`perfis_list`, `canais_list`, `fontes_list`) são pequenas por natureza.

  Toda resposta acima de **256 KB** serializados é recortada na fronteira de item da lista principal,
  com `truncado: true` e o aviso "resultado truncado, use filtros ou a próxima página" (FR-016). Se não
  houver lista para recortar, a resposta vira erro de execução com o mesmo aviso.
- **Mídia:** só o `midia_links` (POST, sem mutação de domínio) devolve links assinados com validade. As
  tools não embutem binários (FR-017).
