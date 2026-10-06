# Quickstart: validar o Histórico do TikTok Studio (020)

Roteiro de validação de ponta a ponta. A forma das rotas está em [contracts/http-api.md](contracts/http-api.md)
e as regras em [data-model.md](data-model.md).

> **Privacidade:** os ZIPs reais do dono (`~/Downloads/Overview_*_atavernanerd.zip` e outros) **nunca**
> entram no repositório nem nos testes automatizados. Os testes geram arquivos sintéticos
> (`tests/integration/studio_helpers.py`, conta `contateste`). Só o passo 5 usa os arquivos reais, à mão,
> na stack de dev.

## 0. Pré-requisitos

- Stack de dev no ar: `docker compose up -d` e `curl http://localhost:8180/api/health` → `ok`.
- Migration aplicada: `docker compose exec api uv run alembic upgrade head` (a cabeça deve ser a
  `0013_historico_studio`).
- As contas @atavernanerd e @meusqueridinhos10 conectadas com métricas (016), com série viva.
- Logado como dono (e, para o passo 4, também como membro).

## 1. Testes automatizados

```bash
npm run test:api -- tests/ -k "studio or analytics or metricas or constitution or migration_0013" -q
docker compose exec -T api uv run ruff check .
npm run gen:contract && npm run check:web
flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/studio.spec.ts e2e/analytics.spec.ts
```

**Esperado:** tudo verde, incluindo:
- a leitura dos arquivos sintéticos em inglês e pt-BR, com e sem virada de ano (SC-002);
- todos os arquivos defeituosos e ZIPs inseguros recusados, com 0 linhas gravadas (SC-003);
- reimportar grava 0, e as fotos da API ficam intactas antes e depois de importar e de desfazer (SC-004);
- a série diária e os indicadores batem com a referência, desfazer volta ao número anterior, e sem
  Studio o número é igual ao da 019 (SC-005, SC-006);
- membro, `system:*` e token de agente recebem 403 e deixam o evento registrado (SC-007);
- os guardas: sem `publicacao`, `httpx`, `minio` nem `extract` no pacote `metricas/studio/`.

## 2. Pré-visualização e confirmação (US1, US2) com arquivos sintéticos

1. Gere os ZIPs sintéticos para a conta de teste da stack:
   `docker compose exec -T api uv run python -m tests.integration.studio_helpers --handle <handle> --saida /tmp/studio`.
   Copie-os para o host com `docker compose cp`.
2. Abra a conta TikTok no perfil → "Histórico do Studio" → envie os dois ZIPs.
   **Esperado:** a pré-visualização mostra:
   - o período com o ano e "ano pelo nome do ZIP";
   - as 2 seções e as 3 entradas ignoradas do ZIP de Seguidores;
   - os totais, as contagens e a amostra.

   Nada foi gravado: `GET …/studio/importacoes` continua vazio.
3. Confirme. **Esperado:**
   - a importação aparece na lista;
   - o histórico da importação tem a versão 1, sem nome de arquivo no snapshot;
   - a cobertura mostra a faixa importada.
4. Envie os mesmos ZIPs de novo. **Esperado:** "já importado em … por …", sem o botão de confirmar.
5. Envie um ZIP renomeado para `…_outraconta.zip`. **Esperado:** "o arquivo é de @outraconta…".
6. Envie só o `Overview.csv` solto. **Esperado:** "ano deduzido" e a caixa "confirmo que é de @…"
   obrigatória para confirmar.
7. Envie o `Content_*.zip` sintético. **Esperado:** "esta seção não é importada…".

## 3. Analytics (US3) e desfazer (US4)

1. Em `/app/metricas`, escolha um período que inclua os dias importados e os primeiros dias de coleta.
   **Esperado:**
   - a série diária mostra os dias do Studio tracejados, com legenda e tooltip "importado do Studio";
   - o dia da 1ª coleta usa o Studio (sem o pico das views acumuladas);
   - os indicadores mostram "inclui N dias importados do Studio";
   - "Ver tabela" e o CSV têm a coluna `fonte`.
2. As abas Quando postar, Curvas e O que funciona não mudam. Num período só com dias do Studio, elas
   mostram a nota "o Studio não traz dado por vídeo nem por hora".
3. Desfaça a importação. **Esperado:**
   - a lista mostra "desfeita por … em …";
   - o analytics volta aos números anteriores;
   - no banco, as linhas de `metricas_studio_dias` continuam lá (`SELECT count(*)`, só leitura).

## 4. Permissões

1. Como membro: a página "Histórico do Studio" mostra a cobertura e a lista, **sem** "Importar" nem
   "Desfazer".
2. Com o cliente de API de um membro (ou um token `system:*`), um `POST …/studio/previa` recebe 403. O
   evento `publicacao_recusada` aparece em `security_events` (só para não humanos).

## 5. Importação real (manual, com o dono)

1. Com os ZIPs reais de @atavernanerd (`~/Downloads`), importe na conta @atavernanerd. **Esperado:**
   - período 25/09/2026 a 01/10/2026;
   - views 118, 201, 1, 2, 6, 834 e 914;
   - seguidores de 0 a 4;
   - o dia 01/10 contado como "coletado" (vale a API, e o Studio aparece no tooltip);
   - o dia 30/09 vale o Studio (dia da 1ª coleta).
2. Exporte o dataset (016) e confira o `studio_dias.csv` e o `dicionario.csv` (versão 2).
3. Repita para @meusqueridinhos10 com os ZIPs dela e confira que o dia 01/10 deixa de mostrar as views da
   vida inteira dos 89 vídeos.

## 6. Pendências de verificação manual

- [ ] Exportar com a interface do Studio em **português** e conferir os sinônimos provisórios (research
      R15). Se algum cabeçalho ou mês diferir, ajuste `SINONIMOS`/`MESES` e tire o `provisorio`.
- [ ] Confirmar com um download de 60 dias (e, se existir, de 365) que o nome do ZIP e o formato se mantêm.
