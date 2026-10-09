# Contrato: shop-tts — o que a 025 acrescenta (DEPENDÊNCIA EXTERNA)

> **Dependência externa.** O serviço fica em `../comfyui-docker/tts_service/app.py` (container `shop-tts`).
> **Esta spec não edita esse serviço.** O contrato base (`/v2/voices/register`, `/v2/voices/design`,
> `/v2/voices/import`, `/v2/tts`, `/v2/lotes/...`) é o de `specs/021-geracao-local/contracts/shop-tts.md`.
> Aqui ficam só o identificador da voz e o que a 025 precisa a mais. A mudança é feita no projeto
> `comfyui-docker` antes do primeiro uso real da voz (decisão D3 da 021).

## Identificador da voz no serviço (`nome`)

O serviço aceita só `[a-z0-9_]{2,40}` (`_nome_ok` em `app.py`) e chama a voz pelo nome
(`/vozes/ref_<nome>.wav`, `ref_texts.json`, `ref_meta.json`). O SociMan **nunca** usa o `vozes.name`
(texto livre, 1..60, renomeável) como nome no serviço. O nome é:

```text
tts_id(voz) = "v_" + voz.id.hex[:32]     # 34 caracteres, [a-z0-9_], estável, único entre perfis
```

- derivado do `id` (não há coluna; função pura em `vozes/tts_id.py`, com teste de formato);
- renomear a voz no SociMan não muda nada no serviço;
- vozes cadastradas pelo CLI do pipeline (nomes como `vendedora_ana`) não colidem (o prefixo `v_` + 32
  hex não é usado pelo pipeline).

## Usos pela 025

| Momento | Chamada | Nome |
|---|---|---|
| candidatos de gravação | `POST /v2/voices/register` (multipart, `arquivo` = `vozes.gravacao_audio_id`, `tom`, `n ≤ 3`) | `tts_id` |
| candidatos sintéticos | `POST /v2/voices/design` (`descricao`, `texto`, `n ≤ 3`, `seed`) | `tts_id` |
| aprovar (linha `vozes_sync` do `gerador`) | `POST /v2/voices/import` (`ref` = `ref_audio_id`, `ref_texto`, `meta = {origem, tom, sociman_voz_id, sha256}`) e conferência do `sha256` em `GET /voices` | `tts_id` |
| testar | `POST /v2/tts` com `voice = tts_id` e o texto | `tts_id` |
| revogar (linha `vozes_sync` do `gerador`) | **novo:** `DELETE /v2/voices/{nome}` | `tts_id` |

## Pedido aditivo da 025: remover uma voz

### `DELETE /v2/voices/{nome}`
- `nome` validado por `_nome_ok`;
- apaga `/vozes/ref_<nome>.wav`, a chave em `ref_texts.json` e em `ref_meta.json` (escrita atômica,
  com o `_lock`), e tira o prompt da voz do cache (`_state["prompts"].pop(nome)`);
- apaga também os lotes temporários (`/out/v2/*`) cujo `lote.json` cite o nome, se ainda existirem;
- **204** se removeu; **404** se a voz não existe (o SociMan trata 404 como "já removida");
- idempotente.

**Por quê:** a revogação do consentimento (FR-033a, exceção 2 da constitution 4.3.0) tem de apagar a
referência da pessoa também no serviço, que guarda uma cópia para narrar.

A lista fechada (`ALLOWED`) do cliente `geracao/shoptts.py` ganha `DELETE /v2/voices/{nome}`.

## Fake
- pytest: `apps/api/tests/fakes/shoptts_fake.py` (da 021) ganha o `DELETE /v2/voices/{nome}` e a
  inspeção das vozes importadas (para conferir import, `sha256` e remoção);
- e2e: o `openshorts-fake` (`/shop-tts/*`, da 021) ganha a mesma rota e `/geracao-e2e/vozes-tts` (lista do
  que foi importado/removido).
