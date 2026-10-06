# Quickstart: validar o MCP (009)

Este é o roteiro de validação de ponta a ponta, um passo por vez, com o comando, uma linha de
explicação e o resultado esperado. A forma das rotas está em [contracts/http-api.md](contracts/http-api.md)
e em [contracts/mcp.md](contracts/mcp.md). As tabelas estão em [data-model.md](data-model.md).

## 0. Pré-requisitos

- A stack de dev no ar: `docker compose up -d` e `curl http://localhost:8180/api/health` → `ok`.
- A migração aplicada: `docker compose exec api uv run alembic current` mostra a `0014_mcp`.
- O `.env` da raiz com `MCP_HABILITADO=true`, seguido de `docker compose up -d api agendador` para
  recriar os containers.
- O edge recarregado depois da mudança no template: `docker compose restart edge`.
- Um login de dono no SPA. Para o passo 3.5, também um login de membro.

## 1. Testes automatizados

```bash
npm run test:api -- tests/ -k "mcp or anotacoes or constitution or history" -q   # stack efêmera
docker compose exec -T api uv run ruff check .
npm run gen:contract && npm run check:web      # contrato + mcp-tools.json, tipos, build, CSP, bundle, segredos
flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/mcp.spec.ts e2e/propostas.spec.ts
```

**Esperado:** tudo verde. O pytest inclui:

- `test_mcp_mapa.py`: toda operação classificada, nenhuma PROIBIDA vira tool e toda rota
  `RequireHumanOwner` está em PROIBIDAS (SC-003);
- `test_mcp_proibidas.py`: cada operação PROIBIDA chamada com um token MCP real, tanto pela tool quanto
  direto na API, devolve 403 `somente_humano` e grava o evento com o cliente (SC-002);
- `test_mcp_protocolo.py`: um cliente MCP do SDK, em processo, nas versões 2025-11-25 e 2026-07-28, faz
  `tools/list` por escopo e `tools/call` de leitura e de escrita, e recebe os erros de execução;
- `test_mcp_credenciais.py`: token mostrado só uma vez, hash, rotação e revogação imediatas, vencimento
  e tempo constante para um `<id>` inexistente;
- `test_mcp_limites.py`: o 61º pedido no minuto recebe 429, o limite diário de escritas vale, e o Redis
  fora do ar dá 503;
- `test_mcp_registro.py`: só inserção (UPDATE e DELETE falham), argumentos sem segredo, via `mcp`/`api`;
- `test_anotacoes_*.py` e `test_destinos_mcp.py`: a trava `destino_aprovado`, o `propostaId` só para
  humano, e o histórico com `actor_mcp_client_id` e reversão pelo dono (SC-004);
- o `check:secrets` passa com o padrão `smcp_` e nenhum token aparece nos artefatos de teste (SC-007).

## 2. Criar clientes (US1)

1. Abra `/app/configuracoes/agentes`. **Esperado:** o cartão "MCP desligado" (a tela está desligada
   por padrão) e a lista vazia.
2. Ligue o interruptor. **Esperado:** "MCP ligado", com o histórico registrando você.
3. Clique em "Novo cliente", com nome "Caçador" e escopo "leitura e propostas". **Esperado:** o diálogo
   mostra `smcp_…` uma vez, com "Copiar" e o aviso. Fechou o diálogo, o token não aparece mais.
4. Crie também "Analista" com escopo "só leitura".
5. Guarde os dois tokens num arquivo temporário 600, fora do repositório:
   `install -m 600 /dev/null ~/.config/openclaw/sociman-mcp.env`, e edite com
   `SOCIMAN_MCP_CACADOR=…` e `SOCIMAN_MCP_ANALISTA=…`. Nunca cole o token no chat.

## 3. Sondar o endpoint direto (US2, US3, US5)

Carregue o token na shell sem mostrá-lo: `set -a; . ~/.config/openclaw/sociman-mcp.env; set +a`.

1. Sem token: `curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8180/mcp`
   → **401**.
2. Com uma origem de navegador:
   `curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Origin: http://evil.example' -H "Authorization: Bearer $SOCIMAN_MCP_ANALISTA" http://localhost:8180/mcp`
   → **403**.
3. Listar as tools com o cliente oficial de inspeção (sem instalar nada no projeto):
   `npx -y @modelcontextprotocol/inspector --cli http://localhost:8180/mcp --transport http --header "Authorization: Bearer $SOCIMAN_MCP_ANALISTA" --method tools/list | jq '.tools | length'`
   → **62** (só leitura). Com o `$SOCIMAN_MCP_CACADOR` → **67**. As flags do inspector mudam entre
   versões: confira com `--help` antes. A alternativa é o script `apps/api/scripts/mcp_sonda.py`
   (tarefa da implementação), que usa o cliente do SDK `mcp`.
4. Uma leitura: `… --method tools/call --tool-name perfis_list | jq '.structuredContent.perfis | length'`
   → igual ao que a tela de perfis mostra.
5. Uma operação proibida direto na API:
   `curl -s -X POST -H "Authorization: Bearer $SOCIMAN_MCP_CACADOR" -H 'Content-Type: application/json' -d '{"version":1}' http://localhost:8180/api/destinos/<id>/aprovar | jq .code`
   → `"somente_humano"`. Em `/app/seguranca`, aparece o evento `publicacao_recusada`
   com "Agente: Caçador".
