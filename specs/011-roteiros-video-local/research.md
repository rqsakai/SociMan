# Pesquisa: 011-roteiros-video-local

Decisões técnicas do plano. Fonte dos fatos:
- o código atual (HEAD `1ce278d`);
- a referência só leitura em `../comfyui-docker/` (`pipeline/run_storyboard.py`, `pipeline/finalizar_hd.py`,
  `runs/bia_vo/`, `tts_service/app.py`, `workflows/api/`).

## R1. Quem conduz o roteiro: máquina de estados nos ganchos da 021, sem serviço novo

- **Decisão:** um módulo puro de decisão `roteiros/maquina.py` com `avancar(db, roteiro, ator)`. A função é
  idempotente: olha a etapa atual, calcula o que falta e cria as gerações ou muda o status. Ela é chamada:
  - pelas ações humanas (criar, planejar, editar, aprovar portão, mudar portões ou modo, tentar de novo);
  - pelo gancho `ao_mudar_estado` dos aplicadores dos 6 passos novos, na mesma transação do gerador (o
    gancho não faz rede: só cria linhas em `geracoes` e muda o status do roteiro).

  O roteiro é travado com `SELECT … FOR UPDATE` em toda chamada. Os passos têm aplicadores em
  `roteiros/aplicadores.py`, registrados no `APLICADORES` da 021, do mesmo jeito que a 025 e a 012 plugam os
  seus.
- **Por quê:** o gerador da 021 já é a fila, já tem a trava de GPU e já chama os ganchos. Uma trilha ou
  um serviço a mais só duplicaria a fila (princípio VIII).
- **Alternativas:**
  - trilha nova no agendador fazendo *polling* dos roteiros: atraso de até um ciclo e estado em dois lugares;
  - serviço `roteirista`: mais um processo para operar.

## R2. Montagem sem GPU: uma 3ª linha no `gerador`, motor `ffmpeg`

- **Decisão:**
  - `geracao_motor` ganha `ffmpeg`;
  - o `gerador` ganha a `LinhaMontagem`, uma thread própria como a `LinhaClaude`, com claim por
    `motor = 'ffmpeg'`, **fora** do índice `uq_geracoes_gpu_rodando` e sem `memoria.subir()`;
  - a montagem baixa as tomadas e a narração do MinIO para `work/tmp` (HD), roda o ffmpeg (que já está na
    imagem) e grava a prévia como candidato de vídeo.
- **Por quê:**
  - o worker de cortes (`sociman worker`) tem a fila amarrada à tabela `cortes`, e generalizá-la mexeria
    na 004 e na 006;
  - o gerador já tem o MinIO e o `work/tmp`;
  - a montagem é curta: segundos para 20 s de vídeo.
- **Alternativa:** um job novo no worker de cortes, rejeitado pelo acoplamento com `Corte`/`CorteStatus`.

## R3. Vídeo nos candidatos: colunas no candidato, objeto no bucket de vídeos, sem cópia para a tomada

- **Decisão:**
  - `geracao_candidatos` ganha `video_key` (bucket `videos`, `geracoes/{geracao_id}/{numero}.mp4`),
    `video_miniatura_key` (bucket `imagens`, `perfis/{perfil}/geracoes/{geracao_id}/{numero}.jpg`),
    `video_duracao_ms`, `video_largura`, `video_altura`, `video_fps` e `video_bytes`;
  - o `ck_candidatos_midia` passa a `num_nonnulls(image_id, audio_id, video_key) <= 1`;
  - o trigger `geracao_candidatos_midia` aceita vídeo nos passos de resultado `video` e nenhuma mídia no
    `roteiro.plano`.

  A tomada criada pelo `cena.clipe` **aponta o mesmo objeto** (`cena_tomadas.video_key = candidato.video_key`,
  `miniatura_key` idem), sem copiar.
- **Por quê:** um objeto só, e a limpeza (R12) apaga uma vez. O `video_key` da tomada é só uma chave; o
  formato `cenas/<cena>/tomadas/<id>.<ext>` da 010 continua para o envio manual.
- **Links:** `MidiaKind` novo `geracao_video` (com validade e Range), para as prévias e os acabamentos. A
  tomada continua com o `cena_tomada` da 010.
