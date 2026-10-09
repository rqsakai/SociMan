# Implementation Plan: Importação da agência

**Branch**: `013-importacao` | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/013-importacao/spec.md`

## Summary

O dono abre "Importar da agência" (configurações) e pede a leitura. A API:
- lê `shared/` e `media/clipes/` da agência por **montagens só leitura** no container, só os caminhos do
  mapeamento (tabela `MAPA` em código), com limites de tamanho e de quantidade e sem seguir link para fora
  (R1, R2);
- interpreta o markdown de forma **determinística** (biblioteca padrão: seções `##`, listas `- Campo:` e
  tabelas `|`), pelos moldes de `_modelo/` (R3);
- **concilia** cada item com o banco pela chave do tipo (slug, plataforma e @, id do canal do YouTube,
  SHA-256, impressão digital do trecho) e o classifica em `novo`, `igual`, `diverge`, `fora` ou
  `aguardando_cota` (R4, R5);
- identifica canais novos pelo `resolver` da 006 (com cota) e propõe o direito (Q1: `autorizado` →
  `sem_acordo`, trocável para `parceiro`) (R6);
- guarda a **pré-visualização no Redis** (30 min, uso único), como na 020 (R7).

Ao confirmar, a API cria a **importação** (`processando`) e responde 202. Uma tarefa de fundo do próprio
processo da API (BackgroundTasks) confere o HD para o total, **grava primeiro os arquivos** (imagens e
vídeos) no MinIO e depois aplica **todas as mutações numa transação**, chamando os services que já existem
(perfis, contas, canais, assets, guia, anotações, conteúdos), cada um com `history.record` e o detalhe
`importacao` (R8, R9). Desfazer arquiva o que foi criado e reverte o que foi trocado, se ninguém mexeu
depois (R10). Nada é publicado, a pasta da agência nunca é escrita, e não entra nenhuma dependência nova.

## Technical Context

**Language/Version**: Python 3.12 (API, uv) · TypeScript 5 / React 19 (SPA, Vite 8)

**Primary Dependencies**: FastAPI, SQLAlchemy 2, Pydantic 2, redis-py, Pillow (validação da 007), ffprobe/
ffmpeg (vídeo próprio da 014). Leitura com `pathlib`, `re`, `hashlib` e `unicodedata` da biblioteca
padrão. **Nenhuma dependência nova** (sem biblioteca de markdown). SPA: TanStack Query, TanStack Table v9 e
shadcn/ui.

**Storage**: PostgreSQL (2 tabelas novas, migration `0016_importacao`, `down_revision = "0015_cenas"`);
Redis para a pré-visualização (TTL); MinIO no HD para as imagens e vídeos novos (≈900 MB hoje, todos
vídeos), com o marcador e o piso de espaço livre

**Testing**: pytest na stack efêmera (`npm run test:api`), com pastas sintéticas geradas em `tmp_path`
(`tests/integration/agencia_helpers.py`); ruff; `npm run check:web`; Playwright na stack e2e efêmera
(`e2e/importacao.spec.ts`) com a pasta `e2e/fixtures/agencia/` montada só leitura

**Target Platform**: SPA (desktop e celular, modo casa) + API no Docker

**Project Type**: web (apps/api + apps/web)

**Performance Goals**: pré-visualização da pasta real (71 arquivos + 70 vídeos, ~900 MB a hashear) em menos
de 1 min sem contar a cota (SC-001); confirmação só de cadastro em menos de 5 s; com os 70 vídeos, em
poucos minutos, com andamento na tela

**Constraints**: só dono humano escreve; a pasta da agência é só leitura (montagem `:ro` e nenhum `open`
de escrita no pacote, guarda); markdown ≤ 2 MB, imagem ≤ 20 MB, vídeo pelos limites da 014, ≤ 2.000
arquivos; nenhum valor editado no SociMan muda sem a escolha do dono; fuso America/Sao_Paulo; CSP
inalterada

**Scale/Scope**: 2 perfis hoje (até ~3 antes da migração dos agentes); ~120 itens por leitura (2 perfis, 3
contas, 29 fontes, 18 imagens, ~40 anotações, 70 clipes); 6 rotas novas; 2 páginas novas

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.* (constitution **4.2.0**)

