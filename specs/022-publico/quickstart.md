# Quickstart: validar o Público (022)

Roteiro de validação de ponta a ponta. A forma das rotas está em [contracts/http-api.md](contracts/http-api.md)
e as regras estão em [data-model.md](data-model.md).

> **Privacidade:** os ZIPs reais do dono (`Followers_*.zip`, `Viewers_*.zip`) **nunca** entram no
> repositório nem nos testes automatizados. Os testes geram arquivos sintéticos
> (`tests/integration/studio_helpers.py`, conta `contateste`), inclusive o `Viewers.xlsx`, montado em
> memória. Só o §5 usa os arquivos reais, à mão, na stack de dev.

## 0. Pré-requisitos

- A stack de dev no ar: `docker compose up -d` e `curl http://localhost:8180/api/health` → `ok`.
- A migration aplicada: `docker compose exec api uv run alembic upgrade head`, com a cabeça em
  `0017_publico` (ou em uma posterior que aponte para ela).
- As contas @atavernanerd e @meusqueridinhos10 conectadas com métricas (016), com série viva.
- Logado como dono (e, para o §4, também como membro).

## 1. Testes automatizados

```bash
npm run test:api -- tests/ -k "studio or publico or analytics or metricas or constitution or mcp_mapa or migration_0017" -q
docker compose exec -T api uv run ruff check .
npm run gen:contract && npm run check:web
flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/publico.spec.ts e2e/studio.spec.ts e2e/analytics.spec.ts
```

**Esperado:** tudo verde, incluindo:
- os CSVs de público e o XLSX sintéticos lidos número a número, com `undefined` → "sem dado" (SC-002);
- os arquivos de público só com o cabeçalho aceitos como "ainda sem dados de público"; um envio só de
  vazios recusado com `studio_sem_dados`;
- os XLSX maliciosos recusados (macro, fórmula, DOCTYPE, link externo, protegido, *bomb*, `..`, 2º nível
  de aninhamento) sem nada gravado (SC-004);
- reimportar grava 0 linhas, e desfazer volta a aba Público ao estado anterior (SC-005);
- os testes da 020 e da 019 sem regressão.

## 2. Importação sintética (US1, US2)

1. Gere os arquivos sintéticos:
   `docker compose exec -T api uv run python -m tests.integration.studio_helpers --handle <handle> --publico --saida /tmp/studio`.
   Copie para o host com `docker compose cp`. Saem um `Followers_<handle>.zip` com os 4 CSVs preenchidos e
   um `Viewers_<handle>.zip` com 7 dias, o 1º com `undefined`.
2. Na conta TikTok, abra "Histórico do Studio" e envie os dois ZIPs. **Esperado** na prévia:
   - **Gênero e Territórios:** a data da foto (o dia seguinte ao último do `FollowerHistory.csv`, origem
     "histórico") e a distribuição;
   - **Atividade:** os dias, o pico e 168 linhas;
   - **Espectadores:** 7 dias, 1 "sem dado" e os totais;
   - nada gravado: `GET …/studio/importacoes` não muda.
3. Confirme. **Esperado:**
   - uma importação com 5 seções (seguidores, gênero, territórios, atividade, espectadores);
   - o histórico na versão 1, sem rótulo nem nome de arquivo no snapshot;
   - a cobertura com a foto e as faixas.
4. Envie de novo os mesmos ZIPs. **Esperado:** "já importado em … por …" em todas as seções, sem o botão
   de confirmar.
5. Gere com `--publico-vazio` (os 3 CSVs só com o cabeçalho, como o arquivo real) e envie só o ZIP de
   Seguidores. **Esperado:** o `FollowerHistory.csv` como na 020 e as 3 seções com "ainda sem dados de
   público…". Confirme: a importação tem `secoesVazias` com as 3.
6. Envie um `Viewers.xlsx` solto. **Esperado:** a caixa "confirmo que este arquivo é de @…" obrigatória.
7. Envie um XLSX com fórmula (`--defeito formula`). **Esperado:** "a planilha tem fórmula (célula B3)…".

## 3. Analytics (US3, US4) e desfazer

1. Em `/app/metricas?aba=publico`, com um período que inclua os dias importados. **Esperado:**
   - **Gênero:** barras de um tom, a % em texto, "foto de 02/10" e a fonte "TikTok Studio";
   - **Territórios:** até 5 países e "Outros";
   - **Atividade:** o mapa 7 × 24, com n por célula, as células de n = 1 marcadas como amostra pequena e a
     nota "horas conforme a TikTok";
   - **Espectadores:** a série com um buraco no dia "sem dado", os novos somados e as médias diárias;
   - "Ver tabela" e o CSV de cada card com `fonte` e `data_foto` (ou `dia` e `hora`).
2. Escolha um período **sem** atividade. **Esperado:** o mapa vazio com "ver os últimos dias com dado";
   clicar muda o período global para os 7 dias que terminam no último dia com dado.
3. Escolha um período que termina depois da foto e começa depois dela. **Esperado:** "foto de 02/10,
   anterior ao período".
4. Em "Quando postar", **esperado:** o 3º mapa "Seguidores on-line (TikTok Studio)", igual ao da aba
   Público; os outros dois mapas não mudam.
5. Desfaça a importação. **Esperado:** a aba Público e o 3º mapa voltam ao estado anterior, e as linhas
   das 3 tabelas continuam no banco (`SELECT count(*)`, só leitura).

## 4. Permissões

1. Como membro: a aba Público aparece, os estados vazios mostram o motivo **sem** o atalho de importar, e
   a página "Histórico do Studio" não tem "Importar" nem "Desfazer".
2. Um `POST …/studio/previa` com o cliente MCP ou com um `system:*` recebe 403 `somente_humano`, com o
   evento `publicacao_recusada`.
3. No MCP, a tool "Analytics: público" responde (leitura).

## 5. Importação real (manual, com o dono)

1. Com os ZIPs reais de @atavernanerd baixados em 02/10/2026, envie o `Followers_atavernanerd.zip` e o
   `Viewers_atavernanerd.zip` na conta @atavernanerd. **Esperado:**
   - o `FollowerHistory.csv`: "já importado" se o dono já o importou na 020; senão, entra como na 020;
   - gênero, territórios e atividade aparecem como "ainda sem dados de público (cerca de 100 seguidores)";
   - os espectadores de 25/09 a 01/10: total "sem dado", 104, 181, 1, 2, 3 e 663; novos 0, 104, 181, 1, 2,
     3 e 622; recorrentes 0, 0, 0, 0, 0, 0 e 41;
   - sem o aviso `espectadores_soma` (o real fecha a conta).

   Confirme: a importação tem `espectadores` nas `secoes` (mais `seguidores`, se o histórico era novo) e
   `secoesVazias` com as 3.
2. Na aba Público: gênero, territórios e atividade com "a TikTok libera com mais seguidores"; os
   espectadores com a série.
3. Exporte o dataset e confira o `studio_espectadores.csv` e o `dicionario.csv` (versão 3).

## 6. Pendências de verificação manual

- [ ] Quando uma conta passar de ~100 seguidores: exportar de novo e conferir no arquivo real os formatos
      de % e de rótulos de gênero e território, o formato de data e hora do `FollowerActivity.csv`, e
      quantos dias de atividade vêm por download (research R14). Ajustar os sinônimos e tirar o
      `provisorio`.
- [ ] Conferir se as horas da atividade batem com o horário de Brasília mostrado no Studio (research R13).
      Se estiverem em UTC, mudar o `FUSO_ATIVIDADE`.
- [ ] Exportar com a interface em **português** e conferir os sinônimos pt-BR das seções novas.