6. Escopo: com o Analista, `… --tool-name anotacoes_create …` → erro de execução "escopo insuficiente" (`escopo_mcp`). Direto na API, a resposta é 403
   `escopo_mcp`.
7. Limite: ajuste o Analista para 5 chamadas por minuto na tela e rode 6 leituras seguidas → a 6ª recebe
   `mcp_limite` com `retryAfterS`.
8. Registro: na aba **Registro**, filtre por "Caçador" → as chamadas dos passos acima, com resultado,
   via (`mcp` ou `api`) e duração, e sem o token em lugar nenhum.
9. Revogue o Analista e repita o passo 4 com o token dele → **401**. O cliente continua na lista como
   "revogado".
10. Membro: entre como membro e abra `/app/configuracoes/agentes` → a área não aparece. Direto na API,
    `GET /api/mcp/clientes` responde 403.

## 4. Ligar um agente do OpenClaw (US6), feito pelo dono

Siga as regras do projeto pai: gateway parado e backup antes de editar, nunca `cat` no
`openclaw.json` e nunca `sudo`.

1. `openclaw gateway stop --force`: para o gateway antes de editar a config.
2. `cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak-$(date +%Y%m%d%H%M%S)`: faz o backup.
3. Crie o drop-in que carrega os tokens no serviço:
   `~/.config/systemd/user/openclaw-gateway.service.d/sociman-mcp.conf`, com
   `[Service]` e `EnvironmentFile=%h/.config/openclaw/sociman-mcp.env`. Depois,
   `systemctl --user daemon-reload`.
4. Registre o servidor do agente, sem sondar ainda (o gateway está parado):
   `openclaw mcp add sociman-cacador --url http://localhost:8180/mcp --transport streamable-http --header 'Authorization=Bearer ${SOCIMAN_MCP_CACADOR}' --no-probe`
5. `openclaw gateway start` e depois `openclaw mcp doctor sociman-cacador --probe`. **Esperado:** a
   conexão funciona e as 67 tools aparecem.
   - **A verificar aqui:** se o `${SOCIMAN_MCP_CACADOR}` foi resolvido no cabeçalho. O doctor não pode
     avisar "literal sensitive header", e a sonda não pode dar 401.
   - Se o OpenClaw não resolver variável em `headers`, use o plano B: o cabeçalho literal, com
     `chmod 600 ~/.openclaw/openclaw.json` e o aviso do doctor anotado como aceito. Registre a
     decisão no CLAUDE.md do projeto pai.
6. `openclaw mcp probe sociman-cacador --json | jq '.protocolVersion'`: anote a versão negociada (a
   esperada é `2025-11-25`, a do SDK 1.30.0 do OpenClaw).
7. Restrinja o servidor ao agente: na política de tools do `cacador`, permita `sociman-cacador` e
   negue os outros `sociman-*`. Depois, `openclaw config validate`.
   - **A verificar:** como o runtime `claude-cli` projeta o servidor (o `bundleMcp`). Pergunte a outro
     agente (ex.: o `pesquisador`) se ele vê as tools do `sociman-cacador`: ele não deve ver.
   - Se não houver como restringir por agente, anote. A proteção continua no servidor (escopo e autoria
     por credencial), mas o dono passa a saber que outro agente poderia usar aquela credencial.
8. Teste real, sem `--deliver`:
   `openclaw agent --agent cacador -m "Use o SociMan: quais vídeos-fonte do perfil <slug> ainda não têm envio? Liste 5."`.
   **Esperado:** a resposta tem os dados do SociMan, e o Registro mostra as chamadas com "Caçador"
   como autor e via `mcp` (SC-008).

## 5. Propostas (US4)

1. Peça ao `cacador`: "selecione o vídeo-fonte <id> para corte no perfil <slug>". **Esperado:** em
   "Gerar cortes", aparece um envio `selecionado` com o selo "Agente: Caçador" no histórico, e nada é
   enviado ao OpenShorts.
2. Peça uma proposta de legenda para um destino em revisão. **Esperado:** a proposta aparece em
   `/app/propostas` e no destino, e os textos do destino não mudam.
3. Clique em "Aplicar" → o formulário é preenchido → "Salvar". **Esperado:** o histórico do destino
   mostra você como autor e "a partir da proposta do Caçador", e a proposta fica "aplicada".
4. Aprove o destino e peça ao agente para editar a legenda. **Esperado:** a recusa
   `destino_aprovado` vem com a sugestão de gravar uma proposta, e nada muda.
5. Reverta, pelo histórico, uma edição feita pelo agente num destino pendente. **Esperado:** volta ao
   estado anterior, com você como autor da reversão.

## 6. Interruptor (FR-007)

1. Desligue o interruptor na tela e repita o passo 3.4. **Esperado:** "acesso MCP desligado pelo dono"
   e uma linha `recusada` no registro.
2. Ligue de novo, ponha `MCP_HABILITADO=false` no `.env` e recrie a API. **Esperado:** o endpoint
   responde 503 e a tela mostra "Desligado no servidor (.env)", com o botão inativo.
