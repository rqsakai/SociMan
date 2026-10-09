# Contrato: shop-tts — pronúncias no pedido (DEPENDÊNCIA EXTERNA X3)

> **Dependência externa.** O serviço fica em `../comfyui-docker/tts_service/app.py`. **Esta spec não edita
> esse serviço.** A mudança é aditiva sobre o contrato `v2` da 021 (`specs/021-geracao-local/contracts/shop-tts.md`,
> X2) e é feita pelo dono ou numa sessão dedicada, antes do quickstart §3. Até lá, o motor de narração é
> testado contra o fake.

## Por que mudar
Hoje o dicionário de pronúncia é o arquivo `/vozes/pronuncia.json` (`app.py:40-56`), lido a cada chamada. No
SociMan, ele vira a tabela `pronuncias` por perfil, editável na tela, e cada perfil tem o seu dicionário.
O arquivo do serviço é um só para todos os perfis.

## Mudança
`POST /v2/tts_paragraph` (e `/v2/tts`) ganham o campo opcional:

```text
pronuncias?: { [escrita: string]: string }    # ex.: {"levinho": "lévinho", "leve": "lévi"}
```

Regras pedidas ao serviço:
- com o campo **presente** (mesmo `{}`), ele **substitui** o `pronuncia.json` naquela chamada; ausente,
  vale o arquivo (o CLI do pipeline continua igual);
- a aplicação é a mesma de hoje: palavra inteira, sem diferenciar maiúsculas, preservando a inicial
  maiúscula; só na entrada do TTS (a validação pela transcrição usa o texto original);
- limite de 500 pares, chaves e valores de 1..60 caracteres; fora disso, 422.

## O que o SociMan manda e espera (já do contrato v2)
```text
POST /v2/tts_paragraph
{ sentences: [str], voice: "v_<hex32>", seed: int, max_attempts: 5, min_similarity: 0.95,
  language: "Portuguese", pronuncias: {...} }
→ Lote { lote_id, arquivo: "narracao.wav", sample_rate: 24000, seconds, ok, similarity, seed, transcript,
         sentences: [{index, text, start, end}], attempts: [{seed, similarity, seconds}] }
```
Depois de baixar (`GET /v2/lotes/{lote_id}/narracao.wav`) e apagar o lote, o SociMan:
1. aplica `atempo=<velocidade>`;
2. divide `start`/`end` pela velocidade;
3. grava o áudio final em `audios`.

A **velocidade não vai ao serviço** (research R5).

## Fake
`apps/api/tests/fakes/shoptts_fake.py` e `e2e/fakes/geracao_fake.py` aceitam o campo, guardam o último
`pronuncias` recebido para o teste conferir e devolvem tempos proporcionais ao tamanho de cada frase.
