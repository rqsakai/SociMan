# Research: Servidor MCP para os agentes (009)

Decisões técnicas da 009. Cada item segue o formato **Decisão / Por quê / Alternativas**. O
levantamento do protocolo e do OpenClaw está em [notas-pesquisa.md](notas-pesquisa.md). Aqui fica só o
que decide a implementação. As versões foram conferidas em 2026-10-02.

## R1. Biblioteca: SDK oficial `mcp` v2, servidor de baixo nível

- **Decisão:** usar o SDK oficial **`mcp` 2.2.x** (PyPI, 2026-09-07, MIT). Do SDK, usamos:
  - o **`Server` de baixo nível**, com handlers `list_tools` e `call_tool` escritos por nós, que
    devolvem as tools com `inputSchema` e `outputSchema` explícitos, montados a partir do OpenAPI (R2);
  - o transporte Streamable HTTP do SDK, montado como sub-app ASGI dentro do FastAPI (R3);
  - nada do `MCPServer` de alto nível (decorators) nem do suporte a OAuth.

  A versão fica fixada no `pyproject` com `>=2.2,<3`.
- **Implementação (T004, 2026-10-05):** o `uv add "mcp>=2.2,<3"` resolveu o **`mcp` 2.3.0** (com o
  `mcp-types` 2.3.0). O `uv tree` não traz framework extra: `starlette`, `uvicorn` e `pydantic` já
  estavam na API; entram `httpx2`, `sse-starlette`, `jsonschema` (usado também para validar os
  argumentos das tools, R2) e `opentelemetry-api` (o middleware de spans do SDK, inerte sem
  exportador). O `/mcp` usa um `StreamableHTTPSessionManager` sem estado **por requisição**, então
  o app não precisa de lifespan.
- **Por quê:**
  - O SDK v2 implementa a versão **2026-07-28** e todas as anteriores, **incluindo o handshake
    `initialize` da 2025-11-25**. Isso é decisivo, porque o OpenClaw 2026.9.6 traz o
    `@modelcontextprotocol/sdk` **1.30.0**, com `LATEST_PROTOCOL_VERSION = "2025-11-25"` (conferido
    no `node_modules` do OpenClaw). O cliente MCP do runtime `claude-cli` (Claude Code 2.1.288) também
    precisa ser atendido, e a versão dele só se confirma pela sonda (quickstart §4). O SDK atende as
    duas eras sem código nosso.
  - Com o servidor de baixo nível, a lista de tools vem **dos dados** (mapa + OpenAPI) e não de funções
    Python. Assim, nenhum tipo é duplicado à mão (princípio IV).
  - É uma dependência só, mantida pelo grupo do protocolo, sem extras.
- **Alternativas:**
  - **FastMCP 4.0.x** (Apache-2.0): `from_fastapi`/`from_openapi` com `RouteMap` gera tools de todas as
    rotas, e a própria documentação diz que um servidor curado vai melhor. Traz um framework inteiro
    (auth própria, providers, transforms) para usar só o mapeamento, e o filtro por escopo e o portão
    teriam de ser refeitos dentro do modelo dele. Recusado pelo princípio VIII.
  - **Implementar o JSON-RPC à mão:** são duas eras de protocolo, cabeçalhos, SSE e erros. É código de
    protocolo nosso sem necessidade.
  - **Servidor em Node** (o mesmo SDK do OpenClaw): seria um segundo runtime no projeto. Recusado.

## R2. Tools geradas do OpenAPI por mapa explícito

