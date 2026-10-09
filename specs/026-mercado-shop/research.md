# Research: Cockpit do TikTok Shop coletado pelo SociMan (026)

Decisões técnicas da 026. Cada item traz **Decisão / Por quê / Alternativas**. A fonte da verdade é a
`spec.md` (com as Clarifications de 2026-10-08), o insumo `docs/insumos/026-mercado-shop.md`, a constitution
4.4.0 (princípio IX) e o registro de risco `docs/decisoes/coleta-mercado.md`. As decisões marcadas **(DONO)**
foram tomadas pelo dono em 2026-10-08 e não são reabertas aqui: este documento registra o porquê e as
alternativas rejeitadas. A mecânica de referência é o `../../tools/tiktok_agendar.py` (Chrome real + Studio
do TikTok; só leitura, fora da worktree).

## Ambiente conferido em 2026-10-08

- **Repo (worktree em `1ce278d`):** a última migration é a `0021_geracao_interrupcoes` (a 012 planeja a
  `0022_produtos_shop` e a 025 a `0021_cadastro_padronizado`, em outras sessões). O pacote `produtos/` **não
  existe** nesta worktree: a ponte com a 012 (R23) é condicionada ao merge dela.
- **Compose:** `edge`, `certgen`, `api`, `worker`, `agendador`, `gerador`, `dockerctl`, `web`, `web-prod`,
  `postgres` (17), `redis`, `mailpit`, `minio`, `minio-init` (cria `sociman`, `sociman-fonts`,
  `sociman-videos`, `sociman-audios`), `imgproxy` (`IMGPROXY_ALLOWED_SOURCES` começa com `s3://sociman/`,
  `IMGPROXY_MAX_SRC_RESOLUTION=40`). Redes `default`, `gpu-local` (externa) e `dockerctl` (interna). A porta
  da API não é publicada (armadilha 3): tudo passa pelo edge.
- **Edge (`docker/nginx/default.conf.template`):** zonas `edge_api` (20 r/s, burst 40), `edge_img` (30 r/s)
  e `edge_mcp` (10 r/s). `location` próprias: cortes 520m, envio avulso e vídeo próprio 2100m, tomadas
  210m, áudios 26m (todas com `proxy_request_buffering off`), fontes 11m, assets 21m, `/api/midia/`
  (`proxy_buffering off`), `/mcp` 1m; o resto de `/api/` fica em 8m. Toda `location` da API apaga
  `X-Sociman-Via`.
- **Portão e token do MCP (molde):** `mcp/portao.py` é dependência global do app
  (`dependencies=[Depends(mcp_portao.dependencia)]` em `main.py`), com sessões próprias e a ordem de recusas
  documentada; `mcp/credenciais.py` tem `FORMATO = ^smcp_([a-z2-7]{8})_([A-Za-z0-9_-]{43})$`, SHA-256 e
  `hmac.compare_digest` com hash fictício; `mcp/limites.py` conta no Redis; `scripts/check-secrets.mjs` tem o
  padrão `smcp_` na linha 17.
- **Fotos só de inserção (molde):** a 0011 cria `metricas_recusa_mudanca()` e o trigger `metricas_so_insercao`
  (`BEFORE UPDATE OR DELETE … FOR EACH ROW`); `TRUNCATE` continua valendo. `metricas/agenda.py` é puro (sem
  banco nem relógio), com as constantes uma por linha.
- **Armazenamento:** `storage.Bucket = imagens | fontes | videos | audios`; `apagar_por_excecao` é o único
  delete (guarda por AST); `datadir.ensure_writable` (503 sem sentinela, 507 abaixo do piso de 20 GB);
  `imaging.validate_image` valida pelo conteúdo (PNG/JPEG/WebP, 40 Mpx) e `image_urls` só monta
  `s3://{s3_bucket}/{key}`; `midia.py` assina `/api/midia/{token}` (HMAC com `JWT_SECRET`, `COM_VALIDADE`
  para vídeo e áudio, `stream_object` com Range).
- **Trilhas e atores:** `agendador.trilhas_padrao()` tem 8 trilhas (`sync`, `openshorts`, `importacao`,
  `lembretes`, `publicacao`, `metricas`, `aprendizado`, `geracao_limpeza`) e
  `test_agendador_sem_trilha_nova` fixa o conjunto. `Actor.kind` aceita `user | anonymous | system:cli |
  system:publicacao | mcp_client`. `publicacao/registro.py` é o único importador do adaptador por rede.
- **Guardas existentes (`test_constitution_guards.py`):** `SOCIAL_SDKS`, `PUBLISH_ENDPOINTS`,
  `PERMITIDO_EM`, `IMPORTS_PROIBIDOS_019/022/023`, varredura de literais por AST (`_strings_de_codigo`),
  seções por spec (006, 008, 014, 015, 016, 017, 019, 009, 020, 010, 013, 022, 023, 021).
- **Analytics (molde da leitura):** `analytics/filtros.py` (período em `APP_TZ`, até 400 dias, anterior de
  mesma duração) e `analytics/mercado.py` (cálculo na leitura, sem gravação);
  `test_analytics_desempenho.py` semeia 10× por SQL (`generate_series`) e exige < 2 s por rota.
- **Host:** Google Chrome 154.0.8037.92 em `/usr/bin/google-chrome`; sessão GNOME **x11** (`DISPLAY=:1`,
  `XAUTHORITY=/run/user/1000/gdm/Xauthority`), e o `systemctl --user show-environment` **já traz**
  `DISPLAY`, `XAUTHORITY`, `DBUS_SESSION_BUS_ADDRESS` e `XDG_SESSION_TYPE`; `graphical-session.target` ativo;
  `Linger=yes`; Python 3.12.3 e uv 0.11.8; Playwright 1.63.0 na venv do `tiktok-shop` (com Chromiums
  empacotados, que **não** serão usados); HD com 1,7 TB livres de 2,7 TB e o sentinela
  `/media/sakai/BACKUP/tiktok/sociman/.sociman-volume` presente; `~/.config/sociman-coletor` ainda não existe.
- **Lições do `tiktok_agendar.py`:** `launch_persistent_context(channel="chrome")` com
  `--disable-blink-features=AutomationControlled`; leitura da API interna assinada
  (`creator/manage/item_list`) por `page.on("response")`, nunca por chamada direta; `time.sleep` não entrega
  eventos na API síncrona (usar `page.wait_for_timeout`); tour react-joyride e banners bloqueiam cliques.

## R1. Coletor em `apps/coletor/`, no host, como serviço systemd de usuário (DONO)

