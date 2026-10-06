# Guia: ligar os agentes do OpenClaw ao MCP do SociMan (spec 009)

Este é o passo a passo do dia a dia, **um passo por vez**: comando, uma linha de explicação, rodar,
conferir. Quem faz é o **dono**. Nenhum agente edita o próprio acesso nem o `~/.openclaw/openclaw.json`.

Regras do projeto pai que valem aqui:

- gateway parado e backup **antes** de editar o `openclaw.json`;
- nunca `cat` no `openclaw.json` inteiro (use `grep -n -A5 mcp` e mascare os valores);
- nunca `sudo`;
- nunca cole um token `smcp_…` no chat, em commit ou em arquivo do repositório.

## 0. Antes de começar

1. `grep -c '^MCP_HABILITADO=true' .env` (na raiz do SociMan): o nível do servidor precisa estar
   ligado (`MCP_HABILITADO=true`). Mudou? `docker compose up -d api` para recriar a API.
2. Em `/app/configuracoes/agentes`, ligue o interruptor da tela ("MCP ligado").
3. `curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8180/mcp` → **401** (o endpoint
   está no ar e pede credencial).

## 1. Mapa recomendado de agente → cliente → escopo

| Agente OpenClaw | Cliente no SociMan | Escopo | Servidor no OpenClaw | Variável |
|---|---|---|---|---|
| `gestor` | Gestor | leitura e propostas | `sociman_gestor` | `SOCIMAN_MCP_GESTOR` |
| `cacador` | Caçador | leitura e propostas (selecionar vídeo-fonte) | `sociman_cacador` | `SOCIMAN_MCP_CACADOR` |
| `planejador` | Planejador | leitura e propostas | `sociman_planejador` | `SOCIMAN_MCP_PLANEJADOR` |
| `revisor` | Revisor | leitura e propostas (anotações) | `sociman_revisor` | `SOCIMAN_MCP_REVISOR` |
| `shop-roteirista` | Shop roteirista | leitura e propostas | `sociman_shop_roteirista` | `SOCIMAN_MCP_SHOP_ROTEIRISTA` |
| `pesquisador`, `estrategista`, `analista`, `produtor`, `shop-analista`, `shop-diretor` | um cliente cada | só leitura | `sociman_<agente>` | `SOCIMAN_MCP_<AGENTE>` |

Uma credencial **por agente**: o registro mostra quem fez o quê, e revogar um não corta os outros. Os
nomes dos servidores usam só letras e `_` porque o OpenClaw monta os nomes das tools como
`<servidor>__<tool>`.

## 2. Criar o cliente e guardar a credencial (fora do `openclaw.json`)

1. Em `/app/configuracoes/agentes` → **Novo cliente**: nome (ex.: "Caçador"), escopo e limites. O
   diálogo mostra o token **uma vez**: clique em "Copiar".
2. `install -m 600 /dev/null ~/.config/openclaw/sociman-mcp.env` (só na primeira vez): cria o arquivo de
   tokens com permissão 600.
3. Abra o arquivo num editor e acrescente a linha `SOCIMAN_MCP_CACADOR=<cole aqui>`. Nada de `echo` com
   o token na linha de comando (ele iria para o histórico do shell).
4. `stat -c '%a' ~/.config/openclaw/sociman-mcp.env` → `600`.

## 3. Carregar os tokens no serviço do gateway (uma vez)

1. `openclaw gateway stop --force`: para o gateway antes de mexer na configuração.
2. `cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak-$(date +%Y%m%d%H%M%S)`: backup.
3. Crie `~/.config/systemd/user/openclaw-gateway.service.d/sociman-mcp.conf` com:

   ```ini
   [Service]
   EnvironmentFile=%h/.config/openclaw/sociman-mcp.env
   ```

   É o mesmo padrão do `youtube.conf`.
4. `systemctl --user daemon-reload`: o systemd relê o drop-in.

## 4. Registrar o servidor do agente

1. Registre sem sondar (o gateway está parado). As aspas simples impedem o shell de expandir a variável:
   quem resolve o `${…}` é o OpenClaw.

   ```bash
   openclaw mcp add sociman_cacador --url http://localhost:8180/mcp --transport streamable-http \
     --header 'Authorization=Bearer ${SOCIMAN_MCP_CACADOR}' --no-probe
   ```