- **Decisão:** criar o arquivo `apps/api/src/sociman_api/mcp/mapa.py` com **três classificações**,
  cobrindo todas as operações do OpenAPI:
  - `TOOLS: dict[operationId, Tool]`, onde `Tool` tem `escopo` (`leitura` ou `propostas`), `escrita`
    (bool), `descricao_extra` (opcional, pt-BR) e `limite_padrao` (opcional, para listas);
  - `FORA: dict[operationId, motivo]`: login, upload de arquivo, `deprecated`, rotas de gestão do
    próprio MCP, `health`, `config`;
  - `PROIBIDAS: dict[operationId, motivo]`: os atos humanos (FR-024).

  O módulo `mcp/ferramentas.py` lê o `app.openapi()` e, para cada item de `TOOLS`, monta a definição
  da tool:
  - **`name`** é o `operationId` (ex.: `perfis_list`), que já está no conjunto de caracteres do spec;
  - **`inputSchema`** é um objeto com os parâmetros de caminho e de query mais o corpo JSON (com os
    `$ref` resolvidos para `$defs` locais);
  - **`outputSchema`** é o schema da resposta 2xx;
  - **`description`** junta o `summary` e a docstring da operação com o `descricao_extra`;
  - **`annotations`** traz `readOnlyHint` (para as leituras) e `destructiveHint=false`.
- **Verificação** (princípio IV, FR-010), em `tests/unit/test_mcp_mapa.py`, que DEVE falhar se:
  1. alguma operação do OpenAPI não estiver em exatamente uma das três listas;
  2. algum operationId do mapa não existir mais;
  3. alguma `PROIBIDA` aparecer em `TOOLS` (a lista proibida também é conferida contra as rotas com
     `RequireHumanOwner`: toda rota H tem de estar em `PROIBIDAS`);
  4. alguma tool de escrita tiver `escopo = leitura`.

  Além disso, o `npm run gen:contract` passa a gerar `packages/contract/mcp-tools.json` (as tools por
  escopo, com os schemas finais), e o `check:contract` regenera e compara. Assim, toda mudança de
  schema que afeta uma tool aparece no diff, como já acontece com o cliente do SPA.
- **Por quê:** a lista curada evita expor ~190 operações a um modelo e mantém uma fonte só (o
  OpenAPI) para tipos e schemas. A classificação obrigatória faz de "rota nova vira tool" uma decisão
  explícita, nunca um padrão.
- **Alternativas:**
  - **Tags no próprio router** (`openapi_extra={"x-mcp": …}`): espalha a política por 15 routers e
    dificulta revisar a lista proibida num lugar só. Recusado.
  - **YAML separado:** é um formato a mais, sem tipagem. O módulo Python é verificado pelo ruff e
    importado pelos testes.

## R3. Transporte e hospedagem: Streamable HTTP dentro da API, em `/mcp`

- **Decisão:**
  - O sub-app ASGI do SDK é montado no FastAPI em **`/mcp`** (fora de `/api`, para não se misturar
    com as rotas REST nem entrar no OpenAPI).
  - O modo é **sem estado**: sem `Mcp-Session-Id` e com respostas JSON (`json_response`), porque
    nenhuma tool precisa de stream.
  - O edge ganha uma `location = /mcp` própria (R9). O OpenClaw usa
    `http://localhost:8180/mcp` (mesmo host). Pela rede de casa, a URL é
    `https://192.168.86.47:8543/mcp` (com a CA da casa).
- **Execução das tools (ponte):** o `call_tool` chama a **própria API em processo**, por
  `httpx.AsyncClient(transport=httpx.ASGITransport(app))`, com o mesmo `Authorization: Bearer` do
  cliente e o cabeçalho interno `X-Sociman-Via: mcp`. A chamada passa por todas as dependências,
  validações, histórico e regras, e o servidor MCP não toca no banco (FR-011). O `httpx` já é
  dependência.
- **Por quê:** é a opção A da clarificação (sem serviço novo, princípio VIII). A ponte ASGI evita a ida
  e volta pela rede e pelo edge e mantém a regra de negócio num lugar só.
- **Alternativas:**
  - **Chamar os services Python direto:** pula as dependências (`RequireUser`, conversões, códigos
    de erro) e duplicaria a montagem das respostas. Recusado.
  - **Chamar pelo edge com HTTP real:** o edge aplicaria o `limit_req` duas vezes e acrescentaria
    latência à toa.
  - **Serviço `mcp` separado** e **stdio:** recusados na clarificação.

## R4. Credencial: token estático com prefixo identificável e hash SHA-256