- **Decisão:** terceiro aplicativo da stack (`apps/coletor/`, pacote `sociman_coletor`, Python 3.12 + uv,
  `pyproject` próprio com `playwright`, `httpx` e `pydantic`), **fora do Docker**, instalado com `uv sync`
  em `apps/coletor/.venv` e executado pela unidade `~/.config/systemd/user/sociman-coletor.service`
  (`ExecStart=%h/…/apps/coletor/.venv/bin/sociman-coletor rodar`, sem `uv` em tempo de execução).
  - **Sessão gráfica:** `[Unit] After=graphical-session.target` e `PartOf=graphical-session.target`;
    `[Install] WantedBy=graphical-session.target`. Neste host o gerenciador de usuário já tem `DISPLAY`,
    `XAUTHORITY` e `DBUS_SESSION_BUS_ADDRESS` (conferido acima), então **não** é preciso
    `import-environment`; o `autoteste` confere as variáveis e falha com mensagem clara se faltarem
    (hosts Wayland precisam de `WAYLAND_DISPLAY`, e o Chrome roda por XWayland com o `DISPLAY`).
  - **Tela bloqueada:** no x11 o display continua vivo e o Chrome renderiza; a coleta segue (a spec exige
    "sessão gráfica ativa", e bloqueada ainda é ativa). **Logout** derruba o `graphical-session.target`, o
    `PartOf` manda SIGTERM, o coletor termina a tarefa atual e fecha a rodada como `interrompida`
    (`TimeoutStopSec=90`, `KillSignal=SIGTERM`). Com `Linger=yes` o gerenciador sobe no boot, mas a unidade
    só ativa depois do login: sem login, nada coleta (sem modo headless, por decisão).
  - **Suspender e retomar:** o coletor detecta o salto de relógio (> 5 min entre voltas), descarta a rodada
    como `interrompida` e pede a fila de novo; o servidor já marca rodadas sem batimento há 10 min.
    `Restart=on-failure`, `RestartSec=60`.
- **Por quê:** o princípio IX exige o navegador fora da API e do compose; um serviço de usuário é o padrão
  que o dono já opera (OpenClaw). Chrome dentro de container exigiria Xvfb ou headless, descartados.
- **Alternativas:** container com Chrome (perde o "navegador real do dono" e exige X no Docker; rejeitada);
  cron do usuário (sem SIGTERM limpo nem `PartOf`; rejeitada); `Type=notify` com watchdog (complexidade sem
  ganho: o servidor já vigia o batimento).

## R2. Chrome real lançado pelo coletor, CDP em loopback por `DevToolsActivePort`, `flock` no perfil

- **Decisão:** o coletor **lança e é dono** do Chrome do sistema (`google-chrome` por `shutil.which`,
  configurável) com `--user-data-dir=~/.config/sociman-coletor/chrome-profile` (700),
  `--remote-debugging-port=0`, `--lang=pt-BR`, `--no-first-run`, `--no-default-browser-check`,
  `--window-size=1280,900`; **sem** flags de automação, sem `--headless`, sem `--remote-allow-origins=*`.
  - **Porta:** lida do arquivo `<perfil>/DevToolsActivePort` (linha 1 = porta, linha 2 = caminho
    `/devtools/browser/<id>`), aceito só se for **mais novo que o lançamento** (mtime), com espera de até
    30 s; a linha `DevTools listening on ws://127.0.0.1:…` do stderr é a reserva. Conecta com
    `connect_over_cdp("http://127.0.0.1:<porta>")`, usa `browser.contexts[0]` (o contexto persistente, com
    os cookies do login) e a única aba. Nenhum log leva a porta nem a URL do websocket.
  - **Reuso:** o Chrome não aceita ligar a porta de depuração numa instância já aberta; se o
    `<perfil>/SingletonLock` apontar para um processo vivo, o coletor **recusa** com "feche o Chrome do perfil
    coletor" em vez de tentar outra coisa. Um `fcntl.flock` (`LOCK_EX | LOCK_NB`) em
    `~/.config/sociman-coletor/coletor.lock` garante um coletor por perfil.
  - **Fim:** `Browser.close` pelo CDP, depois SIGTERM com 15 s e SIGKILL só se preciso. Na pausa por captcha
    ou login (R17) o Chrome **fica aberto** para o dono resolver na própria janela.
  - **Versões:** o pacote `playwright` serve só para `connect_over_cdp` (sem `playwright install`); fica
    pinado por faixa (`>=1.63,<2`) e sobe junto com o Chrome (o CDP muda devagar, mas muda). O Chrome 136+
    recusa depuração remota no perfil padrão: o perfil dedicado atende também a isso.
- **Por quê:** o Chrome lançado pelo Playwright (`launch_persistent_context`, como no `tiktok_agendar.py`)
  carrega flags de automação e um `navigator.webdriver` que a rede pode ler; anexar por CDP a um Chrome que
  só tem a porta de depuração é o navegador real do dono. A porta efêmera em loopback evita colisão e não abre
  nada na LAN; o arquivo é a fonte oficial da porta e não depende de capturar o stderr.
- **Alternativas:** `launch_persistent_context(channel="chrome")` (flags de automação; rejeitada); porta fixa
  (ex.: 9222, previsível e colide com outro Chrome; rejeitada); anexar a um Chrome aberto pelo dono (não dá
  para ligar a porta depois; rejeitada); Chromium do Playwright (não é o navegador do dono; rejeitada).

## R3. Um perfil de Chrome, sempre logado na conta de afiliado do dono (DONO)

- **Decisão:** `sociman-coletor perfil-iniciar` abre o Chrome no perfil dedicado para o dono logar uma vez;
  as sessões ficam só nesse `user-data-dir`. O coletor nunca lê, exporta nem envia cookies; a perda da
  sessão (redirecionamento para login) é o evento `login_perdido` (R17). Um só mercado (`BR`) por perfil e
  por cliente de coleta.
- **Por quê:** decisão do dono registrada em `docs/decisoes/coleta-mercado.md`, com o risco à conta de
  afiliado explicado e aceito; o Affiliate Center só existe logado.
- **Alternativas rejeitadas pelo dono:** perfil anônimo separado, conta coletora separada e ferramenta paga.

## R4. Interceptação por lista fechada de URLs, DOM como reserva, nunca a API assinada (DONO)

