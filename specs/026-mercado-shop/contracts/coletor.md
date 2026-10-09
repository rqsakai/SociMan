# Contrato do coletor: `apps/coletor/` (026-mercado-shop)

O **coletor** é o terceiro aplicativo da stack (constitution 4.4.0, princípio IX): um serviço Python no
desktop do dono, **fora do Docker**, que controla o Chrome real do dono num perfil dedicado, navega como
pessoa pelas páginas que o SociMan pediu e devolve o que viu pela API de ingestão (`contracts/http-api.md`,
rotas **C**). Ele **nunca** fala com o Postgres, com o MinIO ou com o Redis; **nunca** chama a API interna
assinada da rede; **nunca** escreve na rede. Este arquivo é o contrato que o `/speckit-tasks` implementa
e que os testes estáticos de `apps/coletor/tests/` verificam.

## Pacote e dependências

| Item | Valor |
|---|---|
| Pasta | `apps/coletor/` (`pyproject.toml` próprio, `uv`), pacote `sociman_coletor`, versão semver (`__version__`, enviada em `X-Sociman-Coletor-Versao`) |
| Python | 3.12 |
| Dependências | `playwright` (**só** `sync_playwright().chromium.connect_over_cdp`; não baixa navegador: `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` no `uv sync`), `httpx` (só para a API do SociMan), `pydantic` (payloads e config). Nada mais em runtime (guarda `test_dependencias`) |
| Dev | `pytest`, `pytest-httpx` (ou o fake HTTP do próprio projeto), `ruff` |
| Módulos | `main.py` (CLI), `config.py`, `api.py` (cliente da ingestão), `navegador.py` (Chrome + CDP), `navegacao.py` (as únicas ações sobre a página; `CLIQUES_PERMITIDOS`), `ritmo.py` (puro, RNG semeado), `janela.py` (relógio e janela, puro), `sinais.py` (captcha, login, bloqueio, layout), `privacidade.py` (poda), `imagens.py` (download dentro do navegador), `redes/base.py` (Protocol `ColetorRede`), `redes/tiktok_shop.py` (`INTERCEPTAR`, parsers, `esquema = "tiktok_shop/1"`), `estado.py` (contadores do dia, arquivo local), `log.py` |
| Instalação | `systemd/sociman-coletor.service` (unidade de **usuário**: `After=graphical-session.target`, `Restart=on-failure`, `RestartSec=60`, `ExecStart=%h/.local/bin/sociman-coletor rodar`); `uv tool install ./apps/coletor` põe o binário em `~/.local/bin` |

O coletor só roda com a **sessão gráfica ativa**: sem `DISPLAY`/`WAYLAND_DISPLAY` ele registra `sem_tela`
e dorme (sem modo headless, por decisão do dono).

## Configuração local

`~/.config/sociman-coletor/` (modo 700):

| Arquivo | Conteúdo |
|---|---|
| `config.toml` | `api_url = "https://192.168.86.47:8543"`; `ca_cert = "~/.config/sociman-coletor/sociman-ca.crt"` (a CA da casa; sem ela o `autoteste` falha em TLS, nunca desligue a verificação); `chrome_bin = "/usr/bin/google-chrome"` (ou `chromium`); `perfil_dir = "~/.config/sociman-coletor/chrome-profile"`; opcionais com os **mesmos nomes do servidor**: `[limites] paginas_dia = 300`, `imagens_dia = 1500`, `pausa_min_s = 5`, `pausa_max_s = 40`, `janela_inicio = 8`, `janela_fim = 23`; `[log] nivel = "INFO"`, `arquivo = "~/.local/state/sociman-coletor/coletor.log"`; `screenshots = false` (padrão; `true` só grava em disco local para depuração do dono, **nunca envia**) |
| `token` | o `scol_…`, uma linha, modo **600** (o coletor recusa iniciar com modo mais aberto: `token_permissao`) |
| `chrome-profile/` | o perfil dedicado do Chrome (700), logado pelo dono uma vez (`perfil-iniciar`); `DevToolsActivePort` é lido daqui |
| `PARAR` | arquivo de parada local (FR-019): existir = terminar a tarefa atual, fechar a rodada como `interrompida` e não abrir outra; o `parar` do CLI o cria; é removido quando o dono roda `rodar` de novo |
| `estado.json` | `{dataLocal, paginasHoje, imagensHoje, ultimaFilaEm, recuoAte, pausaAte}`, só contagens e datas (reserva local do orçamento; a verdade é do servidor) |