- **Decisão:**
  - **Formato:** `smcp_<id>_<segredo>`, onde:
    - `<id>` tem **8 caracteres base32 minúsculos**, é único, fica salvo em claro e identifica o cliente
      (inclusive no log, sem expor nada);
    - `<segredo>` tem **32 bytes** de `secrets.token_bytes`, em base64url sem padding (43 caracteres).
  - **Armazenamento:** `token_hash = SHA-256(token completo)` (32 bytes, `bytea`). O valor nunca é
    salvo nem logado.
  - **Verificação:** pelo `<id>`, carrega o cliente; calcula o hash do token recebido e compara com
    **`hmac.compare_digest`** (tempo constante). O `<id>` inexistente segue o mesmo caminho, com um
    hash fictício, para não revelar pelo tempo de resposta se o cliente existe (FR-026).
  - **Rotação:** gera um token novo com **`<id>` novo**, para o log distinguir as gerações. O hash antigo é substituído na mesma transação, e a mudança entra no
    histórico com `details.rotacao = true`, sem hash.
  - O `check:secrets` ganha o padrão `smcp_[a-z2-7]{8}_[A-Za-z0-9_-]{43}`, e o log de acesso do edge
    não registra o `Authorization` (já não registra).
- **Por quê:**
  - O token tem 256 bits aleatórios, então um hash rápido basta: um hash lento (argon2) só protege
    segredo de baixa entropia e custaria dezenas de ms em **toda** chamada.
  - O prefixo `smcp_` permite varredura de vazamento e diferencia o token MCP do JWT da sessão na
    mesma dependência de autenticação.
- **Alternativas:**
  - **argon2** (já usado para senhas): lento por chamada, sem ganho para um token aleatório.
  - **HMAC com uma "pimenta" do servidor:** é mais um segredo para guardar junto do backup, com ganho
    marginal.
  - **JWT assinado:** não dá para revogar na hora sem lista de revogação. Recusado.

## R5. Ator, portão e a regra "a API decide"

- **Decisão:**
  - **Ator:** o `Actor` ganha `mcp_client_id` e `mcp_escopo`. O `_actor_from_request` reconhece um
    Bearer `smcp_…` e devolve `Actor(kind="mcp_client", user_id=None, user=None, …)`.
  - **Portão:** antes de devolver o ator, o **portão** (`mcp/portao.py`) confere, nesta ordem, e
    recusa com o código indicado:
    1. o interruptor geral (`MCP_HABILITADO` e `mcp_config.habilitado`) → 403 `mcp_desligado`;
    2. a situação do cliente (revogado ou vencido → 401; suspenso → 403 `mcp_suspenso`);
    3. o `Origin` ausente (R10);
    4. o `operationId` da rota (`request.scope["route"].operation_id`): se está em `PROIBIDAS` → 403
       **`somente_humano`** + evento `publicacao_recusada` (o mesmo padrão do `require_human_owner`);
       se não está em `TOOLS` ou exige escopo maior → 403 `escopo_mcp`;
    5. os limites (R7) → 429 `mcp_limite`.

  O portão vale para **qualquer** requisição com token MCP, tanto pela ponte (R3) quanto direto na
  API. É ele que garante FR-023 e FR-025 mesmo para um agente com `exec` que chame a API com `curl`.
- **Permissões de leitura:** o ator MCP não tem `user`. Logo:
  - o `RequireOwner` o recusa;
  - o código que olha o papel já trata `actor.user is None` como "não dono": são 4 lugares,
    conferidos em `perfis/service_contas.py`, `postagem/service.py`, `analytics/router.py` e
    `publicacao/service.py`.

  Isso dá ao cliente a visão de membro (FR-008, FR-015).
- **Escritas com trava extra:** o `destinos_update` com ator MCP só aceita os estados `pendente` e
  `aprovacao_pedida`; nos demais, devolve 409 `destino_aprovado` (FR-021). O `envios_selecionar` não
  muda.
- **Por quê:** é a defesa em profundidade. O mapa decide o que vira tool, e a API recusa sozinha o
  que não é permitido. Nenhum dos dois depende do texto que o agente manda.
- **Alternativas:**
  - **Só o mapa** (sem portão na API): um agente com acesso à API por fora do MCP escaparia.
    Recusado.
  - **Recusar todo token MCP direto na API:** quebraria o teste de FR-025 e esconderia a recusa em vez
    de registrá-la.

