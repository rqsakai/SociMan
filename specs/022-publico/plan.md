# Implementation Plan: Público

**Branch**: `022-publico` | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/022-publico/spec.md`

## Summary

A importação do TikTok Studio da 020 passa a ler também as seções de **público**:
- do ZIP de Seguidores, o `FollowerGender.csv`, o `FollowerTopTerritories.csv` e o `FollowerActivity.csv`
  (hoje listados como ignorados);
- do ZIP de Espectadores, o `Viewers.xlsx` (hoje recusado).

O XLSX é lido **com a biblioteca padrão** (`zipfile` + `xml.etree`), com as proteções de ZIP da 020
aplicadas também à planilha por dentro. Tudo entra **na mesma importação** da 020: a mesma prévia no
Redis, o mesmo confirmar (tudo ou nada, idempotente por SHA) e o mesmo desfazer.

A migration **`0017_publico`** faz duas coisas:
- amplia `metricas_studio_importacoes` com as colunas de SHA das seções novas, a data da foto e as
  seções que vieram vazias;
- cria três tabelas **só de inserção**: fotos de distribuição, atividade por dia e hora, e espectadores
  por dia.

No analytics:
- a rota nova `analytics_publico` alimenta a aba **Público** (gênero, territórios, mapa de atividade e
  espectadores);
- `analytics_quando_postar` ganha o 3º mapa (campo aditivo).

A cobertura e a exportação da 020 ganham as seções novas (dicionário versão 3). Nada publica. Não há
dependência, serviço nem segredo novo.

## Technical Context

**Language/Version**: Python 3.12 (API, uv) · TypeScript 5 / React 19 (SPA, Vite 8)

**Primary Dependencies**: FastAPI, SQLAlchemy 2, Pydantic 2, python-multipart e redis-py. A leitura usa
`csv`, `zipfile`, `hashlib` e **`xml.etree.ElementTree`** da biblioteca padrão. **Nenhuma dependência
nova:** sem openpyxl e sem defusedxml (R2). Na SPA: TanStack Query, shadcn/ui e ECharts (`BarChart` e
`HeatmapChart`, já registrados na rota lazy do analytics; nenhum tipo novo de gráfico).

**Storage**: PostgreSQL, com a migration `0017_publico` (3 tabelas novas e colunas aditivas numa tabela da
020); Redis para a prévia (a chave da 020, com mais campos); **nada no MinIO nem no HD**

**Testing**: pytest na stack efêmera (`npm run test:api`), ruff, `npm run check:web` e Playwright na stack
e2e efêmera (`e2e/publico.spec.ts`), com fixtures **sintéticas** (CSVs preenchidos e vazios, XLSX gerado
em memória)

**Target Platform**: SPA (desktop e celular, modo casa) + API no Docker

**Project Type**: web (apps/api + apps/web)

**Performance Goals**:
- prévia e confirmação em menos de 1 s para 366 dias de espectadores mais 366 × 24 horas de atividade;
- a aba Público e "Quando postar" em menos de 2 s com 10× o volume (SC-003 da 019).

**Constraints**:
- só um dono humano escreve;
- envio de até 5 MB e até 3 arquivos;
- ZIP e XLSX com até 20 entradas e até 20 MB expandidos, sem DOCTYPE no XML;
- as fotos da API ficam intocadas;
- o dia e a hora da atividade são gravados como vieram no arquivo;
- a CSP não muda;
- os arquivos reais do dono ficam fora do git.

**Scale/Scope**:
- 2 contas e poucas importações por conta; até 5 rótulos por foto;
- até ~8.800 linhas de atividade por importação de 1 ano (em geral, dezenas);
- 1 rota nova e campos aditivos em 4 schemas;
- 1 aba nova na SPA, e acréscimos na página "Histórico do Studio" e em "Quando postar".

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.* (constitution **4.2.0**)

| Princípio | Situação | Como |
|---|---|---|
| **I. Publicação só com decisão humana** | ✅ | Só lê arquivos enviados pelo dono. `metricas/studio/` continua sem importar `publicacao`, `httpx` ou cliente de rede (guarda da 020, ampliada para os módulos novos). A rota nova `analytics_publico` é só leitura e não tem "tiktok" no caminho nem no `operationId`. As escritas continuam nas 3 rotas H da 020 (`RequireHumanOwner`, com registro de recusa) |
| **II. Direito é responsabilidade do dono** | ✅ (não afetado) | Nada toca canal-fonte, envio para corte ou status de direito |
| III. Marca em tokens | ✅ (não afetado) | — |
| **IV. Contrato é a fonte única** | ✅ | Os schemas Pydantic mudam só por acréscimo (campos novos e `Literal` ampliado), a rota nova vai ao OpenAPI e depois `npm run gen:contract`. O MCP: a `analytics_publico` entra no `mapa.py` como tool de leitura (como as outras do analytics), e as 3 rotas de escrita da 020 seguem em `PROIBIDAS` |
| **V. Segurança e segredos** | ✅ | Nenhum segredo novo. O XLSX é aberto **em memória**, com os limites da 020 aplicados à planilha por dentro (entradas, tamanho expandido, razão, caminhos, links, cifrado) e um nível só de aninhamento. Antes do parser, todo XML com `<!DOCTYPE` ou `<!ENTITY` é recusado (proteção contra XXE e *billion laughs* sem defusedxml, R2). Macro, fórmula, link externo e planilha protegida são recusados. Só as partes necessárias são abertas. O `Content.csv` continua nunca aberto. A CSP não muda |
| **VI. Testes antes de pronto** | ✅ | Unitários (formato das seções novas, planilha, datas da atividade, data da foto), testes de XLSX malicioso, integração (prévia, confirmar, idempotência, desfazer, permissões, analytics, anonimização, exportação, migration), guardas e e2e. O princípio VII tem teste (desfazer volta ao estado anterior, observações intocadas) |
| **VII. Humano no controle** | ⚠️ justificado | Mesmo padrão da 020: a importação é versionada (`history.record`, com as colunas novas no snapshot e sem nome de arquivo), e desfazer é a reversão, sem DELETE. **Exceção (a mesma da 020 e da 016):** as fotos, a atividade e os espectadores são observações **só de inserção**, sem `version` própria, com trigger no banco. Não há desfazer por seção (FR-015). Ver Complexity Tracking |
| **VIII. Simplicidade** | ✅ | 0 dependência, 0 serviço, 0 trilha do agendador. São 3 tabelas e o pacote da 020 **só por acréscimo**: 2 módulos novos (`planilha.py` e `publico.py`) e funções novas nos existentes. A importação continua uma só (não há segunda entidade de importação). Uma rota de analytics nova, em vez de espalhar campos por várias |
| Restrições: NVMe × HD | ✅ | Poucos KB por importação, no PG (NVMe). Nenhum arquivo é gravado, então o HD e o marcador não entram |
| Restrições: Redis | ✅ | Só a prévia efêmera da 020 (TTL de 30 min, uso único). O registro fica no PG |
| Restrições: banco | ✅ | Migration Alembic `0017_publico` (`down_revision = "0016_importacao"`), com upgrade/downgrade e `test_migration_0017` |
| Restrições: gráficos do SPA | ✅ | Só ECharts (`BarChart` e `HeatmapChart`, já registrados), na rota lazy. Tooltips escapam o texto vindo de fora (rótulo de território, ADR 0002) |

**Reavaliação pós-design:** mantida. O design não criou serviço, dependência nem armazenamento de arquivo.
A única exceção (VII) é a mesma da 020 e da 016, e está justificada abaixo.

## Project Structure

### Documentation (this feature)

```text
specs/022-publico/
├── plan.md              # este arquivo
├── research.md          # R1–R14
├── data-model.md        # colunas novas, 3 tabelas, prévia, regras derivadas, migration 0017
├── quickstart.md        # roteiro de validação (sintético + manual com o dono)
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/src/sociman_api/metricas/studio/
├── formato.py        # + seções genero/territorios/atividade/espectadores, "undefined", ler_linhas (R1)
├── planilha.py       # NOVO: XLSX → linhas (stdlib), limites, recusas, célula "B4" (R2)
├── publico.py        # NOVO: % e rótulos, hora, leitura das seções novas, data da foto (R1, R4)
├── arquivos.py       # + envio 1–3, entradas novas, Viewers ZIP e XLSX solto, aninhado de 1 nível (R3)
├── datas.py          # + dias distintos da atividade, âncora do ano entre seções (R4)
├── models.py         # + colunas da Importacao; FotoDistribuicao, AtividadeStudio, EspectadoresStudio
├── efetivo.py        # + efetivos do público, foto válida, mapa, espectadores, cobertura (R7)
├── previa.py         # + seções de público na prévia, vazias, studio_sem_dados (R5, R8)
├── service.py        # + confirmar com as seções novas, cobertura ampliada (R8, R10)
├── schemas.py        # + SecaoPublicoPrevia, campos novos de Importacao e Cobertura
└── router.py         # sem rota nova (descrição do upload: 1 a 3 arquivos, .xlsx)
apps/api/src/sociman_api/
├── analytics/publico.py      # NOVO: aba Público (R9; importa metricas.studio.efetivo, só leitura)
├── analytics/quando_postar.py, schemas.py, router.py   # + atividadeSeguidores; rota analytics_publico
├── metricas/export.py, dicionario.py                   # + 3 CSVs, DICIONARIO_VERSAO = 3 (R10)
├── metricas/anonimizar.py                              # sem mudança de código; teste novo (R11)
└── mcp/mapa.py                                         # + analytics_publico (tool leitura)
apps/api/migrations/versions/0017_publico.py
apps/api/tests/
├── unit/test_studio_publico.py, test_studio_planilha.py, test_studio_datas.py (+022),
│   test_constitution_guards.py (+022), test_mcp_mapa.py (sem mudança: só passa a cobrir a rota nova)
└── integration/studio_helpers.py (+ gerador de público e XLSX), test_studio_publico_previa.py,
    test_studio_publico_importacao.py, test_studio_publico_efetivo.py, test_analytics_publico.py,
    test_studio_publico_export.py, test_studio_publico_anonimizar.py, test_migration_0017.py

