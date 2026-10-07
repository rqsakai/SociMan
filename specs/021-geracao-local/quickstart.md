# Quickstart: validar a 021-geracao-local

Roteiro de validação. A §1 é automática (nenhum serviço real). As §2 a §4 são **manuais, com o dono**, na
GPU real, um passo por vez (comando → uma linha de explicação → rodar → ler a saída).

## §0. Pré-requisitos (uma vez)

1. **Constitution 4.3.0 aplicada** (T001): `grep -n "4.3.0" .specify/memory/constitution.md` mostra a versão
   e as "Exceções de eliminação" no princípio VII.
2. **Rede `gpu-local`** (dependência externa, research R5):
   ```bash
   docker network inspect gpu-local >/dev/null 2>&1 || docker network create gpu-local
   ```
   e, no `../comfyui-docker/docker-compose.yml`, `comfyui` e `tts` na rede (ver `contracts/comfyui.md`);
   depois `docker compose -f ../comfyui-docker/docker-compose.yml up -d`.
   **Verificar:** `docker network inspect gpu-local --format '{{range .Containers}}{{.Name}} {{end}}'` lista
   `comfyui` e `shop-tts`.
3. **`dockerctl`** (opção escolhida pelo dono, `contracts/dockerctl.md`): `DOCKERCTL_TOKEN` gerado pelo dono
   no `.env` da raiz (`openssl rand -hex 32`, sem imprimir), `DOCKER_GID` conferido por
   `./scripts/data-setup.sh check`.
4. **Bucket de áudios:** `./scripts/data-setup.sh check` mostra `sociman-audios` (o `ensure_buckets` cria).
5. Subir: `docker compose up -d gerador dockerctl` e `docker compose restart agendador`.
   **Verificar:** `curl -s http://localhost:8180/api/integracoes` (logado) mostra `geracao.comfyui: "ok"`,
   `memoriaComfyui: "ok"`, `gerador: "ativo"`.

## §1. Automático (sem serviço real)

```bash
npm run test:api -- -k "geracao or audio or migration_0020 or constitution"
docker compose exec api uv run ruff check .
npm run gen:contract && npm run check:web
npm run test:e2e -- e2e/geracao.spec.ts
```
Cobre: estados e transições, "um job de GPU por vez" (índice parcial), espera da GPU sem contar
tentativa, RAM 28 → 12 em sucesso/falha/cancelamento/worker reiniciado (fake do `dockerctl`), ordem
`/unload` ↔ `/free`, seeds novas, escolha humana (403 para MCP), passos sem escolha com aplicador
injetado, registro na 008 com `geracao_id`, áudios (formatos, 25 MB, Range), limpeza de 90 dias
(idempotente, escolhido intacto, arquivo em uso mantido, evento) e o guarda do delete restrito.

## §2. Piloto com a GPU real: cena de um cenário

1. No SPA, abra um cenário de teste em `/app/assets/:id` → "Gerar cena" → instrução "cozy bright bedroom,
   morning sun", 2 opções → **Gerar**. **Verificar:** a geração aparece "na fila" e logo "Gerando opção 1
   de 2".
2. Durante o job, no host:
   ```bash
   docker inspect comfyui --format '{{.HostConfig.Memory}}'   # 30064771072 (28 GB) durante o job
   ```
3. Ao terminar: as 2 opções em 768×1344, sem pessoas. Repita o `docker inspect`: **12884901888** (12 GB).
4. Clique em "Usar opção 2" → confirme. **Verificar:** o cenário tem o arquivo novo; o histórico do cenário
   mostra a versão "com a geração <id>"; a geração está "escolhida".
5. "Gerar cena" de novo e, na revisão, "Gerar outras". **Verificar:** a antiga fica "descartada", e as
   seeds da nova são diferentes (detalhe da geração).

## §3. GPU compartilhada e calibração dos pisos

1. Com um envio do OpenShorts processando (006), peça uma cena. **Verificar:** "Aguardando a GPU ficar
   livre", sem virar falha; quando o envio termina, a cena começa sozinha.
2. Calibração: com a GPU parada, `curl -s http://127.0.0.1:8188/system_stats | jq '.devices[0]'` e anote
   `vram_free`. Rode uma cena e anote o pico em `nvidia-smi --query-gpu=memory.used --format=csv -l 2`.
   Ajuste `GERACAO_VRAM_MIN_GB_COMFYUI` se o pico passar do padrão (12 GB).
3. Cancelar no meio: peça uma cena e cancele durante a opção 1. **Verificar:** a GPU para em até ~5 s
   (`nvidia-smi`), a geração fica "cancelada" e o limite volta a 12 GB.
4. Falha forçada: `docker stop comfyui`, peça uma cena. **Verificar:** espera com "O serviço de geração está
   fora do ar", tentativas crescendo; `docker start comfyui` e ela segue.

## §4. Limpeza (sem esperar 90 dias)

```bash
docker compose exec api uv run sociman geracoes limpar --dry-run   # lista o que seria apagado; não apaga
```
Para um teste real, use o banco de teste (o pytest já cobre o caminho com datas semeadas). No dev, **não**
force datas: a limpeza real é irreversível (exceção 1 da 4.3.0).