| Princípio | Situação | Como |
|---|---|---|
| **I. Publicação só com decisão humana** | ✅ | O pacote `agencia/` não importa `publicacao`, `httpx` nem cliente de rede social (guarda em `test_constitution_guards.py`). A única chamada externa é o `resolver`/`create_canal` da 006 (YouTube, leitura de canal, cota). Os clipes viram conteúdos **sem destino**: aprovar, agendar e publicar continuam na 014/015. Sem "tiktok" nem "youtube" em rotas e `operationId` (`agencia_*`) |
| **II. Direito é responsabilidade do dono** | ✅ | O status é **proposto** (Q1) e o dono confere linha a linha; um canal existente só muda com escolha explícita, pelo mesmo `mudar_direito` da 006 (autor e histórico). A importação de direito é rota **H** (dono humano). `negado`/`pendente` viram `sem_acordo` para o aviso aparecer. Teste: SC-003 |
| **III. Marca em tokens** | ✅ | O estilo visual em prosa (§5) fica fora; as expressões só viram **sugestão** de bordão, sem mudar o kit |
| **IV. Contrato é a fonte única** | ✅ | Rotas e schemas Pydantic → `npm run gen:contract`; as tools do MCP saem do mapa explícito da 009 (leitura do registro como tool; prévia, confirmar e desfazer em `PROIBIDAS`) |
| **V. Segurança e segredos** | ✅ | Nenhum segredo novo. Montagens `:ro`; leitura só dos caminhos do mapa, sem seguir link para fora da raiz, com limites (R2). O conteúdo de arquivo fora do mapa nunca é aberto. O texto do markdown é dado (sem IA). Os logs só têm contagens e caminhos relativos. CSP inalterada |
| **VI. Testes antes de pronto** | ✅ | Unitários (leitor, mapeamento, chaves), integração (prévia, confirmar, idempotência, direito, imagens, clipes, desfazer, permissões, migration), guardas e e2e. Princípios I, II e VII com teste no backend (SC-002, SC-003, SC-005) |
| **VII. Humano no controle** | ⚠️ justificado | Toda mutação de domínio passa pelos services existentes, com `history.record` (autor = dono que confirmou; `details.importacao`). A importação tem `version` e histórico; desfazer é a reversão (arquiva e reverte). **Exceções:** (a) os itens da importação são registro só de inserção, sem `version` própria (como os dias da 020); (b) não há "refazer"; (c) arquivos gravados no MinIO antes de uma transação que falha ficam sem referência (o armazenamento não tem delete; mesmo caso dos envios). Ver Complexity Tracking |
| **VIII. Simplicidade** | ⚠️ justificado | 0 dependência, 0 serviço, 0 trilha nova do agendador, 2 tabelas. **Peças novas:** 2 montagens só leitura no compose (dev, e2e) e uma tarefa de fundo do FastAPI para a confirmação com vídeos. Ver Complexity Tracking |
| Restrições: armazenamento NVMe × HD | ✅ | Imagens e vídeos novos vão para o MinIO (HD); os temporários da miniatura usam o `spool_dir` do HD da 014; `datadir.ensure_writable(total)` antes de gravar o primeiro arquivo. No PG só cadastro e o registro |
| Restrições: Redis | ✅ | Só a prévia (TTL 30 min, uso único com `GETDEL`), como na 020. O registro da importação fica no PG |
| Restrições: banco | ✅ | Migration `0016_importacao` (depois da `0015_cenas` da 010), com upgrade/downgrade e `test_migration_0016` |

**Reavaliação pós-design:** mantida. O design reaproveita os services de domínio em vez de gravar direto nas
tabelas (o histórico e as regras de cada entidade ficam num lugar só) e não criou serviço nem dependência.
As duas exceções estão abaixo.

## Project Structure

### Documentation (this feature)