## R6. Histórico com cliente MCP como autor: migração de `entity_versions`

- **Decisão:** na migração `0014_mcp` (`down_revision` = a 0013 da spec 020):
  - `entity_versions` ganha a coluna `actor_mcp_client_id uuid NULL` com FK para `mcp_clientes(id)`
    e o CHECK `ck_entity_versions_ator`:
    `(actor_kind = 'mcp_client') = (actor_mcp_client_id IS NOT NULL)`;
  - `security_events` ganha a mesma coluna e o mesmo CHECK, para as recusas e os eventos de
    autenticação MCP;
  - `history.record` e `auth.events.record_event` gravam `actor.mcp_client_id`, e o `ActorLike` ganha
    o atributo.

  O `actor_user_id` continua com FK para `users` e fica nulo para o ator MCP. Os `created_by` e
  `updated_by` (`AuditMixin`) também ficam nulos nas linhas criadas pelo MCP: o autor de verdade está
  no histórico, como já acontece no `envios` ("o autor do envio fica no histórico").
- **Leitura:** as respostas de `*_versions` ganham `autor: { tipo: "usuario" | "mcp_client" | "sistema",
  id, nome }`, e o SPA mostra o selo "Agente: <nome>" (FR-022). A reversão não muda: é sempre do dono
  humano.
- **Por quê:** uma FK por tipo de ator mantém a integridade sem apagar nada, e o CHECK impede um
  `mcp_client` sem cliente ou um cliente com outro `actor_kind`.
- **Alternativas:**
  - **Um usuário "fantasma" em `users` por cliente:** misturaria agentes com pessoas (login,
    papel, e-mail), e o cliente apareceria como "usuário". Recusado.
  - **Guardar o cliente só em `details`:** fica sem integridade referencial e não dá para filtrar
    direito.

## R7. Limites de uso: Redis na aplicação e `limit_req` no edge

- **Decisão:**
  - **Aplicação (a fonte da verdade, por cliente):** janela fixa no Redis, no mesmo padrão do
    `auth/rate_limit.py`:
    - `mcp:min:{cliente}:{minuto}`, até `limite_por_minuto` (padrão 60), com TTL de 60 s;
    - `mcp:esc:{cliente}:{AAAA-MM-DD em America/Sao_Paulo}`, até `limite_escritas_dia` (padrão 200),
      com TTL de 26 h.

    A escrita é o `Tool.escrita` do mapa. Ao estourar, a resposta é 429 `mcp_limite` com
    `Retry-After`. O registro grava `limite`, e a tela mostra "no limite" quando houve 429 nos
    últimos 5 min. **Se o Redis falhar, o portão nega (503)**: o mesmo comportamento da sessão, que
    já depende do Redis.
  - **Edge (proteção grossa):** a `location = /mcp` usa a zona `edge_mcp`, por IP, com 10 r/s e
    `burst=20 nodelay`. O `log_format` do edge passa a incluir `$http_mcp_name` (o nome da tool, que o
    cliente da versão 2026-07-28 manda) para diagnóstico.
- **Por quê:** o edge não sabe quem é o cliente (ele não valida o token), então o limite por cliente
  tem de ser na aplicação. O edge só barra rajadas e um cliente quebrado antes de chegar à API.
- **Alternativas:**
  - **`limit_req` com chave `$http_mcp_name`:** limitaria por tool para todos os clientes juntos (um
    agente em loop travaria os outros) e não funciona com clientes 2025-11-25, que não mandam o
    cabeçalho. Recusado como limite; o cabeçalho fica só no log.
  - **Chave `$http_authorization` no edge:** poria o token na memória compartilhada do nginx.
    Recusado.
  - **Contador no PostgreSQL:** escreve no banco a cada chamada. O Redis já existe para isso.

## R8. Registro de chamadas: tabela só de inserção, gravada na API

