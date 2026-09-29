# Pesquisa (Fase 0): 004-kit-de-marca

Fontes consultadas: a spec, a constitution 2.0.0, o código da 003 (`history.py`, `storage.py`,
`imaging.py`, `perfis/*`), o `docker-compose*.yml`, o `apps/api/Dockerfile`, o edge
(`docker/nginx/default.conf.template`) e o gerador de cortes em `../openshorts`
(`hooks.py:192-205`, `subtitles.py:224-545`, `app.py:3696` e `:4885`, `main.py:1160-1185`).

## R1. Onde roda o processamento de vídeo (FR-014)
- **Decisão:** um serviço novo no compose, **`worker`**, com a **mesma imagem da API** (que passa a
  ter `ffmpeg`, R2) e o comando `sociman worker`. A fila é a **própria tabela `cortes`** no
  PostgreSQL:
  - o worker pega o próximo com
    `SELECT … FROM cortes WHERE status = 'na_fila' ORDER BY queued_at LIMIT 1 FOR UPDATE SKIP LOCKED`,
    marca `processando`, `started_at`, `heartbeat_at` e `attempts + 1`, e faz commit antes de
    começar o ffmpeg;
  - sem trabalho, dorme 2 s e tenta de novo (polling simples; `LISTEN/NOTIFY` fica para quando
    fizer falta);
  - durante o processamento, atualiza `progress` e `heartbeat_at` a cada 2 s, no máximo;
  - **reinício (FR-014):** ao subir, e a cada volta do laço, o worker devolve para `na_fila` todo
    corte `processando` com `heartbeat_at` mais antigo que 120 s. Depois de 3 tentativas
    interrompidas, o corte vai para `falhou` com "O processamento foi interrompido 3 vezes";
  - **um por vez:** uma réplica do worker e um corte por vez (sem opção de paralelismo).
- **Por quê:**
  - "sobreviver a reinício" exige estado durável, e a constitution diz que o Redis não é banco de
    registro. O Postgres já guarda o corte, então a fila no mesmo lugar não tem estado duplicado;
  - `SKIP LOCKED` é o padrão consagrado de fila em Postgres, sem dependência nova;
  - um processo separado isola o ffmpeg (CPU e ~1 GB de RAM, medidos) do uvicorn, e o
    `--reload` da API em dev não mata um processamento no meio;
  - mesma imagem: nenhum Dockerfile novo, e o worker usa os mesmos modelos e o mesmo `storage.py`.
- **Alternativas:**
  - RQ ou Celery sobre o Redis: dependência nova, o Redis viraria dado de registro (contra a
    constitution), e o estado ficaria dividido entre Redis e Postgres;
  - `BackgroundTasks` do FastAPI ou thread dentro da API: morre com o processo, some no
    `--reload` e disputa CPU com as requisições;
  - chamar o OpenShorts (`/api/hook`): ele só tem os 6 estilos fixos, não tem marca d'água por
    perfil nem card final (Assumptions da spec).