- **Alternativa:** uma tabela `videos` irmã de `audios`, rejeitada. O vídeo do candidato tem um dono só, e
  a 014 e a 010 já guardam o vídeo como colunas.

## R4. ComfyUI: os blocos de vídeo copiados e o `run_bloco` com saída de vídeo

- **Decisão:** copiar para `geracao/workflows/` (com sha256 no `MANIFEST.json`, como a 021):

  | Bloco no SociMan | Origem (`../comfyui-docker/workflows/api/`) | fps | Quadros |
  |---|---|---|---|
  | `clipe_minimax` | `V2 - Clip MiniMax-H3 (início + fim opcional, com áudio)` | 24 | 17k+5 |
  | `clipe_wan` | `V2 - Clip Wan 2.2 14B (início + fim opcional)` | 16 | 4k+1 |
  | `clipe_wan_qualidade` | `V2 - Clip Wan 2.2 14B qualidade (20 passos, sem LightX2V)` | 16 | 4k+1 |
  | `clipe_ltx` | `V2 - Clip LTX-2.5 22B (início + fim opcional, com áudio)` | 24 | 8k+1 |
  | `upscale_video` | `V3 - Upscale vídeo SeedVR2 3B` | herda | — |

  O `keyframe` (Qwen Edit) já está copiado. O `BLOCOS` de `comfyui.py` ganha os 5.

  O `run_bloco` aceita saídas `kind = "video"`. O `SaveVideo` do ComfyUI devolve o arquivo em
  `outputs[node].images`, como na referência. Quando houver, o `last_frame` é ignorado.
- **Quadros (arredondando para cima, como em `runs/bia_vo/gerar.py`):**
  - MiniMax: `17·⌈(d·24 − 5)/17⌉ + 5`;
  - Wan: `4·⌈(d·16 − 1)/4⌉ + 1`;
  - LTX: `8·⌈(d·24 − 1)/8⌉ + 1`.

  `d` é a duração da posição mais **0,1 s** de folga, e o resultado nunca passa do teto do motor. O
  `frames_for` do `run_storyboard.py` arredonda o Wan e o LTX para baixo e trata o Wan qualidade como
  MiniMax: não portar esse erro.
- **Duração máxima por motor** (provisória, calibrada no quickstart §3; `cenas.duracao_max_s` nulo usa
  esta): `minimax` 8 s, `wan` 5 s, `wan_qualidade` 7 s, `ltx` 5 s. A referência aprovada usou MiniMax com
  6,7 s e Wan com 1,8 s.
- **Áudio dos clipes:** o MiniMax e o LTX devolvem áudio do modelo. A montagem e o acabamento **descartam**
  o áudio das tomadas (`-an`); só a narração entra.

## R5. Narração: `/v2/tts_paragraph` com pronúncias e velocidade aplicada pelo SociMan

- **Fatos:** o `TTSRequest` (`tts_service/app.py:131`) tem `sentences`, `voice`, `seed`, `max_attempts`,
  `min_similarity` e `language`. Ele **não** tem velocidade. O `/tts_paragraph`:
  - devolve `narracao.wav` (24 kHz), `similarity`, `seed`, `transcript` e `sentences: [{index, text,
    start, end}]`;
  - refaz com `seed+i` até a similaridade chegar a 0,95, já dentro do serviço.

  O `pronuncia.json` é lido do disco a cada chamada (palavra inteira, sem diferenciar maiúsculas,
  preservando a inicial maiúscula).
- **Decisão:**
  - o pedido v2 ganha o campo **`pronuncias: {escrita: falada}`**. Com o campo presente, o serviço o usa no
    lugar do `pronuncia.json`. É a mudança externa **X3**, aditiva, em `contracts/shop-tts-pronuncias.md`;
  - a **velocidade** é aplicada pelo gerador **depois** da narração e **antes** das durações:
    `ffmpeg -af atempo=<velocidade>` no wav, e os tempos divididos pela velocidade (como o `stage_mix` e o
    `continuous_bounds` do pipeline). O áudio guardado já sai na velocidade final;
  - a similaridade mínima e as tentativas ficam no serviço (`min_similarity = 0.95`, `max_attempts = 5`).
    Se a resposta voltar com `ok = false`, a etapa falha com `entrada_invalida` e a mensagem "a narração
    não bateu com o texto".
