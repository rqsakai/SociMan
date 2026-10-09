# Implementation Plan: Revisão de UX tela a tela

**Branch**: `024-revisao-ux` (trabalho em `004-kit-de-marca-poc`; ver Riscos) | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/024-revisao-ux/spec.md`

## Summary

A queixa central do dono (espaço irregular, blocos encostados, vazios, larguras soltas) vem de uma causa só: o
espaço entre blocos mora dentro do `HeaderCard` (`mt-6` mais a faixa `relative -top-6 -mb-2`). A margem colapsa nas 25
páginas com `space-y-*`. A 024 move esse espaço para um contêiner de página único (`Page`, `gap-6`), refaz a
estrutura do `HeaderCard` sem mudar o visual, põe a faixa na cor da marca nos dois temas e limita o conteúdo a
1440 px no `AppShell`. Sobre essa base:
- o menu vira grupos colapsáveis;
- o perfil perde a aba Cortes (o upload e o estado do HD vão para Conteúdos);
- o Aprendizado vira página de Analytics;
- todas as listas com filtro usam uma `FilterBar` única;
- Conteúdos ganha paginação numerada;
- Gerações ganha contagens por estado de clipe;
- Descobrir explica a pontuação com os temas;
- Propostas e os outros vazios ganham um `EmptyState` padrão;
- datas e arquivos passam a usar campos próprios em pt-BR.

A API só ganha campos e parâmetros opcionais (4 operações). Não há migration nem operação nova no MCP.

## Technical Context

**Language/Version**: TypeScript 5 (React 19, Vite) no `apps/web`; Python 3.12 (FastAPI, uv) no `apps/api`

**Primary Dependencies**: Tailwind 4, shadcn/ui (Radix: Collapsible, Sheet, Tabs, Dialog já instalados), TanStack
Query, TanStack Table v9; SQLAlchemy 2. **Nenhuma dependência nova.**

**Storage**: PostgreSQL (só leitura nova: agregados e uma consulta por chave); `localStorage` para o menu e o último
perfil do Aprendizado

**Testing**: pytest (stack efêmera), Playwright e2e (stack efêmera, com o novo `layout-ritmo.spec.ts`),
`check:web`; capturas do Playwright MCP e o impeccable (critique e finish-reviewer)

**Target Platform**: SPA no navegador (desktop 1280–1920 px e celular 390 px, PWA instalado no modo casa)

**Project Type**: web application (SPA + API)

**Performance Goals**: Descobrir dentro do orçamento do `test_aprendizado_desempenho_perf.py` com a consulta extra de
temas; Conteúdos paginado com `count` igual ao de hoje

**Constraints**: CSP de produção com `script-src 'self'` (nada inline); API só aditiva; e2e e PWA verdes; o dono usa o
dev ao vivo (rotas novas só junto com o código delas)

**Scale/Scope**: cerca de 66 páginas (raiz), 40 HeaderCards, cerca de 20 telas com filtro, 18+2 campos de data, 10 de arquivo,
cerca de 15 testes e2e para ajustar

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Nota |
|---|---|---|
| I. Publicação só com decisão humana | ✅ | Nenhuma mudança em publicação, agendamento ou aprovação. A tabela de cortes do perfil, que tinha "Agendar / Publicar", sai, e esse caminho continua em Conteúdos com as mesmas regras. |
| II. Direito é responsabilidade do dono | ✅ | Aviso de direito e histórico de envio intactos. O `AplicarMarcaDialog` usa a mesma rota `cortes_upload`. |
| III. Marca em tokens | ✅ | Não toca o kit de marca. Os tokens de UI (`--band*`) são do SPA, não da marca das contas. |
| IV. Contrato é a fonte única | ✅ | Campos e parâmetros novos só pelo FastAPI → `gen:contract` (`openapi.json`, `mcp-tools.json`, `schema.d.ts`). |
| V. Segurança e segredos | ✅ | Sem script inline e sem origem nova. O `showPicker()` e a máscara de data são JS do bundle. A CSP não muda (`check:csp`). |
| VI. Testes antes de pronto | ✅ | Testes de contrato da API, e2e ajustados, mais o `layout-ritmo.spec.ts`. A suíte completa roda no fim, com o código congelado. |
| VII. Humano no controle | ✅ | Nenhuma mutação nova. Escritas existentes (upload, arquivar) seguem com histórico. Filtros e estado do menu não são dados de domínio. |
| VIII. Simplicidade | ✅ com justificativa | Componentes novos (`Page`, `FilterBar`, `ServerPagination`, `EmptyState`, `DateField`, `FileField`) substituem padrões duplicados; nenhuma dependência nova (Popover e Calendar do shadcn evitados). Ver Complexity Tracking. |

**Re-check pós-design:** ✅ Os mesmos resultados. Nenhum operationId novo, então o `test_mcp_mapa.py` não muda.
A guarda de import de `canais/` (`aprendizado.afinidade` apenas) é respeitada pondo `temas_por_video` em `afinidade.py`.

## Project Structure

### Documentation (this feature)

```text
specs/024-revisao-ux/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/api-024.md, contracts/ui-024.md
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/src/sociman_api/
├── envios/schemas.py, service_envios.py        # CortesResumo em envios_out (GROUP BY envio_id)
├── canais/schemas.py, service_videos.py        # temas casados + afinidadeEstado
├── aprendizado/afinidade.py                    # TemaAfinidade.acao, temas_por_video()
├── conteudos/router.py, service.py             # offset
└── anotacoes/router.py, service.py             # q
apps/api/tests/integration/test_024_*.py        # contrato (envios, descobrir, conteúdos, anotações)