apps/web/src/
├── lib/analytics.ts                       # + aba "publico" depois de "quando-postar"; hook usePublico
├── pages/analytics/Analytics.tsx          # + aba Público
├── pages/analytics/abas/Publico.tsx       # NOVO: 4 cards
├── pages/analytics/abas/QuandoPostar.tsx  # + 3º mapa
├── components/analytics/Distribuicao.tsx  # NOVO: barras horizontais com p.p. e tabela alternativa
├── components/studio/PreviaStudio.tsx, CoberturaBarras.tsx, EnvioArquivos.tsx   # + seções de público
└── lib/studio.ts                          # tipos gerados novos
e2e/publico.spec.ts
.gitignore                                 # + Viewers.xlsx, FollowerGender.csv, FollowerTopTerritories.csv, FollowerActivity.csv
```

**Structure Decision**: é o web app existente. O código de leitura e de gravação fica em
`metricas/studio/`, porque são seções do mesmo arquivo e da mesma importação da 020. A leitura derivada
(efetivos, foto válida, mapa) fica em `metricas/studio/efetivo.py`, e a apresentação em
`analytics/publico.py`. A regra da 020 continua: o `analytics/` importa o `studio.efetivo`, nunca o
contrário. A aba nova fica na rota lazy do analytics (ECharts); a página de importação continua fora dela.

## Complexity Tracking

| Violação | Por que é necessária | Alternativa mais simples rejeitada porque |
|---|---|---|
| Observações de público sem `version` nem histórico por linha (princípio VII) | São dados de um arquivo externo, imutáveis e numerosos (até 24 linhas por dia na atividade). O histórico fica na importação que os agrupa, como nos dias da 020 e nas fotos da 016 | Versionar cada linha: milhares de versões sem valor de auditoria, e o desfazer viraria N reversões |
| Sem desfazer por seção | A importação é uma decisão só do dono (um envio, uma confirmação); desfazer por seção criaria estados parciais na mesma importação | Estado por seção: mais colunas, mais conflitos de precedência e mais telas, para um caso que se resolve desfazendo e importando de novo |
| Leitor de XLSX próprio (stdlib) em vez de biblioteca | O princípio VIII proíbe dependência nova sem necessidade, e a planilha real tem 1 aba e 32 células de texto. O leitor cobre só o subconjunto do Studio e recusa o resto | openpyxl/defusedxml: dependência nova, com superfície bem maior que a necessária, para ler 8 linhas |
