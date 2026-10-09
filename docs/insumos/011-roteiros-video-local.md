# Insumo: 011-roteiros-video-local (roteiro com cenas reaproveitáveis, keyframes, narração e vídeo local)

Entrada para o `/speckit-specify` da **011** (reservada no backlog como "roteiros por cena e avatar"). É o
**handoff do pipeline de vídeo de produto** que foi fechado em scripts no `../comfyui-docker/pipeline/` e gerou o
primeiro vídeo aprovado pelo dono (`../comfyui-docker/output/candidatos/candidato_01_bia_vestido_verde.mp4`,
receita no `.txt` ao lado). Esta spec **cria** o roteiro e **estende** a 010 (cena) e a 021 (geração local),
como a 012 estendeu a 010.

Depende de: **010** (cenas), **021** (geracoes, candidatos, audios), **012** (produtos e variantes), **025**
(kit do avatar, `vozes`, `assets.voz_id`), **014** (o vídeo final vira conteúdo). Referência técnica testada
(só leitura): `../comfyui-docker/pipeline/PADROES.md`, `run_storyboard.py`, `finalizar_hd.py`,
`../comfyui-docker/runs/bia_vo/gerar.py` e `refazer.py`, `../comfyui-docker/tts_service/app.py`.

## Problema
Hoje a cena da 010 é uma tomada para gerar **à mão no Flow**. O vídeo de produto que funcionou foi gerado
**localmente**: o texto de venda vira uma narração contínua, cada cena tem um **keyframe** aprovado, cada
keyframe vira um **clipe**, e os clipes são cortados no ritmo da fala e montados com acabamento HD. Para fazer
isso no SociMan faltam:
- o **roteiro**: a sequência de cenas com o texto de venda, os produtos, o avatar e a voz;
- o **reuso de cenas** entre roteiros (a mesma cena aprovada serve a vários vídeos, sem gastar GPU de novo);
- **portões opcionais**: o operador pode ver e aprovar ou mudar só pedaços (principalmente os **keyframes** e
  o **texto da narração**) antes do vídeo ser gerado, ou deixar tudo **automático**.

## Entidades

### `roteiros` (nova, versionada)
| Campo | Regras |
|---|---|
| `perfil_id` | imutável |
| `nome` | 1..120 |
| `brief` | texto livre do pedido (o que o vídeo deve mostrar) |
| `avatar_id` | asset `avatar` do perfil (kit da 025), opcional (vídeo só de produto) |
| `voz_id` | `vozes` do perfil (025); padrão = `assets.voz_id` do avatar; voz com consentimento |
| `formato` | enum `roteiro_formato`: `voice_over` (padrão e único nesta spec). Fala na câmera fica **fora** (ver Regras) |
| `frases` | lista ordenada do **texto de venda** (pt-BR), editável; é o que o TTS lê |
| `velocidade` | 0,9..1,2, padrão **1,08** (aplicada antes de calcular as durações) |
| `modo` | enum `roteiro_modo`: `revisar` (padrão) · `automatico` |
| `portoes` | jsonb `{texto, narracao, keyframes, clipes, final}`: cada um `true` = para e espera o operador |
| `status` | enum `roteiro_status` (máquina abaixo) |
| `conteudo_id` | FK → `conteudos` (014), preenchido quando o vídeo final é entregue (origem `video_proprio`) |
| `version`, `archived_*`, AuditMixin | histórico em `entity_versions` (`entity_type = roteiro`) |

### `roteiro_produtos` (nova)
`roteiro_id`, `produto_id` (012), `produto_variante_id` null, `ordem`. **Um ou vários produtos** por roteiro
(vídeo "3 achadinhos"); cada cena aponta o seu produto pela ponte que a 012 já criou em `cenas`.