- **Decisão:**
  - A tabela **`mcp_chamadas`** tem o trigger `mcp_chamadas_so_insercao` (o mesmo padrão de
    `metricas_so_insercao`: UPDATE e DELETE levantam erro; o `TRUNCATE` do `reset-db` e dos testes
    continua valendo).
  - **Onde se grava:** num middleware ASGI da API, para toda requisição cujo ator é `mcp_client`. O
    portão põe em `request.state` o cliente, o operationId e a via (`mcp`, se veio a marca da ponte;
    senão, `api`). O middleware grava **depois** da resposta, numa sessão própria já commitada (como o
    `registrar_recusa`): resultado (`ok`, `erro`, `recusada`, `limite`), status, código do erro,
    duração e, nas escritas, a entidade alterada (tirada da resposta: `id` e tipo do mapa).
  - O próprio servidor MCP grava as falhas que não chegam à API: `nao_autenticado` (com o cliente,
    quando o `<id>` existe), tool desconhecida e erro de protocolo.
  - **Resumo dos argumentos:** só os parâmetros da tool. Chaves com nome sensível (`token`,
    `senha`, `password`, `authorization`, `secret`) são trocadas por `"***"`, cada string é cortada em
    200 caracteres e o JSON inteiro em 2 KB.
  - **Retenção:** sem prazo no primeiro corte (Assumptions da spec). Um índice por
    `(cliente_id, ocorreu_em desc)` e outro por `ocorreu_em` atendem os filtros.
- **Por quê:**
  - Gravar num ponto só (a API) cobre a via MCP e a via direta.
  - Gravar depois da resposta, em sessão própria, sobrevive ao rollback das recusas (armadilha 8 do
    CLAUDE.md).
  - O "só inserção" atende o VII: o registro é prova, não estado.
- **Alternativas:**
  - **Gravar no `call_tool`:** perderia as chamadas diretas na API. Recusado.
  - **Log em arquivo:** o dono não veria pela tela, e ficaria sem filtro. Recusado.

## R9. Edge (nginx)

- **Decisão:** criar uma `location = /mcp` com:
  - `client_max_body_size 1m` e `limit_req zone=edge_mcp burst=20 nodelay`;
  - `proxy_buffering off` e `proxy_read_timeout 120s` (respostas SSE, caso o cliente peça);
  - `proxy_set_header X-Sociman-Via ""`, para apagar qualquer marca da ponte vinda de fora.

  O `X-Sociman-Via` também é apagado em `location /api/` e nas outras `location` da API, porque só a
  ponte em processo (que não passa pelo edge) pode trazer essa marca. GET e DELETE em `/mcp` seguem
  para o app, que responde 405 conforme a versão do protocolo. Depois de mudar o template:
  `docker compose restart edge` (armadilha 13).
- **Por quê:** o MCP tem regras de corpo e de buffering diferentes das rotas REST, e a marca de via não
  pode ser forjada de fora.
- **Alternativas:** usar a `location /api/` existente. Recusado: o buffering e o limite são diferentes.

## R10. Validação de `Origin` (DNS rebinding)

- **Decisão:**
  - No endpoint `/mcp`: se o cabeçalho `Origin` vier e não estiver em `MCP_ORIGENS_PERMITIDAS`
    (`.env`, **vazio por padrão**), a resposta é **403** antes de qualquer autenticação. Clientes
    não-navegador (OpenClaw, Claude Code) não mandam `Origin`.
  - No portão (R5): um token MCP com `Origin` presente é recusado (403 `mcp_origem`), porque nenhum
    navegador deveria usar um token de agente.
- **Por quê:** o spec do Streamable HTTP exige (DEVE) a validação, e o SPA nunca fala com o `/mcp`.
- **Alternativas:** aceitar as origens do SPA. Isso não serve a nenhum uso e abre superfície.

## R11. Interruptor geral em dois níveis

- **Decisão:** espelhar a 015:
  - `MCP_HABILITADO` no `.env` (padrão `false`), lido pela configuração;
  - a tabela de linha única **`mcp_config`** (`id = 1`, `habilitado bool default false`, com
    `version` e histórico, `entity_type = "mcp_config"`), alterada por `PUT /api/mcp/config` só pelo
    **dono humano** (`RequireHumanOwner`).

  Os dois têm de estar ligados.
  - Com o `.env` desligado: o `/mcp` responde 503 com "acesso MCP desligado pelo dono" (erro
    JSON-RPC sem `id`), o portão da API recusa o token MCP com 403 `mcp_desligado` e a tela mostra
    "Desligado no servidor (.env)", com o botão inativo.
  - Com só a tela desligada: as mesmas recusas, com a tela mostrando "Desligado".

  Toda recusa por interruptor vai para o registro.
