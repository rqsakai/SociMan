# Implementation Plan: Histórico do TikTok Studio

**Branch**: `020-historico-tiktok-studio` | **Date**: 2026-10-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/020-historico-tiktok-studio/spec.md`

## Summary

O dono envia, na tela nova "Histórico do Studio" da conta TikTok, os ZIPs da **Visão geral** e de
**Seguidores** exportados do TikTok Studio (ou os CSVs soltos). A API:
- lê os arquivos **em memória** (CSV da biblioteca padrão, ZIP com limites contra *bomb* e *slip*, nunca
  extraído nem guardado);
- reconhece a seção pelo cabeçalho (inglês confirmado, pt-BR provisório);
- deduz o ano das datas pelo nome do ZIP e confere o @ do nome do ZIP com a conta;
- guarda uma **pré-visualização efêmera no Redis** (30 min, de uso único).

Ao confirmar, a API grava uma **importação versionada** e os **dias só de inserção** em duas tabelas
novas (migration `0013`), sem tocar nas fotos da API. O analytics da 019 passa a somar **por dia**: nos dias
que a coleta não cobre inteiros (os anteriores à 1ª coleta e o próprio dia dela), usa o Studio. Cada card
diz a fonte. Desfazer marca a importação, com histórico. A anonimização e a exportação da 016 cobrem os
dados importados. Nada é publicado, e não há dependência nova.

## Technical Context

**Language/Version**: Python 3.12 (API, uv) · TypeScript 5 / React 19 (SPA, Vite 8)

**Primary Dependencies**: FastAPI, SQLAlchemy 2, Pydantic 2, python-multipart, redis-py. Leitura com
`csv`, `zipfile` e `hashlib` da biblioteca padrão. **Nenhuma dependência nova** (sem openpyxl e sem
pandas). Na SPA: TanStack Query, shadcn/ui e ECharts (já existente, só na rota lazy do analytics).

**Storage**: PostgreSQL (2 tabelas novas, migration `0013_historico_studio`); Redis para a
pré-visualização (TTL); **nada no MinIO nem no HD**

**Testing**: pytest na stack efêmera (`npm run test:api`), ruff, `npm run check:web`, Playwright na stack
e2e efêmera (`e2e/studio.spec.ts`), com fixtures **sintéticas** geradas em memória

**Target Platform**: SPA (desktop e celular, modo casa) + API no Docker

**Project Type**: web (apps/api + apps/web)

**Performance Goals**: pré-visualização e confirmação < 1 s para 366 dias; as abas do analytics continuam
< 2 s com 10× o volume (SC-003 da 019), agora somando por dia

**Constraints**: só dono humano escreve; envio ≤ 5 MB; ZIP ≤ 20 entradas e ≤ 20 MB expandido; fotos
da API intocadas; fuso America/Sao_Paulo; CSP inalterada; arquivos reais do dono fora do git

**Scale/Scope**: 2 contas, de 7 a 366 dias por importação, poucas importações por conta; 5 rotas novas;
1 página nova; campos aditivos em 4 schemas da 019

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.* (constitution **4.1.0**)

| Princípio | Situação | Como |
|---|---|---|
| **I. Publicação só com decisão humana** | ✅ | Só lê arquivos enviados pelo dono. `metricas/studio/` não importa `publicacao`, `httpx` nem nenhum cliente de rede (guarda em `test_constitution_guards.py`). Não há "tiktok" em rotas nem em `operationId` (`studio_*`). Escrever (prévia, confirmar, desfazer) é `RequireHumanOwner`, com registro de recusa |
| **II. Direito é responsabilidade do dono** | ✅ (não afetado) | Nenhum envio para corte, canal ou status de direito é tocado |
| III. Marca em tokens | ✅ (não afetado) | — |
| **IV. Contrato é a fonte única** | ✅ | Rotas e schemas Pydantic → `npm run gen:contract`; os campos novos da 019 são aditivos; nada editado à mão em `packages/contract` |
| **V. Segurança e segredos** | ✅ | Nenhum segredo novo. A leitura do ZIP é em memória, com limites (R2): sem *zip bomb*, *zip slip*, link nem aninhado, e sem `extract`. O `Content.csv` (títulos e links) nunca é aberto. Arquivos e nomes não são guardados, exceto os nomes até a anonimização (fora do histórico). A CSP não muda. A página nova não usa script inline. Os arquivos reais ficam fora do git (`.gitignore` e fixtures sintéticas) |
| **VI. Testes antes de pronto** | ✅ | Unitários (formato, datas, ZIP), integração (prévia, importação, permissões, analytics, anonimização, exportação, migration), guardas e e2e. As regras inegociáveis I e VII têm teste no backend (SC-004, SC-007) |
| **VII. Humano no controle** | ⚠️ justificado | A importação tem `version` e `history.record` (created/updated). Desfazer é a reversão, sem DELETE (os dias ficam, e a importação vira `desfeita`). **Exceções:** (a) os dias importados são observações só de inserção, sem `version` própria, como as fotos da 016 (trigger no banco); (b) não há revert genérico nem "refazer": reverter o desfazer é reimportar (mesmo padrão da exceção aprovada de envio e corte na 006). Ver Complexity Tracking |
| **VIII. Simplicidade** | ✅ | 0 dependência, 0 serviço, 0 trilha nova do agendador, 2 tabelas. A prévia usa o Redis que já existe. O XLSX foi descartado depois do arquivo real (Clarifications, ajustes). Uma só soma por dia na 019 em vez de dois caminhos de cálculo |
| Restrições: armazenamento NVMe × HD | ✅ | Nada pesado: menos de 1 KB por semana de dados, no PG (NVMe). Nenhum arquivo é gravado, então o HD e o marcador não entram |
| Restrições: Redis | ✅ | Só estado efêmero (a prévia, com TTL de 30 min e uso único), no mesmo padrão do `state` OAuth da 015. Nada que precise sobreviver: o registro da importação fica no PG |
| Restrições: banco | ✅ | Migration Alembic `0013_historico_studio`, com upgrade/downgrade e `test_migration_0013` |

**Reavaliação pós-design:** mantida. O design não criou serviço, dependência nem armazenamento de arquivo.
A única exceção (VII) é a mesma da 016 e da 006, e está justificada abaixo.

## Project Structure

### Documentation (this feature)

```text
specs/020-historico-tiktok-studio/
├── plan.md              # este arquivo
├── research.md          # R1–R15
├── data-model.md        # 2 tabelas, prévia no Redis, regras derivadas, migration 0013
├── quickstart.md        # roteiro de validação (sintético + manual com o dono)
├── contracts/http-api.md
├── notas-pesquisa.md    # formato confirmado e fontes
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks (não criado aqui)
```

### Source Code (repository root)

```text
apps/api/src/sociman_api/metricas/studio/
├── __init__.py
├── formato.py        # SINONIMOS (en + pt-BR provisório), seções, leitura do CSV e dos números (R1)
├── arquivos.py       # envio → CSVs: assinatura, limites, ZIP em memória, nomes ignorados (R2)
├── datas.py          # meses en/pt, nome do ZIP (início, epoch, handle), ano e dedução, hoje (R3)
├── models.py         # Importacao (versionada), DiaStudio (só inserção)
├── efetivo.py        # primeiro_dia_coberto, dias efetivos, cobertura (R6; só leitura)
├── previa.py         # montar a prévia, contagens, avisos, Redis (GETDEL), base (R4)
├── service.py        # confirmar (lock por série, tudo ou nada, idempotência), desfazer, history (R5, R8)
├── schemas.py        # Previa, Importacao, Cobertura
└── router.py         # /api/contas/{id}/studio/*, /api/studio/importacoes/{id}/desfazer
apps/api/src/sociman_api/
├── metricas/anonimizar.py   # + nomes_arquivos = NULL (R9)
├── metricas/export.py, dicionario.py   # + studio_dias.csv, versão 2 (R10)
├── analytics/base.py        # ganhos_por_dia com 4 contadores; totais_diarios (R7)
├── analytics/visao_geral.py, contas.py, quando_postar.py (calendário), schemas.py   # fontes e campos aditivos
└── main.py                  # include_router do studio
apps/api/migrations/versions/0013_historico_studio.py
apps/api/tests/
├── unit/test_studio_formato.py, test_studio_datas.py, test_studio_zip.py, test_constitution_guards.py (+020)
└── integration/studio_helpers.py (gerador sintético, também CLI para o quickstart),
    test_studio_previa.py, test_studio_importacao.py, test_studio_permissoes.py,
    test_studio_analytics.py, test_studio_anonimizar.py, test_studio_export.py, test_migration_0013.py

