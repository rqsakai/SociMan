# Quickstart: 011-roteiros-video-local

Como provar que a feature funciona. O §1 é automático (sem GPU nem serviço real). O §2 ao §4 são manuais,
**com o dono**, na GPU real. Os detalhes estão no [data-model](data-model.md), em
[contracts/](contracts/) e no [research](research.md).

## 0. Pré-requisitos
- 012 (produtos) e 025 (kit do avatar, vozes) implementadas e com migration aplicada; a 011 vem depois
  (migration `0024`, conferida no gate T001).
- Emenda da constitution **4.4.0** aplicada (T001): exceção (1) ampliada aos intermediários de roteiro.
- Para o §2 em diante, as dependências externas do dono:
  - X1 (rede `gpu-local`);
  - X2 (shop-tts v2);
  - **X3** (campo `pronuncias` no `/v2/tts_paragraph`, [contracts/shop-tts-pronuncias.md](contracts/shop-tts-pronuncias.md));
  - `DOCKERCTL_TOKEN` no `.env`.
- Backup antes da migration: `pg_dump` em `/media/sakai/BACKUP/tiktok/sociman/backups/pre-0024.dump`.

## 1. Automático (sem GPU)
```bash
npm run test:api -- -k "roteiro or tempos or pronuncia or migration_0024 or cena_local or limpeza"
npm run gen:contract && npm run check:web
flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/roteiros.spec.ts
```
Deve passar:
- **Tempos:** `test_tempos_bia_vo` dá 3,327 / 6,722 / 5,315 / 1,826 com os tempos da referência e a
  velocidade 1,08.
- **Fluxo com todos os portões:** o roteiro de 3 cenas (1 reaproveitada com tomada útil) para em cada
  `aguardando_*`. Só 2 keyframes e 2 clipes vão para a fila da GPU, e a montagem roda fora da trava.
  O acabamento sai em 1080×1920 a 24 fps com −14 LUFS (±1). O conteúdo nasce `geradoIa`, sem destino, e
  as cenas viram `usada`.
- **Automático:** a opção 1 é escolhida com o autor `system:roteiro`. Fora do roteiro, `escolher_automatico`
  é recusado. MCP e agente levam 403 `somente_humano`.
- **Invalidações:** editar uma frase em `aguardando_final` volta para `narrando`. Só a posição que cresceu
  além da tomada pede clipe, e nada é apagado.
- **Limpeza:** os intermediários com `desuso_em` há 91 dias são removidos (com o evento
  `eliminacao_intermediarios`). Os de 89 dias e os protegidos ficam: entrega, tomada atual, tomada do
  Flow e keyframe atual.
- **Revogação:** depois de revogar a voz, a narração nova leva 409 `consentimento_revogado`, e o que já
  existia continua.
- **Guardas:** `test_constitution_guards` (seção 011) e `test_mcp_mapa`.

## 2. Manual: roteiro do zero, todos os portões (dono)
1. `docker compose up -d` e `docker compose logs -f gerador`.
2. No perfil de teste, cadastre o dicionário (aba **Vídeo local**: "levinho → lévinho") e confira um
   produto aprovado (012) e o avatar com kit e voz (025).
3. Em **Roteiros → Novo**, preencha nome, brief, produto e avatar e clique em **Planejar**. Confira as
   frases, as cenas e a chamada no **Assistente de IA → Registro**.
4. Aprove o TEXTO, ouça a narração (as palavras do dicionário são faladas como cadastradas) e aprove.
5. Nos keyframes, escolha, regere uma cena e suba uma imagem pronta noutra. Em outro terminal, confira a
   RAM durante o job: `docker inspect comfyui --format '{{.HostConfig.Memory}}'` mostra 28 GB durante e
   12 GB depois.
6. Nos clipes, assista, troque o motor de uma cena para `wan` e regere.
7. Assista à prévia e aprove o FINAL. Confira o conteúdo em **Conteúdos**: marcado como gerado por IA,
   sem destino, com o aviso do MiniMax.

**Medir:** o tempo de cada etapa (keyframe ~1 min, clipe 3 a 8 min, acabamento ~16 a 20 min para 17 s).
**SC-002:** até 75 min para 4 cenas do zero.

## 3. Manual: calibração dos tetos e do modo automático
- Peça um roteiro com uma cena longa (~7 s) em cada motor e ajuste o `duracao_max_s` padrão por motor
  (R4) até não haver corte de qualidade. Anote no `CLAUDE.md`.
- Rode um roteiro **automático** reaproveitando as cenas do §2. Ele deve chegar ao conteúdo sem nenhum
  job de keyframe ou clipe (SC-002, segunda parte) e só com o acabamento na GPU.

## 4. Manual: limpeza e revogação (opcional, banco de teste)
- `docker compose exec api uv run sociman geracoes limpar --dry-run` lista os intermediários que seriam
  removidos. Confira que nenhum item de vídeo entregue aparece.
- Não revogue voz real para testar: o §1 cobre a revogação com dados sintéticos.