- **Por quê:** é o mesmo modelo mental do "Envios automáticos". O `.env` é a trava de quem administra o
  host, e a tela é o botão do dia a dia.
- **Alternativas:** um nível só (`.env`): o dono teria de reiniciar a API para cortar um agente. Recusado.

## R12. Anotações e propostas (domínio novo, pequeno)

- **Decisão:**
  - Criar o pacote **`anotacoes/`** (models, service, schemas e router `/api/anotacoes…`, com
    `operationId` `anotacoes_*`) e o `entity_type = "anotacao"`.
  - **Quem cria:** qualquer ator com `RequireUser` (humano ou MCP com escopo `propostas`).
  - **Quem edita e arquiva:** só o autor, e só com a anotação `aberta`.
  - **Quem descarta:** só um humano (`RequireHuman`, uma dependência nova: `kind == "user"`, com
    qualquer papel). Um ator MCP recebe `somente_humano`, e a operação fica em `PROIBIDAS`.
  - **Aplicar:** acontece no save normal do destino. O `PATCH /api/destinos/{id}` aceita
    `propostaId` (opcional) no corpo; o service confere que a proposta é `proposta_texto` do mesmo
    destino, está `aberta` e que o ator é humano. Feito isso, marca a proposta `aplicada` (com quem
    aplicou e quando) e grava `details.proposta = {id, clienteId}` no histórico do destino. É o mesmo
    caminho do `ia` da 008.
  - **Alvos aceitos:** `perfil`, `conta`, `canal`, `video_fonte`, `corte`, `conteudo` e `destino`.
    A `proposta_texto` só é aceita em `destino` no primeiro corte. Os outros alvos levam só
    `observacao`.
  - **Revert:** `anotacoes_revert`, só do dono humano.
- **Por quê:** é o mínimo para a US4 sem dar ao agente escrita direta nos textos aprovados. Reaproveita
  o padrão "aplicar = preencher o formulário" que o dono já conhece da 008.
- **Alternativas:** usar `ia_chamadas` para as propostas. Ela mede custo e desfecho de chamadas do
  assistente, tem outro dono de regras e não tem alvo genérico. Recusado.

## R13. Gestão de clientes (rotas e tela)

- **Decisão:**
  - As rotas `/api/mcp/clientes…` e `/api/mcp/config` usam `RequireHumanOwner` (inclusive para ler
    clientes e o registro, porque a tela é só de dono e um token MCP nunca as alcança). Todas ficam
    em `PROIBIDAS` no mapa.
  - A criação e a rotação devolvem `token` **uma vez** no corpo da resposta, com `Cache-Control:
    no-store`. As demais respostas nunca trazem o token nem o hash.
  - **Tela:** `/app/configuracoes/agentes`, com duas abas:
    - **Clientes:** tabela, "Novo cliente", diálogo que mostra o token uma vez com "Copiar",
      suspender, reativar, rotacionar e revogar (estes dois com AlertDialog);
    - **Registro:** a DataTable de `mcp_chamadas`, com filtros.

    O cartão do interruptor fica no topo.
  - A caixa **"Propostas dos agentes"** fica em `/app/propostas` (menu, com contador de abertas), e a
    lista de anotações aparece no detalhe de cada item.
- **Por quê:** segue o desenho da 015 (conexões e interruptor) e da 008 (registro). Usa só componentes
  existentes (DataTable, AlertDialog, Field).

## R14. OpenClaw 2026.9.6: como cada agente conecta (feito pelo dono)