## R2. Composição com ffmpeg (FR-015)
- **Decisão:** **renderizar as três camadas como PNG com Pillow** e **compor com um único
  `ffmpeg -filter_complex` de `overlay`s**:
  1. **gancho:** PNG do tamanho do texto, com a quebra por largura em pixels (até 3 linhas),
     `ImageDraw.text(stroke_width, stroke_fill)` para o contorno e `rounded_rectangle` com alfa
     para o fundo com opacidade (o mesmo método do `hooks.py` do OpenShorts). Posição: topo = 12%
     da altura, centro = meio, base = 70% (como o OpenShorts). `enable='between(t,0,D)'`;
  2. **marca d'água:** PNG do logo, da imagem própria ou do texto `@handle` (renderizado com
     Pillow, na fonte da legenda). Escala = `escala% × largura do vídeo`, opacidade com
     `colorchannelmixer=aa=…`, posição por canto com a margem do kit. Visível o vídeo todo;
  3. **card final:** PNG do quadro inteiro (cor de fundo, CTA centralizado e, se ligado, o logo
     acima do CTA), sobreposto a partir de `duração − N` (`enable='gte(t,T-N)'`). O card cobre a
     marca d'água (é a última camada).
  - Todas as medidas são **relativas ao tamanho do vídeo** (edge case de vídeo horizontal).
  - **Saída:** sempre MP4, H.264 (`libx264 -preset veryfast -crf 20 -pix_fmt yuv420p`),
    `-movflags +faststart` (o navegador começa a tocar antes do fim do download). Resolução e fps
    do original são mantidos (nenhum `scale` no vídeo base).
  - **Áudio:** `-map 0:a?` (vídeo sem áudio passa). `-c:a copy` quando o áudio é AAC; senão
    (Opus de WebM, PCM de MOV), `-c:a aac -b:a 192k`.
  - **Progresso:** `-progress pipe:1 -nostats`, lendo `out_time_us` e dividindo pela duração do
    ffprobe. O percentual vai para o banco a cada 2 s, no máximo.
  - **Tempo limite:** o processo do ffmpeg é morto se passar de 10 min (falha "Tempo de
    processamento esgotado").
  - **Pasta de trabalho:** `/hd/work/cortes/{corte_id}/` no HD (R5): o original baixado do
    MinIO, os PNGs das camadas e o `marcado.mp4` temporário. O ffmpeg roda com `cwd` e `TMPDIR`
    nela, e a pasta é removida no `finally`.
- **Medição (2026-09-29, host `sakai-desktop`, 16 threads, ffmpeg 6.1):** vídeo sintético de
  60 s em 1080×1920 a 30 fps com áudio AAC, com as três camadas: **18 s** (`veryfast`), pico de
  1,1 GB de RAM. Dá folga larga para a SC-003 (< 2 min), mesmo que um vídeo real custe o dobro.
- **Por quê:**
  - o `drawtext` não quebra linha por largura, não desenha caixa arredondada e fica frágil com
    escape de texto do usuário (`:`, `'`, `%`); no PNG, o texto nunca entra na linha de comando;
  - o mesmo renderizador Pillow serve à prévia fiel no servidor, se um dia fizer falta, e aos
    testes (o que foi desenhado é conhecido);
  - uma única passada de encode: um só `libx264`.
- **Alternativas:**
  - `drawtext` com `fontfile` e `box=1`: sem quebra por pixel nem cantos arredondados, e escape
    difícil;
  - legendas ASS para o gancho: mais expressivo, mas é outra linguagem para manter;
  - acrescentar o card no fim (concat): muda a duração e exige áudio para os segundos extras.
    **Decisão do dono (2026-09-29): o card fica por cima dos últimos N segundos.**

## R3. Validação de vídeo e de fonte (FR-009, FR-013, US4-4)
- **Vídeo — decisão:** `ffprobe -v error -print_format json -show_format -show_streams` no arquivo
  temporário, antes de ir para o MinIO:
  - aceita se o `format_name` contém `mov,mp4`, `matroska,webm` (só WebM) e existe pelo menos um
    stream de vídeo com codec `h264`, `hevc`, `vp8`, `vp9`, `av1` ou `prores`;
  - recusa (400 `invalid_video`) com a razão: "Não é um vídeo aceito" (ffprobe falha ou sem
    stream de vídeo), "Vídeo mais longo que 3 minutos" (`format.duration > 180`), "Arquivo maior
    que 500 MB", "Resolução não suportada" (lado > 4096 ou < 240);
  - o ffprobe roda com `timeout=30` e sem acesso à rede (`-protocol_whitelist file`);
  - guarda `duration_ms`, `width`, `height`, `fps`, `video_codec`, `audio_codec` (ou null) e a
    rotação (vídeo de celular com `rotate=90` troca largura e altura).
  - Um arquivo que o ffprobe aceita mas o ffmpeg não decodifica falha no worker com "O vídeo está
    corrompido ou não pôde ser lido" e pode ser tentado de novo (US4-5).
- **Fonte — decisão:** **Pillow** (`ImageFont.truetype`), que já é dependência:
  - o arquivo tem até 10 MB e começa com a assinatura `00 01 00 00` ou `true` (TTF) ou `OTTO`
    (OTF). Coleções (`ttcf`), WOFF e WOFF2 são recusados;
  - `ImageFont.truetype(BytesIO(data), 48)` carrega pelo FreeType, e `getname()` dá a família e
    o estilo (guardados para a exportação e para o `@font-face` da prévia);
  - renderizar a amostra "Os achadinhos que você queria" (`getbbox`) precisa dar largura > 0;
  - erro: 400 `invalid_font` ("Não é uma fonte TTF/OTF", "Arquivo maior que 10 MB").
- **Alternativas:** `fontTools` daria o `cmap` completo (saber se faltam acentos) e os nomes da
  tabela `name`, mas é dependência nova para um ganho que a spec não pede (princípio VIII).
  Fica anotado para quando a falta de glifo virar problema.

## R4. Upload grande (FR-013)
- **Decisão:**
  - **edge:** uma `location` só para o envio de cortes, antes da `/api/`:
    `location ~ ^/api/perfis/[^/]+/cortes$` com `client_max_body_size 520m`,
    `proxy_request_buffering off` (o nginx repassa enquanto recebe, sem arquivo temporário no
    edge), `client_body_timeout 120s`, `proxy_read_timeout 300s` e o mesmo `limit_req` e os
    mesmos headers da `/api/`. As demais rotas seguem com 8m;
  - **API:** recusa cedo pelo `Content-Length` (> 500 MB + 1 MB de folga do multipart → 413
    `payload_too_large` com "Arquivo maior que 500 MB"), antes de ler o corpo. Também antes de
    ler o corpo, confere o sentinela e o piso de espaço livre do HD (R5: 503 ou 507);
  - o `UploadFile` do Starlette já faz spool em disco (`SpooledTemporaryFile`, 1 MB em memória);
    o arquivo nunca fica inteiro na RAM. O spool vai para `/hd/work/tmp` (`TMPDIR` da API, no HD,
    R5), nunca para o `/tmp` do container, e é removido no `finally`;
  - depois do ffprobe (R3), o arquivo vai ao bucket `sociman-videos` com `put_object(…, length=-1,
    part_size=16 MiB)` a partir do arquivo em disco (upload multipart do minio-py). O
    temporário é removido no `finally`;
  - **envio interrompido:** a linha do corte só é criada depois que o objeto está no MinIO e o
    ffprobe passou. Um envio cortado não cria linha nem aparece na lista (edge case);
  - o SPA envia com `XMLHttpRequest` (o `fetch` não dá progresso de upload) e mostra o
    percentual.
- **Alternativas:**
  - URL pré-assinada do MinIO para o navegador enviar direto: exigiria publicar a porta S3 do
    MinIO (hoje fechada) ou mais uma `location` no edge, e a validação viraria assíncrona;
  - aumentar o limite de toda a `/api/`: abre 520 MB para qualquer rota.

## R5. Armazenamento: o MinIO único passa para o HD (FR-016, FR-018, SC-007)
- **Decisão do dono (2026-09-29), que vira regra na constitution 2.1.0:** tudo o que é pesado
  ou cresce sem parar fica no **HD de 4 TB** (`/dev/sda1`, ext4, rótulo `BACKUP`, montado em
  `/media/sakai/BACKUP`, 2,1 TB livres, dono `sakai` 1000:1000). No NVMe ficam só o código, os
  containers, o PostgreSQL e o Redis. Não há segundo MinIO nem cota por soma de bytes.
- **Layout no HD:** `SOCIMAN_HD_DIR` (padrão `/media/sakai/BACKUP/tiktok/sociman`) contém:
  - `.sociman-volume`: o **sentinela**, criado só por `scripts/hd-setup.sh` (R12);
  - `minio/`: os dados do **serviço `minio` existente**, que deixa o volume nomeado
    `minio-data` (hoje no NVMe) e passa a usar este bind mount;
  - `work/`: temporários grandes (spool de upload da API e pasta de trabalho do worker e do
    ffmpeg). Nada de vídeo no `/tmp` dos containers.
- **Buckets, todos no mesmo MinIO:**
  - `sociman` (como hoje; o único que o imgproxy lê): logos, banners, imagens de marca d'água
    (`perfis/{perfil_id}/{uuid4}.png`) e pôsteres dos cortes
    (`perfis/{perfil_id}/cortes/{corte_id}/poster.jpg`);
  - `sociman-fonts`: `perfis/{perfil_id}/{uuid4}.{ttf|otf}`;
  - `sociman-videos`: `perfis/{perfil_id}/cortes/{corte_id}/original.{ext}` e `…/marcado.mp4`.
  - O `minio-init` passa a criar os três. O `IMGPROXY_ALLOWED_SOURCES` continua
    `s3://sociman/`, então fontes e vídeos nunca passam pelo imgproxy.
- **Compose:**
  - `minio`: `user: "1000:1000"` (hoje roda como root), bind mount em sintaxe longa
    `SOCIMAN_HD_DIR → /vol` com `bind.create_host_path: false` (se a pasta não existir, o
    container **não sobe**, em vez de o Docker criá-la no NVMe), e `entrypoint` que confere
    `test -f /vol/.sociman-volume` antes de `minio server /vol/minio`. Sem o sentinela, sai com
    uma mensagem clara no log. O console continua em 9101 (só dev); a porta S3 continua fechada;
  - `api` e `worker`: bind de `SOCIMAN_HD_DIR` em `/hd`, também com `create_host_path: false`.
    Usam `/hd/.sociman-volume` (sentinela), `os.statvfs('/hd')` (espaço livre) e
    `/hd/work` (`TMPDIR=/hd/work/tmp` na API, para o spool do Starlette; `/hd/work/cortes/{id}/`
    no worker). Os bytes de imagens, fontes e vídeos passam sempre pelo S3 do MinIO;
  - o volume nomeado `minio-data` sai do compose, mas **não é apagado** pela migração (R12): o
    dono o remove à mão depois de verificar.
- **`storage.py`:** funções recebem o bucket (`"imagens" | "fontes" | "videos"`, mapeados em
  `S3_BUCKET`, `S3_FONTS_BUCKET` e `S3_VIDEOS_BUCKET`), com `put`, `put_file` (multipart, sem
  ler em memória), `get`, `get_to_file`, `stat` e `get_range(key, offset, length)` (R6).
  Continua **sem delete**. Toda escrita passa antes por `hd.ensure_writable(n_bytes)`.
- **Proteções obrigatórias (FR-018), para o MinIO e para o `work/`:**
  1. **sentinela:** sem `/hd/.sociman-volume`, o `minio` não sobe, e a API e o worker recusam
     gravar. Envio de corte, de fonte e de imagem (inclusive o logo e o banner da 003): 503
     `storage_unavailable` ("O HD de dados não está disponível"). O worker confere antes de
     pegar um corte e, sem o sentinela, não pega nada e espera 30 s; se o HD sumir no meio, o
     corte volta para a fila sem contar tentativa;
  2. **piso de espaço livre:** qualquer escrita é recusada quando o espaço livre do HD,
     descontado o tamanho da escrita, fica abaixo de `HD_MIN_FREE_GB` (padrão 20): 507
     `storage_full` ("Pouco espaço no HD de dados"). O envio de corte confere antes de ler o
     corpo (pelo `Content-Length`). O worker confere, antes de processar, que sobram pelo menos
     3× o tamanho do original (cópia de trabalho, resultado temporário e resultado no MinIO);
     senão, marca `falhou` com "Pouco espaço no HD de dados" (dá para tentar de novo);
  3. `GET /api/armazenamento` devolve `{available, reason, freeBytes, totalBytes, minFreeBytes,
     cortesBytes}`, e a aba Cortes mostra uso e espaço livre. O `/api/health` ganha
     `storage: ok | unavailable | low_space`, sem mudar o `status` geral (login e kit continuam
     respondendo).
  - **Nada é apagado** (FR-016). A única limpeza é do `work/`: o worker remove a própria pasta
    de trabalho no `finally` e, ao subir, as pastas de `work/cortes/` que sobraram de um
    processo morto. São temporários, nunca vídeos guardados.
- **Riscos (registrados):**
  - **HD fora do ar = SociMan sem mídia:** sem o HD, `minio`, `api` e `worker` não sobem
    (`create_host_path: false`); se o HD sumir com a stack no ar, logos, fontes e vídeos param
    de abrir e as escritas são recusadas. Nada vai para o NVMe. É o custo aceito de ter um MinIO
    só;
  - o HD se chama `BACKUP`, mas **não é backup**: é o único lugar dos arquivos de mídia. Backup
    fica fora desta spec;
  - HD mecânico/USB é mais lento que o NVMe: o upload e o streaming ficam limitados pela rede de
    casa, e o ffmpeg é limitado pela CPU (a medição de 18 s foi com arquivos no NVMe; refazer
    com `work/` no HD na verificação da SC-003);
  - o MinIO passa a rodar como UID 1000: os arquivos migrados do volume antigo (de root) precisam
    de `chown` na migração (R12);
  - PostgreSQL (NVMe) e MinIO (HD) podem divergir se um for restaurado sem o outro; as linhas
    guardam `sha256` e bytes para conferência.
- **Alternativas:**
  - segundo MinIO só no HD para vídeos (e depois fontes): duas instâncias, duas credenciais e
    dois clientes, para o mesmo ganho (rejeitada pelo dono ao simplificar);
  - bind mount direto do HD na API e no worker, sem MinIO para vídeos: dois jeitos de guardar
    arquivo e streaming com `Range` escrito à mão;
  - cota por soma de bytes no NVMe (proposta original): rejeitada pelo dono.

## R6. Servir vídeo, fonte e imagem de marca d'água (US4-2, FR-011)
- **Problema:** o SPA autentica por `Authorization: Bearer` (padrão híbrido cookieless do volans),
  e `<video src>`, `<a download>` e `@font-face` não mandam esse header. O imgproxy só serve
  imagem.
- **Decisão:** **links assinados de curta duração**, servidos pela API:
  - `POST /api/midia/links` (autenticado) devolve URLs `/api/midia/{token}`; o token é
    `base64url(payload).base64url(HMAC-SHA256)`, com o `JWT_SECRET` e um domínio separado
    (`"midia:"`); o payload tem `{k: tipo, id, v: variante, exp}`;
  - validade: 1 h para vídeo e fonte na interface. Nos links da exportação (FR-011), **sem `exp`**
    (decisão do dono, 2026-09-29): valem enquanto o arquivo existir, e arquivos nunca são
    apagados. É o mesmo nível das imagens públicas da 003 (URL impossível de adivinhar). O
    `kind` do token limita o link a fonte e imagem de marca d'água; vídeo nunca sai sem `exp`;
  - `GET /api/midia/{token}` não pede login, confere assinatura e validade, e faz streaming do
    bucket certo (`sociman-videos`, `sociman-fonts` ou `sociman`) com **suporte a `Range`** (206, `Accept-Ranges: bytes`, `get_object(offset, length)`),
    necessário para o `<video>` pular para o meio. `?download=1` acrescenta
    `Content-Disposition: attachment; filename="<slug>-<data>-marcado.mp4"`;
  - `Cache-Control: private, max-age=3600` e `X-Content-Type-Options: nosniff`; o
    `Content-Type` vem da tabela, nunca do pedido;
  - o edge cria `location ^~ /api/midia/` com `proxy_buffering off` (streaming) e
    `proxy_read_timeout 300s`;
  - o service worker da PWA já ignora `/api/` (`navigateFallbackDenylist`, spec 002), então não
    cacheia vídeo.
- **CSP:** `default-src 'self'` já cobre `media-src` e `font-src` na mesma origem; nada muda
  (princípio V). A prévia **não** usa `blob:` (bloqueado pelo `media-src` herdado).
- **Alternativas:**
  - URL pré-assinada do MinIO: exigiria expor o MinIO pelo edge;
  - cookie de sessão para mídia: quebraria o padrão cookieless;
  - baixar o vídeo com `fetch` e tocar como `blob:`: carrega 500 MB em memória e exige
    `media-src blob:`.

## R7. Prévia do kit na interface (FR-008)
- **Decisão:** prévia **só no navegador**, com HTML e CSS sobre um quadro 9:16 (um
  `<div>` com `aspect-ratio: 9/16` e a imagem de fundo neutra, ou o quadro do último corte
  pronto do perfil, extraído pelo worker como `poster.jpg` no bucket `sociman` e servido pelo
  imgproxy):
  - **fontes:** `FontFace` carregado da URL assinada (R6), com a família interna
    `sociman-{id}`; as quatro padrão vêm da API, empacotadas na imagem (R8);
  - **legenda:** o mesmo cálculo do OpenShorts, para a prévia bater com o resultado:
    `px = font_size × 0,85 / 288 × altura_do_quadro` e margem de `43/288` da altura
    (`subtitles.py:504` e `:228`); contorno com `-webkit-text-stroke` + `paint-order: stroke`;
    fundo com opacidade quando `bg_opacity > 0`; no karaokê, uma palavra com a cor de destaque;
    `pop` e `glow` aproximados com `transform: scale` e `text-shadow`;
  - **gancho:** a mesma geometria do renderizador Pillow (R2): largura máxima de 90%, padding
    30/25, raio 20, fonte de 5% da largura × (0,8 | 1 | 1,3) para P, M e G;
  - **marca d'água e card final:** `<img>` e `<div>` posicionados com as mesmas regras;
  - um aviso fixo: "Prévia aproximada; o resultado final sai do processamento".
- **Por quê:** a spec pede prévia sem processar vídeo; CSS é instantâneo a cada tecla.
- **Alternativas:** `<canvas>` (mais código para quebra de linha e contorno, sem ganho visível);
  prévia renderizada no servidor com Pillow (fiel, mas uma requisição por tecla).

## R8. Fontes padrão
- **Decisão:** Anton e Noto Serif Bold (licença OFL, os mesmos arquivos de
  `../openshorts/fonts`) e Liberation Sans e Liberation Serif Bold (OFL) ficam **no pacote da
  API**, em `sociman_api/marca/fonts/`, com os arquivos de licença. Identificadores fixos:
  `padrao:anton`, `padrao:noto-serif-bold`, `padrao:liberation-sans`, `padrao:liberation-serif`.
  O worker usa os arquivos direto; o SPA os recebe por `GET /api/fontes-padrao/{chave}` (público,
  arquivos livres, `Cache-Control` longo).
- **Por quê:** o worker não depende de fontes do sistema, e a lista é a mesma do gerador de
  cortes (FR-010). Instalar `fonts-liberation` via apt daria o mesmo resultado, mas espalharia
  a origem das fontes.

## R9. Exportação (FR-011, SC-002)
- **Decisão:** `GET /api/perfis/{id}/kit/export` devolve JSON com `"schema": "sociman.kit/1"`
  (o número só muda com quebra de formato), a versão do kit, os **tokens resolvidos** (cores da
  paleta viram hex; fontes viram `{id, nome, família, url}`) e a seção `openshorts`:
  - **`subtitle`:** os campos do `SubtitleRequest` (`app.py:3696`), com os valores já nas faixas
    do `_clamp_number` do gerador (`subtitles.py:505-512`): `font_size` 10–200, `border_width`
    0–10, `bg_opacity` 0–1, `position` top|middle|bottom, `style` classic|karaoke, `effect`
    none|glow|pop|box, `base_opacity` fixo em 1.0 (não é token do kit; é o valor que o próprio
    gerador escolheu como padrão), `uppercase`;
  - **fonte da legenda:** o gerador só tem Anton, Noto Serif e Liberation (via
    `openshorts-fontmap.conf`). Com fonte padrão, `font_name` é a família exata. Com fonte
    própria do perfil, `font_name` cai para a padrão mais parecida (serifada → "Noto Serif";
    condensada/display → "Anton"; senão "Liberation Sans"), e `approximations` registra a troca
    e o link da fonte original;
  - **`hook`:** `{style, size, position, duration_seconds, enabled}`, com **`enabled: false`
    sempre** (decisão do dono, 2026-09-29: só o SociMan queima o gancho). O produtor gera os
    cortes no OpenShorts **sem o gancho automático** (sem `viral_hook_text` queimado; ver
    `main.py:1160-1185`), senão o corte sai com dois ganchos. O preset mais próximo fica só como
    referência, calculado assim:
    1. o grupo vem do fundo: opacidade < 0,2 → só `outline` e `outline_yellow`; senão, só os
       4 com caixa (`classic`, `dark`, `yellow`, `red`);
    2. dentro do grupo, a distância é `0,6 × ΔE(fundo) + 0,4 × ΔE(texto)` (ΔE CIE76 em
       CIELAB, conversão sRGB → Lab feita à mão, sem dependência); no grupo sem caixa, só o
       texto conta;
    3. `exact = distância < 5`; se não for exato, `approximations` recebe uma nota legível
       (ex.: "fundo #FF5FA2 aproximado para red #DC2626; texto exato") e a fonte do gancho
       (o gerador usa sempre Noto Serif Bold);
    4. `size` P|M|G → S|M|L; `position` topo|centro|base → top|center|bottom.
  - **`assets`:** links assinados (R6) **sem validade** das fontes do perfil usadas no kit e da
    imagem de marca d'água (`expiresAt: null`).
  - A interface baixa como `kit-<slug>-v<versão>.json` (`Content-Disposition`).
  - **SC-002:** um teste gera kits aleatórios válidos (hipótese simples com `random` e semente
    fixa, sem dependência) e confere cada campo de `openshorts.subtitle` contra as faixas e
    enums copiados do gerador.
- **Alternativas:** YAML (o gerador e os agentes já falam JSON); só o preset sem os tokens (perde
  o que o gerador não suporta, contra a US3-2).

## R10. Modelo de dados e histórico (FR-007, princípio VII)
- **Decisão:** reaproveitar `entity_versions` e `history.py` da 003:
  - **`brand_kits`**, um por perfil, com uma coluna JSONB por seção (`palette`, `caption`,
    `hook`, `watermark`, `end_card`, `catchphrases`, `series`). O snapshot é por seção, então o
    `changed_fields` do histórico diz "legenda" ou "gancho", e a tela de histórico genérica da
    003 funciona sem mudança;
  - o kit é **preguiçoso**: sem linha, o `GET` devolve o kit padrão com `version: 0`, e o
    primeiro `PUT` com `version: 0` cria a linha (`created`). Nenhuma migration de dados;
  - o `PUT` troca o kit inteiro (os tokens são validados juntos, porque um depende do outro:
    referências à paleta e às fontes). Controle otimista e reversão (só dono) como na 003;
  - **fontes** (`brand_fonts`): versionadas (`name`, `archived`), arquivar e restaurar, nunca
    apagadas; arquivar em uso → 409 `font_in_use` com os campos do kit que a usam (US2-3);
  - **imagem de marca d'água:** reaproveita a tabela `images` com o novo valor `watermark` no
    enum `image_kind` e o `imaging.validate_image` (PNG ou WebP com canal alfa, mínimo 64×64);
  - **cortes** (`cortes`): a linha é o job. A criação e o "tentar de novo" geram versão
    (`created`, `updated`) com o autor. As transições do worker (`processando`, `pronto`,
    `falhou`, progresso) são estado de job, com timestamps próprios, e não entram no histórico
    (seriam dezenas de versões sem valor de reversão). Não existe reversão de corte.
  - O corte guarda `kit_version` **e** `kit_tokens` (os tokens resolvidos no envio). O worker
    usa só o `kit_tokens`, então um kit alterado depois do envio não muda o corte (edge case).
- **Alternativas:** kit em uma coluna JSONB só (histórico sem granularidade); tabelas
  normalizadas por seção (sete tabelas para o que é lido e gravado sempre junto).

## R11. Testes (princípio VI, SC-002, SC-004)
- **Decisão:**
  - **unit:** schema do kit (faixas, enums, cores, referências à paleta e às fontes), resolução
    de tokens, preset mais próximo (cada um dos 6 presets exatos dá distância 0; rosa → `red`;
    sem caixa e texto amarelo → `outline_yellow`), mapeamento para o `SubtitleRequest` (SC-002,
    com kits gerados), quebra do gancho em 3 linhas e recusa acima disso, token de mídia
    (assinatura, validade, adulteração), montagem do `filter_complex` (string esperada);
  - **integration (stack efêmera, ffmpeg real na imagem):**
    - fontes: TTF e OTF válidos (as fontes padrão do pacote), `.ttf` que é texto, 11 MB,
      arquivar em uso (409) e fora de uso;
    - kit: padrão com `version: 0`, criar, editar, 409 de concorrência, histórico por seção,
      reversão pelo dono e 403 para membro, referência a cor inexistente (400 com o campo);
    - cortes: vídeo sintético gerado nos testes por `ffmpeg -f lavfi` com **cor sólida**
      (`color=c=0x808080:s=1080x1920:d=10`) + `sine`, e variantes sem áudio, horizontal
      (1920×1080), WebM (VP9 + Opus), 181 s (recusado), arquivo de texto com `.mp4` (recusado);
    - **SC-004 por amostragem:** o teste chama a função de processamento do worker direto (sem o
      serviço), extrai quadros com `ffmpeg -ss t -frames:v 1` em t = 0,5 s (gancho), no meio
      (só marca d'água) e em `T − 0,5` s (card) e confere, com Pillow, a cor média da região
      esperada de cada camada (fundo sólido cinza facilita: qualquer desvio é da camada). Também
      confere que o gancho **não** está no meio e que a duração, a resolução e a presença de
      áudio batem com o original. A mesma abordagem foi validada à mão em 2026-09-29;
    - fila: dois cortes enviados ficam em ordem; um `processando` com `heartbeat_at` antigo
      volta para `na_fila`; o terceiro abandono vira `falhou`;
    - mídia: `Range` devolve 206 com o trecho certo; token vencido ou adulterado → 403; link de
      exportação sem `exp` abre, e um token de vídeo sem `exp` é recusado;
    - **HD (FR-018, SC-007):** sem o sentinela, o envio de corte, de fonte e de logo dá 503 e
      nenhum objeto é gravado; com o piso configurado acima do livre real do tmpfs, dá 507; o
      worker sem sentinela não pega corte; o worker remove a própria pasta de `work/` no fim e
      as sobras ao subir; `/api/armazenamento` e o `/api/health` refletem cada caso;
    - nenhuma rota DELETE (SC-005) e o teste-guarda da 001 (princípio I) cobrindo `cortes`.
  - **e2e (Playwright, dev):** editar o kit de um perfil e ver a prévia mudar; enviar fonte;
    exportar o JSON; enviar um MP4 pequeno (gerado no setup do e2e), esperar "Pronto" e tocar o
    vídeo. O e2e precisa do serviço `worker` no compose de dev.
  - A imagem de teste (`sociman-api-test`) é a mesma da API, então já terá `ffmpeg`.
  - A stack efêmera continua com o MinIO em tmpfs, agora com os buckets `sociman-test`,
    `sociman-fonts-test` e `sociman-videos-test`, e ganha um tmpfs montado em `/hd` no `pytest`,
    onde a fixture cria `work/` e o sentinela (e o remove nos testes de SC-007). Nada da stack
    de teste toca o HD.

## R12. Infra: migrar o MinIO para o HD (primeira tarefa da implementação)
- **Decisão:** um script idempotente, `scripts/hd-setup.sh`, rodado pelo dono uma vez, um passo
  por vez (subcomandos `check`, `init`, `count`, `migrate` e `verify`, na ordem abaixo; a troca
  do compose vai no commit da tarefa), com verificação em cada passo:
  1. **conferir o HD:** `findmnt -no SOURCE,FSTYPE -T "$SOCIMAN_HD_DIR"` precisa mostrar um
     ponto de montagem diferente de `/` (aborta se o caminho cair no NVMe); o dono do caminho é
     1000:1000;
  2. **estrutura:** cria `minio/`, `work/tmp/` e `work/cortes/` e o sentinela
     `.sociman-volume` (conteúdo: data e `findmnt`, só para diagnóstico), tudo como UID 1000;
  3. **contagem antes:** um `mc` descartável na rede do compose
     (`docker run --rm --network sociman_default minio/mc …`) lista o bucket `sociman` do volume
     atual (`mc ls --recursive | wc -l` e `mc du`), guardados para comparar. O script também
     anota o digest da imagem `minio/minio` em uso e fixa essa tag no compose, para a versão não
     mudar entre a cópia e a subida;
  4. **cópia com o MinIO parado:** `docker compose stop edge imgproxy api minio`, depois
     `docker run --rm -v sociman_minio-data:/from:ro -v "$SOCIMAN_HD_DIR/minio":/to alpine sh -c
     'cp -a /from/. /to/ && chown -R 1000:1000 /to'`. A cópia do diretório de dados é segura
     com o servidor parado e a mesma versão de imagem (formato `xl.meta` idêntico);
  5. **trocar o compose:** o `minio` passa para o bind mount do HD, com `user` 1000, o
     sentinela no `entrypoint` e `create_host_path: false`; o `minio-init` cria também
     `sociman-fonts` e `sociman-videos`; `api` e `worker` ganham o bind `/hd` e o `TMPDIR`;
     o volume nomeado sai da lista de volumes do serviço (mas **não** é removido);
  6. **verificar:** `docker compose up -d`; a contagem e o `mc du` do bucket `sociman` batem com
     o passo 3; `docker volume inspect sociman_minio-data` ainda existe; um logo de perfil da 003
     abre em `/img/...` (200, pelo `curl` com a URL que `GET /api/perfis` devolve);
     `du -sh $SOCIMAN_HD_DIR/minio` cresceu e o NVMe não; `npm run test:api` e
     `npm run test:e2e` verdes.
  - O volume `minio-data` só é removido pelo dono, à mão, depois de alguns dias sem problema.
- **Alternativa:** `mc mirror` entre dois MinIO temporários (o antigo no volume e o novo no HD).
  Serve como plano B se a cópia direta der problema de formato (por exemplo, se a imagem do
  MinIO for atualizada no meio), mas exige dois servidores e credenciais temporárias.