### `roteiro_cenas` (nova)
| Campo | Regras |
|---|---|
| `roteiro_id`, `ordem` | ordem 0..n-1 sem buracos |
| `cena_id` | FK → `cenas` (010). **Reuso:** a mesma cena pode estar em vários roteiros |
| `frases` | índices de `roteiros.frases` cobertos por esta cena (toda frase em exatamente uma cena) |
| `inicio_s`, `duracao_s` | **derivados** da narração (não editáveis); a cena dura o tempo das suas frases |
| `tomada_id` | `cena_tomadas` usada neste roteiro (uma cena pode ter várias tomadas; cada roteiro escolhe) |

### `cenas` (010): só acréscimos
- `motor`: enum `cena_motor` (`minimax` padrão · `wan` · `wan_qualidade` · `ltx`); ver "Motor por cena".
- `largura`, `altura`: padrão **736×1280** (resolução nativa; ver Regras).
- **Keyframes** como imagens da própria cena (tabela `images`, `kind` novo `keyframe`):
  `keyframe_inicial_id` (obrigatório para gerar clipe), `keyframe_final_id` (opcional),
  `keyframe_instrucao` (en, o que gerou o inicial), `keyframe_refs` (image ids: kit do avatar, look, recorte ou
  flat do produto, cenário). Trocar o keyframe da cena invalida as tomadas `geracao_local` dela (ficam, mas
  marcadas "keyframe antigo").
- `duracao_max_s`: até quanto a tomada local pode durar (o clipe é cortado na duração da cena no roteiro).
- `tomada_origem` (010) ganha **`geracao_local`**; `cena_tomadas` ganha `geracao_id` (FK → `geracoes`). O
  ponto de extensão já está previsto no data-model da 010.
- **Reuso e variação:** cena `usada` não muda (regra da 010). Para variar (outro produto, look ou cenário),
  "Duplicar" e trocar o campo, o que pede **keyframe novo** (o resto da cena é aproveitado).

### `roteiro_narracoes` (nova; uma ativa por roteiro)
`roteiro_id`, `audio_id` (FK → `audios` da 021; take **contínuo**), `voz_id`, `texto_hash` (das frases
narradas), `tempos` jsonb `[{frase, inicio_s, fim_s}]` (alinhamento do Whisper), `similaridade`, `seed`,
`velocidade`. Mudar o texto ou a voz marca a narração como desatualizada.

### `pronuncias` (nova; por perfil)
Dicionário de **grafia falada** só para o TTS (ex.: `levinho → lévinho`, `leve → lévi`): a legenda e o roteiro
continuam com a grafia certa. Agudo = vogal aberta, circunflexo = fechada. Hoje é `input/vozes/pronuncia.json`
no shop-tts; no SociMan vira tabela editável e é enviado a cada pedido de narração.

### Passos novos na 021 (a lista fechada do FR-002 cresce)
| Passo | Motor | Resultado | Opções | Observação |
|---|---|---|---|---|
| `roteiro.plano` | claude | texto | — | do brief + produtos + avatar: frases de venda + lista de cenas, **preferindo reusar cenas da biblioteca**; vai direto (passo de texto) e é editável |
| `roteiro.narracao` | tts | áudio + tempos | 1 | `/tts_paragraph` contínuo, com `pronuncias`; refaz com outra seed se a transcrição não bater (≥ 0,95) |
| `cena.keyframe` | comfyui | imagem | 2 | Qwen Image Edit com as refs da cena; o escolhido vira `keyframe_inicial_id` |
| `cena.clipe` | comfyui | **vídeo** | 1 | bloco do `motor` da cena; vira `cena_tomadas` (origem `geracao_local`) |
| `roteiro.montagem` | ffmpeg (worker) | vídeo | 1 | corta cada tomada na `duracao_s`, junta, mistura a narração a −14 LUFS |
| `roteiro.acabamento` | comfyui | vídeo | 1 | SeedVR2 + filtro + 1080×1920 24 fps (ver Regras) |