- **Decisão:** `redes/tiktok_shop.py` tem `INTERCEPTAR: tuple[re.Pattern, ...]` sobre o **caminho** da URL
  (sem host, sem query); `page.on("response")` guarda o corpo JSON de cada resposta cujo caminho casa, e o
  parser monta os `campos` a partir desses corpos. O DOM só entra quando um campo esperado não veio
  (`origem = "dom"` no item). O coletor **nunca** reproduz uma chamada assinada (sem `fetch` fora do
  contexto da página, sem `X-Gnarly`, sem `request.get` em caminhos da API).
  - **Payload `tiktok_shop/1`** (contrato `contracts/ingestao.md`): envelope por item `{tarefaId, status,
    coletadoEm, fonte: "tiktok_shop/1", paginas, imagens, campos, bruto, imagensRef}`; os `campos` têm
    **nomes do SociMan**, por tipo de tarefa (produto: `redeProdutoId, titulo, descricao, atributos[],
    variantes[{redeSkuId, nome, precoCentavos, estoqueVisivel}], argumentos[], selos[], categoria[{nivel,
    redeCategoriaId, nome}], loja{redeLojaId, nome, oficial}, vendidos{texto, min, max, exato}, precoMin,
    precoMax, precoOriginal, moeda, nota, nAvaliacoes, disponivel, lancadoEm?, afiliado{comissaoPct,
    criadores, vendas7d, vendas30d, planoAberto, amostraGratis}?`; ranking, loja, categorias, vitrine,
    avaliações e vídeos têm os seus). A tradução do JSON da rede para esses nomes mora no parser do coletor
    (`MAPEAMENTO: dict[campo, caminho]`); o servidor valida com Pydantic (desconhecido em `campos` →
    `invalido`) e guarda o que sobra em `fotos.campos` (jsonb).
  - **Sonda com o dono (1ª tarefa prática):** `uma-vez --limite 1 --sonda` visita **uma** página de produto
    (e uma do Affiliate Center) com o dono olhando, **não envia nada**, grava o bruto podado em
    `~/.config/sociman-coletor/sonda/<data>/` e imprime: os caminhos de URL interceptáveis (sem query), a
    árvore de **chaves** de cada JSON (tipos e profundidade, sem valores) e os campos do contrato ainda sem
    caminho. A partir disso, o dev preenche `INTERCEPTAR` e `MAPEAMENTO` e grava uma fixture **anonimizada**
    (valores trocados) em `apps/coletor/tests/fixtures/`. Até a sonda, nenhum nome de campo da rede é
    adivinhado: o parser nasce com o contrato e fixtures sintéticas.
- **Por quê:** é a mecânica que já funcionou no Studio (`ler_agendados`), lê exatamente o que a página pediu
  e sobrevive melhor a mudanças de layout do que seletores CSS. O bruto completo (R8) permite renormalizar.
- **Alternativas:** só DOM (frágil e sem os campos numéricos exatos); chamar a API interna (proibido pelo
  princípio IX e detectável pela assinatura); adivinhar nomes de campo antes da sonda (geraria parser errado).

## R5. Ações permitidas por AST e navegação só a partir da fila (DONO)

- **Decisão:** `navegacao.py` é o **único** módulo que chama `page.goto`, `click`, `mouse.wheel`,
  `keyboard.press` e `wait_for_*`; `CLIQUES_PERMITIDOS` é uma tupla fechada de seletores/papéis (fechar aviso,
  aba de categoria, paginação, "ver mais" de avaliações). `test_acoes_permitidas` (AST) falha se qualquer
  outro módulo chamar essas APIs, se aparecer `fill`, `type`, `press_sequentially`, `set_input_files`,
  `evaluate` com `fetch`/`XMLHttpRequest`, ou `context.request` fora de `imagens.py`. `goto` só aceita URLs
  vindas da fila (host e caminho conferidos contra a tarefa); navegação interna da página é por clique
  permitido, nunca por URL montada.
- **Por quê:** o princípio IX exige lista fechada com teste; a ação proibida mais provável por acidente é um
  clique em "Adicionar à vitrine" num card do Affiliate Center.
- **Alternativas:** lista de proibidos (cresce sempre atrasada); revisão manual (não é teste).

## R6. Ritmo ditado pelo servidor; "página" e "imagem" e o menor dos dois limites

- **Decisão:**
  - **página** = cada navegação iniciada pelo coletor que carrega conteúdo de uma tarefa: um `goto`, uma
    troca de aba de categoria ou uma paginação (cada uma conta 1, **ao começar**, mesmo que falhe). Rolagem e
    "ver mais" na mesma página não contam. Cada tipo de tarefa tem `paginas_estimadas` (produto 1, +1 se a
    tarefa pede a página do Affiliate Center; ranking 1; avaliações até 2; vídeos 1; loja 1; categorias 1;
    vitrine 1 por página rolada);
  - **imagem** = cada arquivo baixado por `context.request.get` (R7), até `IMAGENS_POR_PRODUTO_MAX = 9` e
    só quando o servidor pediu (`baixar` no retorno do item); não conta como página;
  - **menor dos dois:** o coletor tem `paginas_dia`, `imagens_dia`, `pausa_min_s`, `pausa_max_s` e `janela`
    locais (`config.toml`, padrões 300/1500/5/40/08–23) e recebe os do servidor em `GET /fila` (`limites`);
    vale `min()` para tetos e pausas mínimas, `max()` para a pausa mínima e a interseção para a janela. O dia
    do orçamento é a `dataLocal` que o servidor manda na fila (não o relógio do desktop);
  - **servidor autoritativo:** `orcamentoRestanteHoje = paginas_dia − Σ paginas dos itens recebidos hoje −
    Σ paginas_estimadas das tarefas em lease`; a fila entrega no máximo isso; o coletor para de pedir ao
    atingir o seu contador local (que conta antes de navegar, por isso é conservador). Os dois contam; na
    dúvida, quem para primeiro ganha.
  - `ritmo.py` é puro: `random.Random(semente)` injetável, pausa uniforme em `[min, max]`, pausa longa
    (2 a 6 min) a cada bloco de 12 a 20 páginas, rolagem em 3 a 7 passos; `test_ritmo` confere com relógio
    simulado que nenhuma pausa fica abaixo do mínimo.
- **Por quê:** FR-016 e o princípio IX; contar a página ao começar evita que falhas "não contem" e virem um
  laço de recarregar.
- **Alternativas:** contar requisições de rede (uma página gera dezenas; incontável como "ritmo humano");
  só o servidor contar (o coletor pararia tarde se perdesse a conexão).

## R7. Imagens baixadas no contexto do navegador e enviadas por multipart com sha256 (DONO)

- **Decisão:** `imagens.py` usa `context.request.get(url)` (cookies, UA e `Referer` do próprio Chrome), teto
  de 8 MB por arquivo, e calcula o `sha256` do conteúdo. O coletor manda em `campos.imagens` só
  `[{ordem, urlHash}]` (sha256 da URL, nunca a URL); o servidor responde por item `baixar: [ordens]` (os
  `urlHash` que não conhece para aquela ficha), e o coletor, ainda na página, baixa só essas e envia
  `POST /api/coleta/coletas/{id}/imagens` (multipart: `sha256`, `ordem`, `fichaRef`, arquivo; até 10 por
  requisição e 50 MB). No servidor: recalcula o sha (diferente → `invalido`), `imaging.validate_image`
  pelo conteúdo (kind `imagem`, `max_bytes` 8 MB, sem redimensionar), `SELECT` por sha em
  `mercado_imagens` (existe → `repetido`, só grava o vínculo `mercado_produto_imagem_usos (ficha_id,
  imagem_id, ordem)` com `ON CONFLICT DO NOTHING`), senão `storage.put` e `INSERT`. Avaliações com fotos de
  clientes seguem o mesmo caminho (prefixo `mercado/avaliacoes/`).