**Limites efetivos** = `min(local, servidor)` para páginas, imagens e teto da rodada; `pausa_min_s` =
`max(local, servidor)`; `pausa_max_s` = `max(local, servidor)`; janela = interseção (FR-016). Os do
servidor chegam em cada `GET /fila` e `batimento`.

## CLI (`sociman-coletor`)

| Comando | O que faz | Sai com |
|---|---|---|
| `rodar` | laço contínuo: dentro da janela pede a fila, abre a rodada, executa, fecha; fora da janela ou com fila vazia dorme (`DORMIR_FILA_VAZIA_MIN = 15`, até a próxima janela quando `fora_da_janela`); respeita `PARAR` e SIGTERM | só por sinal ou `PARAR` |
| `uma-vez --limite N` | uma rodada com no máximo N páginas (≤ `itens_por_coleta`), ignora a janela com `--fora-da-janela` (só para a sonda guiada com o dono, X6); fecha a rodada com `motivo = "limite"` | 0 se todas as páginas devolveram `gravado|repetido`; 2 se houve `erro|invalido`; 3 se parou por sinal |
| `dry-run [--limite N]` | pede a fila (reserva **não** é marcada: `GET /fila?simular=true` devolve sem lease), imprime tipo, chave, nível e URL **sem parâmetros**, não abre o Chrome, não envia nada | 0 |
| `autoteste` | confere: config, token (modo 600), CA, `GET /api/health`, `GET /fila?simular=true` com o token (401/403/426 viram mensagens claras), Chrome encontrado, perfil com `flock` livre, sessão gráfica, fuso local × fuso do servidor (aviso, não erro); **não** abre páginas da rede | 0 ok; 1 com a lista de falhas |
| `perfil-iniciar` | abre o Chrome **sem CDP** no perfil dedicado, na página de login da rede, e espera o dono fechar (X1); imprime "perfil pronto" | 0 |
| `parar` | cria `PARAR` e envia `POST /eventos {tipo: "parar_local"}` se há rodada aberta; `--agora` também envia SIGTERM ao processo (PID em `estado.json`) | 0 |
| `reprocessar --desde AAAA-MM-DD [--ate] [--tipo]` | para cada rodada do período (`GET /api/coleta/coletas?de&ate`), baixa o bruto (`GET …/bruto/{tarefaId}`), roda o parser **atual** e reenvia os campos por `…/itens` com `reprocessadoDe`; não abre o Chrome; respeita o `limite_por_minuto` | 0; 2 se algum item voltou `invalido` |
| `--versao` | imprime a versão e o protocolo | 0 |

Toda saída de terminal segue `log.py`: nunca cookie, token, nome, @, texto de avaliação ou URL com `?`.

## Protocolo com a API (versão `1`)

Cabeçalhos em toda requisição: `Authorization: Bearer scol_…`, `X-Sociman-Coleta-Protocolo: 1`,
`X-Sociman-Coletor-Versao: <semver>`, `X-Sociman-Chrome-Versao: <versão>` (quando conhecida),
`User-Agent: sociman-coletor/<semver>`. Nunca envia `Origin` nem cookies.

Ciclo de uma rodada:

