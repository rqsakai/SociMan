# sociman-coletor

O coletor de mercado do SociMan (spec 026, constitution IX). Um serviço Python que roda **no
desktop do dono, fora do Docker**, controla o Chrome real num perfil dedicado, navega como pessoa
pelas páginas que o SociMan pediu e devolve o que viu pela API de ingestão (`/api/coleta/*`).

O que ele **nunca** faz: falar com o banco, o MinIO ou o Redis; chamar a API interna assinada da
rede; clicar em qualquer coisa que escreva na rede (seguir, curtir, comentar, adicionar à vitrine,
comprar, pedir amostra); contornar captcha ou login; gravar em log cookie, token, nome, @, texto de
avaliação ou URL com parâmetros. A lista de ações permitidas é fechada e tem teste estático
(`tests/test_guardas.py`). O contrato completo está em `specs/026-mercado-shop/contracts/coletor.md`.

## Instalação (o dono, no host)

Pré-requisitos: Python 3.12, `uv`, Google Chrome ou Chromium instalado, sessão gráfica.

```bash
cd apps/coletor
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 uv sync        # não baixa navegador: usa o Chrome do sistema
uv run sociman-coletor autoteste --sem-token      # acha o Chrome e confere a sessão gráfica
```

### 1. Configuração local (`~/.config/sociman-coletor/`, modo 700)

`config.toml` (todos os campos opcionais; valores padrão abaixo):

```toml
api_url = "https://192.168.86.47:8543"            # ou "http://localhost:8180" em dev, sem CA
ca_cert = "~/.config/sociman-coletor/sociman-ca.crt"   # a CA da casa; nunca desligue a verificação
chrome_bin = "/usr/bin/google-chrome"             # ou "chromium"; vazio = procura no PATH
perfil_dir = "~/.config/sociman-coletor/chrome-profile"
screenshots = false                               # true só grava em disco local; nunca envia

[limites]            # mesmos nomes do servidor; vale o MENOR (pausas: o MAIOR; janela: interseção)
# paginas_dia = 300
# imagens_dia = 1500
# pausa_min_s = 5
# pausa_max_s = 40
# janela_inicio = 8
# janela_fim = 23

[log]
nivel = "INFO"
arquivo = "~/.local/state/sociman-coletor/coletor.log"
```

### 2. Perfil do Chrome (uma vez)

```bash
uv run sociman-coletor perfil-iniciar
```

Abre o Chrome **sem automação** no perfil dedicado. Faça o login na conta de afiliado e no
Affiliate Center e feche a janela. O coletor não grava nada do login.

### 3. Aceite de risco e token

Em `/app/configuracoes/coleta`: leia o aviso, confirme o aceite de risco, crie um cliente e copie o
token (`scol_…`) **uma única vez** para o arquivo:

```bash
umask 077
printf '%s\n' 'scol_…' > ~/.config/sociman-coletor/token
chmod 600 ~/.config/sociman-coletor/token
uv run sociman-coletor autoteste
```

O coletor recusa iniciar se o arquivo do token tiver modo mais aberto que 600 (`token_permissao`).
O token nunca vai por argumento nem por variável de ambiente.

### 4. Sonda guiada

Com a coleta ligada no servidor (`COLETA_HABILITADO=true` + botão da tela) e **1 link de produto**
colado na aba Mercado de um perfil:

```bash
uv run sociman-coletor dry-run                 # mostra a fila sem reservar nem abrir o Chrome
uv run sociman-coletor uma-vez --limite 1      # 1 página; fecha a rodada com motivo "limite"
```

Esperado: 1 item `gravado` na tela, a ficha, as imagens e a primeira foto. Abra o bruto pela tela e
**confira os nomes dos campos reais** do Affiliate Center brasileiro. O adaptador
(`sociman_coletor/redes/tiktok_shop.py`) nasce com `INTERCEPTAR` vazia e um formato de referência
nos parsers; a sonda preenche os padrões de URL e ajusta os nomes de chave. Depois de ajustar:

```bash
uv run sociman-coletor reprocessar --desde 2026-10-09   # reaplica o parser sem recoletar
```

### 5. Ligar como serviço de usuário

```bash
uv tool install ./apps/coletor                                   # binário em ~/.local/bin
cp apps/coletor/systemd/sociman-coletor.service ~/.config/systemd/user/
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY
systemctl --user enable --now sociman-coletor
journalctl --user -u sociman-coletor -n 50 --no-pager
```

Códigos de saída: 4 (token inválido, escopo ou cliente suspenso) e 5 (protocolo antigo) **não**
reiniciam (`RestartPreventExitStatus=4 5`); resolva na tela ou atualize o coletor.

## Parar, pausar e retomar

- Parar na hora: `uv run sociman-coletor parar` (cria `~/.config/sociman-coletor/PARAR`; com
  `--agora` manda SIGTERM) ou `systemctl --user stop sociman-coletor`. A rodada termina a tarefa
  atual e fecha como "interrompida". `rodar` apaga o `PARAR` ao começar.
- Pausar N horas ou desligar: `/app/configuracoes/coleta`.
- Captcha ou login perdido: o sino avisa; o Chrome fica aberto na página; resolva e clique
  **"Continuar"** na tela. O coletor retoma 60 min depois. Sem clique em 2 h a rodada fecha com
  "pausa vencida".
- Bloqueio suspeito (3 recusas 429/403 seguidas) ou layout mudou (5 páginas sem campos): a rodada
  fecha e o coletor recua 24 h (`estado.json`, `recuoAte`).

## Comandos

| Comando | O que faz |
|---|---|
| `rodar` | laço contínuo do serviço |
| `uma-vez --limite N [--fora-da-janela]` | uma rodada com até N páginas |
| `dry-run [--limite N]` | imprime a fila (sem reserva), sem abrir o Chrome |
| `autoteste [--sem-token]` | config, token, CA, `/api/health`, fila simulada, Chrome, perfil, sessão gráfica, fuso |
| `perfil-iniciar` | abre o Chrome sem CDP para o dono logar |
| `parar [--agora]` | cria `PARAR` (e manda SIGTERM) |
| `reprocessar --desde AAAA-MM-DD [--ate] [--tipo]` | reaplica o parser atual ao bruto guardado |
| `--versao` | versão e protocolo |

## Desenvolvimento

```bash
cd apps/coletor
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 uv sync
uv run ruff check .
uv run pytest -q            # test_fluxo precisa do Chromium do Playwright; sem ele fica "skipped"
```

Nenhum teste toca a rede real nem usa conta de ninguém: o servidor falso (`tests/sintetico/`) serve
páginas HTML sintéticas e o SociMan falso é um `httpx.MockTransport`.
