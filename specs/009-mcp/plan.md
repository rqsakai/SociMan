# Implementation Plan: Servidor MCP para os agentes

**Branch**: `009-mcp` | **Date**: 2026-10-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-mcp/spec.md`

## Summary

A API ganha um **endpoint MCP** (`/mcp`, Streamable HTTP sem estado, atrás do edge) para os agentes
do OpenClaw lerem o domínio e deixarem propostas. As decisões principais:

- **Biblioteca:** o SDK oficial `mcp` v2, que atende a versão 2026-07-28 e a 2025-11-25 do cliente do
  OpenClaw.
- **Tools:** geradas do OpenAPI por um **mapa explícito** que classifica as 195 operações em tool, fora
  ou proibida. A verificação acusa qualquer operação sem classificação.
- **Execução:** cada tool chama a própria API em processo (ponte ASGI), com o token do cliente. A regra
  de negócio fica só na API.
- **Credencial:** um token `smcp_<id>_<segredo>` por cliente (hash SHA-256), emitido, rotacionado e
  revogado só pelo dono humano.
- **Portão na API:** um portão de autenticação vale para qualquer requisição com token MCP. Ele aplica
  o interruptor de dois níveis, a situação do cliente, a origem, o mapa (PROIBIDA → `somente_humano` +
  evento; fora do escopo → `escopo_mcp`) e os limites no Redis.
- **Histórico:** ganha o autor `mcp_client` (FK nova em `entity_versions` e `security_events`).
- **Registro:** toda chamada vai para a tabela só de inserção `mcp_chamadas`.
- **Propostas:** um domínio pequeno, **anotações e propostas**, que o humano aplica pelo save normal
  do destino.
- **SPA:** ganha a tela de agentes (clientes, interruptor, registro), a caixa "Propostas dos agentes" e
  o selo "Agente: <nome>" no histórico.
- **Guia do OpenClaw:** um servidor por agente, com a credencial fora do `openclaw.json`.

## Technical Context

**Language/Version**: Python 3.12 (API, uv) · TypeScript 5 / React 19 (SPA, Vite 8)

**Primary Dependencies**:
- API: FastAPI, SQLAlchemy 2, Pydantic 2, Redis, `httpx` (já existe, para a ponte ASGI) e **`mcp`
  2.2.x (novo, SDK oficial do protocolo; servidor de baixo nível e transporte Streamable HTTP)**;
- SPA: shadcn/ui, TanStack Query e TanStack Table v9, **sem dependência nova**.

**Storage**: PostgreSQL. Uma migração (`0014_mcp`, depois da 0013 da spec 020) cria 4 tabelas (`mcp_clientes`, `mcp_config`,
`mcp_chamadas` só de inserção e `anotacoes`) e acrescenta `actor_mcp_client_id` em `entity_versions` e
`security_events`. O Redis guarda os contadores de limite.

**Testing**:
- pytest na stack efêmera (`npm run test:api`), incluindo um cliente MCP do SDK em processo nas duas
  versões do protocolo;
- ruff e `npm run check:web` (com o `mcp-tools.json` e o padrão `smcp_` no `check:secrets`);
- Playwright na stack e2e efêmera (`flock /tmp/sociman-e2e.lock npm run test:e2e`);
- a sonda manual com o OpenClaw (quickstart §4).

**Target Platform**: API no Docker (rede de casa). O cliente é o gateway do OpenClaw no mesmo host
(`http://localhost:8180/mcp`) ou na LAN (`https://192.168.86.47:8543/mcp`).

**Project Type**: web (apps/api + apps/web)

**Performance Goals**:
- leitura comum em ≤ 1 s com o volume atual (SC-006);
- autenticação e portão em < 5 ms (um SELECT por `token_id` e um pipeline no Redis);
- `ultimo_uso_em` gravado no máximo 1 vez por minuto por cliente.

**Constraints**:
- nenhum ato humano alcançável por token MCP (I, II, VII);
- nenhuma regra de negócio fora da API;
- o token nunca aparece depois da emissão;
- o `Origin` é validado;
- o endpoint fica só atrás do edge (a porta da API continua sem publicação);
- textos em pt-BR.