- **Por quê:** mexe o mínimo no serviço externo (só um campo). A regra "velocidade antes das durações"
  fica no SociMan, que é quem calcula as durações.

## R6. Durações a partir da narração (porte do `continuous_bounds`)

Função pura `roteiros/tempos.py:limites(tempos, posicoes, total_s)`:
- `inicio[0] = 0`;
- `inicio[i] = inicio(1ª frase da posição i) − 0,08`;
- `fim[i] = inicio[i+1]`;
- `fim[último] = total_s + 0,45`;
- `duracao = max(1,0, fim − inicio)`, com 3 casas.

Os tempos já chegam divididos pela velocidade (R5). Com a narração da referência (`runs/bia_vo`), os
valores batem com o `plano.json` (3,327 / 6,722 / 5,315 / 1,826): esse é o teste de regressão
`test_tempos_bia_vo`. As constantes `LEAD = 0,08` e `TAIL = 0,45` ficam no código. A ordem das posições
segue a ordem das frases: a validação garante que cada posição cobre frases **contíguas** e que a ordem
das posições acompanha a das frases. Sem isso, os tempos não dão um corte contínuo.

## R7. Prompt do clipe local: `cenas/prompt_local.py`, sem mexer no prompt do Flow

`montar_clipe(cena, avatar_descricao, tem_rosto)` monta, em inglês:
1. a ação, o plano, o movimento e a câmera;
2. a descrição fixa do avatar (kit da 025) quando há avatar;
3. as regras fixas:
   - `MOUTH_CLOSED` ("Her mouth stays closed in a gentle smile the whole time, she does not speak, her jaw
     does not move."), quando há avatar e o plano não é `detalhe_produto`;
   - `AMBIENTE_FIXO` ("The room, furniture, walls and lighting stay exactly the same for the whole
     shot."), sempre;
4. o sufixo de realismo.

A **fala**, o texto na tela e o áudio da 010 nunca entram. O `cenas/prompt.py` (Flow) não muda. Os avisos
do keyframe (FR-028) usam uma lista de padrões (`luz`/`light`/`lighting change`, `phone video`) e só
avisam, sem bloquear.

## R8. Cena `pronta` antes do clipe

A 010 só aceita tomada em cena `pronta`/`usada`, com o prompt congelado. Ao passar o portão KEYFRAMES
(aprovado ou desligado), a máquina chama `cenas.service.marcar_pronta(db, ator, cena)` para cada cena
em `rascunho`, com o mesmo ator da passagem:
- o humano que aprovou;
- `system:roteiro` no automático, cujo histórico mostra "sistema (automático)".

Se a validação de `pronta` falhar (ex.: modo `quadros` sem quadros), o roteiro para em
`aguardando_keyframes` com o motivo, mesmo com o portão desligado. A tomada local grava em `prompt_usado`
o prompt do clipe (R7), e não o `prompt_congelado` do Flow: o `registrar_tomada` da 010 ganha o parâmetro
`prompt_usado`.

## R9. Escolha automática só dentro do roteiro

- **Decisão:**
  - ator novo **`Actor(kind="system:roteiro")`**, que o `history.py` exibe como "sistema (automático)";
  - função nova `geracao.service.escolher_automatico(db, geracao)`, chamada **só** por
    `roteiros/automatico.py`, no gancho do `cena.keyframe` (`rodando → revisao`). A função confere, na
    mesma transação:
    1. o passo é `cena.keyframe`;
    2. `params.extras.roteiroId` aponta um roteiro não arquivado do mesmo perfil, com a posição ainda
       pedindo aquele keyframe;
    3. o roteiro está em `automatico` ou com `portoes.keyframes = false`.

    Satisfeitas as três, escolhe o candidato `numero = 1` pelo mesmo caminho do `escolher` humano (versão
    da cena com `details.geracao_id` e `details.automatico = true`).
- **Guardas** (`test_constitution_guards.py`, seção 011):
  - nenhum módulo além de `roteiros/automatico.py` chama `escolher_automatico`;
  - `escolher_automatico` recusa qualquer passo que não seja `cena.keyframe`;
  - o `test_gerador_nunca_escolhe_sozinho` da 021 continua valendo: o gerador não chama `aplicar` fora
    de `sem_escolha`, e a escolha automática roda no gancho, não no gerador;
  - nenhuma rota aceita ator que não seja humano para ligar o modo, mudar portões ou aprovar
    (`RequireHuman`, em `PROIBIDAS`).
- **Autor das outras etapas automáticas:** os passos de resultado único (`sem_escolha`) seguem a 021: o
  autor é quem pediu a geração. As gerações que a máquina cria sozinha (sem clique humano naquela
  transação) têm `created_by` = o humano que deu o último comando no roteiro (`roteiros.comandado_por`).
  Assim, o "autor do pedido" da 021 continua sendo uma pessoa.

## R10. Reuso, tomada útil e "keyframe antigo" derivados

- `cena_tomadas.keyframe_image_id` grava o keyframe inicial usado no clipe.
- "keyframe antigo" é **derivado**: `origem = geracao_local AND keyframe_image_id <> cena.keyframe_inicial_id`.
  Não há flag gravada.
- **Tomada útil de uma posição:** não arquivada, sem `limpa_em`, do keyframe atual (as do Flow nunca
  entram no reuso automático) e com `duracao_ms ≥ duracao_s·1000`. A ordem de preferência é:
  1. a tomada que a posição já tinha;
  2. a `tomada_escolhida_id` da cena;
  3. a local mais recente.

  No portão CLIPES, o operador pode escolher qualquer tomada da cena com duração suficiente, inclusive
  uma do Flow.
- "Narração desatualizada" também é derivada: `roteiro_narracoes.texto_hash <> hash_atual(roteiro)`, com
  `hash = sha256(json([frases já com as pronúncias aplicadas], voz_id, voz.ref_audio_id, velocidade))`. A
  função de pronúncia (`roteiros/pronuncia.py`) espelha a do serviço: palavra inteira, sem diferenciar
  maiúsculas, preservando a inicial.

## R11. Acabamento: SeedVR2 por posição, depois o ffmpeg, tudo dentro do job de GPU

O job `roteiro.acabamento` (motor `comfyui`, linha GPU, RAM 28 GB) faz, em `work/tmp`:
1. para cada posição: corta a tomada em `duracao_s` (sem áudio, `fps=24`), roda o `upscale_video` na
   resolução da cena e aplica `hqdn3d=0:0:3:3`. Os blocos de 41 quadros já estão no workflow copiado
   (conferir no `MANIFEST` na tarefa do bloco);
2. concatena as posições;
3. aplica `scale=…:1920:flags=lanczos,crop=1080:1920,unsharp=3:3:0.3,fps=24` e mistura a narração
   (`aresample=48000, loudnorm=I=-14:TP=-1.5:LRA=11`), com `libx264` crf 16, `+faststart` e aac 192k.

Esta é a receita do `finalizar_hd.py`. O vídeo do candidato aprovado foi ampliado em 736×1280 (resolução
da cena), apesar do padrão 720×1248 do script: vale a resolução da cena (Divergência 4 da spec). O
`comfy_free` roda no fim; os passos ffmpeg usam CPU, ainda com a GPU travada para este job.

## R12. Limpeza dos intermediários (exceção 1 ampliada, emenda 4.4.0)

- **Coluna técnica `desuso_em`** em `cena_tomadas`, `roteiro_narracoes` e `geracoes`: quando o artefato
  deixou de ser atual. Ela é preenchida pela máquina ao substituir ou invalidar, ao arquivar o roteiro e,
  no acabamento, na entrega (o conteúdo já tem a sua cópia). Ela volta a `NULL` se o artefato voltar a
  ser atual (ex.: o operador escolhe de novo uma tomada antiga).
- **Protegidos na hora da limpeza** (calculado, nunca gravado):
  - tudo o que está numa `roteiro_entregas` (narração, tomadas, keyframes);
  - a tomada escolhida e o keyframe atual de cada cena;
  - a tomada atual de cada posição e a narração ativa de roteiro não arquivado;
  - tomadas `flow_manual`;
  - qualquer mídia que o `uso.midia_em_uso` da 021 diga que está em uso.
- **Apaga** (trilha `geracao_limpeza` da 021, mesma volta, fase 2 em `geracao/limpeza.py`, o único que
  pode chamar o delete): artefatos com `desuso_em < agora − 90 dias` e não protegidos.
  - **Objetos:** o vídeo e a miniatura do candidato ou da tomada, e o áudio.
  - **Linhas** (seguindo o padrão da revogação LGPD da 025, sem apagar a linha que outras referenciam):
    - `cena_tomadas`: `video_key`, `miniatura_key` e `bytes` vão a `NULL` e `limpa_em = now()` (os CHECKs
      aceitam mídia nula só com `limpa_em`);
    - `geracao_candidatos`: as colunas de vídeo ou áudio vão a `NULL`;
    - `audios`: DELETE da linha (e `roteiro_narracoes.audio_id → NULL`, com `limpa_em`).

  A linha fica para o histórico, com "arquivo removido em <data>".
- **Exceção:** `storage.Excecao` ganha `intermediarios_90d`. O evento é `eliminacao_intermediarios`
  (`system:agendador`/`system:cli`, `details = {excecao, roteiroId?, cenaId?, tomadas, narracoes,
  candidatos, audios, bytes, mantidos}`).
- **Guardas:** `DELETE_PERMITIDO` não muda (`storage.py`, `geracao/limpeza.py`). O guarda de UPDATE em
  `geracao_candidatos` passa a aceitar `geracao/limpeza.py`, além do `revogacao.py`.
- **Ajuste na spec:** a Divergência 6 dizia que a tomada "some". O plano mantém a linha sem a mídia, como
  a 021 e a 025 fazem.

## R13. Entrega: conteúdo da 014, marca de IA e vínculo das cenas

Na transação que aplica o `roteiro.acabamento`:
1. o gerador grava o vídeo HD no MinIO; o aplicador cria o conteúdo com o arquivo já no MinIO pelo
   `conteudos.video_proprio.create_de_objeto` (miolo a extrair do `create_de_arquivo`, cópia no MinIO).
   O conteúdo nasce com o título = nome do roteiro e o `gerado_ia = true` (coluna nova);
2. grava a `roteiro_entregas` (snapshot das posições, tomadas, keyframes, narração, motores);
3. chama `cenas.usos.definir` para ligar as cenas ao conteúdo, com o ator = `roteiros.comandado_por`
   (`cena_usos.criado_por` é humano; Divergência 5);
4. muda o roteiro para `pronto` e grava `conteudo_id`.

**Marca de IA na publicação:** ao montar as opções de rede de um destino de conteúdo `gerado_ia`, o
`conteudoIa` (`OpcoesTikTok.conteudo_ia` → `is_aigc`) vem `true` por padrão, no formulário (SPA) e no
servidor quando o campo vier ausente. O humano ainda decide o destino.

**Atribuição:** se `'minimax' = ANY(roteiro_entregas.motores)`, o detalhe do conteúdo mostra "Este vídeo
usa o modelo MiniMax H3: a licença exige exibir 'MiniMax H3' em uso comercial". O texto não é inserido
sozinho no post.

## R14. Limite de cenas

`config.roteiro_max_cenas: int = Field(8, ge=1, le=20)` (env `ROTEIRO_MAX_CENAS`), passado ao serviço da
`api` e ao `gerador` no compose. Ele é conferido:
- ao salvar as posições;
- ao aplicar o `roteiro.plano`: se a IA propuser mais cenas, o plano é cortado e avisa "a IA propôs N
  cenas; o limite é M".

Um roteiro que já passa do limite continua válido, mas não aceita posição nova (409 `limite_cenas`).

## R15. Pronúncias e padrão de portões

- `pronuncias`: uma linha por par, versionada (`entity_type = pronuncia`), arquivável, com
  UNIQUE `(perfil_id, lower(escrita)) WHERE archived_at IS NULL` → 409 `pronuncia_existe`. Escrita e
  falada com 1..60 caracteres, uma palavra ou expressão curta, sem quebra de linha.
- `roteiro_padroes`: uma linha por perfil (`perfil_id` PK, `modo`, `portoes`, `version`), como a
  `cena_padroes` da 010. Sem linha = `version 0`, valendo o padrão do código.

## R16. Revogação e consentimento (FR-048)

A conferência é feita nos `montar_params` dos aplicadores `roteiro.narracao`, `cena.keyframe` e
`cena.clipe`, e no `avancar`. A voz com `consentimento.revogado_em` ou o avatar com
`consentimento.revogado_em` levam a:
- 409 `consentimento_revogado` na ação humana;
- `falhou` com `entrada_invalida` e a mensagem "consentimento revogado" na máquina.

A montagem e o acabamento só usam o que já existe e não conferem. O `revogacao.py` da 025 **não** toca
`cena_tomadas`, `roteiro_narracoes`, `roteiro_entregas` nem as gerações de alvo `cena`/`roteiro`. Há um
teste que garante isso: as referências a imagens do kit apagadas ficam como ids soltos em
`keyframe_refs`, exibidos como "referência removida".

## R17. MCP

Todas as rotas novas de escrita são `RequireHuman` (reverter: `RequireHumanOwner`) e ficam em
`PROIBIDAS`. As leituras (`roteiros_listar`, `roteiros_detalhe`, `roteiros_versoes`, `pronuncias_listar`,
`roteiro_padroes_ler`) ficam em `FORA`, como as da 021. O `test_mcp_mapa.py` acusa qualquer rota sem
classificação.

## R18. Fakes

- **pytest:**
  - o `comfyui_fake` reconhece os 5 blocos novos pela assinatura dos nós e devolve um **mp4 sintético**
    gerado com `ffmpeg -f lavfi testsrc2` na largura, altura, fps e quadros pedidos (cache por parâmetros
    num diretório do pytest). O `upscale_video` devolve o vídeo de entrada com o tamanho pedido;
  - o `shoptts_fake` responde `/v2/tts_paragraph` com um wav senoidal e os tempos proporcionais ao número
    de caracteres de cada frase, e grava o `pronuncias` recebido para o teste conferir. Os modos `ok=false`
    e 503 ficam controláveis.
- **e2e:** o `geracao_fake.py` (stdlib, sem ffmpeg) devolve um mp4 pequeno fixo de 8 s em 736×1280,
  guardado em `e2e/fixtures/geracao/clipe_8s.mp4` (~60 KB, cor sólida), e um wav fixo. O `/shop-tts` ganha
  o `/v2/tts_paragraph`. A montagem e o acabamento usam o ffmpeg real do container do gerador, porque o
  e2e testa a receita.
- **Regressão da referência:** o `test_tempos_bia_vo` usa os tempos de `runs/bia_vo/narration/timings.json`,
  copiados como fixture (só números).

## R19. Migration

`0024_roteiros_video_local`, com `down_revision = "0023_cadastro_padronizado"`. O número é
**provisório**: a 012 entrou primeiro como `0022_produtos_shop` (2026-10-08) e a 025 deve virar
`0023_cadastro_padronizado`, e o gate T001 confere `alembic heads`. Ver o data-model.

## R20. SPA

- Item **"Roteiros"** no menu (no nível de Conteúdos), com:
  - `/app/roteiros` (lista com filtros perfil, status e produto; `FilterBar`, `ServerPagination`);
  - `/app/roteiros/:id` (detalhe com as 5 etapas em seções, o andamento e os botões do portão);
  - `/app/roteiros/novo?perfil=`.
- O perfil ganha a aba **"Vídeo local"**, com o padrão de portões e as pronúncias.
- O detalhe faz polling de 2 s enquanto há geração aberta (como a 021) e mostra:
  - o player do áudio e as frases com os tempos;
  - as opções de keyframe (componentes da 021);
  - os players de vídeo das tomadas e da prévia.

  Tudo com `<video>` e `<audio>` nativos e links `/api/midia/…`; a CSP não muda.
- O upload de keyframe usa o `FileField` (≤ 20 MB, com `location` de 21m no edge).
