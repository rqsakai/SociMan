# Implementation Plan: AI Studio (biblioteca da agência)

**Branch**: `004-kit-de-marca-poc` (de trabalho) | **Date**: 2026-10-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/029-ai-studio/spec.md`

## Summary

Tirar a biblioteca de criação de dentro do perfil e torná-la **da agência**, com um **perfil base opcional**. A biblioteca são os avatares, os cenários, os outros assets (007), as cenas (010), os produtos (012) e as vozes (025).

**Técnica** (research R1–R13):
- **Banco:** o `perfil_id` dessas tabelas, e de `images`, `audios`, `geracoes` e `ia_chamadas`, passa a aceitar nulo e vira versionado, sem renomear.
- **Perfil base da geração:** uma função única (`perfilBaseId` com 3 estados) decide qual perfil vale em cada geração e chamada de IA, e grava o perfil usado.
- **Cenas:** saem as recusas de "item de outro perfil".
- **Rotas:** novas rotas da agência (`/api/assets`, `/api/cenas`, `/api/produtos`, `/api/vozes`, `/api/geracoes`, `/api/audios`, `/api/estudio/resumo`). As rotas por perfil ficam `deprecated`, com o mesmo comportamento.
- **SPA:**
  - grupo **AI Studio** no menu lateral, com listas separadas por tipo e filtro de perfil base na URL;
  - "+ Novo …" em diálogo dentro da cena;
  - a página do perfil perde 4 abas e ganha atalhos, e os links antigos redirecionam.
- **Migration** `0024_ai_studio`. A 011 passa para a `0027` (a `0025_mercado_shop` é da 026 e a `0026_uniao_mercado` une as pontas).

## Technical Context

**Language/Version**: Python 3.12 (API, uv) · TypeScript / React 19 (SPA)

**Primary Dependencies**:
- API: FastAPI 0.141, SQLAlchemy 2, Alembic, Pydantic 2;
- SPA: TanStack Query, TanStack Table v9, shadcn/ui, Tailwind 4, React Router.

Nada novo.

**Storage**:
- PostgreSQL: migration `0024_ai_studio`;
- MinIO no HD, com o prefixo `agencia/` para os arquivos novos sem perfil. As chaves antigas não mudam.

**Testing**:
- pytest na stack efêmera (`npm run test:api`);
- Playwright na stack e2e (`flock … npm run test:e2e`);
- `check:web`.

**Target Platform**: Linux, Docker Compose (dev e modo casa)

**Project Type**: web (API + SPA + contrato gerado)

**Performance Goals**: as listas da agência em menos de 1 s com 5 mil itens (SC-006); pedir uma geração continua abaixo de 300 ms (025).

**Constraints**:
- contrato gerado (IV);
- sem DELETE no domínio (VII);
- MCP só lê (I/VII);
- CSP estrita;
- e2e isolado.

**Scale/Scope**: hoje, dezenas de itens por tipo; o desenho prevê 5 mil.

## Constitution Check

*GATE: passou antes da fase 0 e foi conferido de novo depois do desenho.*

| Princípio | Como a 029 cumpre |
|---|---|
| I. Publicação só com decisão humana | nenhuma rota nova fala com rede social; as escritas novas ficam fora do MCP (`FORA`/`PROIBIDAS`); a guarda de import de `publicacao` cobre os módulos novos |
| II. Direito é do dono | não toca canais nem envios |
| III. Marca em tokens | o kit de marca continua do perfil; só o seletor passa a listar a biblioteca da agência |
| IV. Contrato é a fonte única | rotas novas no OpenAPI, `gen:contract`, `mcp-tools.json` regenerado; nada editado à mão |
| V. Segurança e segredos | sem segredo novo; o `perfilId` do cliente é validado (400 `perfil_invalido`); as chaves do MinIO continuam sem dado pessoal |
| VI. Testes antes de pronto | pytest (migration, perfil base, listas, usos cruzados, MCP, desempenho) e e2e `ai-studio.spec.ts` antes de marcar pronto |
| VII. Humano no controle | mudar o perfil base é uma edição versionada, e o revert é só do dono; escolher opções continua `RequireHuman`; a desduplicação das vozes grava versão `system:migration` |
| VIII. Simplicidade | sem renomear a coluna, sem tabela de ligação, sem "perfil da agência" falso; as listas reaproveitam os componentes das abas |
| Restrições técnicas (NVMe × HD, 2.1.0) | os arquivos continuam no MinIO do HD; o banco continua no NVMe |
| Exceções de eliminação (4.3.0) | nenhuma nova; a revogação (025) não muda |

Sem violação: a tabela "Complexity Tracking" fica vazia.

## Project Structure

### Documentation (this feature)

```text
specs/029-ai-studio/
├── spec.md
├── plan.md              # este arquivo
├── research.md          # R1–R13
├── data-model.md        # migration 0024, colunas anuláveis, unicidade de voz
├── quickstart.md        # §0 backup e migration, §1 automático, §2 manual
├── contracts/http-api.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── migrations/versions/0024_ai_studio.py            # novo
├── src/sociman_api/
│   ├── perfis/base.py                               # novo: resolver(item_perfil_id, pedido) → Perfil | None (R4)
│   ├── estudio/{__init__,router,schemas}.py         # novo: GET /api/estudio/resumo
│   ├── assets/{models,service,router,schemas,busca,usos}.py      # perfil anulável e versionado, rotas da agência
│   ├── cenas/{models,service,router,usos_assets,padroes}.py      # sem a recusa de outro perfil, padrões do perfil base
│   ├── produtos/{models,service,router,router_perfil,fluxo}.py   # idem
│   ├── vozes/{models,service,router}.py                          # nome único na agência
│   ├── geracao/{models,service,router,router_audios,audios,uso}.py  # perfilBaseId, lista por alvo
│   ├── ia/{models,service,contexto}.py              # perfil base na chamada; resumo "Sem perfil"
│   ├── perfis/models.py                             # images.perfil_id anulável
│   ├── marca/service_kit.py                         # seletor da biblioteca da agência
│   ├── mcp/mapa.py                                  # classificar as rotas novas
│   └── main.py                                      # incluir o router do estudio
└── tests/
    ├── integration/{estudio_helpers,test_migration_0024,test_perfil_base,test_agencia_listas,
    │                test_cena_cruzada,test_vozes_nome_agencia,test_estudio_resumo,test_estudio_desempenho}.py
    └── unit/{test_perfil_base_resolver,test_mcp_mapa,test_constitution_guards}.py