**Scale/Scope**: 11 agentes (até ~15 clientes), dezenas a centenas de chamadas por hora. O mapa tem 195
operações, das quais 62 viram tool de leitura e 5 de escrita. São 22 rotas REST novas (clientes,
config, registro, anotações) e 1 rota alterada (`destinos_update`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|---|---|---|
| **I. Publicação só com decisão humana** | ✅ | Conectar conta, aprovar, recusar, agendar (todas as variantes), enviar agora, confirmar envio, tentar de novo, marcar postado e mudar o interruptor de publicação estão em **PROIBIDAS** (contracts/mcp.md). São duas camadas: o mapa não as expõe, e o portão da API recusa com `somente_humano` + `publicacao_recusada` qualquer token MCP que as chame direto (R5). O teste percorre toda a lista com um token real. O `publicacao/` não é importado pelo `mcp/` (guarda em `test_constitution_guards.py`). O `destinos_update` com ator MCP só vale antes da aprovação (FR-021) e nunca regrava um snapshot de publicação |
| **II. Direito é do dono** | ✅ | `canais_direito`, `envios_enviar` (que confirma o aviso de direito), `envios_retry`, `envios_confirmar_qualidade`, `cortes_retry` e `cortes_aplicar_marca` estão em PROIBIDAS. O agente só **seleciona** (envio `selecionado`); o envio com o aviso continua humano e registrado (`direitoNoEnvio`) |
| III. Marca em tokens | ✅ (não afetado) | O kit é só leitura pelo MCP (`kit_get`, `kit_export`); o `kit_update` está em FORA |
| **IV. Contrato é a fonte única** | ✅ | As tools saem do `app.openapi()` (nome = operationId, schemas da operação). O mapa só classifica. O `gen:contract` gera `packages/contract/mcp-tools.json`, e o `check:contract` acusa divergência. O `test_mcp_mapa.py` falha com operação sem classificação, id inexistente ou PROIBIDA mapeada (R2). As rotas novas entram no OpenAPI e no cliente do SPA como sempre |
| **V. Segurança e segredos** | ✅ | O token tem 256 bits, guarda só o SHA-256, é comparado em tempo constante e é mostrado 1 vez com `no-store` (R4). O `check:secrets` ganha o padrão `smcp_`. O `Origin` é validado (R10). O edge apaga `X-Sociman-Via` de fora (R9), e a porta da API continua sem publicação. A CSP não muda (o SPA não fala com o `/mcp`). O registro mascara argumentos sensíveis (R8). No OpenClaw, a credencial fica fora do config (R14) |
| **VI. Testes antes de pronto** | ✅ | pytest com um teste por regra inegociável (I/II: `test_mcp_proibidas.py`; VII: histórico com autor MCP e reversão), protocolo nas duas versões, credenciais, limites, registro e anotações; ruff; `check:web`; e2e `mcp.spec.ts` (tela, token uma vez, revogar, interruptor, membro sem acesso) e `propostas.spec.ts` (aplicar e descartar); sonda real com o OpenClaw (quickstart §4) |
| **VII. Humano no controle** | ✅ | Toda escrita MCP passa pelo `history.record` com `actor_kind = mcp_client` e `actor_mcp_client_id` (CHECK no banco, R6). O selo "Agente: <nome>" aparece no histórico. A reversão é do dono (as `*_revert` estão em PROIBIDAS para o MCP). Anotações e clientes têm versão e histórico, sem DELETE (revogar é estado final). O `mcp_chamadas` é só de inserção. A exceção já aprovada (envio sem revert) é desfeita arquivando o envio, ato humano. **Clientes MCP e interruptor:** as mudanças são desfeitas pela ação inversa (reativar, editar, religar), com histórico. A **revogação é final de propósito** (credencial possivelmente vazada); para voltar, cria-se um cliente novo. Suspender continua reversível. **Exceção aprovada pelo dono em 2026-10-02** (ver Complexity Tracking) |
| **VIII. Simplicidade** | ⚠️ justificado | 1 dependência nova no backend (`mcp`), 4 tabelas e 0 serviço novo (o endpoint fica dentro da API, como decidido na clarificação). Nenhum framework MCP de alto nível, nenhum OAuth, nenhum recurso ou prompt MCP. A dependência nova entra por **emenda 4.1.0 → 4.2.0** ("Servidor MCP: SDK oficial `mcp` (Python), dentro da API, atrás do edge") e pelo **ADR 0003**, aprovados pelo dono em 2026-10-02 (tarefas T002 e T003). Ver Complexity Tracking |

**Reavaliação pós-design:** mantida. O design não abriu nenhuma exceção nova.

Itens a confirmar durante a implementação, sem impacto nos princípios:

1. a versão do protocolo do cliente do runtime `claude-cli`;
2. se o OpenClaw resolve `${VAR}` em `headers` (há o plano B do quickstart §4.5);
3. se dá para restringir um servidor MCP a um único agente.

O item 3, se não der, enfraquece só o isolamento entre agentes do lado do OpenClaw. A autoria e o
escopo continuam garantidos no servidor, e o dono é avisado no guia.

## Project Structure

### Documentation (this feature)

```text
specs/009-mcp/
├── spec.md                 # especificação (clarificada)
├── notas-pesquisa.md       # protocolo MCP 2026-07-28 e cliente do OpenClaw
├── plan.md                 # este arquivo
├── research.md             # R1–R14
├── data-model.md           # tabelas novas, colunas novas, regras
├── quickstart.md           # validação, inclusive a sonda do OpenClaw
├── contracts/
│   ├── http-api.md         # gestão de clientes, config, registro, anotações, mudanças em rotas
│   └── mcp.md              # endpoint /mcp, tools/list, tools/call, classificação das 195 operações
├── checklists/requirements.md
└── tasks.md                # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── pyproject.toml                         # + mcp>=2.2,<3
├── migrations/versions/0014_mcp.py         # 4 tabelas, 2 colunas, CHECKs, trigger só inserção
├── scripts/mcp_sonda.py                   # sonda manual com o cliente do SDK (quickstart §3)
└── src/sociman_api/
    ├── config.py                          # + mcp_habilitado, mcp_origens_permitidas
    ├── main.py                            # monta /mcp, middleware do registro, routers novos
    ├── history.py                         # record() grava actor_mcp_client_id; ActorLike + mcp_client_id
    ├── auth/
    │   ├── deps.py                        # Actor + mcp_client_id/mcp_escopo; _actor_from_request reconhece smcp_; RequireHuman
    │   └── events.py                      # record_event grava actor_mcp_client_id
    ├── mcp/
    │   ├── __init__.py
    │   ├── mapa.py                        # TOOLS / FORA / PROIBIDAS (R2)
    │   ├── ferramentas.py                 # app.openapi() + mapa → definições de tool; export mcp-tools.json
    │   ├── servidor.py                    # Server de baixo nível (list_tools/call_tool), sub-app Streamable HTTP, Origin, 401
    │   ├── ponte.py                       # chamada em processo (httpx.ASGITransport) + recorte de 256 KB + erro → isError
    │   ├── credenciais.py                 # gerar, hash, verificar (compare_digest), token_id
    │   ├── portao.py                      # interruptor, situação, Origin, mapa, limites (R5)
    │   ├── limites.py                     # janelas no Redis (R7)
    │   ├── registro.py                    # middleware de mcp_chamadas + resumo mascarado (R8)
    │   ├── models.py                      # McpCliente, McpConfig, McpChamada
    │   ├── schemas.py
    │   ├── service.py                     # criar, editar, suspender, reativar, rotacionar, revogar, config
    │   └── router.py                      # /api/mcp/* (RequireHumanOwner), operationId mcp_*
    ├── anotacoes/
    │   ├── models.py, schemas.py, service.py, router.py   # /api/anotacoes*, operationId anotacoes_*
    └── postagem/service.py                # update_textos: trava MCP (FR-021) + propostaId (aplicar)
apps/api/tests/
├── unit/test_mcp_mapa.py, test_mcp_credenciais.py, test_constitution_guards.py (+009)
└── integration/test_mcp_protocolo.py, test_mcp_proibidas.py, test_mcp_portao.py, test_mcp_limites.py,
    test_mcp_registro.py, test_mcp_clientes.py, test_anotacoes.py, test_destinos_mcp.py,
    test_history_autor_mcp.py, mcp_helpers.py

packages/contract/mcp-tools.json           # gerado pelo gen:contract (escopos → tools)
scripts/check-contract.mjs + gen:contract  # + geração (exportador Python) e comparação do mcp-tools.json
scripts/check-secrets.mjs                  # + padrão smcp_

docker/nginx/default.conf.template         # location = /mcp, zona edge_mcp, X-Sociman-Via apagado, $http_mcp_name no log

apps/web/src/
├── pages/configuracoes/Agentes.tsx        # abas Clientes | Registro, cartão do interruptor
├── components/mcp/
│   ├── ClientesTable.tsx, NovoClienteDialog.tsx, TokenUmaVezDialog.tsx, ClienteAcoes.tsx
│   └── RegistroChamadasTable.tsx
├── pages/propostas/Propostas.tsx          # caixa "Propostas dos agentes"
├── components/anotacoes/AnotacoesDoItem.tsx, PropostaCard.tsx   # no detalhe de destino, conteúdo, corte, canal…
├── components/VersionHistory.tsx         # (acréscimo) selo "Agente: <nome>" e "a partir da proposta"
└── lib/mcp.ts, lib/anotacoes.ts           # hooks TanStack Query

e2e/mcp.spec.ts, e2e/propostas.spec.ts      # + helper que chama /mcp com o token emitido no teste
docs/guia-mcp-openclaw.md                  # o passo a passo do quickstart §4 para o dia a dia
docs/adr/0003-servidor-mcp.md              # novo ADR (+ linha no docs/adr/README.md)
.specify/memory/constitution.md            # emenda 4.2.0 (Restrições técnicas: Servidor MCP)
CLAUDE.md (SociMan)                        # seção "MCP (desde a spec 009)"
```

**Structure Decision**: web app existente (apps/api + apps/web).

- O pacote `mcp/` cuida do protocolo, das credenciais, do portão e do registro. Ele **não** tem regra
  de domínio: chama a API pela ponte.
- O pacote `anotacoes/` é domínio próprio, com histórico.
- A única mudança em domínio existente é a trava e o `propostaId` em `postagem/service.update_textos`.
- O guarda de constitution ganha duas verificações: o `mcp/` não importa `publicacao` nem services de
  domínio (só `history`, `auth`, `db` e `redis`), e toda rota `RequireHumanOwner` está em `PROIBIDAS`.

## Complexity Tracking

| Violação | Por que é necessária | Alternativa mais simples rejeitada porque |
|---|---|---|
| Dependência nova `mcp` (SDK oficial). Emenda 4.2.0 e ADR 0003 aprovados pelo dono em 2026-10-02 | Falar MCP 2026-07-28 **e** 2025-11-25 (o OpenClaw usa o SDK 1.30.0, da 2025-11-25) com Streamable HTTP. O SDK cobre as duas eras, os cabeçalhos e o JSON-RPC | Implementar o protocolo à mão (duas eras, SSE, validação de cabeçalhos) seria código de protocolo nosso para manter. O FastMCP traz um framework inteiro para usar só o gerador |
| 4 tabelas novas (`mcp_clientes`, `mcp_config`, `mcp_chamadas`, `anotacoes`) | Credencial individual revogável (FR-001…FR-005), interruptor com histórico (FR-007), auditoria só de inserção (FR-028) e propostas sem escrita direta em textos aprovados (FR-018/FR-020) | Guardar os clientes no `.env`: o dono não revogaria pela tela, e não haveria histórico nem autor no banco. Registrar em arquivo: o dono não veria. Usar `ia_chamadas` para propostas: o modelo e o dono das regras são outros (R12) |
| Coluna `actor_mcp_client_id` em `entity_versions` e `security_events` | O VII exige o cliente MCP identificado como autor, com integridade referencial | Um usuário "fantasma" por agente em `users` misturaria agentes com pessoas (login, papel). Guardar só em `details` fica sem FK e sem filtro |
| Revogação de cliente MCP sem reversão (VII: "o dono DEVE poder reverter"). **Aprovada pelo dono em 2026-10-02** | Reverter uma revogação ressuscitaria uma credencial que pode ter vazado; a revogação é um ato de segurança | Permitir `revert` em `mcp_clientes`: reabriria um token comprometido. O dono cria outro cliente em segundos, e o histórico do revogado continua consultável |
