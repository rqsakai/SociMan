# Implementation Plan: Aprender com o desempenho

**Branch**: `023-aprendizado` | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/023-aprendizado/spec.md`

## Summary

Um pacote novo, `aprendizado/`, liga as métricas da 016 e da 019 ao que o dono decide postar:

- **Temas:** cada perfil tem uma taxonomia de temas, só o dono edita, com histórico. A IA (008) propõe a
  lista inicial, que só vale ao salvar.
- **Classificação:** a IA classifica cada post num tema e num estilo de gancho. A classificação roda numa
  **trilha nova do agendador** (`aprendizado`), com limite diário por perfil. A correção do dono nunca é
  sobrescrita.
- **Análise:** a estatística é **calculada na leitura**, sem tabela agregada:
  - medida da 019 em log(views + 1), relativa à conta;
  - duas partes: entrega e rendimento;
  - encolhimento com 5 pseudo-posts e intervalo por reamostragem com semente fixa;
  - concentração, separabilidade hashtag × tema, blocos de hashtags e "distribuição travada";
  - esquecimento com meia-vida de 30 dias (R1–R4).
- **Recomendações:** são calculadas na leitura por regras fixas. Só as **decisões** do dono (aceitar,
  rejeitar) e as recomendações nascidas de hipótese são gravadas. Aceitar grava as **preferências**
  versionadas do perfil ou da conta, e "fixar hashtag" grava no **guia da 017** (R6, R7).
- **Análise da IA dos melhores:** é um **pedido assíncrono** que a mesma trilha executa:
  - com quadros opcionais extraídos pelo `extract_frame` (ffmpeg) que já existe em `cortes/compose.py`;
  - os quadros vão para o HD, com marcador e piso de espaço;
  - o custo estimado é mostrado antes de confirmar (R3, R5).
- **Fechar o ciclo:**
  - o Descobrir (006) e as oportunidades do Mercado (019) ganham, **com perfil escolhido**, uma afinidade
    calculada em SQL na leitura (palavras-chave sem acento, até ±20 pontos);
  - os temas cortados ficam escondidos por padrão, com contador e filtro (R9);
  - o assistente (008/017) passa ao prompt `ia/3`, com o bloco `<desempenho>` entre `<guia_conta>` e
    `<perfil>`, versões e exemplos gravados na chamada, e as hashtags "evitar" retiradas pelo servidor (R8).
- **Diagnóstico de distribuição:** sinais calculados na leitura, mais as conferências do dono, gravadas com
  histórico (R10).
- **Migration:** `0018_aprendizado`, com 6 tabelas e 3 colunas em `ia_chamadas`.

Nada publica. Não há dependência nova nem serviço novo.

## Technical Context

**Language/Version**: Python 3.12 (API, uv) · TypeScript 5 / React 19 (SPA, Vite 8)

**Primary Dependencies**:
- API: FastAPI, SQLAlchemy 2, Pydantic 2, SDK `anthropic` (já usado pela 008), `statistics`, `random` e
  `math` da biblioteca padrão (sem numpy nem scipy).
- Quadros: `ffmpeg`, que já está na imagem da API, via `cortes.compose.extract_frame`, e Pillow, que já
  existe, para reduzir a 512 px.
- SPA: TanStack Query, TanStack Table v9, shadcn/ui e ECharts (já existente, só em rota lazy).

**Nenhuma dependência nova.**

**Storage**:
- PostgreSQL: 6 tabelas novas e 3 colunas em `ia_chamadas`, na migration `0018_aprendizado`
  (`down_revision = "0017_publico"`).
- Os quadros são temporários, em `${SOCIMAN_DATA_DIR}/work/tmp/aprendizado/<analise>/` (HD, com
  `.sociman-volume` e piso de espaço), e são apagados no fim da análise. Nada vai para o MinIO.

**Testing**:
- pytest na stack efêmera (`npm run test:api`), mais ruff e `npm run check:web`;
- Playwright na stack e2e (`e2e/aprendizado.spec.ts`);
- o Claude falso (`tests/fakes/anthropic_fake.py` e `openshorts-fake` `/v1/messages`) ganha os 3 schemas
  novos.

**Target Platform**: SPA (desktop e celular, modo casa), API e agendador no Docker

**Project Type**: web (apps/api + apps/web)

**Performance Goals**:
- análise e recomendações < 2 s com 10× o volume da 019;
- Descobrir com afinidade: no máximo +300 ms, com 50 mil vídeos-fonte e 30 temas × 20 palavras;
- classificação: 1 chamada por post, ≤ 50 por perfil por dia.

**Constraints**:
- só o dono humano escreve (`RequireHumanOwner`);
- GETs não gravam nada;
- a afinidade não toca no direito (princípio II);
- fixas e proibidas da 017 valem;
- fuso America/Sao_Paulo;
- CSP inalterada;
- o custo de IA nunca chega a membro (o servidor manda `null`).

**Scale/Scope**:
- hoje: 2 contas, cerca de 40 posts e 42 mil vídeos-fonte;
- 30 temas por perfil no máximo;
- cerca de 25 rotas novas;
- 1 página lazy com 5 abas;
- campos aditivos no Descobrir, no Mercado e no registro da IA.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.* (constitution **4.2.0**)

| Princípio | Situação | Como |
|---|---|---|
| **I. Publicação só com decisão humana** | ✅ | `aprendizado/` não importa `publicacao`, `httpx` nem serviços que mudam destino ou agenda (guarda R13). Nenhuma rota agenda, aprova ou publica. A "janela de horário" aceita é só uma dica de leitura no agendamento. Não há "tiktok" nem "youtube" em rotas nem em `operationId` (`aprendizado_*`) |
| **II. Direito é responsabilidade do dono** | ✅ | A afinidade só mexe na **ordem** e no filtro de temas cortados. `canais_fonte.direito` e o `aviso_direito` do `enviar` (006) ficam intocados, com teste (SC-008). O status de direito continua visível no Descobrir e nas oportunidades |
| III. Marca em tokens | ✅ (não afetado) | — |
| **IV. Contrato é a fonte única** | ✅ | Schemas Pydantic → `npm run gen:contract`. Os campos novos de `VideoFonte`, `MercadoOut` e `IaChamada` são aditivos. As tools do MCP saem do mapa (`mcp/mapa.py`) |
| **V. Segurança e segredos** | ✅ | Nenhum segredo novo; a chave da Anthropic continua só em api e agendador. Os quadros ficam só no HD temporário, nunca no git nem no MinIO. Os textos vindos da rede (legenda, transcrição) entram no prompt dentro de tags e não como instrução, e a saída da IA é validada por schema (R5). Tooltips com `encodeHTML` (ADR 0002). A CSP não muda |
| **VI. Testes antes de pronto** | ✅ | Unitários da estatística com casos de referência (SC-003/SC-004), integração por rota, permissões (SC-006), a trilha, a migration, as guardas, desempenho e e2e das 4 histórias principais. Os princípios I, II e VII têm teste no backend |
| **VII. Humano no controle** | ⚠️ justificado | Temas, classificações, preferências, decisões de recomendação e conferências têm `version`, `history.record` e reversão pelo dono. A IA grava como `system:aprendizado`, nunca como humano. **Exceções:** (a) a análise da IA é um registro imutável, criado com `history` e sem edição nem revert (como as chamadas da 008); (b) as recomendações por regra não são gravadas até a decisão, porque são cálculo de leitura, como os insights da 019. Ver Complexity Tracking |
| **VIII. Simplicidade** | ⚠️ justificado | 0 dependência e 0 serviço. **1 trilha nova** do agendador (`aprendizado`), exigida pela Clarification 3 (classificação automática com limite) e pela análise assíncrona com quadros. Não há tabela de cache: a afinidade e a estatística são calculadas na leitura, com plano B documentado (R2, R9) |
| Restrições: armazenamento NVMe × HD | ✅ | Os quadros (pesados e temporários) vão para o HD, com `datadir.ensure_writable()` (marcador e piso de espaço). Se o HD estiver fora, a análise com quadros falha com `hd_indisponivel` e a sem quadros continua. As tabelas são pequenas e ficam no PG (NVMe) |
| Restrições: Redis | ✅ (não usado) | — |
| Restrições: banco | ✅ | Migration Alembic `0018_aprendizado` com upgrade e downgrade, e `test_migration_0018` |
| Restrições: gráficos | ✅ | ECharts só na rota lazy da área de Aprendizado, com os charts já registrados pela 019 (Bar, Scatter, Heatmap). Nenhum chart novo é registrado (R12) |

**Reavaliação pós-design:** mantida. O design não criou serviço nem dependência. As duas exceções (trilha
nova e registros imutáveis) estão abaixo.

## Project Structure

### Documentation (this feature)

```text
specs/023-aprendizado/
├── plan.md              # este arquivo
├── research.md          # R1–R15
├── data-model.md        # 6 tabelas, colunas em ia_chamadas, entidades calculadas, migration 0018
├── quickstart.md        # roteiro de validação
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/src/sociman_api/aprendizado/
├── __init__.py
├── models.py          # Tema, Classificacao, Preferencias, Analise, Decisao, Conferencia
├── constantes.py      # MIN_*, K_ENCOLHIMENTO, MEIA_VIDA_DIAS, JANELA_DIAS, limites das regras, pesos, LIMITE_DIARIO
├── estatistica.py     # funções puras: log1p, pesos, encolhimento, reamostragem, confiança (R1)
├── fatores.py         # extrai os fatores de PostAnalisado + Classificacao (R1)
├── analise.py         # efeitos por fator, 2 partes, concentração, separabilidade, blocos, travada, alta/queda (R1–R4)
├── recomendacoes.py   # regras → Recomendacao calculada; filtro das decididas; chave estável (R6)
├── preferencias.py    # leitura efetiva (perfil + conta), aceitar, rejeitar, reverter; fixar → guia (R7)
├── temas.py           # CRUD, juntar, arquivar, revert, versão da taxonomia (R2)
├── classificacao.py   # pendentes, montar entrada, gravar (ia ou dono), corrigir, revert (R3)
├── analise_ia.py      # estimativa, pedido, execução (quadros + chamada), hipóteses (R5)
├── quadros.py         # baixa o vídeo do MinIO para o HD tmp, extract_frame × 4, reduz a 512 px, limpa (R5)
├── afinidade.py       # a_tema / a_canal; expressão SQL para o Descobrir e o Mercado (R9)
├── desempenho.py      # bloco <desempenho> para a ia/3: preferências + até 3 exemplos (R8)
├── diagnostico.py     # sinais por conta e por post, checklist fixo (R10)
├── conferencias.py    # marcações do dono, com histórico (R10)
├── trilha.py          # rodar(db): 1 análise pendente; depois a classificação até o limite (R4)
├── schemas.py
└── router.py          # /api/perfis/{id}/aprendizado/*, /api/aprendizado/* (operationId aprendizado_*)
apps/api/src/sociman_api/ (acréscimos)
├── agendador.py                 # Trilha("aprendizado", s.agendador_aprendizado_s, trilha.rodar, _sem_ia)
├── config.py                    # agendador_aprendizado_s (300)
├── ia/tipos.py                  # aprendizado.taxonomia | .classificacao | .analise
├── ia/regras_padrao.py          # regras padrão dos 3 tipos
├── ia/prompt.py                 # PROMPT_VERSION = "ia/3"; bloco <desempenho>
├── ia/cliente.py                # user como texto ou blocos (texto + image/jpeg base64)
├── ia/saida.py                  # _sem_evitadas depois de _com_fixas; schemas das 3 saídas novas
├── ia/service.py, ia/models.py, ia/schemas.py   # desempenho_*_version, desempenho_exemplos
├── canais/service_videos.py, canais/schemas.py  # score exibido + afinidade; mostrarCortados; ocultosPorTema
├── analytics/mercado.py, analytics/schemas.py   # afinidade e ocultos nas oportunidades (só leitura)
├── metricas/anonimizar.py       # limpa textos da 023 (R11)
├── mcp/mapa.py                  # leituras como tool `leitura`; escritas em PROIBIDAS (R13)
└── main.py                      # include_router
apps/api/migrations/versions/0018_aprendizado.py
apps/api/tests/
├── unit/test_aprendizado_estatistica.py, test_aprendizado_analise.py, test_aprendizado_recomendacoes.py,
│   test_aprendizado_desempenho.py, test_ia_prompt.py (+ia/3),
│   test_constitution_guards.py (+023), test_mcp_mapa.py (+023)
├── fakes/anthropic_fake.py      # schemas taxonomia, classificacao, analise (com e sem imagem)
└── integration/aprendizado_helpers.py, test_aprendizado_temas.py, test_aprendizado_classificacao.py,
    test_aprendizado_trilha.py, test_aprendizado_analise_api.py, test_aprendizado_analise_ia.py,
    test_aprendizado_recomendacoes_api.py, test_aprendizado_preferencias.py, test_aprendizado_descobrir.py,
    test_aprendizado_gerador.py, test_aprendizado_diagnostico.py, test_aprendizado_permissoes.py,
    test_aprendizado_anonimizar.py, test_aprendizado_custo.py, test_aprendizado_afinidade_norm.py (PG),
    test_aprendizado_desempenho_perf.py, test_migration_0018.py

