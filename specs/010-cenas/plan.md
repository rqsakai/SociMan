# Implementation Plan: Cenas para o Flow/Veo

**Branch**: `010-cenas` | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-cenas/spec.md`

## Summary

Cada perfil ganha uma biblioteca de **cenas**: tomadas de até 8 s para o dono gerar à mão no Google
Flow/Veo. A cena referencia o **avatar** (com um arquivo de look ou de pose), o **cenário** e uma **foto de
produto** da biblioteca de assets da 007, e guarda enquadramento, ação, fala, texto na tela, iluminação e
estilo, áudio, duração e modo do Flow. A API **monta o prompt** em inglês numa função pura
(`cenas/prompt.py`), na ordem fixa do shop-diretor, com a descrição do avatar copiada caractere a
caractere. O prompt é calculado ao vivo em `rascunho` e **congelado** (texto + versões do avatar e do
cenário) ao marcar `pronta`; o aviso "mudou" compara as versões e o "Remontar" recongela (Q3).

As **tomadas** (MP4/MOV/WebM de 1 a 30 s) vão para o bucket de vídeos no HD pelo mesmo recebimento em
streaming do vídeo próprio da 014, com miniatura e o prompt congelado do momento. O **vínculo** cena ×
conteúdo vídeo próprio (Q2) é uma tabela de ligação com histórico nos dois lados e define o status
`usada`. A **IA** da 008 ganha 5 tipos de campo da cena (modo "só proibidas" da 017). O **MCP** da 009 ganha
as leituras de cena e o tipo de anotação **`proposta_cena`** (Q1); todas as escritas de cena ficam fora ou
proibidas no mapa. Uma migration (`0015_cenas`), nenhuma dependência e nenhum serviço novo.

## Technical Context

**Language/Version**: Python 3.12 (API, uv) · TypeScript 5 / React 19 (SPA, Vite)

**Primary Dependencies**: FastAPI, SQLAlchemy 2, Pydantic 2, Alembic, MinIO SDK, ffprobe/ffmpeg (já na
imagem). SPA: TanStack Query, TanStack Table v9, shadcn/ui. **Nenhuma dependência nova.**

**Storage**: PostgreSQL: 4 tabelas novas (`cenas`, `cena_tomadas`, `cena_usos`, `cena_padroes`) e
alterações na `anotacoes` (enums e CHECK), migration **`0015_cenas`** (`down_revision = "0014_mcp"`).
MinIO no HD: bucket de vídeos `cenas/<cena_id>/tomadas/<tomada_id>.<ext>` e miniaturas no bucket
`sociman`.

**Testing**: pytest na stack efêmera (`npm run test:api`), ruff, `npm run gen:contract && npm run
check:web`, Playwright na stack e2e efêmera (`e2e/cenas.spec.ts`), com o Claude falso e o cliente MCP de
teste. Nenhum serviço real.

**Target Platform**: SPA (desktop e celular, modo casa) + API no Docker

**Project Type**: web (apps/api + apps/web)

**Performance Goals**: lista de cenas com filtros < 500 ms com 200 cenas (SC-006); montar o prompt < 10
ms (função pura); envio de tomada de 30 s limitado pelo disco

**Constraints**: nada aqui publica, aprova ou agenda; MCP sem escrita de domínio (só `proposta_cena`);
tomadas ≤ 200 MB e 1–30 s; HD com sentinela e piso; CSP inalterada; prompt em inglês com fala em pt-BR

**Scale/Scope**: 1–3 perfis, dezenas a poucas centenas de cenas por perfil, até ~5 tomadas por cena; ~18
rotas novas; 2 páginas novas (aba "Cenas" do perfil e detalhe da cena); acréscimos em Conteúdo, Assets,
Propostas, Assistente de IA e no mapa do MCP

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.* (constitution **4.2.0**)

| Princípio | Situação | Como |
|---|---|---|
| **I. Publicação só com decisão humana** | ✅ | `cenas/` não importa `publicacao`, `httpx` nem cliente de rede (guarda em `test_constitution_guards.py`). Não chama o Flow/Veo/HeyGen. O vínculo com o conteúdo não aprova nem agenda; o vídeo final segue a 014. Sem "tiktok"/"youtube" em rotas e `operationId` (`cenas_*`) |
| **II. Direito é responsabilidade do dono** | ✅ (não afetado) | Nenhum envio para corte nem canal-fonte. Tomadas são geradas pelo dono |
| **III. Marca em tokens** | ✅ (não afetado) | A cena não altera o kit; estilo e negative padrão do perfil ficam em `cena_padroes`, não no kit |
| **IV. Contrato é a fonte única** | ✅ | Schemas Pydantic → `npm run gen:contract`; tools MCP vêm do OpenAPI pelo mapa (só acréscimo de classificação) |
| **V. Segurança e segredos** | ✅ | Nenhum segredo novo. Tomadas validadas pelo conteúdo (ffprobe), sem executar nada do arquivo; links de mídia HMAC da 004. Texto de proposta MCP é dado (schema fechado `extra="forbid"`). CSP inalterada |
| **VI. Testes antes de pronto** | ✅ | Unitários (montagem do prompt, avisos, status), integração (CRUD, congelar/remontar, tomadas, vínculo, IA, MCP, permissões, migration), guardas e e2e. VII e a recusa MCP têm teste no backend (SC-004, SC-005) |
| **VII. Humano no controle** | ✅ | `cena`, `cena_tomada` e `cena_padroes` têm `version`, `__versioned_fields__` e `history.record`; arquivar/restaurar, revert só pelo dono. O vínculo grava histórico na cena e no conteúdo. O agente só grava anotação `proposta_cena` (já versionada pela 009) |
| **VIII. Simplicidade** | ✅ | 0 dependência, 0 serviço, 0 trilha do agendador. Reaproveita recebimento de vídeo (014), links de mídia (004), usos de assets (007), IA (008), guia (017) e anotações (009). `usada` é status gravado pelo serviço do vínculo (sem trigger) |
| Restrições: NVMe × HD | ✅ | Tomadas e miniaturas no MinIO (HD), temporários em `work/tmp` com sentinela e piso (`datadir.py`); só metadados no PG |
| Restrições: banco | ✅ | Migration `0015_cenas` com upgrade/downgrade e `test_migration_0015` |

**Reavaliação pós-design:** mantida. O design não criou serviço nem dependência. A única alteração em
tabela de outra spec é aditiva (`anotacoes`: dois valores de enum e o CHECK ampliado), coberta pelo teste
de migration e pelos testes da 009.

## Project Structure

### Documentation (this feature)

```text
specs/010-cenas/
├── plan.md              # este arquivo
├── research.md          # R1–R12
├── data-model.md        # 4 tabelas, anotacoes ampliada, máquina de status, migration 0015
├── quickstart.md        # roteiro de validação (automático + manual com o dono no Flow)
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
apps/api/src/sociman_api/cenas/
├── __init__.py
├── models.py        # Cena, CenaTomada, CenaUso, CenaPadroes; enums CenaStatus, CenaModo, CenaPlano, CenaMovimento
├── prompt.py        # montar(cena, avatar, arquivo, cenario, padroes) -> PromptMontado (puro, R2)
├── avisos.py        # fala longa, ingredientes, duração × modo, produto sem foto, proibidas (puro, R4)
├── ingredientes.py  # até 3 imagens na ordem avatar → produto → cenário, com links de mídia (R3)
├── service.py       # criar, editar, duplicar, status (pronta/rascunho), congelar, remontar, arquivar, reverter
├── padroes.py       # cena_padroes por perfil (estilo e negative padrão), versionado
├── tomadas.py       # envio em streaming (reusa 014), ffprobe, miniatura, escolher, arquivar (R6)
├── usos.py          # vínculo cena × conteúdo: definir conjunto, status usada/pronta, histórico nos 2 lados (R7)
├── usos_assets.py   # provedor "cena" para assets.usos.register (R8)
├── schemas.py
├── router_perfil.py # /api/perfis/{id}/cenas…, /api/perfis/{id}/cenas/padroes
└── router.py        # /api/cenas/{id}…, /api/cenas/tomadas/{id}…, /api/conteudos/{id}/cenas
apps/api/src/sociman_api/
├── anotacoes/models.py, schemas.py, service.py   # alvo `cena`, tipo `proposta_cena`, CamposCena, aplicar_cena (R9)
├── ia/tipos.py, regras_padrao.py, contexto.py, aplicacao.py   # 5 tipos `cena.*` (R10)
├── mcp/mapa.py                                   # leituras de cena em TOOLS; escritas em FORA/PROIBIDAS (R11)
├── conteudos/consulta.py, schemas.py             # `cenas` no detalhe do conteúdo (só leitura)
└── main.py                                       # include_router das cenas
apps/api/migrations/versions/0015_cenas.py
apps/api/tests/
├── unit/test_cenas_prompt.py, test_cenas_avisos.py, test_ia_tipos.py (+cena), test_mcp_mapa.py (verde),
│   test_constitution_guards.py (+010)
└── integration/cenas_helpers.py, test_cenas.py, test_cenas_prompt_congelado.py, test_cenas_tomadas.py,
    test_cenas_usos.py, test_cenas_ia.py, test_cenas_mcp.py, test_cenas_permissoes.py, test_migration_0015.py