apps/web/src/
├── components/shell/{nav.ts,Sidebar.tsx,AppShell.tsx,HeaderCard.tsx,Page.tsx,EmptyState.tsx,tone.ts}
├── components/ui/{card.tsx,tabs.tsx,date-field.tsx,file-field.tsx}
├── components/data-table/{DataTable.tsx,FilterBar.tsx,ServerPagination.tsx}
├── components/conteudos/{AtalhosConteudos.tsx,FiltrosConteudos.tsx,AplicarMarcaDialog.tsx}
├── components/canais/ScoreReason.tsx, components/envios/EnvioStatus.tsx
├── lib/{filtros.ts,conteudos.ts,aprendizado.ts,envios.ts}
├── index.css                                   # --band*, tone-dark escuro, scrollbar-gutter
├── App.tsx                                     # /app/aprendizado + redirects
└── pages/**                                    # raiz <Page>, FilterBar, tons, max-w removidos
e2e/{helpers.ts,layout.spec.ts,layout-ritmo.spec.ts, + specs da tabela do ui-024.md}
```

**Structure Decision**: o monorepo atual (apps/web + apps/api + e2e). Nada de pacote novo.

## Ordem de entrega (fatias, cada uma verde antes da próxima)

1. **Base de layout (US2):** `Page`, `AppShell` com 1440 px, `scrollbar-gutter`, `HeaderCard` e `Card`, `Tabs`, tons
   e `--band`; migrar as raízes e tirar os `max-w-*`. O `layout-ritmo.spec.ts` entra aqui.
2. **Menu (US1):** `navTree`, `Sidebar` com Collapsible, lembrança e o helper `nav()` nos e2e.
3. **API aditiva:** `cortesResumo`, temas e `afinidadeEstado`, `offset` e `q`, com os testes de contrato e o
   `gen:contract`. É a pré-condição das fatias 4 a 7 (o dono usa o dev ao vivo).
4. **Perfil e Aprendizado (US3):** a aba Cortes sai, o `AplicarMarcaDialog` entra, Aprendizado vira página com
   redirects, e o cabeçalho e as abas mudam no celular.
5. **Descobrir (US4) e Gerações (US5).**
6. **Conteúdos (US6):** `ServerPagination`, página na URL e atalhos.
7. **FilterBar (US7):** componente, `lib/filtros.ts` e migração de todas as telas do inventário (R5).
8. **Vazios e ajustes (US8):** `EmptyState`, Propostas, Agentes, `DateField` e `FileField`, datas ad hoc.
9. **Verificação final:** suítes completas com o código congelado, capturas e impeccable (SC-009).

## Riscos

- **Working tree compartilhado:** há mudanças sem commit de outra frente (spec 021: `agendador.py`, constitution
  4.3.0, `CLAUDE.md`, migrations). A 024 toca `App.tsx`, o contrato gerado e os e2e. Recomendação: começar a
  implementação **depois do commit da 021**, ou numa worktree própria (`024-revisao-ux`). O `gen:contract`
  regera arquivos que a 021 também muda.
- **Volume de e2e:** a FilterBar e o DateField mudam a forma de preencher filtros em muitos testes. O helper
  `preencherData` e os rótulos acessíveis estáveis reduzem o retrabalho. Rode só a suíte afetada a cada fatia e a
  completa no fim.
- **PWA:** Sidebar e AppShell estão no shell em cache. Rode `test:e2e:pwa` na fatia 2 e no fim.

## Complexity Tracking

| Item | Por que é preciso | Alternativa mais simples rejeitada porque |
|---|---|---|
| `FilterBar` (componente novo) | 20 telas com 4 padrões de filtro; a spec exige um só | ajustar cada tela à mão manteria a divergência e duplicaria a lógica de etiquetas e de URL |
| `DateField` / `FileField` | o Chromium desenha `type=date` e `type=file` na língua do sistema operacional (mm/dd/yyyy, "Choose File") | o Calendar do shadcn exigiria `react-day-picker` (dependência nova); `lang` não resolve |
| `ServerPagination` | paginação numerada com total do servidor | o `ClientPagination` só pagina dados já carregados |
| `Page` e `EmptyState` | ritmo e vazio únicos, medidos pelo e2e | classes repetidas em 66 páginas voltariam a divergir |