apps/web/src/
├── pages/aprendizado/Aprendizado.tsx      # rota lazy /app/perfis/:id/aprendizado (abas na URL)
├── pages/aprendizado/abas/                # Analise, Temas, Recomendacoes, Diagnostico, AnalisesIa
├── components/aprendizado/                # EfeitoLinha, GraficoEfeitos, MatrizHashtagTema, CartaoRecomendacao,
│                                          # ClassificacaoEditor, PedidoAnalise (estimativa), SinaisDistribuicao
├── lib/aprendizado.ts                     # hooks TanStack Query (cliente gerado)
├── App.tsx                                # rota lazy
├── pages/descobrir/*                      # selo "tema cortado", contador e filtro "mostrar temas cortados", motivo
├── pages/analytics/abas/OQueFunciona.tsx, Mercado.tsx   # atalho para Aprendizado; ocultos nas oportunidades
├── pages/ia/*                             # registro: versões do desempenho e exemplos; finalidades no resumo
├── pages/conteudos/* (agendamento)        # dica "janela preferida" (só leitura)
└── pages/perfis/tabs/GuiaTab.tsx          # origem "recomendação 023" no histórico das fixas
e2e/aprendizado.spec.ts, e2e/fakes/server.py (Claude falso: 3 schemas)
```

**Structure Decision**: o web app existente (apps/api + apps/web). O pacote `aprendizado/`:
- **lê** `analytics.base` (posts, medida, estagnação), `analytics.alertas` (referências da estagnação) e
  `metricas` (vídeos e vínculo), sem duplicar esses cálculos;
- **escreve** só nas próprias tabelas, no guia (por `ia.service_guia`, ao fixar) e em `ia_chamadas` (pelo
  `ia.service`).

`analytics/` e `canais/` importam só as funções de leitura `aprendizado.afinidade` e
`aprendizado.preferencias.efetivas`. A página fica numa rota lazy própria, porque usa o ECharts.

## Complexity Tracking

| Violação | Por que é necessária | Alternativa mais simples rejeitada porque |
|---|---|---|
| Trilha nova `aprendizado` no agendador (princípio VIII; guarda `test_agendador_sem_trilha_nova`) | Clarification 3: a classificação dos posts novos é automática, com limite diário. A análise com quadros leva de 30 s a 2 min (download do vídeo, ffmpeg, chamada com imagens), passa do timeout de uma requisição e precisa do HD montado, que o agendador já tem | Classificar na trilha `metricas`: mistura leitura da rede com IA paga, e um erro da IA atrasaria a coleta. Rodar a análise na requisição: 504 do edge e o worker HTTP fica preso. O `worker` de cortes: é fila de vídeo com SKIP LOCKED por corte, e misturar IA nele confunde as tentativas e a prioridade |
| Análise da IA sem edição nem revert (princípio VII) | É o registro do que a IA disse num momento, como `ia_chamadas`. Editar falsificaria a evidência. A ação humana sobre ela (transformar uma hipótese em recomendação e decidir) tem histórico | Versionar a análise: não há mutação humana para versionar |
| Recomendações por regra não são gravadas antes da decisão (princípio VII) | São cálculo de leitura, como os insights da 019. Gravar em GET violaria "GET não escreve", e uma tarefa periódica só para isso seria mais uma peça | Gravar todas numa trilha: tabela crescendo com recomendações que ninguém decidiu, e "superada" vira estado a manter |
| Expressão SQL de afinidade com `translate()` paralela ao `normalizar()` em Python | Ordenar e paginar o Descobrir por cursor exige o score no SQL. Uma tabela de casamento por perfil precisaria de recálculo a cada taxonomia nova e a cada sync | Tabela `aprendizado_fonte_temas` (plano B do R9, só se o teste de desempenho passar de +300 ms). O teste de paridade garante o mesmo resultado nos dois lados |
| Tabela `aprendizado_fonte_temas` (migration `0019_aprendizado_fonte_temas`, plano B do R9, aplicada em 2026-10-06) | O casamento na leitura custava de 1,3 a 5,5 s sobre 42 mil vídeos-fonte (medido no dev), muito acima de +300 ms (R14) | O casamento na leitura (a expressão acima) não cabe na meta. A tabela é um cache derivado e reconstruível, sem `history`, refeito pela trilha a cada versão de taxonomia e incremental a cada sync. Sem casamento em dia, a afinidade fica neutra |
