# Notas de pesquisa: 009-mcp

**Data**: 2026-10-02 · **Para**: `/speckit-specify` e `/speckit-plan` da spec 009 · **Escopo**: estado atual do
protocolo MCP (versão, transportes, autenticação, segurança) e como o OpenClaw 2026.9.6 (o cliente
que vai usar o SociMan) consome servidores MCP.

## 1. Versão atual do protocolo

- A versão vigente é a **2026-07-28** (GA). A anterior é a 2025-11-25. [F1] [F2]
- Mudanças que importam para o SociMan [F2]:
  - **Protocolo sem estado:** acabaram a sessão de protocolo (`Mcp-Session-Id`) e o handshake
    `initialize`. Cada requisição leva a versão e as capacidades do cliente em `_meta`, e o servidor
    DEVE implementar `server/discover`. Estado entre chamadas, quando houver, vira um identificador
    explícito passado como argumento da tool.
  - **Streamable HTTP** com cabeçalhos obrigatórios `MCP-Protocol-Version`, `Mcp-Method` e `Mcp-Name`
    (o nome da tool). O servidor DEVE recusar com 400 `HeaderMismatch` (-32020) quando o cabeçalho e o
    corpo divergem. Isso permite medir e limitar por tool no edge (nginx) sem abrir o corpo.
  - Sem GET de stream nem retomada por `Last-Event-ID`; notificações de mudança só via
    `subscriptions/listen` (opcional).
  - `tools/list` DEVE ser determinístico (mesma ordem) e PODE variar conforme a credencial
    (ex.: só as tools que o escopo do cliente permite). [F4]
  - **Deprecados:** transporte HTTP+SSE (de 2024-11-05), Roots, Sampling e Logging, e o registro
    dinâmico de cliente OAuth (RFC 7591), substituído por *Client ID Metadata Documents*.
- **Compatibilidade:** clientes da era 2025-11-25 ainda fazem `initialize`. Um servidor só 2026-07-28
  responde 405 a GET/DELETE, ignora `Mcp-Session-Id` e devolve erro moderno no 400, para o cliente
  saber que deve usar a versão nova. Quem precisa atender as duas eras implementa o comportamento das
  duas revisões. [F3]
  **Risco para o plano:** não sabemos qual versão o cliente MCP do OpenClaw 2026.9.6 fala. Conferir com
  `openclaw mcp probe` antes de escolher o SDK/versão do servidor.

## 2. Transportes

- Há dois transportes padrão: **stdio** (subprocesso lançado pelo cliente) e **Streamable HTTP** (um
  endpoint que aceita POST e responde com JSON ou com SSE da própria requisição). [F3]
- Requisitos de segurança do Streamable HTTP [F3]:
  - o servidor DEVE validar o cabeçalho `Origin` (contra DNS rebinding) e responder 403 se ele for inválido;
  - rodando localmente, DEVERIA escutar só em localhost;
  - DEVERIA autenticar todas as conexões.
- Atrás de proxy, o servidor DEVERIA mandar `X-Accel-Buffering: no` nas respostas SSE. Isso pesa para
  o nosso edge nginx (é o mesmo cuidado das `location` sem buffering das specs 004 e 006). [F3]

## 3. Autenticação

- A autorização do MCP é **OPCIONAL**. Quando existe [F5]:
  - em HTTP, DEVERIA seguir o perfil OAuth 2.1 do MCP: Protected Resource Metadata (RFC 9728),
    Resource Indicators (RFC 8707), validação de audiência, `iss` (RFC 9207) e PKCE;
  - em **stdio**, NÃO DEVERIA usar OAuth: as credenciais vêm do ambiente.
- Regras que valem para qualquer esquema [F5] [F6]:
  - token só no cabeçalho `Authorization: Bearer`, nunca na URL;
  - token inválido → 401; escopo insuficiente → 403 (`insufficient_scope`);
  - **token passthrough é proibido:** o servidor só aceita tokens emitidos para ele e não os repassa;
  - **mínimo privilégio:** escopo pequeno por padrão, nada de escopo "faz-tudo";
  - identificadores de estado não valem como autenticação.
- O spec não proíbe um token estático (chave de API) mandado como `Bearer`: o perfil OAuth é
  "SHOULD" para quem implementa autorização. Para um servidor interno da rede de casa, com clientes
  configurados à mão pelo dono, o token estático por cliente é o caminho mais simples. A contrapartida
  é que ficamos fora do fluxo de descoberta automática (o cliente não "faz login" sozinho).

## 4. Tools: definição e segurança

