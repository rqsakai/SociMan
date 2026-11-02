# Quickstart: 031-video-guiado

Guia de validação. As rotas estão em [contracts/http-api.md](contracts/http-api.md) e as tabelas em
[data-model.md](data-model.md). O §1 roda sem GPU. Do §2 em diante, o teste é feito **com o dono**, na GPU real.

## §0. Pré-requisitos

- A correção de memória do ComfyUI de 2026-10-13 (`/free` antes de devolver e o `dockerctl` conferindo o uso)
  já está na main (research R12).
- O host foi reiniciado depois da atualização do driver da NVIDIA: `nvidia-smi` sem "version mismatch",
  `comfyui` e `shop-tts` no ar.
- Backup antes da migration:
  ```bash
  docker compose exec -T postgres pg_dump -U sociman -Fc sociman \
    > /media/sakai/BACKUP/tiktok/sociman/backups/pre-0028.dump
  docker compose exec api uv run alembic upgrade head   # 0028_video_guiado
  docker compose restart api gerador agendador
  ```
- `.env`: `ROTEIRO_TRECHO_BASE_S=5` e `ROTEIRO_GRADE_MAX=6`. São os padrões, e as linhas podem ficar de fora.

## §1. Automático (sem GPU)

```bash
npm run test:api -- -k "guiado or quadros or trechos or conversa or migration_0028 or roteiro or constitution"
docker compose exec api uv run ruff check .
npm run gen:contract && npm run check:web
flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/video-guiado.spec.ts e2e/roteiros.spec.ts
```

Esperado:
- **criar:** o guiado nasce com a grade copiada e já pede as perguntas. Uma duração fora da grade dá 422.
  Trocar o perfil desmarca os itens que não servem mais (teste de tela);
- **chat:** 5 perguntas no máximo, respondidas só com cliques. O plano monta, e a soma das posições bate com a
  duração (SC-004);
- **reuso:** com o mesmo avatar, cenário e variante, o reuso `total` não pede nenhuma geração (SC-003). Com
  outro avatar, o reuso `plano` cria uma cena derivada com `origem_cena_id`. Cena de outro produto não é
  proposta;
- **quadros:** a cadeia pede o quadro i+1 com `base_image` = quadro i. Recusar o quadro 1 arquiva o 1 e os
  seguintes e mantém o 0. Só os trechos que tocam um quadro refeito são pedidos de novo (FR-028);
- **trechos:** cada trecho recebe `start_image` e `end_image` certos. A montagem gera exatamente a
  duração-alvo, com ±0,5 s (`ffprobe`). Um bloco de fala que não cabe gera o aviso `fala_nao_cabe`;
- **wizard:** varrendo o e2e, nenhuma tela do
  wizard mostra prompt ou texto de fala (SC-002);
- **"não aprovo":** um pedido "ambíguo" gera um esclarecimento sem gerar nada. Um pedido claro refaz só o alvo
  (SC-005);
- **guardas:** o `roteiros/automatico.py` continua sendo o único que escolhe sozinho. Todas as rotas novas
  estão classificadas no `mcp/mapa.py`;
- **regressão:** o `e2e/roteiros.spec.ts` da 011 (roteiro antigo no avançado) continua passando.

## §2. Primeiro vídeo guiado real (com o dono)

1. Abrir **AI Studio → Vídeos → Novo vídeo** e escolher:
   - Avatar & POV;
   - Queridinhos;
   - Queridinha (com a voz Roberta pré-carregada);
   - um cenário de quarto;
   - a saída de praia kaftan preta;
   - **20 s**.
2. Responder às perguntas só por cliques e montar. O **modal de cenas** mostra a decisão de cada posição.
3. **Esperado:**
   - a narração é aprovada pelo áudio;
   - a sequência de quadros de cada cena aparece junta;
   - recusar um quadro com "mais de lado, mostrando a manga" refaz só ele e os seguintes;
   - o vídeo final tem 20 s, e o conteúdo aparece na Central sem destino.
4. Anotar o tempo de GPU de cada etapa (estimativa no research R11: ~1 h para 20 s).

## §3. Medições do plano (com o dono)

- **Trecho-base:**
  - gerar no MiniMax, com o mesmo par de quadros, um trecho de 5 s e outro de 8 s;
  - comparar a fidelidade ao quadro final e ao produto;
  - se o de 8 s empatar, trocar `ROTEIRO_TRECHO_BASE_S=8` (grade 8 a 32 s) e reiniciar `api` e `gerador`.
- **Emenda:**
  - montar uma cena de 3 trechos e olhar as duas emendas quadro a quadro (`ffmpeg -ss` perto das emendas);
  - se o salto for visível, ligar o cross-fade de 2 quadros (parâmetro da montagem).
- **Deriva de identidade:** comparar o rosto do quadro 0 com o do quadro 3 da mesma cena. Se mudar, somar o
  `rosto_34` às âncoras (R3).
- **SC-006:** contar as cenas recusadas por "o fim não é o planejado" no mesmo produto e comparar com o teste
  de 2026-10-13 (1 keyframe).

## §4. Avançado e roteiros antigos

- Abrir um roteiro da 011. Ele vem no **avançado**, e o switch explica por que não há wizard.
- No guiado, trocar para o avançado:
  - pedir 2 opções de um quadro;
  - editar a instrução do quadro 2;
  - voltar ao wizard, onde o quadro aparece "a refazer" e as aprovações anteriores continuam (SC-007).