- **Por quê:** baixar fora do navegador seria uma segunda identidade (sem cookies, outro UA) e um alvo fácil
  de bloqueio; o `urlHash` evita rebaixar as mesmas imagens todo dia (o teto de 1.500/dia só se gasta com
  produto novo ou ficha mudada) e cumpre FR-021 (nenhuma URL com parâmetros sai do coletor).
- **Alternativas:** baixar pelo servidor (a API teria hosts da rede: proibido); mandar a URL para o servidor
  decidir (vaza URL assinada); baixar sempre e deduplicar depois (gasta o orçamento à toa).

## R8. Bruto completo em gzip no bucket `sociman-mercado`, parsers no coletor, `reprocessar --desde` (DONO)

- **Decisão:** cada item leva `brutoGzipB64` (JSON com `{interceptado: [{padrao, caminho, status,
  corpo}], dom?: {...}}`, podado de PII, gzip, base64; teto 2 MB comprimido; o coletor divide os lotes por
  tamanho, ≤ 50 itens e ≤ 32 MB). O servidor descomprime, **poda de novo** (R16), grava em
  `bruto/<coleta_id>/<tarefa_id>.json.gz` no bucket novo **`sociman-mercado`** (`S3_MERCADO_BUCKET`,
  `storage.Bucket` ganha `"mercado"`, `minio-init` e `data-setup.sh init` o criam) e guarda `bruto_ref`,
  `esquema_versao` (`tiktok_shop/1`) e `bytes` na foto/ficha. Sem HD: a foto numérica é gravada,
  `bruto_ref = NULL` e `bruto_pendente = true`; o coletor guarda a cópia local por 7 dias em
  `~/.config/sociman-coletor/pendentes/` e reenvia (`POST …/{id}/bruto`) quando a fila avisa
  `brutosPendentes`.
  - **Reprocessar:** `sociman-coletor reprocessar --desde <data> [--tipo produto]` lista as coletas
    (`GET /api/coleta/coletas?desde=`), baixa cada bruto pelo link assinado (`MidiaKind mercado_bruto`,
    **com validade** de 1 h, bucket `mercado`), roda o parser atual e reenvia os itens com
    `reprocessadoDe = <item_id>`; a ingestão só preenche o que faltava (campos nulos da ficha/foto do mesmo
    dia e turno viram **nova linha** só se o `hash_conteudo` mudar; a foto existente nunca muda: o trigger
    impede).
- **Por quê:** FR-012 e o princípio IX (bruto para reprocessar sem recoletar); gzip reduz 5 a 10× o JSON da
  rede; o bucket separado isola o que o imgproxy nunca deve ler e facilita backup por tipo.
- **Alternativas:** bruto no Postgres (jsonb de centenas de KB por página, 300/dia; NVMe; rejeitada); parsers
  no servidor (a API ganharia conhecimento da rede e do layout, e a 027 teria de mudar a API a cada layout).

## R9. Imagens do lago no bucket `imagens` com prefixo `mercado/`, links estáveis, CSP e imgproxy intactos

- **Decisão:** as imagens de produto e de avaliação ficam no bucket `imagens` (`sociman`) com a chave
  `mercado/<sha[:2]>/<sha>.<ext>` (produtos) e `mercado/avaliacoes/<sha[:2]>/<sha>.<ext>`, registradas em
  `mercado_imagens` (sha256 UQ, `content_type`, `bytes`, `width`, `height`, `object_key`), **não** em
  `images` (que tem `perfil_id`). As miniaturas saem por `imaging.image_urls(object_key)` sem mudança: o
  imgproxy já aceita `s3://sociman/` e a CSP já cobre `/img/` na mesma origem (`img-src 'self'`). O original
  (galeria, "Baixar") sai por `midia.py` com `MidiaKind mercado_imagem`, **sem validade** (lago permanente:
  nunca é apagado, logo o link é estável como o `imagem` da 007); `router_midia.py` mapeia
  `mercado_imagem → bucket imagens` e `mercado_bruto → bucket mercado`.
- **Por quê:** o imgproxy só lê o bucket `imagens`; pôr as imagens no `sociman-mercado` exigiria mudar
  `IMGPROXY_ALLOWED_SOURCES` e o `_url` do `imaging.py`. O prefixo separa o lago do que é por perfil.