- **Decisão (guia no quickstart §4):** um **servidor por agente** em `mcp.servers`, com nome
  `sociman-<agente>`, transporte `streamable-http`, URL `http://localhost:8180/mcp` e o cabeçalho
  `Authorization: Bearer <token do cliente daquele agente>`. A credencial fica **fora do
  `openclaw.json`**:
  - o caminho preferido é uma referência de ambiente (`${SOCIMAN_MCP_<AGENTE>}`), com as variáveis num
    arquivo 600 em `~/.config/openclaw/sociman-mcp.env`, carregado por um drop-in do serviço systemd
    do gateway (o mesmo padrão do `youtube.env`);
  - **a verificar:** se o `mcp.servers.*.headers` aceita a referência. O `openclaw mcp doctor` avisa
    quando o cabeçalho é literal. A doc confirma `${VAR}` e SecretRef para o `env` de servidores MCP,
    mas não diz nada explícito sobre `headers`. Se não aceitar, o plano B é o cabeçalho literal, com
    `openclaw.json` 600 e o aviso aceito no quickstart.
- **Restringir ao agente:** cada agente recebe o seu servidor na política de tools dele
  (`agents.entries.<id>.tools`) e nega os `sociman-*` dos outros. **A verificar na sonda:** como o
  runtime `claude-cli` projeta os servidores (`bundleMcp`). Se não for possível restringir por agente,
  a proteção continua no servidor: cada credencial só faz o que o escopo dela permite e fica
  registrada com o nome do cliente.
- **O que só o dono faz no `openclaw.json`**, seguindo as regras do projeto pai:
  1. `openclaw gateway stop --force`;
  2. backup `cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak-$(date +%Y%m%d%H%M%S)`;
  3. `openclaw mcp add …` / `openclaw mcp set …` para cada agente;
  4. `openclaw config validate` e `openclaw mcp doctor --probe`;
  5. `openclaw gateway start`.

  O arquivo nunca é exibido inteiro (só `grep -n -A5 mcp` com os valores mascarados). Nenhum agente
  edita o próprio acesso.
- **Por quê:** a doc do OpenClaw recomenda credencial por agente no servidor MCP, porque a lista de
  skills não é fronteira de autorização. Com isso, a identidade fica no SociMan, e não na boa vontade
  do cliente.
- **Alternativas:**
  - **Um servidor só, com uma credencial para todos:** perde a autoria por agente (VII). Recusado.
  - **OAuth `per-requester`:** foi recusado na clarificação.

### Resultado da sonda (T006, 2026-10-05, só leitura da doc e do pacote instalado)

1. **Versão do cliente do OpenClaw:** o pacote 2026.9.6 traz o `@modelcontextprotocol/sdk` **1.30.0**,
   com `LATEST_PROTOCOL_VERSION = '2025-11-25'` (conferido em `node_modules`). O servidor atende essa
   versão pelo `initialize` (testado em `test_mcp_protocolo.py`, modo `legacy`). A versão do cliente do
   runtime `claude-cli` só se confirma com o gateway real (quickstart §4.6, com o dono).
2. **`${VAR}` em `headers`:** a doc do gateway (`docs/gateway/config-extensions.md`) mostra
   `headers: { Authorization: "Bearer ${MCP_REMOTE_TOKEN}" }` num servidor `streamable-http`, e o
   `docs/cli/mcp/transports.md` diz que o `mcp doctor` só avisa de valores **literais** em cabeçalhos
   sensíveis. Então o caminho preferido (variável no `EnvironmentFile` do serviço) é suportado pela doc;
   a confirmação final é o `openclaw mcp doctor --probe` sem o aviso de cabeçalho literal (§4.5).
3. **Restringir um servidor a um agente:** `agents.entries.<id>.tools.allow/deny` também valem para os
   servidores MCP nativos, com nomes `<servidor-seguro>__<tool>` (`docs/gateway/cli-backends.md`,
   "Bundle MCP overlays"); no `claude-cli`, o OpenClaw omite o servidor ou manda `--disallowedTools`.
   Logo, dá para negar os `sociman…__*` dos outros agentes na política de cada um. O nome "seguro" exato
   do servidor (hífen vira `_`?) se confere com `openclaw mcp probe <servidor>` na sonda; o guia
   (`docs/guia-mcp-openclaw.md`) usa nomes só com letras e `_` (`sociman_cacador`) para evitar a dúvida.