- Uma tool tem `name` (1 a 128 caracteres, `[A-Za-z0-9_.-]`, única no servidor), `title`,
  `description`, `inputSchema` (JSON Schema 2020-12), `outputSchema` opcional e `annotations`
  (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`). [F4]
- As **anotações não são garantia**: o cliente DEVE tratá-las como não confiáveis. A proteção real
  fica no servidor. [F4]
- Há dois tipos de erro [F4]:
  - **erro de protocolo** (JSON-RPC): tool desconhecida ou pedido malformado;
  - **erro de execução** (`isError: true`, com texto acionável): regra de negócio, validação. É este
    que o modelo usa para se corrigir.
  No SociMan, o 403 `somente_humano` e o 409 `version_conflict` viram erros de execução com mensagem em pt-BR.
- O servidor DEVE validar entradas, controlar acesso, **limitar a taxa** de invocações e sanitizar as
  saídas. O cliente DEVERIA registrar o uso para auditoria e pedir confirmação humana nas operações
  sensíveis. [F4]
- Para tools com `outputSchema`, `structuredContent` DEVE seguir o schema, e o texto serializado
  DEVERIA vir junto, por compatibilidade. [F4]

## 5. Gerar tools a partir do OpenAPI (princípio IV)

- O FastMCP (o framework Python de MCP mais usado) gera um servidor a partir de um OpenAPI ou de um app
  FastAPI (`FastMCP.from_fastapi`/`from_openapi`). O mapeamento usa uma lista ordenada de `RouteMap`
  (por método, padrão de URL e tags) para TOOL, RESOURCE ou EXCLUDE. Os cabeçalhos (ex.: Bearer) são
  repassados ao app. [F7] [F8]
- A própria documentação do FastMCP avisa: **LLMs vão muito melhor com um servidor curado** do que com
  a conversão automática de todas as rotas. A conversão total é para começar, não para produção. [F7]
- **Implicação:** o princípio IV é atendido com uma **lista explícita** de operationIds → tool
  (curadoria), com nome, schemas e descrição derivados do OpenAPI. A verificação automatizada acusa
  operationId inexistente, schema divergente e qualquer rota proibida mapeada. A regra de negócio
  continua só na API: a tool chama a rota.
- Escolher biblioteca (FastMCP × SDK oficial `mcp` × gerador próprio) é decisão do plano, e passa
  pelo princípio VIII (dependência nova precisa de justificativa).

## 6. Como o OpenClaw 2026.9.6 consome MCP (cliente)

Fonte: a documentação instalada com o pacote (`~/.openclaw/tools/node-v24.19.0/lib/node_modules/openclaw/docs/`)
e `openclaw mcp --help`. O `openclaw.json` foi lido só com `grep`: hoje há `mcp.apps.enabled=true` e
nenhum `mcp.servers`.

- Os servidores ficam em `mcp.servers` (config **global** do gateway). Transportes: `stdio`, `sse`
  (padrão quando omitido) e `streamable-http` (precisa ser explícito). [O1] [O2]
- **Credencial por cabeçalho:** `headers: { "Authorization": "Bearer …" }`. O `mcp doctor` avisa
  quando um cabeçalho sensível está como literal no config e recomenda usar o mecanismo de segredos.
  Também há suporte a OAuth (`openclaw mcp login`, inclusive `per-requester`), mTLS (`--client-cert`,
  `--client-key`) e `--ssl-verify`. [O2]
- **Filtro de tools por servidor:** `toolFilter.include/exclude` (`openclaw mcp tools <nome>`). As tools
  MCP passam pela mesma política de tools dos agentes. [O1]
- **Isolamento por agente:** a própria documentação diz que a lista de skills por agente *não* é
  fronteira de autorização e recomenda, para isolar o MCP por agente, "**preferir credenciais por
  agente no servidor MCP**". [O3] Na prática:
  - registrar **um servidor por agente** (ex.: `sociman-cacador`), cada um com a sua credencial;
  - permitir só esse servidor na política de tools de cada agente.
  Como restringir um servidor a um agente no runtime `claude-cli` ainda precisa ser verificado no
  plano. A projeção `codex.agents` existe, mas é só do Codex.
- Os agentes rodam no runtime `claude-cli`, que recebe os servidores MCP por um config gerado
  (`bundleMcp`). [O4]
- O gateway roda no mesmo host do SociMan, o que torna `localhost` viável. O endpoint MCP não precisa
  sair da rede de casa.

## 7. Conclusões para a spec

1. Usar **Streamable HTTP** (stdio exigiria um processo por agente, com a credencial no ambiente, e o
   SSE está deprecado). O endpoint fica atrás do edge, com validação de `Origin` e de autenticação.
2. **Credencial por cliente**, emitida e revogada pelo dono. Token estático (Bearer) é o mais simples
   e é aceito pelo spec; OAuth 2.1 e mTLS ficam como alternativas (ver o [NEEDS CLARIFICATION] da spec).
3. `tools/list` **filtrado pelo escopo** da credencial: quem só lê nem vê as tools de escrita.
4. **Lista curada** de operationIds, gerada do OpenAPI e verificada. Nunca a conversão de todas as rotas.
5. Defesa no servidor: anotações de tool não protegem nada. Os atos humanos continuam barrados pela
   API (`somente_humano`), e o mapa também não os expõe (duas camadas).
6. Limite de taxa por cliente e registro de chamadas no servidor (o spec exige rate limit e recomenda log).
7. Verificar a versão de protocolo que o OpenClaw fala antes de fixar a versão do servidor.

## Fontes

- [F1] The 2026-07-28 Specification (blog oficial): https://blog.modelcontextprotocol.io/posts/2026-07-28/
- [F2] Key Changes 2026-07-28: https://modelcontextprotocol.io/specification/2026-07-28/changelog
- [F3] Transports / Streamable HTTP 2026-07-28: https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
- [F4] Server Features / Tools 2026-07-28: https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- [F5] Authorization 2026-07-28: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
- [F6] Security Best Practices: https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices
- [F7] FastMCP + FastAPI: https://gofastmcp.com/integrations/fastapi
- [F8] FastMCP + OpenAPI: https://gofastmcp.com/integrations/openapi
- [O1] OpenClaw, "Connect MCP servers": `docs/tools/mcp.md` (pacote 2026.9.6)
- [O2] OpenClaw, "Transports and OAuth": `docs/cli/mcp/transports.md`; `openclaw mcp add --help`
- [O3] OpenClaw, skills config (aviso sobre isolamento de MCP por agente): `docs/tools/skills-config.md`
- [O4] OpenClaw, CLI backends / bundle MCP: `docs/gateway/cli-backends.md`