apps/web/src/
├── pages/perfis/ContaStudio.tsx          # cobertura, importar/prévia/confirmar (dono), lista e desfazer
├── components/studio/                    # EnvioArquivos, PreviaStudio, CoberturaBarras, ListaImportacoes
├── lib/studio.ts                         # hooks TanStack Query (cliente gerado)
├── App.tsx                               # rota /app/contas/:id/studio
├── pages/perfis/ContasTab.tsx            # link "Histórico do Studio" no cartão TikTok
└── pages/analytics/abas/VisaoGeral.tsx, QuandoPostar.tsx, Contas.tsx   # fonte na série, calendário, indicadores, link
e2e/studio.spec.ts
.gitignore                                # Overview_*.zip, Followers_*.zip, Content_*.zip, Viewers_*.zip
```

**Structure Decision**: o web app existente (apps/api + apps/web). O código fica em `metricas/studio/`
porque é uma fonte de métricas da série da 016, e reaproveita a série, a função do trigger, a
anonimização e a exportação. A 019 (`analytics/`) **importa** `metricas.studio.efetivo` (só leitura), nunca
o contrário. A página de importação fica fora da rota lazy do analytics, porque escreve e não precisa do
ECharts.

## Complexity Tracking

| Violação | Por que é necessária | Alternativa mais simples rejeitada porque |
|---|---|---|
| Dias importados sem `version` ou histórico por linha (princípio VII) | São observações de um arquivo externo, imutáveis e numerosas; o histórico fica na importação que as agrupa (mesmo padrão das fotos da 016) | Versionar cada dia: centenas de versões sem valor de auditoria, e o desfazer viraria N reversões |
| Sem revert genérico nem "refazer" da importação | Desfazer **é** a reversão; reativar uma desfeita criaria mais um estado e mais conflitos | "Refazer": o mesmo efeito que reimportar o arquivo, com mais código e casos |
| Mudança de base no cálculo da 019 (soma por dia em vez do delta do período) | É o único jeito de trocar só os dias sem cobertura pelo Studio, com um só caminho de cálculo; o resultado sem Studio é idêntico (teste de regressão) | Subtrair os dias do Studio do delta do período: dois caminhos de cálculo e erro de borda no dia da 1ª coleta |