Os candidatos da 021 ganham mídia de **vídeo** (`video_key` no bucket de vídeos, miniatura) além de imagem e
áudio. A trava de GPU e a RAM de 28 GB da 021 valem para `cena.*` e `roteiro.acabamento`.

## Fluxo e portões
```
brief + produtos + avatar
 └► [roteiro.plano] ─► frases de venda + cenas (novas ou reaproveitadas)   ⟵ portão TEXTO
     └► [roteiro.narracao] ─► áudio contínuo + tempos por frase             ⟵ portão NARRAÇÃO
         └► [cena.keyframe] para cada cena sem keyframe ─► 2 opções         ⟵ portão KEYFRAMES
             └► [cena.clipe] para cada cena sem tomada útil                 ⟵ portão CLIPES
                 └► [roteiro.montagem] ─► prévia com a voz                  ⟵ portão FINAL
                     └► [roteiro.acabamento] ─► vídeo HD ─► conteúdo na 014 (rascunho)
```
- **O operador vê tudo, sempre.** Em cada portão ligado, o roteiro para em `aguardando_<portão>`; em cada
  portão desligado (ou no modo `automatico`), escolhe a opção 1 e segue. Os portões podem ser ligados ou
  desligados a qualquer momento, e o padrão do perfil fica nas configurações.
- **O que dá para mexer em cada portão:**
  - TEXTO: editar, incluir ou remover frases; trocar, reordenar, reaproveitar ou duplicar cenas; mudar a
    atribuição frase → cena.
  - NARRAÇÃO: ouvir, editar uma frase (refaz a narração inteira, que é contínua), trocar a voz ou a velocidade.
  - KEYFRAMES: por cena, escolher entre as opções, **regerar só aquela**, editar a instrução, trocar refs ou
    **subir uma imagem pronta**.
  - CLIPES: por cena, ver a tomada, **regerar só aquela**, trocar o motor ou escolher outra tomada existente.
  - FINAL: assistir a prévia; aprovar manda para o acabamento.
- **Invalidações em cascata** (nunca apaga nada, só marca e pede):
  - texto mudou → narração desatualizada → durações recalculadas → montagem refeita;
  - keyframe mudou → tomadas daquela cena desatualizadas → clipe refeito;
  - duração da cena cresceu além da tomada → aviso "tomada curta, regerar clipe" (nunca congela quadro).
- **Reuso sem GPU:** cena com tomada aprovada de duração ≥ a necessária e keyframe atual não gera nada.
- **Modo automático:** escolhe a opção 1 nos passos de escolha (`cena.keyframe`) e segue; o histórico registra
  o autor `sistema (automático)`. Isso **altera a regra da 021** ("escolha sempre humana") **só dentro do roteiro
  com o modo ligado**. O vídeo final vai para a 014 **como rascunho**; publicar e agendar seguem a aprovação
  humana da 014/015 (princípio I).

### Estados do roteiro
```
rascunho ─► planejando ─► aguardando_texto ─► narrando ─► aguardando_narracao ─► gerando_keyframes ─►
aguardando_keyframes ─► gerando_clipes ─► aguardando_clipes ─► montando ─► aguardando_final ─►
finalizando ─► pronto (conteúdo criado)
qualquer ─► falhou (com etapa e erro; "Tentar de novo" retoma da etapa) · qualquer ─► arquivado
```
Os `aguardando_*` só existem com o portão ligado. Voltar a uma etapa anterior (ex.: editar texto em
`aguardando_clipes`) reposiciona o status e aplica as invalidações.

## Regras aprendidas (requisitos; fonte: `../CLAUDE.md`, `PADROES.md`, candidato 1)
- **Formato voice over.** Lip-sync local foi testado com LTX-2.5 (áudio travado), Wan 2.2 S2V e LatentSync 1.6:
  nenhum ficou natural (o LatentSync fecha a boca nas vogais do português). A avatar aparece sorrindo,
  mostrando o produto, sem falar. Fala na câmera fica fora desta spec.