2. `openclaw config validate`: confere o arquivo.
3. `openclaw gateway start` e depois `openclaw mcp doctor sociman_cacador --probe`.
   **Esperado:** conecta, lista as tools do escopo (67 com "leitura e propostas", 62 com "só leitura") e
   **não** avisa "literal sensitive header".
   - **Plano B** (se o doctor acusar 401 ou o `${…}` não for resolvido): gateway parado, backup, troque o
     cabeçalho pelo valor literal (`openclaw mcp unset` + `openclaw mcp add … --header 'Authorization=Bearer <token>'`, digitado no terminal, sem colar em chat), rode `chmod 600 ~/.openclaw/openclaw.json` e
     anote no `CLAUDE.md` do projeto pai que o aviso do doctor foi aceito.
4. `openclaw mcp probe sociman_cacador --json | jq '.protocolVersion'`: anote a versão negociada
   (esperada: `2025-11-25`).

## 5. Restringir o servidor ao agente

1. `openclaw mcp probe sociman_cacador`: confira as tools e o prefixo que o OpenClaw usa na política
   (esperado `sociman_cacador__perfis_list`).
2. Gateway parado e backup (passos 3.1 e 3.2). Na política de tools de **cada outro** agente, negue o
   servidor do caçador; no caçador, negue os dos outros. Exemplo para o `pesquisador`:
   `agents.entries.pesquisador.tools.deny: ["sociman_cacador__*", "sociman_gestor__*", …]`.
3. `openclaw config validate` e `openclaw gateway start`.
4. Confira: pergunte ao `pesquisador` se ele vê tools do `sociman_cacador` → não deve ver.
   Se não houver como restringir, anote: a proteção continua no SociMan (escopo e autoria por
   credencial), mas outro agente poderia usar aquela credencial.

## 6. Teste real

`openclaw agent --agent cacador -m "Use o SociMan: quais vídeos-fonte do perfil <slug> ainda não têm envio? Liste 5."`
(sem `--deliver`). **Esperado:** a resposta tem os dados do SociMan, e a aba **Registro** de
`/app/configuracoes/agentes` mostra as chamadas com "Caçador" e via `mcp`.

Sonda sem o OpenClaw (opcional), sem mostrar o token:

```bash
set -a; . ~/.config/openclaw/sociman-mcp.env; set +a
SOCIMAN_MCP_TOKEN="$SOCIMAN_MCP_CACADOR" uv run --directory apps/api python scripts/mcp_sonda.py \
  --modo legacy --tool perfis_list
```

Pela rede de casa: `--url https://192.168.86.47:8543/mcp --ca docker/certs/ca/sociman-ca.crt`.

## 7. Rotacionar ou revogar (sem mexer no resto da config)

- **Credencial vazou ou perdeu:** em `/app/configuracoes/agentes`, **Rotacionar** no cliente. A antiga
  para de valer na hora. Troque só a linha do agente em `~/.config/openclaw/sociman-mcp.env` e rode
  `systemctl --user restart openclaw-gateway.service`. O `openclaw.json` não muda (ele só tem o
  `${SOCIMAN_MCP_…}`).
- **Tirar um agente:** **Revogar** (final; para voltar, crie outro cliente). Depois, com o gateway
  parado e backup, `openclaw mcp unset sociman_<agente>` e apague a linha do arquivo de tokens.
- **Pausar todo mundo:** o interruptor da tela. Para cortar no servidor, `MCP_HABILITADO=false` no
  `.env` e `docker compose up -d api`.

## O que os agentes podem e não podem fazer

- **Só leitura:** perfis, contas, kit, guia, assets, canais e vídeos-fonte, envios, cortes, conteúdos
  e destinos, calendário, métricas e analytics, histórico e links de mídia.
- **Leitura e propostas:** também anotações e propostas de texto, selecionar vídeo-fonte para corte (sem
  enviar) e editar os textos de um destino **ainda não aprovado**.
- **Nunca:** conectar conta, aprovar, agendar, publicar, enviar para corte, mudar o direito do canal,
  reverter, mexer em usuários, credenciais, guia ou regras. A API recusa com `somente_humano` e grava o
  evento, mesmo se o agente chamar a API direto.