```text
janela.dentro() e sem PARAR
  └─▶ GET /api/coleta/fila?limite=min(itens_por_coleta, limite local)
        ├─ habilitada=false | tarefas=[] → dormir (motivoVazia decide quanto); nenhuma rodada abre
        └─ tarefas → POST /api/coleta/coletas (201 Coleta; 409 coleta_em_andamento → esperar 5 min e tentar de novo, nunca forçar)
             └─▶ navegador.conectar() (Chrome + CDP; 1 aba)
                  para cada tarefa, em ordem:
                    ritmo.pausa() → navegacao.abrir(url) → sinais.checar() → redes.tiktok_shop.coletar(tarefa)
                    → privacidade.podar(bruto) → (imagens) imagens.baixar(shas ≤ imagensMax) → api.enviar_imagens()
                    → api.enviar_itens([item])  (lotes de 1 a 10 itens: a cada item ou a cada 5 páginas)
                    → estado.contar(); a cada 60 s POST …/batimento (thread própria)
                    → resposta com parar=true → sai do laço
                    → a cada BLOCO_PAGINAS = 10 páginas: ritmo.pausa_longa() (60..180 s)
                  fim das tarefas ou orçamento → POST …/fim {motivo}
             └─▶ captcha | login_perdido → POST /eventos; Chrome fica aberto na página; laço de espera por batimento
                  (continuarEm preenchido → esperar CAPTCHA_ESFRIAR_MIN = 60 min → evento retomou → segue);
                  batimento com parar=true (pausa_vencida) → POST …/fim {motivo: "pausa_vencida"}
             └─▶ bloqueio_suspeito | layout_mudou → POST /eventos → POST …/fim → recuo local de 24 h (estado.recuoAte)
```

Regras do protocolo:
- **Itens:** `status = ok` com `campos` + `bruto` (gzip + base64 do JSON interceptado, já podado, ≤ 2 MB
  descomprimido) + `imagens` (shas); `status = erro` com `erroCodigo` (`pagina_sem_campos`,
  `timeout_navegacao`, `http_4xx`, `http_5xx`, `redirecionada`, `interceptacao_vazia`, `parser_falhou`);
  `status = captcha` quando o captcha apareceu **nesta** página (o evento vai junto).
- **Imagens antes dos itens:** os arquivos vão por `…/imagens` (≤ 10 por chamada, cada ≤ 5 MB, com o
  `manifesto`); só depois o item cita os shas. Recusa `orcamento` → para de baixar na rodada; o item vai
  mesmo assim (o produto fica `imagens_pendentes` no servidor).
- **Idempotência do lado do coletor:** se `…/itens` falhar na rede (timeout) depois de enviado, reenvia o
  mesmo lote uma vez; o servidor responde `repetido` sem gravar duas vezes (FR-027).
- **Respostas do portão:** 401 → registra `token_invalido`, fecha o Chrome e **para o serviço** (sai com
  código 4; o systemd não reinicia em `Restart=on-failure` com `RestartPreventExitStatus=4`); 403
  `escopo_coleta`/`coleta_suspensa` → idem; 426 → imprime a mensagem do servidor e para (código 5); 429 →
  espera `Retry-After` (ou 60 s); 503 `coleta_desligada`/`coleta_indisponivel` → fecha a rodada se aberta
  e dorme 15 min.