- **Resolução nativa 736×1280.** Gerar em 480p e ampliar deixou o vídeo borrado; o MiniMax turbo é treinado em
  768p.
- **Motor por cena:**
  - padrão `minimax` (~3–8 min por cena);
  - `wan` (~3 min) para **plano de rosto sem fala**: o MiniMax gera vídeo e áudio juntos e mexe a boca
    ("boca de fantoche");
  - `wan_qualidade` (20 passos, ~40 min por 6,7 s) opcional para tecido/giro quando a física importa.
- **Prompt da cena** sempre com "boca fechada / não fala" quando há rosto, e "o quarto, as paredes e a luz não
  mudam" (o MiniMax inventou fundo num giro).
- **Keyframe:** descreve o **estado final**; nunca pedir mudança de luz (recolore o produto); sem "phone video"
  no prompt (desenha moldura de celular); close de produto **de lado** (manga, laço), nunca centrado no decote.
- **Avatar:** identidade pelo kit da 025; corpo fora do padrão (plus size) nasce do corpo inteiro.
- **Narração:** contínua (um take só, sem cortes entre frases); velocidade aplicada **antes** de calcular as
  durações; os cortes do vídeo seguem a fala (cada cena começa ~0,08 s antes da sua frase; a última termina
  0,45 s depois da fala); só voz com consentimento.
- **Acabamento:**
  - SeedVR2 3B na resolução da cena, em blocos de 41 quadros (blocos pequenos dão tranco);
  - `hqdn3d=0:0:3:3` (tira a cintilação a cada 4 quadros);
  - lanczos para **1080×1920, 24 fps, sem interpolação** (o FILM borra o movimento).
- **Publicação:** selo "conteúdo gerado por IA" no conteúdo final; o MiniMax-H3 exige atribuição em produto
  comercial (licença comunitária).
- **Tempos de referência (RTX 5060 Ti):**

| Etapa | Tempo |
|---|---|
| keyframe | ~1 min |
| clipe MiniMax | 3–8 min |
| clipe Wan | ~3 min |
| acabamento | ~16–20 min para 17 s |
| vídeo de 4 cenas, do zero | ~45–60 min |

## Dependências externas (`../comfyui-docker`), documentar em `contracts/`
- Blocos por contrato (`workflows/api/*.params.json`): `V2 - Keyframe (Qwen Edit)`,
  `V2 - Clip MiniMax-H3 …`, `V2 - Clip Wan 2.2 14B …` (rápido e `qualidade`), `V3 - Upscale vídeo SeedVR2 3B`.
- Lógica de referência: `pipeline/run_storyboard.py` (`run_block`, `concat` com `durations`, `comfy_free`),
  `pipeline/finalizar_hd.py`, `runs/bia_vo/gerar.py` e `refazer.py`.
- shop-tts: `POST /tts_paragraph` (frases, voz, seed → `narracao.wav` + tempos) e `pronuncia.json` (passa a vir do
  SociMan no pedido: mudança de contrato a registrar).

## Decisões do dono (2026-10-08), já tomadas
1. Portões aprovados por **dono ou membro** (como na 012); o histórico registra quem.
2. Roteiro com **um ou vários produtos** (`roteiro_produtos`).
3. No automático, o vídeo final vai para a 014 **como rascunho**; publicar e agendar seguem a aprovação humana.
4. Modo automático é opção do roteiro e mexe na regra da 021 só dentro do roteiro.
5. Formato único nesta spec: **voice over**.

## Fora do escopo
Fala na câmera e lip-sync; música de fundo e legendas queimadas (a 014 trata a legenda do post); LoRA por
avatar; motion templates (molde de movimento a partir de gravação); vídeo horizontal.

## Perguntas abertas (para o clarify, se precisar)
- Limite de cenas por roteiro (o candidato 1 tem 4; sugerir até 8).
- Guardar as tomadas não usadas por quanto tempo (a 021 limpa candidatos em 90 dias; tomada é da cena).