apps/web/src/
├── pages/perfis/tabs/CenasTab.tsx        # lista com filtros (DataTable), nova cena, duplicar
├── pages/cenas/CenaDetalhe.tsx           # formulário, prompt e ingredientes, tomadas, usos, histórico
├── pages/cenas/CenaHistorico.tsx
├── components/cenas/                      # CenaForm, PromptPainel, Ingredientes, Tomadas, AvisoMudou, SeletorCenas
├── lib/cenas.ts                           # hooks TanStack Query (cliente gerado)
├── App.tsx                                # rotas /app/cenas/:id e /app/cenas/:id/historico
├── pages/perfis/PerfilDetalhe.tsx         # aba "Cenas" (?aba=cenas)
├── pages/conteudos/ConteudoDetalhe.tsx    # bloco "Cenas" do vídeo próprio (SeletorCenas)
└── pages/propostas/Propostas.tsx          # tipo `proposta_cena`: Aceitar → /app/perfis/:id/cenas/nova?proposta=…
e2e/cenas.spec.ts
```

**Structure Decision**: pacote próprio `cenas/` (domínio novo, com tabelas próprias), no mesmo molde de
`assets/` e `conteudos/`. A cena depende de `assets` (leitura e o registro de usos), de `conteudos`
(vínculo) e de `ia.guia` (proibidas); nenhum desses importa `cenas`, exceto pelo registro do provedor de
usos e pelo `anotacoes.service` (validação do alvo `cena`). A 011 (scripts) vai referenciar `cenas.id`.

## Complexity Tracking

| Violação | Por que é necessária | Alternativa mais simples rejeitada porque |
|---|---|---|
| Prompt congelado gravado na cena (duplica texto que vem dos assets) | É o registro de como a tomada foi gerada (Q3); a 007 permite editar o avatar a qualquer momento | Recalcular sempre: a cena `usada` mudaria sozinha e não bateria mais com a tomada |
| Alteração aditiva na tabela `anotacoes` da 009 | A proposta de cena é anotação (Q1) para reaproveitar caixa, limites, registro e permissões | Tabela própria de propostas de cena: duplicaria a caixa "Propostas dos agentes" e as regras de autor |
