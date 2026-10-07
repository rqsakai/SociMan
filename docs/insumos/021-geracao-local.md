# Insumo: 021-geracao-local (jobs de geração local com candidatos)

Entrada para o `/speckit-specify`. **Pré-requisito** da 007 estendida (avatar, voz, cenário) e da 012
(produtos). Referência técnica testada: `../comfyui-docker/pipeline/` (`PADROES.md`, `run_storyboard.py`,
`avatares.py`, `produtos.py`, `voz.py`) e o serviço `shop-tts`.

## Problema
Todo cadastro padronizado segue o mesmo ciclo: **pedir uma geração → a IA local gera N opções → o dono
escolhe → a escolhida vira o arquivo oficial**. Hoje isso vive em pastas (`_candidatos/<lote>/opcao_N.png`).
O SociMan precisa de uma entidade única para esse ciclo, usada por todos os tipos de asset (e, depois, pelo
render de storyboards).

## Entidades

### `geracoes` (o job)
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid FK → perfis | |
| `alvo_tipo` | enum `geracao_alvo` (`asset`, `voz`, `produto`) | a quem o resultado pertence |
| `alvo_id` | uuid | id do asset / voz / produto |
| `passo` | text | o que está sendo gerado. Ex.: `avatar.rosto_origem`, `avatar.rosto_frontal`, `avatar.rostos_34`, `avatar.corpo_base`, `avatar.look`, `avatar.pose`, `avatar.identidade`, `voz.gravacao`, `voz.design`, `produto.ficha`, `produto.recorte`, `produto.flat`, `cenario.cena`, `cenario.variacao` (check com a lista) |
| `motor` | enum `geracao_motor` (`comfyui`, `tts`, `claude`) | |
| `params` | jsonb | entrada resolvida: instrução/prompt, referências (`image_id`s), seeds, `n` de opções, rótulo (nome do look/pose/variação) |
| `n_opcoes` | smallint | padrão 2 (rosto de origem: 4; voz: até 3) |
| `status` | enum `geracao_status` (ver Estados) | |
| `progress` | smallint 0..100 | |
| `etapa_mensagem` | text null | pt-BR curto ("Gerando opção 2 de 2") |
| `attempts`, `next_attempt_at` | | backoff quando a GPU está ocupada (503 do TTS, OOM do ComfyUI) |
| `error_code`, `error_message` | text null | `gpu_ocupada`, `servico_fora`, `sem_memoria`, `entrada_invalida`, `internal` |
| `escolhido_id` | uuid null FK → geracao_candidatos | |
| `started_at`, `finished_at` | timestamptz null | |
| AuditMixin | | `created_by` = quem pediu |

### `geracao_candidatos` (as opções)
| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `geracao_id` | uuid FK | |
| `numero` | smallint | 1..n (o "opção N" que o dono vê) |
| `image_id` | uuid null FK → images | candidato de imagem |
| `audio_id` | uuid null FK → audios | candidato de voz (ver 007) |
| `seed` | bigint null | |
| `metricas` | jsonb | por tipo: voz → `{segundos, similaridade, transcricao, teste_audio_id}`; identidade → `{nota, observacao}` |
| `created_at` | | |

Check: exatamente um de `image_id`/`audio_id`, exceto passos só de texto (`produto.ficha`,
`avatar.identidade`), cujo resultado vai em `metricas`/no alvo.

### `audios` (novo; irmão da `images` da 003)
Imutável; só é apagado pela limpeza de candidatos de 90 dias. `id`, `perfil_id`, `object_key` (`perfis/{perfil_id}/{uuid}.wav`), `formato`,
`sample_rate`, `duracao_ms`, `sha256`, `created_at/by`. Limite de upload: 25 MB, wav/m4a/ogg/mp3.

## Estados
```
na_fila ──worker──▶ rodando ──▶ revisao ──"usar opção N"──▶ escolhido
   ▲                  ├─GPU ocupada / 503─▶ na_fila (backoff)
   │                  └─erro─▶ falhou ──"Tentar de novo"──┘
revisao ──"gerar outras"──▶ (nova geração com seeds novas; a antiga fica `descartada`)
qualquer não-final ──cancelar──▶ cancelada
```
- `escolhido`, `descartada`, `cancelada` são finais. Escolher copia a referência do candidato para o alvo
  (ex.: vira `asset_files` do slot) e grava a versão do alvo com `details.geracao_id`.
- Passos com `--auto` no pipeline (escolher a opção 1) **não** existem no SociMan: sempre há revisão humana,
  exceto passos de texto (`produto.ficha`, `avatar.identidade`), que vão direto para o alvo e são editáveis.
- Candidatos não escolhidos são apagados 90 dias depois (ver Decisões); o escolhido nunca é.

## Worker (trilha `geracao`)
- No máximo **um** job `comfyui`/`tts` rodando por vez, e só com a GPU desocupada (ver Decisões). Jobs `claude` rodam fora dessa fila.
- ComfyUI: o worker usa os blocos de `workflows/api/*.params.json` (`cutout`, `keyframe`, `retrato`,
  `cena`), preenchendo parâmetros pelo contrato, como o `run_block` do pipeline. Libera a VRAM do ComfyUI
  antes de chamar o TTS e vice-versa (`/free` e `POST /unload`).
- shop-tts: endpoints `/voices/register`, `/voices/design`, `/voices/approve`, `/tts`, `/tts_paragraph`.
  **Mudança de contrato necessária:** hoje eles recebem caminhos de arquivo (`/in`, `/out`); o SociMan
  precisa enviar/receber arquivos (multipart, ou URL assinada do MinIO) e uma rota para **importar** uma voz
  aprovada (wav + transcrição), porque a fonte da verdade passa a ser o SociMan.
- Chamadas ao Claude entram no registro de chamadas da 008 (custo do mês).

## Fora do escopo
Render de storyboards e vídeos (spec futura do motor de cenas); LoRA por avatar.

## Decisões do dono (2026-10-06)
1. **RAM do ComfyUI:** o worker sobe o limite do container para 28 GB **só durante** o job `comfyui` e
   **devolve para 12 GB logo em seguida**, inclusive quando o job falha ou é cancelado (`finally`). O
   worker precisa de acesso ao Docker para isso. Ao subir, o worker confere se o limite voltou (se não
   voltou, registra erro e tenta de novo antes do próximo job).
2. **GPU compartilhada com o OpenShorts:** sem fila única. Antes de iniciar um job `comfyui`/`tts`, o
   worker verifica se a GPU está desocupada (sem job do OpenShorts processando e VRAM livre suficiente);
   se não estiver, o job continua `na_fila` e tenta de novo depois (backoff), com a mensagem "Aguardando a
   GPU ficar livre".
3. **Limpeza:** candidatos não escolhidos (e os arquivos deles) são apagados **90 dias** depois que a
   geração termina. Escolhidos nunca são apagados.