apps/web/src/
├── components/shell/nav.ts                          # grupo AI Studio
├── components/estudio/{PerfilBaseField,PerfilBaseFiltro,NovoItemDialog}.tsx   # novos
├── pages/estudio/{Avatares,Cenarios,Vozes,Produtos,Cenas,Assets,Movimentos,RedirectEstudio}.tsx  # novos
├── pages/perfis/tabs/{AssetsTab,CenasTab,ProdutosTab,VozesTab}.tsx  # viram listas sem perfil obrigatório
├── pages/perfis/PerfilDetalhe.tsx                   # sem as 4 abas, card "Ver no AI Studio", redirecionamentos
├── pages/cenas/*                                    # "+ Novo …" nos seletores, perfil base
├── pages/estudio/Estudio.tsx                        # removido (vira redirecionamento)
└── App.tsx                                          # rotas /app/estudio/*

e2e/
├── ai-studio.spec.ts                                # novo
└── layout.spec.ts, assets/cenas/produtos/cadastro-padronizado/geracao.spec.ts  # navegação nova
```

**Structure Decision**: o padrão de sempre do repo (API FastAPI por pacote de domínio, SPA por página, contrato gerado). Um pacote novo pequeno (`estudio/`) guarda só o resumo; o resto são mudanças nos pacotes de cada tipo.

## Ordem de implementação (insumo para o /speckit-tasks)
1. **Gate:** head `0023`; corrigir a numeração da 011 (agora `0027`); base de testes verde.
2. **Fundação:** migration `0024` + modelos anuláveis + `perfis/base.resolver` + `images`/`audios` sem perfil.
3. **US1:** rotas de lista da agência, o resumo e o MCP (`mapa.py`), e na SPA o menu e as listas.
4. **US2:** `perfilBaseId` na geração e no assistente, o PATCH do perfil base e o `PerfilBaseField`.
5. **US3:** a cena cruzada (tirar as recusas, padrões do perfil base) e o `NovoItemDialog`.
6. **US4:** a página do perfil, os redirecionamentos e o kit de marca.
7. **US5:** as rotas antigas `deprecated` com regressão, e os testes de leitura pelo MCP.
8. **Polimento:** desempenho (SC-006), `CLAUDE.md` (seção "AI Studio (desde a spec 029)"), `docs/visao.md`, e2e inteiro e a migration no dev com backup `pre-0024.dump`.

## Complexity Tracking

Nenhuma violação a justificar.