- **Alternativas:** linhas em `images` com `perfil_id` nulo (quebra a FK `NOT NULL` e a guarda "lago sem
  perfil"); segundo bucket no imgproxy (mais configuração e `IMGPROXY_ALLOWED_SOURCES` para manter).

## R10. Token `scol_`, portão global `coleta/portao.py` e cabeçalho de protocolo (DONO)

- **Decisão:** `coleta/credenciais.py` é cópia do `mcp/credenciais.py` com `PREFIXO = "scol_"` e o mesmo
  `FORMATO`; `coleta_clientes` = `mcp_clientes` + `mercado` (versionada; rotação troca o `<id>`, revogação é
  final, `no-store` na resposta que mostra o token). `coleta/portao.py` é a **segunda dependência global**
  do app (`dependencies=[Depends(mcp_portao.dependencia), Depends(coleta_portao.dependencia)]`): todo
  `Bearer scol_` passa por ela, na ordem do FR-025: credencial (401) → interruptor (`COLETA_HABILITADA` **e**
  `coleta_config.habilitada`: na fila responde vazia com `habilitada=false`; nas outras rotas 503
  `coleta_desligada`) → revogado/vencido (401) ou suspenso (403) → `Origin` presente (403 `coleta_origem`) →
  rota fora de `/api/coleta/*` (403 `escopo_coleta`) → limites no Redis (`coleta:min:<cliente>:<minuto>`,
  120/min; 429). Ator `Actor(kind="coletor", coleta_cliente_id=…)`, sem usuário e **sem versionamento**: a
  ingestão não chama `history.record` (o lago não tem `entity_versions`; a ficha é versionada por
  `hash_conteudo`). O cabeçalho `X-Sociman-Coleta-Protocolo: 1` é exigido nas rotas de ingestão; ausente ou
  diferente → 426 `protocolo_incompativel` com a versão esperada no corpo. O `scripts/check-secrets.mjs`
  ganha o padrão `scol_`. A gestão (`/api/coleta/clientes`, `/config`, `/config/continuar`) é
  `RequireHumanOwner`; o `mcp/mapa.py` põe a ingestão em `FORA` e a gestão em `PROIBIDAS`.
- **Por quê:** é o molde da 009, já testado, e cumpre FR-024/FR-025 sem segredo novo na API. Um portão
  global garante que um token do coletor nunca vale em `/api/perfis` por engano.
- **Alternativas:** reaproveitar `smcp_` com escopo `coleta` (misturaria dois atores e dois mapas); JWT
  assinado para o coletor (não revoga sem lista; rejeitada).

## R11. Como o coletor (host) alcança a API

- **Decisão:** `config.toml` com `api_url` e `ca_cert`. Em casa: `api_url = "https://192.168.86.47:8543"` e
  `ca_cert = "~/.config/sociman-coletor/sociman-ca.crt"` (a CA pública do edge, baixada de
  `http://192.168.86.47:8180/sociman-ca.crt`; `httpx.Client(verify=ca_cert)`). Em dev:
  `api_url = "http://localhost:8180"` (o edge só redireciona para HTTPS quando o `Host` é o IP da casa). O
  token fica em `~/.config/sociman-coletor/token` (600), nunca no `config.toml` nem no `Environment=` da
  unidade (legível por `systemctl show`). Timeouts 30 s (JSON) e 300 s (imagens); repetição com recuo só em
  erro de rede ou 5xx e só nas rotas idempotentes (todas as de ingestão são, por R13).
- **Por quê:** a porta da API não é publicada; o edge aplica rate limit e TLS; a CA da casa já existe (002).
- **Alternativas:** publicar `api:3001` no host (contraria a armadilha 3); `verify=False` (rejeitada).

## R12. Fila como tabela `mercado_fila`, montada pela trilha `mercado` com revezamento (DONO + Clarification 2)

- **Decisão:** `mercado_fila` é operacional e **nunca apagada** (trigger `mercado_recusa_delete()` só para
  `DELETE`; UPDATE permitido em `estado`, `lease_ate`, `coleta_id`, `ordem`, `resultado`). Colunas: `tipo`
  (CHECK com `produto | ranking | categorias | vitrine | loja | avaliacoes | produto_videos` e os reservados
  `busca_assunto | video`), `chave`, `rede`, `mercado`, `fonte`, `data_local`, `turno` (`manha | noite |
  NULL`), `nivel` (1 a 8, FR-026), `perfil_slot` (uuid ou NULL = "perfil global"), `ordem`, `paginas_estimadas`,
  `estado` (`pendente | entregue | ok | erro | repetido | expirada`), `lease_ate`, `coleta_id`. UQ
  `(tipo, chave, data_local, turno) NULLS NOT DISTINCT` (PG 15+; aqui 17).
  - **Trilha `mercado`** (`AGENDADOR_MERCADO_S`, padrão 300 s; ociosa sem `COLETA_HABILITADA` ou sem
    `coleta_config.habilitada`, com motivo no log), a cada volta e nesta ordem: (1) `cadencia.recalcular`
    (puro) → `UPDATE mercado_produtos SET calor, proxima_coleta_em` (estado técnico, permitido); (2) montar a
    fila do dia com `INSERT … SELECT … ON CONFLICT DO NOTHING` por tipo (idempotente: rodar 10× dá o mesmo
    conjunto); (3) **revezamento**: em Python (centenas de linhas), por `nivel`: as tarefas com perfil são
    agrupadas por `perfil_slot`; um produto de vários perfis vai para o perfil interessado que tem **menos
    tarefas já ordenadas naquele nível** (é "o primeiro cuja vez chega"); as sem perfil formam o slot
    global; `ordem = nivel·10⁶ + rodada·10³ + posicao_do_perfil`, onde `rodada` é o `ROW_NUMBER()` dentro do
    slot e `posicao_do_perfil` segue `perfis.created_at` (ordem fixa). A fila é entregue por `ordem`; o que
    sobra do dia **não é apagado**: amanhece `expirada` e o produto ganha `prioridade_atrasada = true`, que o
    põe no topo do nível no dia seguinte; (4) devolver leases vencidos (`lease_ate < now()` → `pendente`,
    `coleta_id = NULL`); (5) marcar `mercado_coletas` sem batimento há 10 min como `interrompida`; (6) criar
    interesses automáticos (abaixo); (7) notificar `coleta_parada` se ligada e sem item `ok` há 48 h
    (`dedupe_key = coleta_parada:<data>`).
  - **Lease:** `GET /fila?limite=` faz `UPDATE … WHERE id IN (SELECT id FROM mercado_fila WHERE estado =
    'pendente' AND data_local = :hoje ORDER BY ordem FOR UPDATE SKIP LOCKED LIMIT :n) SET estado =
    'entregue', lease_ate = now() + interval '20 minutes', coleta_id = :rodada RETURNING …`, respeitando o
    orçamento (R6). Fechar a rodada devolve as tarefas `entregue` dela.
  - **Interesses automáticos** (`system:mercado`, `Actor.kind` novo, com `history.record`): `ranking` para
    os 30 primeiros de cada ranking das categorias do perfil (UQ parcial `(coalesce(perfil_id, nil),
    mercado_produto_id, origem)` em `situacao <> 'encerrado'`); `loja`/`categoria` para produtos com
    `primeira_vez_em ≥ hoje − 30 d` de lojas seguidas e das categorias do perfil, até
    `MAX_RELACIONADOS_DIA = 10` por perfil (conta os criados hoje), e a notificação
    `mercado_relacionados_novos` com `dedupe_key = mercado_relacionados:<perfil>:<data>` (um aviso por dia).
- **Por quê:** a fila como tabela dá idempotência, lease e auditoria com SQL que o repo já usa (`SKIP
  LOCKED` da 004/021); calcular a fila "na leitura" (como dizia o insumo) tornaria o lease e o orçamento um
  cálculo repetido a cada pedido. O revezamento em Python é simples de testar (SC-010: 3 perfis, fila 3×).
- **Alternativas:** `ROW_NUMBER` por perfil direto no SQL de montagem (o produto comum a dois perfis exige
  escolher o slot antes de numerar: fica um `LATERAL` difícil de ler); fila no Redis (não é banco de
  registro); apagar o que sobrou do dia (contraria "nunca apagada").

## R13. Idempotência por `(tipo, chave, data_local, turno)`, dia e turno decididos pelo servidor (DONO)

- **Decisão:** `mercados.py` define `BR = Mercado(codigo="BR", fuso="America/Sao_Paulo", moeda="BRL")`. Na
  ingestão, `data_local` e `turno` vêm do `coletadoEm` do item **limitado** a `[now − 15 min, now]` (fora
  disso, vale `now()` do servidor), convertido ao fuso do mercado; `turno = manha` antes de **15:30**, senão
  `noite`. A foto grava sempre o turno real; a UQ `uq_mercado_produto_fotos (produto_id, data_local, fonte,
  turno)` e o `INSERT … ON CONFLICT DO NOTHING` fazem o reenvio responder `repetido` (nada gravado). Para a
  fila, tarefas de 1/dia têm `turno = NULL` e as de 2/dia `manha`/`noite` (UQ `NULLS NOT DISTINCT`).
- **Por quê:** FR-027 e o edge case do relógio errado; a janela de 15 min aceita o lote que chega minutos
  depois da visita sem confiar num relógio quebrado. 15:30 divide a janela 08–23 em duas metades úteis.
- **Alternativas:** só o relógio do servidor (um lote enviado às 00:02 dataria errado a visita das 23:58);
  só o do coletor (edge case da spec).

## R14. Cadência quente / semanal / parada e visitas de avaliações e vídeos (DONO + Clarification 3)

- **Decisão:** `cadencia.py` é puro (como `metricas/agenda.py`), com constantes nomeadas: `QUENTE_1_DIA`,
  `QUENTE_2_DIA` (novo em alta e manual: `manha` e `noite`), `SEMANAL_APOS_DIAS_FORA_RANKING = 7`,
  `PARADA_APOS_DIAS_SEM_INTERESSE = 30`; manual e vitrine nunca esfriam; parado volta a quente ao reaparecer
  em ranking (mesma volta). Avaliações: só quentes, na 1ª visita (2 páginas) e a cada
  `AVALIACOES_INTERVALO_DIAS = 30`; vídeos: só quentes, a cada `VIDEOS_INTERVALO_DIAS = 7` (1 página); ambos
  nos níveis 7 e 8 da fila e dentro do teto de páginas. O estado por produto (`calor`, `proxima_coleta_em`,
  `ultima_avaliacoes_em`, `ultimo_videos_em`) fica em `mercado_produtos` (técnico, atualizável).
- **Por quê:** FR-040/FR-040a; a função pura permite o teste de SC-005 (30 dias simulados) sem relógio.
- **Alternativas:** cadência por idade como na 016 (o produto não tem "idade" útil; o que importa é o
  interesse e o ranking).

## R15. Lago sem perfil, nada apagado, só-inserção com a função da 016; migration `0025_mercado_shop`; ator sem versão (DONO)

- **Decisão:** todas as tabelas do lago levam `rede platform` e `mercado text CHECK (mercado ~ '^[A-Z]{2}$')`
  e **nenhuma** coluna `perfil_id | conta_id | tenant_id | created_by | user_id` (guarda por inspeção do
  metadata). Só inserção, reaproveitando **`metricas_recusa_mudanca()`** (trigger `mercado_so_insercao`
  `BEFORE UPDATE OR DELETE`) em `mercado_produto_fichas`, `mercado_produto_fotos`, `mercado_loja_fotos`,
  `mercado_ranking_fotos`, `mercado_ranking_foto_itens`, `mercado_avaliacoes`, `mercado_produto_videos`,
  `mercado_imagens`, `mercado_produto_imagem_usos` e `mercado_coleta_eventos`. **Rodadas**
  (`mercado_coletas`): nunca apagadas e **imutáveis depois de fechadas** (função nova
  `mercado_recusa_fechada()`: recusa `DELETE` sempre e `UPDATE` quando `OLD.fim_em IS NOT NULL`); abertas,
  aceitam batimento e contagens. `mercado_produtos`, `mercado_lojas`, `mercado_categorias` e `mercado_fila`
  aceitam UPDATE só em colunas técnicas (lista no data-model) e nunca `DELETE` (`mercado_recusa_delete()`).
  A migration é a **`0025_mercado_shop`**, provisória: a 1ª tarefa confere `alembic heads` e renumera.
  Enums novos: `notificacao_tipo` ganha `coleta_captcha | coleta_login | coleta_bloqueio | coleta_layout |
  coleta_parada | coleta_retomou | mercado_relacionados_novos | mercado_novo_em_alta` (o último fica
  reservado para a 028) em bloco `autocommit` como na 0011.
- **Por quê:** princípio IX ("lago permanente e neutro"), FR-001/FR-002/FR-006 e a guarda FR-057. Reusar a
  função da 016 evita um segundo "só inserção" com outra mensagem.
- **Alternativas:** `created_by` nas tabelas do lago (quebra a guarda; a autoria é a `coleta_id`); soft
  delete (`archived_at`) no lago (não há o que arquivar: esfriar é cadência).

## R16. Terceiros: autor por hash com pepper, fotos de clientes como vêm, vídeos com @ público, poda em dois lados (DONO + Clarification 1)

- **Decisão:** `autor_hash = sha256(MERCADO_HASH_PEPPER ‖ rede ‖ id_do_autor)` (pepper `SecretStr` do `.env`
  da raiz, gerado pelo dono, nunca impresso; sem pepper, itens de avaliações respondem `invalido` com
  `pepper_nao_configurado`, e `GET /api/integracoes` mostra). As fotos anexadas pelos clientes são guardadas
  como vêm (R7, decisão do dono registrada). Vídeos top guardam `rede_video_id`, `autor_handle` (@ público),
  `views`, `likes`, `legenda`, `publicado_em`; nunca nome, foto ou bio. **Poda de PII:** a lista de chaves
  fica em `contracts/pii-chaves.json` (ex.: `nickname`, `nick_name`, `user_name`, `display_name`,
  `avatar*`, `bio`, `signature`, `uid` depois de virar hash); o coletor (`privacidade.py`) poda antes de
  enviar e o servidor (`coleta/privacidade.py`) poda de novo e **recusa** o item (`invalido`,
  `pii_no_bruto`) se ainda achar alguma chave; os dois testes leem o mesmo JSON para não divergir.
- **Por quê:** princípio IX e FR-010/FR-011/FR-029; o pepper impede ligar o hash a um id público por
  tentativa; duas podas porque o coletor é código de terceiro em relação à API.
- **Alternativas:** hash sem pepper (reversível por dicionário de ids); descartar as fotos de clientes
  (rejeitada pelo dono).

## R17. Sinais: captcha e login param e avisam; bloqueio e layout recuam 24 h; kill switch em 3 níveis (DONO)

- **Decisão:** `sinais.py` detecta, por fixtures: `captcha` (URL ou DOM de verificação), `login_perdido`
  (redirecionamento para login), `bloqueio_suspeito` (`BLOQUEIO_SERIE = 3` respostas 429/403 seguidas nos
  caminhos interceptados) e `layout_mudou` (`PARSES_VAZIOS_MAX = 5` páginas seguidas sem campo reconhecível).
  Em captcha ou login: `POST /api/coleta/eventos`, a rodada vira `pausada`, o Chrome fica aberto, o coletor
  consulta `GET /fila` a cada 60 s e só retoma quando `continuarEm` (gravado pelo dono em
  `POST /config/continuar`, só dono humano) estiver preenchido **e** passado `CAPTCHA_ESFRIAR_MIN = 60`; sem
  clique em `CAPTCHA_ESPERA_MAX = 2 h`, fecha a rodada como `pausada`. Em bloqueio ou layout: evento, rodada
  `interrompida` e `recuo_ate = now() + 24 h` no `coleta_config` (o servidor devolve fila vazia até lá).
  Eventos viram notificação para os donos com `dedupe_key = coleta_<tipo>:<data>` (um por tipo por dia).
  **Parar:** fila vazia (interruptor), arquivo `~/.config/sociman-coletor/PARAR` (conferido antes de cada
  tarefa) e `systemctl --user stop` (SIGTERM): nos três, termina a tarefa atual e fecha a rodada.
- **Por quê:** FR-017/FR-018/FR-019; o recuo fica no servidor para valer mesmo se o coletor reiniciar.
- **Alternativas:** resolver captcha (proibido); recuo só local (some num restart).

## R18. Multipart grande pela borda: `location` próprias, sem buffer, limites na API

- **Decisão:** duas `location` novas no edge, no padrão das uploads da 004/021 (`proxy_request_buffering
  off`, `proxy_set_header X-Sociman-Via ""`, zona `edge_api`):
  `location ~ ^/api/coleta/coletas/[^/]+/itens$ { client_max_body_size 34m; client_body_timeout 120s; }` e
  `location ~ ^/api/coleta/coletas/[^/]+/imagens$ { client_max_body_size 52m; client_body_timeout 300s;
  proxy_read_timeout 300s; }`. A API confere antes: ≤ 50 itens e ≤ 32 MB (413 `lote_grande`), ≤ 10 arquivos
  e ≤ 8 MB cada (413 `imagem_grande`), spool em `work/tmp` do HD (`TMPDIR`), sha conferido antes de qualquer
  gravação. As demais rotas de `/api/coleta/*` ficam no `/api/` padrão (8m). `docker compose restart edge`
  depois de mudar o template (armadilha 13).
- **Por quê:** as recusas devem vir da API com código, não um 413 do nginx; sem buffer, o nginx não grava
  50 MB em arquivo temporário no container.
- **Alternativas:** uma `location` genérica `/api/coleta/` com 52m (abriria o limite para rotas pequenas).

## R19. Consulta de leitura em SQL: `DISTINCT ON` para v(d), `LAG` para o GMV, índices e < 2 s com 10×

- **Decisão:** `mercado/consulta.py` monta, por pedido, um CTE de **escopo** (produtos do filtro: perfil →
  interesses ativos + categorias; loja; categoria; texto) e três CTEs `v_<ponto>` com
  `SELECT DISTINCT ON (produto_id) produto_id, vendidos, vendidos_min, vendidos_max, vendidos_exato,
  preco_centavos, fonte_prioridade FROM mercado_produto_fotos WHERE produto_id IN (escopo) AND data_local
  <= :d ORDER BY produto_id, data_local DESC, turno DESC, fonte_prioridade` para `d = de − 1`, `ate` e
  `ate − 7` (crescimento), onde `fonte_prioridade` é `CASE fonte WHEN 'affiliate' THEN 0 ELSE 1 END` quando
  a janela coincide com `vendas_7d/30d` (FR-044). O GMV usa `LAG(vendidos) OVER (PARTITION BY produto_id
  ORDER BY data_local, turno)` e `LAG(preco_centavos)` sobre as fotos de `[de − 1, ate]`, com
  `SUM(GREATEST(delta, 0) * preco_anterior)` e `BOOL_OR(delta < 0)` como `inconsistente`; min/max/ponto
  médio saem das colunas `vendidos_min/max`. Ordenação e `LIMIT/OFFSET` da aba Produtos acontecem **no
  SQL** sobre o CTE final (o número derivado é coluna); `calculo.py` (puro) só aplica as marcas (`estimado`,
  `motivos`, `amostraPequena`, `nFotos`) e os indicadores compostos (retorno por afiliado, novo em alta,
  quartis por categoria com `percentile_cont`).
  - **Índices:** `ix_mercado_produto_fotos_serie (produto_id, data_local DESC, turno DESC)` (o `DISTINCT ON`
    vira um index scan por produto), `ix_mercado_produto_fotos_data (data_local)`,
    `ix_mercado_ranking_itens_produto (produto_id, ranking_foto_id)`,
    `ix_mercado_interesses_perfil (perfil_id, situacao)`, `ix_mercado_produtos_categoria (categoria_id)`.
  - **Volume 10×:** 300 fotos/dia × 365 × 10 ≈ 1,1 M de fotos para ~3.000 produtos; o `DISTINCT ON` com o
    índice composto lê ~3 linhas por produto por ponto. `test_mercado_desempenho.py` semeia por SQL
    (`generate_series`, como a 019) e exige < 2 s nas rotas de leitura (FR-050, SC-007).
- **Por quê:** calcular em Python para milhares de produtos a cada pedido estoura os 2 s e repete lógica
  que o Postgres faz melhor; `DISTINCT ON` é o idioma do PG para "última foto até d".
- **Alternativas:** tabela agregada por dia (proibida: nada agregado é gravado, FR-042); `LATERAL` por produto
  (equivalente, menos legível); view materializada (idem, agregado gravado).

## R20. Guardas novos da seção "spec 026" (DONO)

- **Decisão:** em `test_constitution_guards.py`: (a) `pyproject` da API sem `playwright | selenium |
  pyppeteer` (soma a `SOCIAL_SDKS`); (b) `mercado/` e `coleta/` sem `httpx`, `playwright`,
  `sociman_api.publicacao` e sem literais de hosts da rede (lista nos testes, nunca em `src/`); (c) metadata:
  nenhuma tabela `mercado_*` ou `coleta_*` do lago com `perfil_id | conta_id | tenant_id | created_by |
  user_id` (exceção declarada: `mercado_interesses`, `mercado_perfil_config`, `coleta_clientes`,
  `coleta_config`); (d) nenhum `delete | DELETE | TRUNCATE | apagar_por_excecao` em `mercado/` e `coleta/`
  (AST + literais); (e) integração: UPDATE e DELETE nas tabelas só-inserção levantam erro; (f) o portão
  `scol_` recusa `escopo_coleta` fora de `/api/coleta/*` e o token só existe como hash
  (`coleta_clientes.token_hash`, sem coluna de texto); `check:secrets` acusa o padrão; (g)
  `test_agendador_sem_trilha_nova` ganha `mercado`; (h) leituras `mercado_*` só `GET` e sem `history`
  (como a 019); (i) nenhuma rota ou `operationId` com `tiktok` (já coberto por `PUBLISH_TERMS`). No coletor
  (`apps/coletor/tests/`): `test_acoes_permitidas` (R5), `test_privacidade_poda` (R16), `test_ritmo` (R6) e
  `test_log_sem_pessoal` (o `log.py` só aceita contagens, ids de produto, durações e códigos; um teste
  passa cookie, @ e texto e espera recusa).
- **Por quê:** FR-057 e a constitution ("cada regra inegociável tem teste").

## R21. Testes: coletor falso na ingestão, servidor HTML sintético para o coletor, e2e sem rede

- **Decisão (pytest da API):** `tests/integration/mercado_helpers.py` com `criar_cliente_coleta`,
  `ligar_coleta` (aceite + interruptor + `COLETA_HABILITADA`), e o **coletor falso** `ColetorFalso` (usa o
  `TestClient` com o token `scol_` e o cabeçalho de protocolo; métodos `abrir_rodada`, `enviar_produto(dias,
  curva)`, `enviar_ranking`, `enviar_avaliacoes`, `enviar_imagem(bytes)`, `fechar`), que gera as fotos
  sintéticas dos cenários da US1 (subindo, estável, sem comissão) e das US4/US5. Nenhum fake HTTP novo: a
  ingestão é a própria API.
- **Decisão (coletor):** `apps/coletor/tests/` em dois níveis. **Unitários sem navegador**: `ritmo` (RNG e
  relógio injetados), `privacidade`, `sinais` (fixtures HTML/JSON), `parser` (fixtures anonimizadas),
  `acoes_permitidas` (AST), `log`. **Integração com navegador** (`@pytest.mark.navegador`, só com
  `COLETOR_TESTE_CHROME=1` e Chrome presente; roda no quickstart): `servidor_sintetico.py` (stdlib
  `http.server` em `127.0.0.1`) serve páginas HTML que carregam JSON pelos **mesmos caminhos** de
  `INTERCEPTAR` (os padrões são por caminho, sem host) e uma página de captcha sintética; `api_falsa.py`
  (stdlib) responde `/api/coleta/*` com fila apontando para o servidor sintético; o teste roda
  `uma-vez --limite 3` num perfil temporário e confere 3 itens aceitos, pausas respeitadas e parada no
  captcha, e que **nenhum** host além de `127.0.0.1` foi pedido (listener de `request`).
- **Decisão (e2e):** o coletor falso é o próprio teste Playwright, pelo `request` (APIRequestContext) contra o
  edge da stack efêmera, com o token criado pela UI em `/app/configuracoes/coleta`; fixtures em
  `e2e/fixtures/mercado/*.json`; `COLETA_HABILITADA=true` e `MERCADO_HASH_PEPPER` fixo no
  `docker-compose.e2e.yml`. O `openshorts-fake` não muda. Nenhum teste chama a rede real.
- **Por quê:** o padrão da casa (fakes por transporte e stack efêmera); a ingestão é HTTP, então o "fake" é um
  cliente, não um servidor.
- **Alternativas:** serviço `coletor` no compose do e2e com Chrome (Xvfb no Docker; contraria R1);
  fake da rede no `openshorts-fake` (a API nunca fala com a rede: não há o que falsear).

## R22. Volume e espaço: estimativa e piso do HD

- **Decisão:** estimativa por dia com 300 páginas: bruto gzip 300 × ~300 KB ≈ **90 MB/dia** (≈ 33 GB/ano);
  imagens só de produto novo ou ficha mudada (R7): ~40 primeiras visitas × 6 + avaliações ≈ 300 a 400
  imagens × ~250 KB ≈ **100 MB/dia** (≈ 36 GB/ano), com o teto de 1.500/dia como limite superior (≈ 375
  MB/dia); Postgres: ~300 B por foto → < 50 MB/ano (NVMe, desprezível). Total ≈ **70 GB/ano** no HD (1,7 TB
  livres), em linha com o insumo. Toda gravação passa por `datadir.ensure_writable(n)` (piso
  `DATA_MIN_FREE_GB = 20`); o bloco `coleta` do `GET /api/integracoes` mostra bytes do mês e espaço livre.
- **Por quê:** FR-030 e a constitution (HD, sentinela e piso); o número confirma que o bruto cabe sem
  política de retenção (o lago é permanente).
- **Alternativas:** compressão `zstd` (melhor razão, mas mais uma dependência; gzip da stdlib basta).

## R23. Ponte com a 012 condicionada ao merge (DONO)

- **Decisão:** `produtos.mercado_produto_id` (uuid nulo, FK → `mercado_produtos`, em
  `__versioned_fields__`) e "Adotar no catálogo" (`POST /api/mercado/produtos/{id}/adotar {perfilId}`, só
  humano) entram **só depois do merge da 012** nesta branch: a migration e o service ficam numa tarefa
  marcada `[depende da 012]`, e o 1º passo da tarefa confere a existência do pacote `produtos/` e da coluna
  esperada. "Adotar" copia título, categoria, link da loja e argumentos para `produtos.create` e **copia** as
  imagens do lago para `images` do perfil (novo objeto em `perfis/<perfil>/produtos/…`, kind `produto`,
  mesmo conteúdo), grava `details.origem = "mercado_026"` no histórico e cria o interesse `manual` se não
  existir; adotar de novo → 409 `ja_adotado` com o `produtoId`.
- **Por quê:** a worktree parte de `1ce278d`, sem `produtos/`; escrever contra um pacote inexistente geraria
  conflito no merge. Copiar (e não referenciar) mantém o lago sem perfil e o catálogo íntegro se a imagem do
  lago mudar de ficha.
- **Alternativas:** referenciar `mercado_imagens` direto do produto (acopla o catálogo ao lago).

## R24. O que fica pronto para a 027 e a 028

- **Decisão:** (a) tipos `busca_assunto` e `video` já no CHECK de `mercado_fila.tipo` e no contrato, com a
  ingestão respondendo `invalido` (`tipo_nao_suportado`) até a 027; (b) `mercado_produto_videos` criada e
  populada pelas tarefas `produto_videos` desde já; (c) `mercado_interesses.origem` com `video` e
  `tema_id` (FK nula → `aprendizado_temas`); (d) tools MCP `mercado_*` de leitura em `TOOLS` (escopo
  `leitura`, descrições em pt-BR: produtos, detalhe, série, rankings, lojas, categorias, interesses) para a IA
  da 028 ler o cockpit e propor por `anotacoes`; (e) `fonte` versionada (`tiktok_shop/1`) e
  `fontes/registro.py` como único importador do adaptador (molde `publicacao/registro.py`); (f) enum
  `mercado_novo_em_alta` reservado (R15); (g) `mercados.py` com a dimensão em código para outro país entrar
  sem migration de forma.
- **Por quê:** evitar migration e mudança de contrato a cada spec da sequência; nada disso cria tela nem
  comportamento novo na 026.
- **Alternativas:** deixar tudo para a 027 (mais uma migration de enum e outra rodada no `mcp/mapa.py`).
