# Research: Geração local com candidatos (021)

Decisões técnicas da 021. Cada item traz **Decisão / Por quê / Alternativas**. A referência testada é o
pipeline do projeto vizinho `../comfyui-docker/` (só leitura): `pipeline/run_storyboard.py` (`run_block`,
`comfy_free`, `tts_unload`), `pipeline/cenarios.py` (a cena 768×1344), `tts_service/app.py` (shop-tts) e
`docker-compose.yml` (ComfyUI com `mem_limit: 12g` e portas em `127.0.0.1`). O ambiente foi conferido em
2026-10-07:
- GPU instalada: RTX 5060 Ti 16 GB (`nvidia-smi`);
- o OpenShorts usa a GPU (`openshorts/docker-compose.override.yml`, `driver: nvidia`);
- o ComfyUI publica em `127.0.0.1:8188` e o shop-tts em `127.0.0.1:8200`;
- a última migration do SociMan é a `0019_aprendizado_fonte_temas`.

As decisões marcadas **(DONO)** foram tomadas pelo dono em 2026-10-07 (ver `plan.md`, "Decisões do
dono"): R4 = opção A (`dockerctl`), R5 = opção A (`gpu-local`).

## R1. Onde roda a fila: um serviço novo `gerador` (mesma imagem)

- **Decisão:** criar o processo `sociman gerador` como um **serviço novo do compose** (`gerador`), com a
  mesma imagem da API, no padrão do `worker` da 004 e do `agendador` da 006. Ele tem duas linhas:
  - **linha GPU:** pega um job `comfyui` ou `tts` por vez;
  - **linha Claude:** pega um job `claude` por vez, numa thread própria, sem esperar a GPU (FR-019).

  Um advisory lock do Postgres garante uma instância ativa (como o agendador). A limpeza de 90 dias **não**
  fica no gerador: é uma trilha do agendador (R12).
- **Por quê:**
  - um job de GPU leva minutos e bloqueia. Numa trilha do agendador, ele prenderia a thread da trilha e
    misturaria com as voltas curtas das outras;
  - o gerador é o **único** container que precisa falar com o ComfyUI, o shop-tts e o `dockerctl` (R4, R5).
    Num serviço próprio, esses acessos (rede `gpu-local`, rede `dockerctl`, token) ficam só nele, e a API,
    o worker e o agendador continuam sem eles (princípio V).
- **Alternativas:**
  - **trilha `geracao` no agendador** (como diz o insumo): mistura um job longo com trilhas de 15 a 60 s e
    dá ao agendador, que já tem os segredos da TikTok, o acesso ao Docker. Rejeitada;
  - **dentro do `worker` da 004:** o worker é um laço de um corte por vez; juntar as duas filas faria um
    corte esperar uma geração de 10 min e vice-versa. Rejeitada.

## R2. Fila na tabela `geracoes`, com "um job de GPU por vez" garantido pelo banco

- **Decisão:** o mesmo padrão da fila de cortes (`cortes/queue.py`):
  - **claim:** pega o próximo `na_fila` com `next_attempt_at IS NULL OR next_attempt_at <= now()`, por
    `created_at, id`, com `FOR UPDATE SKIP LOCKED`. Marca `rodando`, `started_at`, `heartbeat_at` e
    `attempts + 1`, e faz commit antes de chamar o motor;
  - **um de GPU por vez:** índice único parcial `uq_geracoes_gpu_rodando ON geracoes ((true)) WHERE
    status = 'rodando' AND motor IN ('comfyui', 'tts')`. Um segundo claim de GPU falha no banco, mesmo com
    dois processos por engano;
  - **heartbeat:** a cada 5 s durante o job. `requeue_stale` devolve para `na_fila` todo `rodando` sem
    heartbeat há mais de 120 s (FR-023). Na 3ª interrupção, vai para `falhou` (`internal`, "O processamento
    foi interrompido 3 vezes");
  - **"é meu":** as funções de fim só tocam a linha se ela ainda for deste processamento (`status =
    rodando` e o mesmo `attempts`). Uma geração cancelada no meio nunca é sobrescrita pelo resultado que
    chega depois (FR-011).
- **Por quê:** é o padrão que já funciona (004/006), sem fila nova (sem Redis, sem Celery). O índice parcial
  é a garantia mais barata do FR-019.
- **Alternativas:** advisory lock por motor (some se o processo cair no meio, mas não protege contra um
  UPDATE manual); fila no Redis (o Redis não é banco de registro, constitution).

## R3. "GPU livre": envios da 006 + VRAM medida pelo próprio ComfyUI

- **Decisão:** antes de um claim de GPU, o gerador confere, em ordem:
  1. **OpenShorts:** nenhum envio da 006 em `processando` (o OpenShorts está cortando). Um envio em
     `aguardando_openshorts` ainda não começou e não conta;
  2. **o outro motor solto:** antes de um job `comfyui`, chama `POST /unload` do shop-tts; antes de um job
     `tts`, chama `POST /free` do ComfyUI com `unload_models: true` (FR-022; igual a `comfy_free` e
     `tts_unload` do pipeline);
  3. **VRAM:** lê `GET /system_stats` do ComfyUI (`devices[0].vram_free`, `torch_vram_total`) e calcula a
     VRAM disponível para o job como `vram_free + torch_vram_total` (o que o ComfyUI já tem em cache conta
     como dele). Precisa ser pelo menos o piso do motor: `GERACAO_VRAM_MIN_GB_COMFYUI` (padrão 12) e
     `GERACAO_VRAM_MIN_GB_TTS` (padrão 6).

  Se 1 ou 3 falhar, a geração continua `na_fila`, com `etapa_mensagem = "Aguardando a GPU ficar livre"`,
  `next_attempt_at = now() + 30 s` e **sem** contar tentativa (FR-018, FR-020). Um ComfyUI fora do ar no
  passo 3 é `servico_fora` (R8).
- **Por quê:**
  - a VRAM medida pelo ComfyUI (`torch.cuda.mem_get_info`) é a do **dispositivo**, inclusive de outros
    processos (OpenShorts, OpenClaw, jobs que o SociMan não conhece). Assim, o gerador não precisa de GPU
    nem de `nvidia-smi` no container;
  - o estado dos envios cobre o caso comum (OpenShorts carregando o modelo, ainda com pouca VRAM em uso).
- **Alternativas:**
  - `nvidia-smi` no container do gerador: exige `gpus: all` no SociMan só para ler um número. Rejeitada;
  - fila única com o OpenShorts: o dono recusou (Clarifications).
- **Calibração:** os pisos são calibrados no quickstart §3 com o FLUX schnell, o Qwen Edit e o Qwen3-TTS.
  Ficam em constantes de configuração, não na tela.

## R4. RAM do ComfyUI: 28 GB só durante o job, pelo `dockerctl` (DONO: decidida A)

> **RISCO DE SEGURANÇA.** Mudar o limite de memória de um container exige a API do Docker. Quem acessa o
> `docker.sock` tem **poder total sobre o host** (pode criar um container privilegiado que monta `/` e
> virar root). Montar o socket direto no gerador, na API ou no agendador está **fora de questão**. O
> mecanismo abaixo restringe o poder a duas operações fixas, mas o processo que segura o socket continua
> sendo um ponto de poder total: ele tem de ser mínimo, sem dependências e alcançável só pelo gerador.

- **Opções comparadas:**

  | | Mecanismo | O que o gerador pode pedir | Onde fica o poder total | Prós | Contras |
  |---|---|---|---|---|---|
  | **A** | **`dockerctl`**: container próprio no compose do SociMan, ~80 linhas de Python só da stdlib, com o `docker.sock` montado, numa rede `internal` só com o gerador | 3 ações **sem parâmetros**: `GET /comfyui/memoria`, `POST /comfyui/memoria/subir`, `POST /comfyui/memoria/devolver`. O `dockerctl` monta o corpo sozinho (`Memory` e `MemorySwap` de constantes dele) e só fala com `POST /containers/comfyui/update` e `GET /containers/comfyui/json` | No `dockerctl` | Versionado no repo, sobe e desce com a stack, testável; o gerador nunca vê o socket | O socket fica montado num container (somente leitura não protege o socket) |
  | **B** | **Serviço no host** (unit systemd de usuário, mesmo script de A), ouvindo só no IP da rede `gpu-local` | As mesmas 3 ações | No processo do host (usuário `sakai`, que está no grupo `docker`) | Nenhum container com o socket | Fora do repo e do compose (mais um serviço para lembrar, como o OpenClaw); o IP da rede tem de ser fixo; o ufw precisa liberar |
  | C | Proxy genérico do socket (ex.: `tecnativa/docker-socket-proxy`) com `CONTAINERS=1, POST=1` | Qualquer `POST /containers/*`: criar, `exec`, iniciar | No proxy, **e no gerador** (pode criar container privilegiado) | Pronto, sem código | Filtra por seção da API, não por container nem por corpo: na prática, é o socket inteiro. **Rejeitada** |
  | D | Socket montado no gerador | Tudo | No gerador | Nenhum código | **Rejeitada**: o gerador fala com a rede e recebe saídas de modelos |
  | E | Manter o ComfyUI sempre com 28 GB | Nada | Ninguém | Zero risco novo | Contraria a decisão do dono (12 GB fora do job) e aperta a RAM do host com o ComfyUI ocioso |

- **Recomendação: A (`dockerctl` no compose)**, com estas travas:
  - **rede:** `dockerctl` só na rede `dockerctl` (`internal: true`, sem saída e sem porta publicada), onde
    só está o gerador;
  - **autenticação:** header `Authorization: Bearer ${DOCKERCTL_TOKEN}` (segredo no `.env` da raiz, só no
    gerador e no `dockerctl`, gerado pelo dono e nunca impresso). A comparação é em tempo constante;
  - **allowlist fixa no código:** 3 rotas; o nome do container (`comfyui`), a versão da API do Docker e os
    valores (`28g` e `12g`, de `DOCKERCTL_MEM_JOB` e `DOCKERCTL_MEM_NORMAL`) vêm do ambiente do `dockerctl`,
    nunca do pedido. O corpo do pedido é ignorado. Qualquer outro método ou caminho → 404, com log;
  - **container endurecido:** `read_only: true`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`,
    `user: "1000:<gid do docker>"` (o `scripts/data-setup.sh check` descobre o gid), sem shell no comando e
    sem dependência além da stdlib;
  - **auditoria:** cada ação vai para o log do `dockerctl` (data, ação, valor antes e depois).
- **Fluxo no gerador** (`geracao/memoria.py`):
  - ao subir: `GET /comfyui/memoria`; se não estiver em 12 GB, loga o erro, chama `devolver` e só libera a
    linha GPU depois de ler 12 GB (FR-021);
  - antes de um job `comfyui`: `subir` e conferir 28 GB; senão, a geração volta para `na_fila` com
    `servico_fora` na mensagem e espera;
  - num `finally` (sucesso, falha, cancelamento, SIGTERM): `devolver` e conferir 12 GB. Se não voltar, loga,
    marca a linha GPU como "travada" e tenta de novo a cada 30 s, sem pegar outro job de GPU (cenário 4 da
    US2);
  - os jobs `tts` não mexem na RAM do ComfyUI.
- **Por quê A e não B:** as duas têm o mesmo poder no mesmo tipo de processo. A vence por ficar no repo,
  com teste, e por não depender de IP fixo nem de regra no ufw. B é a saída se o dono não quiser o socket
  em nenhum container.
- **Sem o `dockerctl`** (variável vazia): a linha GPU **não roda jobs `comfyui`** e mostra "Ajuste de
  memória do ComfyUI não configurado" em `GET /api/integracoes`. Os jobs `tts` e `claude` seguem.

## R5. Rede: ComfyUI e shop-tts em `127.0.0.1` (DONO: decidida A)

- **Problema:** o ComfyUI (`127.0.0.1:8188`) e o shop-tts (`127.0.0.1:8200`) só escutam no loopback do
  host. O `host.docker.internal` (como o OpenShorts na 006) aponta para o IP do bridge do Docker, e não para
  o loopback: os containers do SociMan não os alcançam.
- **Opções:**

  | | Ligação | Mudança no `../comfyui-docker` | Exposição | Prós | Contras |
  |---|---|---|---|---|---|
  | **A** | **Rede Docker externa `gpu-local`** (`docker network create gpu-local`): `comfyui` e `shop-tts` entram nela; no SociMan, só o `gerador` | `networks: [default, gpu-local]` nos 2 serviços e `networks: gpu-local: external: true` | Nenhuma porta nova; só containers da rede alcançam | Sem ufw, sem IP fixo, nome estável (`http://comfyui:8188`, `http://shop-tts:8200`); as portas `127.0.0.1` continuam para o pipeline do host | A rede tem de existir antes dos dois `up` (passo no `data-setup.sh init`) |
  | B | Bind no IP do bridge (`172.17.0.1:8188`) e `host.docker.internal` | Trocar as portas | Qualquer container do host alcança | Igual à 006 | Depende do IP do bridge; o ufw costuma barrar o tráfego de outra bridge para o host; abre para todo container |
  | C | `network_mode: host` no gerador | Nenhuma | O gerador vê toda a rede do host | Nenhuma mudança fora | O gerador perde os nomes `postgres`, `minio`, `redis` e fica exposto. **Rejeitada** |
  | D | Bind em `0.0.0.0` | Trocar as portas | LAN inteira (o ComfyUI não tem senha) | Simples | **Rejeitada** |

- **Recomendação: A.** A mudança no `../comfyui-docker/docker-compose.yml` é uma **dependência externa**:
  esta spec só a descreve (`contracts/comfyui.md`, `contracts/shop-tts.md`) e o dono a aplica. As URLs
  ficam em `COMFYUI_URL` e `SHOP_TTS_URL` (padrões `http://comfyui:8188` e `http://shop-tts:8200`), e no e2e
  apontam para o `openshorts-fake` (R13).

## R6. Workflows do ComfyUI: cópia versionada dos 4 blocos

- **Decisão:** copiar para `apps/api/src/sociman_api/geracao/workflows/` os pares `*.api.json` +
  `*.params.json` dos blocos que a 021 e as specs seguintes usam:

  | Bloco | Arquivo no pipeline | Uso |
  |---|---|---|
  | `cena` | `V3 - Imagem FLUX schnell (txt2img)` | `cenario.cena` a partir de prompt (piloto) |
  | `keyframe` | `V2 - Keyframe (Qwen Edit)` | `cenario.cena` a partir de foto; variações, looks, poses e kit do avatar (025) |
  | `retrato` | `V3 - Retrato Juggernaut XL (txt2img)` | `avatar.rosto_origem` (025) |
  | `cutout` | `V2 - Cutout (BiRefNet, fundo branco)` | `produto.recorte` (012) |

  O arquivo `workflows/MANIFEST.json` guarda, por bloco, o nome de origem e o sha256 dos dois arquivos. O
  teste `test_workflows_manifest` confere os hashes. Atualizar um bloco = copiar de novo e atualizar o
  manifesto (passo no quickstart).
  - O **`cenario.cena` de prompt** monta o prompt como o `cmd_criar` do pipeline: o texto do dono, mais o
    sufixo `REALISMO` (sem pessoas, sem texto, área livre embaixo), 768×1344. **Com foto de referência**,
    usa o `keyframe` com a instrução + o sufixo `MANTER`. Os sufixos ficam em `geracao/passos.py`;
  - o resultado é normalizado para **768×1344** com Pillow (`ImageOps.fit`, como o `fit_9x16`), em memória,
    e validado por `imaging.validate_image` (kind `fundo`) antes de virar imagem.
- **Preencher o bloco** (`geracao/comfyui.py`, porte do `run_block`): para cada parâmetro do contrato,
  `kind = image` sobe a imagem por `POST /upload/image` (subpasta `sociman`, nome = `<geracao_id>_<n>_<param>`);
  `image_optional` ausente remove o nó e religa como no pipeline (`drop`, `consumers`, `rewire`); os demais
  vão em `inputs`. Depois `POST /prompt`, polling de `GET /history/{prompt_id}` a cada 2 s (com heartbeat),
  `GET /view` do 1º arquivo da saída e `POST /free` (`unload_models: false`).
- **Por quê:** o SociMan não pode ler arquivos do `../comfyui-docker` em tempo de execução (outro projeto,
  outro container), e os blocos mudam pouco. O manifesto evita uma cópia alterada sem querer.
- **Alternativas:** ler os JSONs do projeto vizinho por bind mount (acopla os dois repos e quebra o e2e);
  gerar o workflow em código (perde o contrato testado no pipeline).

## R7. Seeds, número de opções e andamento

- **Decisão:**
  - **seeds:** a 1ª geração de um alvo e passo sorteia uma base (`secrets.randbelow(2**31 - 1) + 1`). A opção
    *i* usa `base + i - 1` (igual ao pipeline). "Gerar outras" usa `max(seeds já usadas naquele alvo e
    passo) + 1` em diante, e por isso nunca repete. As seeds ficam em `params.seeds` e em cada candidato;
  - **número de opções:** vem do registro do passo (`geracao/passos.py`): 2 por padrão, 4 no
    `avatar.rosto_origem`, até 3 nos passos de voz. O pedido pode reduzir (mínimo 1), nunca aumentar;
  - **andamento:** com *n* opções, cada uma vale `100/n`. Na opção *i*, o progresso vai a `(i-1)·100/n` e a
    mensagem diz "Gerando opção i de n". Ao fim de cada opção, o candidato é gravado na hora (a tela mostra
    as opções prontas antes das outras). A tela lê a geração a cada 2 s enquanto ela não for final.
- **Por quê:** o ComfyUI não dá progresso pelo HTTP sem websocket, e uma geração tem de 2 a 4 opções de
  20 s a 2 min cada; o passo por opção basta. Gravar cada candidato ao terminar evita perder trabalho se o
  worker cair no meio.
- **Alternativas:** websocket do ComfyUI para o progresso por amostra (mais um protocolo para 2 a 4
  opções); seeds só aleatórias (não garantem "nunca repetir").

## R8. Erros, espera e tentativas

- **Decisão:** `geracao/erros.py` traduz a falha de cada motor para os códigos do FR-017:

  | Causa | Código | Efeito |
  |---|---|---|
  | GPU ocupada (R3) | `gpu_ocupada` | `na_fila`, +30 s, **sem** contar tentativa; mensagem "Aguardando a GPU ficar livre" |
  | shop-tts 503 / ComfyUI com `OutOfMemoryError` na execução | `sem_memoria` | `na_fila` com espera crescente (30 s, 1, 2, 4, 8 min; teto 15 min), conta tentativa; depois de 6, `falhou` |
  | conexão recusada, timeout, 5xx | `servico_fora` | igual a `sem_memoria`, depois de 6 tentativas `falhou` |
  | referência sumida ou arquivada, saída fora do formato, imagem inválida | `entrada_invalida` | `falhou` na hora |
  | qualquer outra exceção | `internal` | `falhou` na hora (detalhe só no log) |

  As mensagens em pt-BR ficam em `MENSAGENS` (uma por código). O `error_message` grava a mensagem curta, e
  nunca o texto cru do serviço. "Tentar de novo" zera `attempts`, `next_attempt_at` e o erro (o erro
  anterior fica no histórico da geração, R10).
- **Por quê:** separar "esperar" de "falhar" é o FR-018: a GPU ocupada é normal e não pode virar falha.
- **Alternativas:** um código por exceção do motor (vaza detalhe técnico para a tela).

## R9. Cancelar

- **Decisão:** cancelar é uma transação na API: `status = cancelada`, `finished_at = now()`, histórico. O
  gerador confere o status a cada heartbeat (5 s). Ao ver `cancelada`:
  - ComfyUI: `POST /interrupt` (se o prompt em execução é o dele, por `GET /queue`) e `POST /queue
    {"delete": [prompt_id]}` para os que estão esperando;
  - shop-tts: não há como interromper; o resultado é descartado ao chegar;
  - o `finally` devolve a RAM (R4).

  Candidatos já gravados de uma geração cancelada ficam (podem ser vistos) e seguem a limpeza de 90 dias.
  O resultado que chegar depois não vira candidato, porque o UPDATE "é meu" (R2) falha.
- **Por quê:** o FR-011 pede "quando possível". Uma geração cancelada para de gastar GPU em até 5 s no
  ComfyUI.

## R10. Histórico: `geracoes` é versionada (`entity_type = "geracao"`)

- **Decisão:** a geração ganha `version`, e `__versioned_fields__ = (status, escolhido_id, error_code,
  error_message)`. As ações **humanas** chamam `history.record` na mesma transação:

  | Ação | Ação do histórico | `details` |
  |---|---|---|
  | pedir | `created` | `{passo, motor, alvoTipo, alvoId, nOpcoes}` |
  | cancelar | `updated` | `{acao: "cancelar", de: <status>}` |
  | tentar de novo | `updated` | `{acao: "tentar_de_novo", erroAnterior: {code, message}}` |
  | gerar outras | `updated` na antiga (`descartada`) + `created` na nova | `{acao: "gerar_outras", novaGeracaoId}` / `{deGeracaoId}` |
  | escolher | `updated` | `{acao: "escolher", candidatoId, numero}` |

  As mudanças do gerador (`rodando`, `revisao`, `falhou`, andamento, espera, candidatos) são **estado de
  job**, sem versão (como o envio da 006). As ações exigem `version` no corpo (409 `version_conflict`).
  **Não há "reverter"** para a geração: um ato humano já é o desfecho (cancelar, escolher) e o caminho de
  volta é pedir outra geração. É a mesma exceção aprovada de envio e corte na 006 (Complexity Tracking).
- **Escolher no alvo** também grava a versão do alvo (`assets`, `updated`, `details.geracao_id` e
  `details.candidato`), com o humano que escolheu como autor (FR-009).
- **Passos sem escolha** (texto e `produto.recorte`): a versão do alvo tem como autor **quem pediu**
  (`created_by` da geração), com `details.geracao_id` e `details.automatico: true`; a geração vai a
  `escolhido` como estado de job.
- **Por quê:** o insumo não dava `version` à geração, mas sem ela cancelar e tentar de novo não ficariam no
  histórico (princípio VII). Seguir o envio da 006 é o padrão conhecido.
- **Alternativas:** registrar só na versão do alvo (perde cancelar e tentar de novo); uma tabela de eventos
  própria (duplica o `entity_versions`).

## R11. Áudios: tabela `audios`, bucket próprio, ffprobe, link com validade

- **Decisão:**
  - **tabela `audios`** (irmã de `images`), imutável, com as colunas do insumo;
  - **bucket novo `sociman-audios`** (`S3_AUDIOS_BUCKET`), no mesmo MinIO do HD. `storage.Bucket` ganha
    `"audios"`, e o `ensure_buckets` o cria. A chave é `perfis/{perfil_id}/audios/{uuid}.{ext}` (`wav`,
    `m4a`, `ogg`, `mp3`, pelo formato detectado). O insumo dizia `.wav`, mas o arquivo enviado é guardado
    como veio (a gravação original da pessoa, sem conversão); os candidatos do shop-tts são `.wav`;
  - **validação pelo conteúdo** (`geracao/audios.py`): o upload vai para `work/tmp` no HD (spool do
    `TMPDIR`, como o envio avulso), com teto de 25 MB (`read(limite + 1)` → 413 `arquivo_grande`). Depois,
    `ffprobe` (já na imagem, `cortes/probe.py`): `format_name` em `wav`, `mov,mp4,m4a…` (só com `codec` de
    áudio aac/alac e sem vídeo), `ogg`, `mp3`; exatamente 1 fluxo de áudio, sem vídeo; duração > 0 e
    ≤ 10 min. Grava `formato`, `sample_rate`, `duracao_ms` e `sha256`. Fora disso, 400 `audio_invalido`;
  - **edge:** `location ~ ^/api/perfis/[^/]+/audios$` com `client_max_body_size 26m` e
    `proxy_request_buffering off` (como as rotas de upload grande da 004/007), para a recusa vir da API;
  - **links:** `MidiaKind` ganha `"audio"`, em `VIDEO_KINDS`-like para validade: sempre com `exp` (1 h na
    interface), com `Range` (206/416) pelo `stream_object`, `Content-Type` pelo formato. Os candidatos de
    imagem usam o `imagem` que já existe, **com** `exp` (o arquivo pode ser apagado pela limpeza, então não
    há link estável para ele);
  - **CSP:** o `<audio>` usa `/api/midia/` na mesma origem; nenhuma diretiva muda (o `default-src 'self'`
    cobre `media-src`).
- **Por quê:** é o mesmo caminho das imagens e dos vídeos, com o HD, o sentinela e o piso (`datadir`). Um
  bucket separado deixa a limpeza e o backup por tipo simples e não mistura áudio com o bucket que o
  imgproxy lê.
- **Alternativas:** guardar no bucket de vídeos (mistura tipos e regras de link); converter tudo para wav
  no upload (perde o original, que a 025 quer para a análise de codec e bitrate).

## R12. Limpeza de 90 dias (exceção 1 da emenda 4.3.0)

- **Decisão:** trilha nova `geracao_limpeza` no agendador (`AGENDADOR_GERACAO_LIMPEZA_S`, padrão 3600 s).
  Cada volta, em lotes de 200 gerações:
  1. seleciona gerações com `status IN (escolhido, descartada, cancelada, entregue, falhou)`, `finished_at <
     now() - interval '90 days'` e `limpa_em IS NULL`;
  2. para cada uma, os candidatos com `id <> escolhido_id` (ou todos, se não há escolhido);
  3. para cada imagem ou áudio desses candidatos (inclusive `image_par_id` e `metricas.teste_audio_id`), confere
     **`midia_em_uso`** (`geracao/uso.py`). Candidato com a mídia já nula (revogação LGPD da 025) é
     **pulado**. Um arquivo em uso **não** é apagado, e o candidato fica (com o
     motivo no log). "Em uso" =
     - imagem em `asset_files` (qualquer, mesmo arquivada);
     - imagem escolhida por outra geração (`escolhido_id` de qualquer geração aponta um candidato com a
       mesma imagem);
     - imagem ou áudio referenciado em `params` de alguma geração não final ou terminada há menos de 90 dias;
     - imagem nos tokens de algum kit (`marca/tokens.fields_using_image`) ou nos ingredientes de cena (010,
       `cenas/usos_assets`);
     - os provedores que a 025 e a 012 registrarem (vozes, produtos);
  4. apaga, **nesta ordem e numa transação por geração**: as linhas de `geracao_candidatos`, depois as de
     `images`/`audios`, e por fim os objetos do MinIO, **depois do commit** (um objeto órfão é inofensivo;
     uma linha apontando para objeto apagado, não);
  5. marca `geracoes.limpa_em = now()` e grava **um evento** `eliminacao_candidatos` em `security_events`
     (`actor_kind = "system:agendador"`, `outcome = "ok"`, `details = {excecao: "candidatos_90d",
     geracaoId, perfilId, candidatos: N, imagens: N, audios: N, bytes: N, mantidos: N}`).
  - **Delete restrito:** `storage.apagar_por_excecao(key, *, bucket, excecao: Literal["candidatos_90d",
    "lgpd_revogacao"])` é a **única** função de delete do `storage.py`. O teste-guarda
    `test_constitution_guards::test_delete_so_nas_excecoes` confere por AST que só `geracao/limpeza.py`
    (e, na 025, o módulo da revogação LGPD) a importam, e que nenhum módulo de `mcp/` ou de `ia/` a alcança;
  - **nunca por IA, agente ou MCP:** não há rota HTTP nem tool de MCP para a limpeza. O CLI
    `sociman geracoes limpar [--dry-run]` (ator `system:cli`) existe para o quickstart e roda o mesmo código.
- **Por quê:** é a exceção (1) da emenda 4.3.0, com o evento que a emenda exige (quem, quando, contagem e
  motivo). A conferência de uso protege a regra "o escolhido nunca" e qualquer reuso que não passou pelo
  `escolhido_id`.
- **Alternativas:** apagar em cascata pelo banco (não alcança o MinIO e não registra evento); lifecycle
  rule do MinIO por prefixo (não sabe qual candidato foi escolhido).

## R13. Testes sem serviço real: fakes do ComfyUI, do shop-tts e do `dockerctl`

- **Decisão (pytest):** três fakes novos em `apps/api/tests/fakes/`, no padrão do `__init__.py`
  (`httpx.MockTransport`, estado, `.requests`, falhas programáveis, fixture no próprio módulo):
  - `comfyui_fake.py`: `/upload/image`, `/prompt` (valida que os nós do contrato foram preenchidos),
    `/history/{id}` (fica "rodando" por N chamadas), `/view` (PNG sintético do tamanho pedido, com a seed
    desenhada), `/free`, `/interrupt`, `/queue`, `/system_stats` (VRAM programável). Falhas: fora do ar,
    `OutOfMemoryError` na execução, saída vazia;
  - `shoptts_fake.py`: o **contrato novo** do shop-tts (`contracts/shop-tts.md`): `register`, `design`,
    `import`, `tts`, `tts_paragraph`, `lotes/{id}/{arquivo}` (WAV sintético), `unload`, `health`, 503
    programável;
  - `dockerctl_fake.py`: guarda o limite atual; falhas "não volta para 12 GB" e "fora do ar".

  Os clientes (`geracao/comfyui.py`, `geracao/shoptts.py`, `geracao/memoria.py`) seguem o padrão
  `get_*_client(transport=None)`, e o `rodar` do gerador recebe os clientes por parâmetro.
- **Decisão (e2e):** o `openshorts-fake` (`e2e/fakes/server.py`) ganha os prefixos `/comfyui/*`,
  `/shop-tts/*` e `/dockerctl/*` com o mesmo comportamento, e rotas de controle `/geracao-e2e/*`:
  `POST /geracao-e2e/gpu {ocupada: bool}`, `POST /geracao-e2e/falhas {motor, falha}`,
  `GET /geracao-e2e/memoria` (histórico dos limites) e `GET /geracao-e2e/pedidos`. O
  `docker-compose.e2e.yml` ganha o serviço `gerador` (sem `dockerctl` real: `DOCKERCTL_URL` aponta para o
  fake) com `COMFYUI_URL=http://openshorts-fake:8000/comfyui` e `SHOP_TTS_URL=http://openshorts-fake:8000/shop-tts`.
  O PNG sintético usa o `zlib`/`struct` que o fake já importa (sem Pillow no fake).
- **Por quê:** é o padrão da casa (006, 008, 015, 016): nenhum teste chama serviço real.

## R14. Motor `claude` e o registro da 008

- **Decisão:**
  - o motor `claude` (`geracao/motor_claude.py`) usa o cliente e o custo da 008 (`ia/cliente.py`,
    `ia/custo.py`) e grava **toda** chamada em `ia_chamadas` (com sucesso ou erro), com `tipo_campo =
    <passo>`, `entity_type = <alvo_tipo>`, `entity_id = <alvo_id>` e a coluna nova **`geracao_id`** (FK →
    geracoes). No sucesso, o desfecho vai direto para `aplicada` (`desfecho_por = created_by` da geração);
    no erro, `erro`;
  - os **tipos de campo** dos passos de texto entram em `ia/tipos.py` (`TipoCampoId`) **pela spec que os
    usa**: `produto.ficha` na 012 e `avatar.identidade` na 025, cada um com o seu schema de saída, a sua
    regra padrão e `listar_regras` conforme a spec. A 021 entrega o caminho (motor, registro com
    `geracao_id`, custo no resumo do mês, aplicação direta pelo aplicador do passo) e o testa com um tipo e
    um aplicador **injetados no teste** (o registro de passos aceita sobrescrita só em teste);
  - o resumo de custo da tela do assistente (008) passa a somar as chamadas com `geracao_id` (já soma por
    `ia_chamadas`; nada muda além de aparecerem os tipos novos).
- **Por quê:** a 008 é o único registro de chamadas ao Claude e o lugar do custo do mês. Declarar os tipos
  agora, sem schema nem regra, criaria tipos vazios na tela de regras.
- **Alternativas:** um registro próprio para as gerações (duas contas de custo).

## R15. Registro de passos e aplicadores

- **Decisão:** `geracao/passos.py` é um registro em código (como `ia/tipos.py`): para cada um dos 15 passos,
  `Passo(id, motor, alvo_tipo, resultado: "imagem"|"par_imagem"|"audio"|"texto", n_padrao, n_max,
  sem_escolha: bool, aplica_alvo: bool, bloco: str | None, image_kind)`. O CHECK `ck_geracoes_passo` no banco repete a lista (teste cruzado).
  - **aplicadores:** cada passo **disponível** tem um `Aplicador` (`validar_alvo`, `montar_params`,
    `aplicar(db, actor, geracao, candidato)`). Na 021, só existe o do **`cenario.cena`**: o candidato vira
    um `asset_files` `referencia` do cenário (via `assets.service._attach`, com `notes` = "Gerado (opção N)"
    e `look` vazio), e o primeiro vira o `primary_file_id`. A 025 troca isso pelo slot `cena`;
  - **protocolo `Aplicador`** (`geracao/aplicadores.py`; coordenado com a 025 em 2026-10-07):
    - `validar_alvo(db, alvo) -> None`: perfil, existência, arquivado, tipo de asset;
    - `montar_params(db, actor, alvo, pedido) -> dict`: monta e valida `params`, inclusive o
      **`extras`** do pedido (objeto opcional ≤ 2 KB; cada aplicador aceita só as chaves dele, e uma chave
      desconhecida dá 400 `entrada_invalida` com `field = "extras.<chave>"`). Guardado em `params.extras`.
      Hoje só a pose usa (`extras.quandoUsar`, ≤ 300, vai para `asset_files.quando_usar` ao escolher);
    - `aplicar(db, actor, geracao, candidato) -> None`: leva o resultado ao alvo (só nos passos com
      `aplica_alvo`);
    - **`ao_mudar_estado(db, geracao, de: GeracaoStatus | None, para: GeracaoStatus) -> None`**: opcional;
      a implementação padrão não faz nada. A 021 o chama **na mesma transação de toda transição**, de job
      ou humana: pedir (`de = None`), `na_fila → rodando`, `rodando → na_fila`, `rodando → revisao`,
      `→ falhou`, `→ cancelada`, `→ descartada`, `→ escolhido`, `→ entregue` e "tentar de novo". Regras:
      não faz chamada de rede nem de motor; uma exceção desfaz a transição inteira (na API vira o erro da
      rota; no gerador, a geração vai para `falhou` com `internal`). Em "Gerar outras", a nova geração é
      criada (e o gancho dela chamado) **antes** de a antiga virar `descartada`, para o aplicador ver a nova
      como aberta. Helper para o aplicador: `fila.abertas_do_alvo(db, alvo_tipo, alvo_id, exceto=None)`;
  - pedir um passo **sem aplicador** responde 409 `passo_indisponivel` ("Este passo chega com o cadastro de
    <avatar|voz|produto>");
  - **`produto.recorte`** é `sem_escolha = True` (Clarifications Q2) e **`produto.ficha`** e
    **`avatar.identidade`** são `resultado = "texto"`, também sem escolha. Todos os outros têm revisão
    humana obrigatória: o gerador **nunca** chama `aplicar` para eles (teste-guarda).
- **`avatar.rostos_34` (contradição da spec, resolvida com a 025 em 2026-10-07):** um passo só, e **cada
  opção é um par**: `image_id` = lado esquerdo e a coluna nova **`image_par_id`** = lado direito (CHECK
  `image_par_id IS NULL OR image_id IS NOT NULL`; o trigger exige as duas só nesse passo). O motor roda o
  bloco duas vezes por opção (esquerda e direita, mesma seed), e o andamento conta "Gerando par i de n".
  Escolher preenche os dois slots do kit (aplicador da 025), com um `escolhido_id` só. A limpeza e o
  `midia_em_uso` tratam as duas imagens. Dividir em duas gerações foi rejeitado porque quebra "1 escolha =
  1 par" na 025.
- **`voz.teste` (coordenado com a 025):** passo novo, motor `tts`, alvo `voz`, resultado áudio, `n = 1`,
  `params.texto`. Sem escolha e sem aplicador de alvo: o gerador grava o candidato (`audio_id`,
  `metricas = {segundos, texto}`) e leva a geração a um **estado final novo, `entregue`**. Reaproveitar
  `descartada` foi rejeitado: `descartada` quer dizer "trocada por Gerar outras", e misturar os dois
  sentidos confundiria a tela, o histórico e a contagem da limpeza. O áudio entra na limpeza de 90 dias
  como "não escolhido" (exceção 1 da 4.3.0).

## R16. Alvo arquivado, concorrência e permissões

- **Decisão:**
  - **permissões:** ler (lista, detalhe, versões, áudio) é `RequireUser`; pedir,
    cancelar, tentar de novo, gerar outras, escolher e enviar áudio são **`RequireHuman`** (dono ou
    membro; outro ator → 403 `somente_humano` + `publicacao_recusada`, como na 009/015). Nada é
    `RequireHumanOwner`, porque nada publica nem conecta conta. O MCP (009) não ganha tool de geração;
  - **escolher:** `SELECT … FOR UPDATE` na geração, confere `status = revisao` e a `version` do corpo, e o
    `alvoVersion` do alvo (409 `version_conflict` se o alvo mudou). Duas abas: a segunda recebe 409
    `geracao_decidida`;
  - **alvo arquivado:** pedir → 409 `alvo_arquivado`; escolher → 409 `alvo_arquivado`; cancelar → aceito;
  - **referências (delegadas ao aplicador; pedido da 012, 2026-10-07):** o service genérico só confere
    que cada id de `referencias` é uma imagem **do mesmo perfil**. A regra de onde a imagem pode estar fica no
    `Aplicador.montar_params` de cada passo: nos passos de asset (o `cenario.cena` da 021 e os da 025), o
    padrão é "em arquivo ativo de asset ativo" (helper `aplicadores.referencia_de_asset_ativo`); nos passos de
    produto (012), as imagens de `produto_variantes`. Fora da regra → 400 `entrada_invalida` com o campo. No
    claim, o gerador chama o mesmo validador do aplicador de novo; sumiu → `falhou` com `entrada_invalida`
    (edge case da spec);
  - **`alvoTipo = produto` no POST genérico** → 409 `alvo_incompativel`: a 012 pede as gerações de produto
    pelas rotas próprias dela, que usam o mesmo service por dentro.
- **Por quê:** é o modelo de permissões que já existe; a escolha humana (FR-008) é o `RequireHuman`.
