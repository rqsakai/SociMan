# ADR 0003: Servidor MCP dentro da API, com o SDK oficial `mcp`

**Status:** Aceita (2026-10-02, decisão do dono) · **Constitution:** 4.2.0 (Restrições técnicas) ·
**Spec:** 009-mcp (research R1, R3, R4 e R5)

## Contexto
- Os 11 agentes do OpenClaw precisam ler o domínio do SociMan e deixar propostas, sem ganhar nenhum
  ato que a constitution reserva a humanos (princípios I, II e VII).
- O OpenClaw 2026.9.6 fala MCP com o `@modelcontextprotocol/sdk` 1.30.0 (versão de protocolo
  2025-11-25, com `initialize`). A versão vigente do protocolo é a 2026-07-28 (sem estado, com
  `server/discover`). O servidor precisa atender as duas eras.
- O princípio IV exige que as tools saiam do OpenAPI, e o VIII pede o mínimo de peças novas.

## Decisão
- **Biblioteca:** o SDK oficial **`mcp` v2** (Python, `>=2.2,<3`), usando só o `Server` de baixo
  nível (handlers `list_tools` e `call_tool` nossos) e o transporte Streamable HTTP. Nada do servidor
  de alto nível nem do OAuth do SDK.
- **Hospedagem:** **Streamable HTTP sem estado em `/mcp`, dentro da própria API**, montado como
  sub-app ASGI e atrás do edge (`location = /mcp`). Nenhum serviço novo; a porta da API continua sem
  publicação.
- **Tools:** geradas de `app.openapi()` por um **mapa explícito** (`mcp/mapa.py`) que classifica toda
  operação em `TOOLS`, `FORA` ou `PROIBIDAS`. Um teste falha com operação sem classificação.
- **Execução:** cada tool chama a própria API em processo (**ponte ASGI**, `httpx.ASGITransport`), com
  o token do cliente e a marca interna `X-Sociman-Via: mcp`. Nenhuma regra de negócio fora da API.
- **Credencial:** token estático por cliente, `smcp_<8 base32>_<43 base64url>` (256 bits), guardado só
  como SHA-256 e comparado com `hmac.compare_digest`. Emitido, rotacionado e revogado só pelo dono
  humano, e mostrado uma vez.
- **Portão na API:** toda requisição com token MCP passa pelo portão (interruptor em dois níveis,
  situação do cliente, `Origin`, mapa e limites). Operação em `PROIBIDAS` → 403 **`somente_humano`** +
  evento `publicacao_recusada`, pela ponte ou direto na API.
- **Autoria:** o histórico (`entity_versions`) e os eventos de segurança ganham
  `actor_mcp_client_id`, com o CHECK `(actor_kind = 'mcp_client') = (actor_mcp_client_id IS NOT NULL)`.

## Alternativas recusadas
- **FastMCP** (`from_fastapi`/`from_openapi`): traz um framework inteiro (auth, providers, transforms)
  para usar só o gerador, e o escopo e o portão teriam de ser refeitos no modelo dele (VIII).
- **Serviço `mcp` separado** ou **stdio**: recusados na clarificação de 2026-10-02 (serviço a mais;
  credencial no ambiente de cada processo).
- **JSON-RPC à mão:** duas eras de protocolo, cabeçalhos e SSE para manter.

## Consequências
- Uma dependência nova no backend (`mcp`), registrada na constitution 4.2.0.
- Defesa em profundidade: o mapa não expõe atos humanos e a API os recusa sozinha, mesmo para um
  agente com `exec` que chame a API com `curl`.
- **Exceção ao VII aprovada pelo dono em 2026-10-02:** a **revogação** de um cliente MCP é final, sem
  reversão, porque reverter ressuscitaria uma credencial possivelmente vazada. Para voltar, o dono cria
  outro cliente; o histórico do revogado continua consultável. Suspender continua reversível.
- Toda rota nova da API precisa ser classificada no mapa antes de passar nos testes.