- **Relógio:** o coletor **não** decide dia nem turno; manda `coletadoEm` com fuso (ISO 8601) e usa o
  `agoraServidor` da fila para corrigir a própria noção de "hoje" no `estado.json` (Edge "relógio
  errado"). A janela é avaliada no fuso do servidor (`fuso` da resposta).

## Navegador (`navegador.py`)

- Lança o Chrome do sistema: `<chrome_bin> --user-data-dir=<perfil_dir> --remote-debugging-port=0
  --no-first-run --no-default-browser-check --lang=pt-BR --window-size=1280,900`. **Sem** flags de
  automação (`--headless`, `--disable-blink-features`, `--enable-automation`, `--remote-allow-origins=*`
  são proibidas: guarda `test_flags_chrome`). A porta de depuração é lida de `<perfil_dir>/DevToolsActivePort`
  (efêmera, só loopback); conexão por `connect_over_cdp("http://127.0.0.1:<porta>")`.
- **`flock`** exclusivo em `<perfil_dir>/.sociman.lock` antes de lançar: outro processo no mesmo perfil →
  `perfil_em_uso` e sai (Edge "dois coletores").
- Uma **única aba**: `context.pages[0]`; novas abas abertas pela página são fechadas na hora
  (`context.on("page", fechar)`); popups e downloads são cancelados.
- Interceptação **passiva**: `page.on("response", …)` filtra pela lista fechada `INTERCEPTAR` de
  `redes/tiktok_shop.py` (padrões de URL da API interna que a própria página chama) e guarda o JSON da
  resposta. O coletor **nunca** chama `page.route`, `page.request`, `context.request` nem reproduz a
  chamada assinada (FR-014; guarda AST).
- Timeout de navegação 45 s; `wait_until = "domcontentloaded"` + espera pelas respostas interceptadas (até
  15 s) + rolagem em passos; DOM só como reserva quando a interceptação veio vazia (`parser_dom`).
- Chrome fechado pelo dono no meio da rodada (`TargetClosedError`) → `POST …/fim {motivo:
  "servico_parado"}` (vira `interrompida`), sem relançar o Chrome na mesma rodada.

## Ações permitidas (lista fechada; `navegacao.py`)

| Ação | Playwright | Uso | Limite |
|---|---|---|---|
| `abrir(url)` | `page.goto(url)` | só a `url` da tarefa, ou a URL de paginação/aba derivada dela pelo adaptador (`redes.tiktok_shop.url_pagina(url, n)`), FR-023 | 1 por página |
| `rolar()` | `page.mouse.wheel(0, dy)` | `dy` ∈ 300..900 px por passo, 3..8 passos com `pausa_curta` entre eles | por página |
| `mover_mouse()` | `page.mouse.move(x, y, steps)` | pontos aleatórios dentro da janela, antes de rolar ou clicar | |
| `esperar(ms)` | `page.wait_for_timeout(ms)` | sempre pelo `ritmo.py` | |
| `clicar(alvo)` | `page.locator(sel).click()` | **só** com `alvo ∈ CLIQUES_PERMITIDOS` (abaixo); o seletor vem do adaptador | ≤ 3 cliques por página |
| `voltar()` | `page.go_back()` | só depois de um clique de aba/paginação, para fechar o ciclo | |

```python
CLIQUES_PERMITIDOS = frozenset({
    "fechar_aviso",        # banner de cookies, tour, "Entendi", modal informativo
    "aba_categoria",       # trocar a aba/categoria de um ranking
    "paginacao",           # próxima página de ranking, avaliações ou vídeos
    "ver_mais",            # expandir descrição ou lista de atributos
    "fechar_modal",        # X de um modal que a própria página abriu
})
```

**Proibido** (guarda AST `test_acoes_permitidas` sobre todo o pacote, exceto `imagens.py` para `request`):
`fill`, `type`, `press`, `keyboard`, `set_input_files`, `select_option`, `check`, `uncheck`, `drag_and_drop`,
`dblclick`, `tap`, `evaluate` com string contendo `fetch(` ou `XMLHttpRequest`, `route`, `request`,
`unroute`, `expose_function`, `add_init_script`, `new_page`, `new_context`, qualquer `click` fora de
`navegacao.clicar`, e qualquer seletor de clique cujo texto case com
`Adicionar|Promover|Seguir|Comprar|Enviar|Comentar|Curtir|Salvar|Solicitar|Amostra|Compartilhar|Denunciar|
Favoritar|Pedir|Entrar|Sair|Login|Cadastr` (regex sem acento e sem caixa, aplicada ao `inner_text` antes
de clicar: casou → **não clica**, registra `clique_bloqueado` e segue). O `imagens.py` só pode fazer
`page.request.get(url_da_imagem)` para URLs de imagem que a própria página carregou (lista `IMAGENS_HOSTS`
do adaptador) e é o único módulo onde `request` aparece.

## Ritmo humano (`ritmo.py`, puro, RNG semeado para o teste)

| Constante | Valor | Uso |
|---|---|---|
| `PAUSA_MIN_S`, `PAUSA_MAX_S` | 5, 40 (ou os do servidor, o maior) | entre páginas e antes de clicar: `uniform` com viés para o centro (soma de dois uniformes) |
| `PAUSA_CURTA_MS` | 300..1500 | entre passos de rolagem e movimentos de mouse |
| `BLOCO_PAGINAS` | 10 | a cada bloco, `PAUSA_LONGA_S` = 60..180 |
| `ROLAGEM_PASSOS`, `ROLAGEM_PX` | 3..8, 300..900 | |
| `JITTER_JANELA_MIN` | 0..20 | minutos aleatórios depois de `janela_inicio` antes do 1º pedido do dia |
| `DORMIR_FILA_VAZIA_MIN` | 15 | com fila vazia dentro da janela |

`test_ritmo`: com semente fixa, 10.000 pausas ficam em `[min, max]`, a média fica no terço central e
nenhuma sequência tem duas pausas iguais seguidas.

## Sinais e paradas (`sinais.py`, `janela.py`)

| Sinal | Detecção | Ação |
|---|---|---|
| `captcha` | URL ou título com os padrões `CAPTCHA_PADROES` do adaptador (ex.: `/verify`, "Verificação", `captcha`), ou iframe de desafio | item `captcha`; evento `captcha`; Chrome fica aberto na página; espera o `continuarEm` por batimento; retoma só depois de `CAPTCHA_ESFRIAR_MIN = 60`; sem clique em `CAPTCHA_ESPERA_MAX_H = 2` o servidor encerra (`pausa_vencida`). **Nunca** recarrega em laço, **nunca** tenta resolver |
| `login_perdido` | redirecionamento para `LOGIN_PADROES` ou resposta interceptada com código de sessão inválida | evento `login_perdido`; mesma espera do captcha; o dono reloga no Chrome aberto e clica "Continuar" |
| `bloqueio_suspeito` | `BLOQUEIO_SERIE = 3` respostas 429/403 em páginas seguidas, ou 5 páginas seguidas com `http_4xx` | evento; fecha a rodada; recuo local `RECUO_BLOQUEIO_H = 24` (o servidor também grava `pausada_ate`) |
| `layout_mudou` | `PARSES_VAZIOS_MAX = 5` páginas seguidas com interceptação **e** DOM sem campos reconhecíveis | evento; fecha a rodada; recuo de 24 h; o dono atualiza o coletor e roda `reprocessar` |
| `parar_local` | arquivo `PARAR` | termina a tarefa atual, evento `parar_local`, `…/fim {motivo: "parar_local"}` |
| `servico_parado` | SIGTERM/SIGINT | idem com `motivo: "servico_parado"` (até 30 s para fechar; `TimeoutStopSec=45`) |
| `fora_da_janela` | relógio × janela efetiva | não abre rodada; rodada aberta termina a tarefa e fecha com `fora_da_janela` |
| `orcamento` | `paginasRestantes = 0` na resposta | fecha com `orcamento`; dorme até o próximo dia local |
| `sem_tela` | sem `DISPLAY`/`WAYLAND_DISPLAY` | não abre rodada; tenta de novo em 15 min |

Eventos `iniciado` (ao abrir a rodada, com `versaoColetor` e `chromeVersao`) e `parado` (ao sair do
serviço) são informativos e não notificam.

## Privacidade (`privacidade.py`) e logs (`log.py`)

- **Poda do bruto** antes de enviar: remove, em qualquer profundidade, as chaves da lista fechada
  `CHAVES_PESSOAIS` (`nickname`, `nick_name`, `user_name`, `username`, `display_name`, `name`,
  `avatar`, `avatar_url`, `avatar_thumb`, `profile`, `bio`, `signature`, `email`, `phone`, `mobile`,
  `address`, `uid` quando dentro de `review`/`comment`, `sec_uid`, `user`, `author` **exceto** o campo
  `unique_id`/`handle` em `videos` (o @ público, FR-011)) e substitui por `"[podado]"`; URLs com `?` perdem
  a query. O id do autor da avaliação é trocado por `autorRef` (o id cru, que o servidor transforma em
  `autor_hash` com o pepper e descarta). Depois da poda, `privacidade.verificar(bruto)` falha se restar
  alguma chave da lista (o item sai como `erro` `bruto_pessoal_local`, sem ir ao servidor). O servidor
  repete a verificação (FR-029). `test_privacidade_poda` usa fixtures sintéticas com as chaves em várias
  profundidades.
- **Logs** (`log.py`, `logging` com filtro): só `tarefaId`, tipo, `redeProdutoId`, códigos, contagens,
  durações e URLs **sem** parâmetros; o filtro recusa linhas com `scol_`, `Cookie`, `sessionid`, `@` seguido
  de letra, ou qualquer texto > 200 caracteres (FR-021). `test_log_sem_pessoal` roda uma rodada completa
  contra o servidor falso e procura no arquivo de log e no stdout.
- **Capturas de tela** desligadas por padrão; com `screenshots = true` vão só para disco local; nenhuma
  rota do protocolo as aceita.
- O **token** é lido do arquivo a cada início, nunca passa por argumento de linha de comando nem por
  variável de ambiente (apareceria em `ps`).

## Adaptador `redes/tiktok_shop.py` (esquema `tiktok_shop/1`)

Protocol `ColetorRede` (`redes/base.py`):
```text
esquema: str                                   # "tiktok_shop/1"
INTERCEPTAR: tuple[re.Pattern, ...]            # padrões de URL de resposta a guardar (lista fechada)
IMAGENS_HOSTS: frozenset[str]
CAPTCHA_PADROES, LOGIN_PADROES: tuple[re.Pattern, ...]
url_canonica(url) -> str                        # sem parâmetros; o servidor compara com a da tarefa
url_pagina(url, n) -> str                       # paginação derivada da URL da tarefa
coletar(pagina, tarefa, interceptadas) -> Resultado   # Resultado = {campos, bruto, imagens: [{sha256, url, origem}], erroCodigo}
```
Os campos reais do Affiliate Center brasileiro são confirmados na **sonda guiada** (`uma-vez --limite 1`
com o dono, 1ª tarefa prática do quickstart); a sonda pode ajustar nomes de chaves em `INTERCEPTAR` e nos
parsers, não as regras nem o formato abaixo.

### Payloads normalizados (`campos`), por tipo de tarefa

Todos em camelCase; `null` quando a página não expõe; números sem formatação ("1,2 mil" vira
`{valor: 1200, min: 1150, max: 1249, exato: false}`); dinheiro em centavos com `moeda`; datas ISO 8601.

**`produto`** (`fonte` = `pagina_publica`, `affiliate` ou `ambas`; com `ambas`, o item traz os dois blocos
e o servidor grava uma foto por fonte):
```json
{
  "redeProdutoId": "7291…", "urlCanonica": "https://…/product/7291…",
  "ficha": {
    "titulo": "Shorts de linho…", "descricao": "…",
    "atributos": [{ "nome": "Material", "valor": "Linho" }],
    "variantes": [{ "redeVarianteId": "17…", "nome": "Bege / M", "precoCentavos": 4990, "precoOriginalCentavos": 7990, "estoqueVisivel": 12, "imagemSha": "<sha256>" }],
    "argumentos": ["Frete grátis", "Tecido fresco"], "selos": ["Mais vendido", "Cupom R$ 5"],
    "categoria": { "redeCategoriaId": "cat789", "caminho": [{ "redeCategoriaId": "cat1", "nome": "Moda" }, { "redeCategoriaId": "cat45", "nome": "Feminino" }, { "redeCategoriaId": "cat789", "nome": "Shorts" }] },
    "loja": { "redeLojaId": "loja123", "nome": "Loja X", "oficial": true, "url": "https://…/shop/loja123" },
    "lancadoEm": "2026-09-20",
    "imagensSha": ["<sha256>", "<sha256>"]
  },
  "paginaPublica": {
    "vendidos": { "valor": 12400, "min": 12350, "max": 12449, "exato": false },
    "precoMinCentavos": 4990, "precoMaxCentavos": 5990, "precoOriginalCentavos": 7990, "moeda": "BRL",
    "nota": 4.8, "nAvaliacoes": 311, "estoqueVisivel": 230, "disponivel": true,
    "campos": { "cupons": ["R$ 5"], "freteGratis": true }
  },
  "affiliate": {
    "comissaoBp": 1200, "nCriadores": 37, "vendas7d": 410, "vendas30d": 1620,
    "precoMinCentavos": 4990, "precoMaxCentavos": 5990, "moeda": "BRL",
    "campos": { "planoAberto": true, "amostraGratis": true, "comissaoDirecionadaBp": null }
  }
}
```

**`ranking`** (`fonte` = `affiliate`):
```json
{ "rankingTipo": "mais_vendidos", "janela": "7d",
  "categoria": { "redeCategoriaId": "cat45", "caminho": [ "..." ] },
  "itens": [ { "posicao": 1, "redeProdutoId": "7291…", "urlCanonica": "https://…", "titulo": "…", "imagemSha": "<sha256>",
               "valorExibido": "12,3 mil vendidos", "valorNum": 12300,
               "campos": { "precoMinCentavos": 4990, "comissaoBp": 1200, "nCriadores": 37 },
               "loja": { "redeLojaId": "loja123", "nome": "Loja X", "oficial": true } } ] }
```
Itens: até `RANKING_ACOMPANHAR_TOP = 30` por tarefa (o adaptador para de paginar depois disso).

**`categorias`** (semanal):
```json
{ "categorias": [ { "redeCategoriaId": "cat1", "nome": "Moda", "nivel": 1, "paiRedeId": null },
                  { "redeCategoriaId": "cat45", "nome": "Feminino", "nivel": 2, "paiRedeId": "cat1" } ] }
```

**`vitrine`** (a vitrine do próprio dono, diária; `fonte` = `affiliate`):
```json
{ "itens": [ { "redeProdutoId": "7291…", "urlCanonica": "https://…", "titulo": "…", "imagemSha": "<sha256>",
               "adicionadoEm": "2026-09-30", "campos": { "comissaoBp": 1200 } } ] }
```

**`loja`** (ficha + foto + produtos novos):
```json
{ "redeLojaId": "loja123", "nome": "Loja X", "oficial": true, "url": "https://…/shop/loja123",
  "foto": { "nota": 4.7, "seguidores": 15800, "envioNoPrazoPct": 97.5, "tempoRespostaPct": 92.0, "nProdutos": 84,
            "vendidosTotal": { "valor": 230000, "min": 225000, "max": 234999, "exato": false }, "campos": {} },
  "produtos": [ { "redeProdutoId": "7300…", "urlCanonica": "https://…", "titulo": "…", "imagemSha": "<sha256>",
                  "precoMinCentavos": 3990, "moeda": "BRL", "vendidos": { "valor": 120, "exato": true }, "novo": true } ] }
```

**`avaliacoes`** (`extra.paginas` páginas; `fonte` = `pagina_publica`):
```json
{ "redeProdutoId": "7291…", "pagina": 1, "totalPaginas": 14,
  "itens": [ { "redeAvaliacaoId": "av1…", "autorRef": "6812…", "texto": "Tecido ótimo, veio no prazo.", "nota": 5,
               "dataAvaliacao": "2026-10-02", "variante": "Bege / M", "imagensSha": ["<sha256>"], "curtidas": 3, "campos": {} } ] }
```
`autorRef` é o único dado do autor que sai do coletor, e só para virar `autor_hash` no servidor. Nome,
@, foto de perfil e bio do autor são **podados antes** (`test_privacidade_poda` cobre a chave `user`
das avaliações). As fotos do cliente vão como imagens normais (`origem = "avaliacao"`).

**`produto_videos`** (1 página; `fonte` = `affiliate`):
```json
{ "redeProdutoId": "7291…",
  "itens": [ { "posicao": 1, "redeVideoId": "7320…", "autorHandle": "fulana.achados", "views": 1250000, "likes": 84000,
               "comentarios": 1200, "compartilhamentos": 3100, "legenda": "…", "publicadoEm": "2026-09-28T19:02:00-03:00",
               "campos": { "duracaoS": 34, "produtoMarcado": true } } ] }
```
`autorHandle` = o @ público (FR-011). Nome de exibição, foto e bio do criador são podados.

**Reservados (027):** `busca_assunto` e `video` podem vir na fila de um servidor mais novo; o coletor da
026 responde com item `erro` `tipo_desconhecido` sem abrir a página.

## Imagens (`imagens.py`)

- Só URLs de `IMAGENS_HOSTS` que a própria página carregou (interceptação `response` com `Content-Type:
  image/*`), até `min(imagensMax da tarefa, imagens_por_produto, imagensRestantes)`; download pelo contexto
  do navegador (`page.request.get`, com os cookies do perfil), **sem redimensionar**; `sha256` calculado
  localmente e conferido pelo servidor; arquivos ≤ 5 MB (maiores são descartados com `imagem_grande`).
- Cache local por sha na rodada (a mesma imagem em dois produtos sobe uma vez); `repetidas` do servidor
  entram no cache. Nada fica em disco depois da rodada (buffer em memória, ≤ 50 MB por lote).

## Eventos e notificação (resumo do lado do coletor)

| Evento | Quando o coletor envia | Pausa? |
|---|---|---|
| `iniciado` | ao abrir a rodada | não |
| `captcha` | na detecção (com o item `captcha`) | sim, até "Continuar" + 60 min |
| `login_perdido` | na detecção | sim, idem |
| `retomou` | ao voltar da pausa | não |
| `bloqueio_suspeito` | 3 recusas seguidas | fecha a rodada, recuo 24 h |
| `layout_mudou` | 5 parses vazios seguidos | fecha a rodada, recuo 24 h |
| `parar_local` | arquivo `PARAR` | fecha a rodada |
| `parado` | SIGTERM, antes de sair | fecha a rodada |

O servidor deduplica a notificação do sino por tipo e dia; o coletor pode reenviar o evento sem efeito
colateral.

## Testes (`apps/coletor/tests/`)

| Teste | O que garante |
|---|---|
| `test_acoes_permitidas` | AST de todo o pacote: nenhum método proibido; todo `click` em `navegacao.clicar`; `request` só em `imagens.py`; nenhuma string com host da rede fora de `redes/tiktok_shop.py`; nenhuma reprodução de chamada assinada (`X-Gnarly`, `_signature`, `msToken` ausentes) |
| `test_flags_chrome` | a linha de comando do Chrome tem exatamente as flags do contrato e nenhuma de automação |
| `test_privacidade_poda` | fixtures sintéticas com chaves pessoais em várias profundidades saem podadas; `verificar` falha quando resta alguma; `autorRef` passa; `autorHandle` em `videos` passa |
| `test_ritmo` | distribuições das pausas (semente fixa) dentro dos limites; `min(local, servidor)` e `max` nas pausas |
| `test_janela` | janela, interseção com a do servidor, `fora_da_janela` cruzando a meia-noite, fuso do servidor |
| `test_sinais` | páginas sintéticas de captcha, login, 429 em série e layout vazio disparam o sinal certo, uma vez |
| `test_log_sem_pessoal` | rodada completa contra o servidor falso: log e stdout sem `scol_`, cookie, @, nome ou texto de avaliação |
| `test_protocolo` | com o SociMan falso (`pytest-httpx`): cabeçalhos, lotes ≤ 10 itens, imagens antes dos itens, 401/426 param o serviço, 429 espera, 409 `coleta_em_andamento` espera, `parar=true` fecha, `continuarEm` retoma só depois de 60 min (relógio simulado) |
| `test_parsers` | fixtures HTML/JSON sintéticas (nunca páginas reais salvas) por tipo de tarefa produzem os payloads acima; "1,2 mil" e "10 mil+" viram faixa |
| `test_uma_vez` | `uma-vez --limite 3` contra o servidor falso da rede e o SociMan falso: 3 páginas, 3 `gravado`, pausas respeitadas (relógio simulado), captcha sintético para e registra (US2) |

Nenhum teste toca a rede real nem usa a conta do dono. O servidor falso da rede serve páginas HTML
sintéticas que carregam JSON pelos mesmos caminhos de `INTERCEPTAR`.