```text
specs/013-importacao/
├── plan.md              # este arquivo
├── research.md          # R1–R12
├── data-model.md        # 2 tabelas, prévia no Redis, chaves e situações, migration 0016
├── quickstart.md        # roteiro de validação (sintético + real com o dono)
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/src/sociman_api/agencia/
├── __init__.py
├── pastas.py         # raízes (config), varredura com limites, sem link para fora, impressão digital (R1, R2)
├── mapa.py           # MAPA: padrão de caminho → leitor/destino ou motivo de "fora" (R1)
├── markdown.py       # seções, listas "- Campo: valor", tabelas, normalização (R3)
├── leitores.py       # perfil.md, INDEX.md, fontes.md, pesquisa.md, ideias, registro-clipes, persona.md
├── itens.py          # Item (tipo, origem, chave, impressão, dados) e as situações (R4)
├── conciliar.py      # por tipo: procura no banco, compara e classifica; status de direito (R5, R6)
├── previa.py         # montar, cota, Redis (SET EX / GETDEL), base de versões (R7)
├── aplicar.py        # confirmar: HD, arquivos antes, transação com os services, resultado por item (R8, R9)
├── desfazer.py       # arquivar o criado, reverter o trocado, "não desfeito" com motivo (R10)
├── models.py         # Importacao (versionada), ImportacaoItem (só inserção)
├── schemas.py        # Previa, ItemPrevia, Escolhas, Importacao, Estado
└── router.py         # /api/agencia/* (operationId agencia_*)
apps/api/src/sociman_api/
├── config.py               # AGENCIA_SHARED_DIR, AGENCIA_CLIPES_DIR (padrão /agencia/shared, /agencia/clipes)
├── main.py                 # include_router (acréscimo)
├── history.py             # contexto `origem_importacao` (contextvars) somado aos `details` do record (R8)
├── mcp/mapa.py             # leitura do registro como tool; prévia, confirmar e desfazer em PROIBIDAS (acréscimo)
└── conteudos/video_proprio.py  # função `create_de_arquivo` (Path já no disco), sem mudar a rota (R9)
apps/api/migrations/versions/0016_importacao.py
apps/api/tests/
├── unit/test_agencia_markdown.py, test_agencia_leitores.py, test_agencia_mapa.py,
│   test_agencia_direito.py, test_constitution_guards.py (+013)
└── integration/agencia_helpers.py (gerador da pasta sintética),
    test_agencia_previa.py, test_agencia_confirmar.py, test_agencia_idempotencia.py,
    test_agencia_direito.py, test_agencia_imagens.py, test_agencia_clipes.py,
    test_agencia_guia_anotacoes.py, test_agencia_desfazer.py, test_agencia_permissoes.py,
    test_migration_0016.py
docker-compose.yml                # api: 2 montagens :ro (AGENCIA_SHARED_HOST, AGENCIA_CLIPES_HOST)
docker-compose.e2e.yml            # api: e2e/fixtures/agencia montada :ro
.env.example                      # as 2 variáveis, comentadas

apps/web/src/
├── pages/configuracoes/ImportacaoAgencia.tsx        # estado, ler, prévia, escolhas, confirmar, lista
├── pages/configuracoes/ImportacaoDetalhe.tsx        # /app/configuracoes/importacao/:id (itens, desfazer)
├── components/importacao/                           # PreviaTabela, ItemDiverge, EscolhaDireito, Andamento
├── lib/importacao.ts                                # hooks TanStack Query (cliente gerado)
├── App.tsx                                          # 2 rotas (acréscimo)
└── components/shell/Sidebar.tsx                     # link em Configurações (acréscimo)
e2e/importacao.spec.ts
e2e/fixtures/agencia/{shared,clipes}/                # pasta sintética (sem dado real do dono)
```

**Structure Decision**: o web app existente (apps/api + apps/web). Pacote novo `agencia/`, porque a
importação é transversal (perfil, conta, canal, asset, guia, anotação, conteúdo) e não pertence a nenhum
desses pacotes. Ele **chama** os services de domínio e nunca grava direto nas tabelas deles; nenhum pacote
de domínio importa `agencia/`. A única mudança fora do pacote, além dos acréscimos, é extrair de
`conteudos/video_proprio.create` o miolo que aceita um arquivo já no disco.

## Complexity Tracking

| Violação | Por que é necessária | Alternativa mais simples rejeitada porque |
|---|---|---|
| 2 montagens só leitura no compose (princípio VIII) | A API precisa ler `shared/` e `media/clipes/` (≈900 MB) da agência, na mesma máquina | Enviar um ZIP pela tela: 900 MB pelo navegador, cópia duplicada no HD e conciliação de imagens mais difícil; uma CLI no host: sem pré-visualização nem escolhas na tela |
| Confirmação em tarefa de fundo do FastAPI (princípio VIII) | Gravar 70 vídeos e as miniaturas leva minutos; a requisição não pode ficar presa ao timeout do edge | Trilha nova no agendador: serviço a mais para um ato raro e humano; um envio por clipe pela SPA: quebra o "tudo ou nada" |
| Itens sem `version` própria (princípio VII) | São o registro imutável do que a importação leu e decidiu; o histórico de cada mudança fica na entidade de destino e na importação | Versionar cada item: centenas de versões sem valor de auditoria |
| Sem "refazer"; arquivos órfãos no MinIO após falha (princípio VII) | Desfazer **é** a reversão; reimportar refaz. O MinIO não tem delete (004) | "Refazer" e limpeza de órfãos: mais estados e um delete que a constitution evita |
