# Implementation Plan: Cockpit do TikTok Shop coletado pelo SociMan

**Branch**: `026-mercado-shop` (worktree `worktree-026-mercado-shop`) | **Date**: 2026-10-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/026-mercado-shop/spec.md`

## Summary

O SociMan ganha a **inteligência de mercado** do TikTok Shop, coletada por ele mesmo, em três peças:
- um **serviço `coletor`** no desktop do dono (`apps/coletor/`, Python, **fora do Docker**, systemd de
  usuário), que lança o Chrome do sistema num perfil dedicado logado na conta de afiliado do dono, conecta por
  CDP em loopback, navega como pessoa (uma aba, 08h–23h, pausas de 5 a 40 s, 300 páginas e 1.500 imagens por
  dia), intercepta as respostas da API interna que a página carrega e devolve campos, bruto e imagens;
- a **API de ingestão** (`coleta/`): token `scol_` só com hash, portão global, cabeçalho de protocolo, fila
  ditada pelo servidor, idempotência por (tipo, chave, dia, turno), bruto gzip no bucket novo
  `sociman-mercado`, imagens originais deduplicadas no bucket `imagens` (prefixo `mercado/`);
- o **lago global e permanente** (`mercado/`): produtos, fichas versionadas por conteúdo, fotos diárias só de
  inserção (2/dia para quentes e manuais), lojas, categorias, rankings, avaliações (autor por hash) e vídeos
  top; a **camada de interesse** por perfil (acompanhamentos com origem, categorias do nicho, vitrine para
  todos); e a **leitura** calculada na hora (vendas/dia, GMV, crescimento, novo em alta, retorno por afiliado),
  tudo marcado como estimado, em `/app/mercado`, no detalhe do produto, na aba Mercado do perfil e em
  `/app/configuracoes/coleta` (aceite de risco, interruptor, tokens, rodadas).

Dois reforços do princípio IX atravessam o plano: o coletor **só lê** (lista fechada de ações com teste
estático) e **nada do lago é apagado**. A ponte com a 012 (`produtos.mercado_produto_id` e "Adotar no
catálogo") fica condicionada ao merge da 012, que está em outra sessão. Nada publica.

## Technical Context

**Language/Version**: Python 3.12 (API e coletor, uv) · TypeScript 5 / React 19 (SPA, Vite)

**Primary Dependencies**: API: FastAPI, SQLAlchemy 2, Pydantic 2, Pillow (validar imagem pelo conteúdo),
nenhuma dependência nova. **Coletor (`apps/coletor/`, `pyproject` próprio):** `playwright` (só a
biblioteca, para `connect_over_cdp`; o navegador é o Chrome do sistema), `httpx`, `pydantic`. A API **não**
ganha `playwright` (guarda). SPA: TanStack Query, TanStack Table, shadcn/ui, ECharts modular (chunk
`graficos`); nada novo.

**Storage**: PostgreSQL (NVMe): 20 tabelas novas e 1 coluna na 012, migration `0025_mercado_shop`
(provisória; o gate T001 confere o próximo número livre: a 012 ocupa `0022` em outra sessão, a 025 e a 011
reservam `0023` e `0024`). MinIO no HD: imagens do lago no bucket `imagens` com prefixo `mercado/<sha[:2]>/`
(o imgproxy só lê esse bucket), bruto gzip no bucket novo **`sociman-mercado`**; sentinela `.sociman-volume`
e piso de espaço em toda gravação (`datadir.ensure_writable`). Redis: só o limite de requisições do portão e
o estado do coletor para o painel de integrações (60 s).

**Testing**: pytest na stack efêmera (`npm run test:api`) com o **coletor falso** (`tests/fakes/coletor_fake.py`:
posta resultados sintéticos na ingestão), ruff, `npm run check:web`, Playwright (`e2e/mercado.spec.ts`, com o
coletor falso dentro do `openshorts-fake`). No `apps/coletor/tests/`: parsers com JSON sintético, ritmo e
janela com relógio e RNG semeados, cliente da API com transporte falso, servidor HTML sintético que carrega
JSON pelos mesmos caminhos, e as guardas (ações permitidas por AST, poda de dados pessoais, log). Nenhum
teste toca a rede real. A validação real é a **sonda** com o dono (quickstart §2) antes de ligar.

**Target Platform**: Linux (host `sakai-desktop`): API, agendador e SPA no Docker; o coletor no host, com a
sessão gráfica do dono (Chrome visível; sem modo headless)

**Project Type**: web (`apps/api` + `apps/web`) + **1 aplicativo novo fora do compose** (`apps/coletor/`);
nenhum serviço novo no compose (a trilha `mercado` roda no `agendador` existente)

**Performance Goals**: leituras do cockpit < 2 s com 10× o volume de um ano (≈ 1,1 M fotos); ingestão de um
lote de 50 itens < 1 s; fila montada pela trilha em < 5 s; coletor: pausas de 5–40 s entre ações (FR-016), o que dá cerca de 1 página a cada 20–90 s somando a permanência

**Constraints**:
- só leitura na rede; lista fechada de ações no coletor (AST) e nenhuma chamada direta à API assinada;
- ritmo e tetos vêm do servidor; o coletor aplica o menor entre o seu e o do servidor;
- lago sem `perfil_id`, `conta_id`, `tenant_id`, `created_by`; nada apagado (tabelas de foto com trigger);
- terceiros só por identificador público e contadores; autor de avaliação por hash com pepper; fotos de
  clientes guardadas como vêm (decisão do dono, registrada);
- aceite de risco registrado antes de ligar; interruptor em dois níveis; captcha/login param e avisam;
- HD obrigatório para imagens e bruto (sem HD: foto numérica gravada e item "bruto pendente");
- CSP inalterada; porta da API fechada; o coletor alcança a API só pelo edge (HTTPS da casa com a CA, ou
  `localhost:8180` em dev);
- nenhum nome de rede em rotas e `operationId` (`coleta_*`, `mercado_*`).

**Scale/Scope**: ~200 produtos quentes, 25 rankings, 40 primeiras visitas e 35 páginas de lojas, vídeos e
avaliações por dia (300 páginas); ≈ 100 MB/dia de imagens + 90 MB/dia de bruto gzip ≈ 70 GB/ano no HD;
2 perfis hoje; 5 telas/abas novas no SPA; 32 rotas novas; 20 tabelas.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.* (constitution **4.4.0**, princípio
IX aprovado pelo dono em 2026-10-08 e já aplicado em `.specify/memory/constitution.md`)

| Princípio | Situação | Como |
|---|---|---|
| **I. Publicação só com decisão humana** | ✅ | Nenhum código novo fala com API de publicação. O coletor é **só leitura** (FR-014, FR-015) e a API não ganha nenhum endereço da rede: os padrões de URL interceptados vivem só em `apps/coletor/`. Guardas: `mercado/` e `coleta/` sem `httpx`/`publicacao`/hosts da rede; `apps/api/pyproject.toml` sem automação de navegador; `coleta_*`/`mercado_*` sem "tiktok" (o teste existente de nomes cobre) |
| **II. Direito é responsabilidade do dono** | ✅ (não afetado) | Nenhum envio para corte. O status de direito dos canais não é tocado |
| **III. Marca em tokens** | ✅ (não afetado) | O kit não muda |
| **IV. Contrato é a fonte única** | ✅ | Rotas e schemas Pydantic → `npm run gen:contract` (`packages/contract` e `mcp-tools.json`). O protocolo do coletor é um subconjunto dessas rotas (`contracts/http-api.md`), com cabeçalho de versão (`X-Sociman-Coleta-Protocolo: 1`, 426 se diferente). O contrato do serviço `coletor` (`contracts/coletor.md`) não entra no OpenAPI: é CLI e payloads validados por Pydantic nos dois lados |
| **V. Segurança e segredos** | ✅ | Token `scol_` só como hash, mostrado uma vez, rotação e revogação (clone do MCP), padrão no `check:secrets`; portão global que recusa o token fora de `/api/coleta/*`, com `Origin` e com a coleta desligada; `MERCADO_HASH_PEPPER` no `.env` da raiz (gerado pelo dono). No host: perfil do Chrome `700`, porta CDP efêmera só em loopback, `flock`, token em arquivo `600`, logs sem dado pessoal, capturas desligadas. A sessão da conta de afiliado **nunca** chega à API. CSP e portas inalteradas |
| **VI. Testes antes de pronto** | ✅ | Unitários (fórmulas, cadência, revezamento, idempotência, poda, token), integração (ingestão com o coletor falso, fila, trilha, permissões, migration, só-inserção, sem perfil no lago, HD ausente), guardas (I, IX, VII), e2e (`mercado.spec.ts`), e no coletor os testes próprios. As regras inegociáveis têm teste no backend: só leitura (AST do coletor + sem rede na API), aceite de risco antes de ligar (SC-003), nada apagado (SC-004/SC-005), terceiros por hash (SC-006) |
| **VII. Humano no controle** | ✅ | Versionados com `history.record`: `coleta_clientes`, `coleta_config` (aceite, interruptor, tetos), `mercado_perfil_config`, `mercado_interesses` (inclusive os criados por `system:mercado`), o vínculo em `produtos`. O lago é **observação da rede**: fichas versionadas por conteúdo (só inserção) e fotos só de inserção, sem autor humano, como as fotos da 016 (exceção já aceita lá). **Nenhuma eliminação**: a 026 não usa nem amplia as exceções da 4.3.0; nem a limpeza de 90 dias se aplica. Reversão: interesses, config do perfil, config da coleta e clientes (só dono) |
| **VIII. Simplicidade** | ⚠️ justificado | Um aplicativo novo fora do compose (`apps/coletor/`), um bucket novo e 20 tabelas. Justificativas em Complexity Tracking. Nenhum serviço novo no compose, nenhuma dependência nova na API, nenhuma fila fora do PG |
| **IX. Coleta de mercado** | ✅ | Só leitura com lista fechada e teste; serviço separado no desktop, fala só com a ingestão; API sem navegador nem hosts da rede; ritmo do servidor; interruptor em dois níveis com aceite de risco (`coleta_config.risco_aceito_em`, `docs/decisoes/coleta-mercado.md`); captcha/login param e avisam; terceiros por hash (fotos de clientes guardadas por decisão registrada do dono); lago neutro e permanente; tudo estimado; nenhuma recomendação vira ação (a 028 é só proposta) |
| Restrições: coletor fora do Docker | ✅ | `apps/coletor/` com `pyproject` próprio; unidade systemd de usuário; só ele automatiza navegador |
| Restrições: armazenamento NVMe × HD | ✅ | Imagens e bruto no MinIO do HD; PG só com o normalizado e as referências; marcador e piso em toda gravação; sem HD, item "bruto pendente" |
| Restrições: Redis | ✅ | Só limite do portão e estado efêmero do coletor; nada de registro |
| Restrições: banco | ✅ | `0025_mercado_shop` (provisório) com upgrade/downgrade e `test_migration_0025`; a coluna da 012 só entra se a tabela `produtos` existir (ver Dependências) |
| Restrições: portas | ✅ | Nenhuma porta nova; o coletor usa o edge (8543/8180) |
| Restrições: containers UID 1000 | ✅ (não afetado) | Nenhum container novo |

**Reavaliação pós-design:** mantida. O design confirmou que a fila é uma tabela nunca apagada montada pela
trilha (R12), que as imagens do lago ficam no bucket `imagens` com prefixo para o imgproxy servir miniaturas
sem mudar a CSP nem o `IMGPROXY_ALLOWED_SOURCES` (R9), e que o único ponto de contato com a rede é o
processo no host. Todas as rotas novas estão classificadas no `mcp/mapa.py`: ingestão em `FORA`, gestão e
escritas em `PROIBIDAS`, leituras `mercado_*` e `coleta_estado` em `TOOLS` (escopo `leitura`).

## Decisões do dono (brainstorm e clarificações de 2026-10-08)

Registradas no insumo e na spec; o plano as segue sem reabrir:
1. Coleta própria com a **conta de afiliado do dono**, um perfil de Chrome logado sempre; risco aceito e
   registrado (`docs/decisoes/coleta-mercado.md`).
2. Coletor no **Chrome real do desktop**, ingestão por API com token; nunca escrita direta no banco.
3. **Lago global e permanente**, sem perfil; nada apagado; multi-tenant em spec futura (o interesse ganha o
   tenant).
4. Cadência 2/dia para quentes e manuais; avaliações e vídeos só para quentes (1ª visita + 30 d; 7 d).
5. Vitrine vale para todos os perfis; revezamento entre perfis quando a fila passa do teto.
6. Fotos de clientes nas avaliações guardadas como vêm; autor por hash.
7. Qualquer humano acompanha, pausa, encerra e segue loja; reversão só dono; MCP só lê.
8. Vídeos top já na 026; vínculo com a 012 agora (condicionado ao merge da 012).

## Dependências e ordem

- **012 (produtos)** está sendo implementada em outra sessão a partir do mesmo HEAD; esta worktree não tem o
  pacote `produtos/` nem a migration `0022`. A migration da 026 **não** cria a coluna `produtos.mercado_produto_id`
  se a tabela não existir; a tarefa "Adotar no catálogo" (US6) e a coluna ficam numa fase final, executada
  depois do merge da 012 (ou numa migration `0026` própria, se a ordem de merge inverter). O gate T001 decide.
- **Constitution 4.4.0** já aplicada. A emenda prevista pela 011 passa a ser a 4.5.0.
- **Dependências externas do dono** (X1–X7 do insumo; detalhadas no quickstart): perfil do Chrome logado,
  categorias do nicho, token, aceite de risco, unidade systemd, sonda `uma-vez --limite 3`, lista inicial.

## Project Structure

### Documentation (this feature)

```text
specs/026-mercado-shop/
├── plan.md              # este arquivo
├── research.md          # Phase 0: R1–R24 (Chrome/CDP, systemd, orçamento, payloads, borda, SQL, trilha, rede, testes, volume, imgproxy, 027/028)
├── data-model.md        # Phase 1: 20 tabelas + coluna da 012, enums, índices, versionado × foto × operacional
├── contracts/
│   ├── http-api.md      # rotas /api/coleta/* e /api/mercado/*, permissões, erros, classificação MCP
│   └── coletor.md       # serviço do host: CLI, config, protocolo, ações permitidas, payloads tiktok_shop/1, eventos
├── quickstart.md        # Phase 1: validação automática, sonda guiada com o dono, ligar de verdade, conferir o cockpit
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
apps/coletor/                                   # NOVO aplicativo (host, fora do Docker)
├── pyproject.toml                              # python 3.12, uv; deps: playwright, httpx, pydantic
├── README.md                                   # instalação pelo dono (quickstart §2)
├── systemd/sociman-coletor.service             # unidade de usuário (sessão gráfica)
├── sociman_coletor/
│   ├── main.py                                 # CLI: rodar | uma-vez --limite N | dry-run | autoteste | perfil-iniciar | parar | reprocessar --desde
│   ├── config.py                               # ~/.config/sociman-coletor/config.toml + token (600)
│   ├── api.py                                  # cliente httpx da ingestão (fila, coletas, itens, imagens, batimento, fim, eventos, bruto)
│   ├── navegador.py                            # acha/lança o Chrome, DevToolsActivePort, connect_over_cdp, flock
│   ├── navegacao.py                            # CLIQUES_PERMITIDOS, rolagem, fechar aviso (única fonte de cliques)
│   ├── ritmo.py                                # puro: pausas, blocos, "o menor dos dois" limites (RNG semeado)
│   ├── janela.py                               # puro: janela de horário no fuso do mercado
│   ├── sinais.py                               # captcha, login perdido, bloqueio suspeito, layout mudou
│   ├── privacidade.py                          # poda de chaves pessoais do bruto
│   ├── imagens.py                              # download no contexto do navegador, sha256, teto
│   ├── log.py                                  # logger sem dado pessoal
│   └── redes/
│       ├── base.py                             # Protocol ColetorRede
│       └── tiktok_shop.py                      # INTERCEPTAR (padrões de URL), parsers → tiktok_shop/1
└── tests/                                      # parsers (JSON sintético), ritmo, janela, api (transporte falso), servidor HTML sintético, guardas (AST)

apps/api/src/sociman_api/
├── coleta/                                     # NOVO: ingestão, clientes, config, portão
│   ├── models.py                               # coleta_clientes, coleta_config, coleta_eventos
│   ├── credenciais.py                          # scol_<8>_<43>, só SHA-256 (molde mcp/credenciais.py)
│   ├── portao.py                               # dependência global para Bearer scol_
│   ├── ingestao.py                             # valida, normaliza (fonte da rede), grava fichas/fotos/imagens/bruto, idempotência
│   ├── fila_api.py                             # GET fila: reserva, limites, orçamento restante
│   ├── service.py                              # clientes, config, aceite, pausar, continuar, eventos → notificações
│   ├── schemas.py
│   └── router.py                               # /api/coleta/* (coletor e dono)
├── mercado/                                    # NOVO: lago, interesse, leitura, trilha
│   ├── models.py                               # tabelas do lago + interesse (data-model.md)
│   ├── mercados.py                             # BR = fuso + moeda (em código)
│   ├── constantes.py                           # todas as constantes nomeadas
│   ├── fontes/base.py, fontes/tiktok_shop.py, fontes/registro.py   # adaptador por rede (molde publicacao/registro.py)
│   ├── cadencia.py                             # puro: calor e próxima coleta
│   ├── fila.py                                 # monta a fila do dia: níveis, revezamento por perfil, orçamento, leases
│   ├── interesses.py                           # acompanhamentos, categorias do perfil, seguir loja (history)
│   ├── calculo.py                              # puro: fórmulas (FR-044..FR-049)
│   ├── consulta.py                             # SQL de leitura (DISTINCT ON/LAG), cartões, séries, rankings, lojas, resumo
│   ├── filtros.py                              # filtro comum
│   ├── adotar.py                               # ponte com a 012 (fase final)
│   ├── trilha.py                               # trilha `mercado` do agendador
│   ├── schemas.py
│   ├── router.py                               # /api/mercado/*
│   └── router_perfil.py                        # /api/perfis/{id}/mercado/*
├── agendador.py                                # + Trilha("mercado", …)
├── config.py                                   # + coleta_habilitada, agendador_mercado_s, mercado_hash_pepper, coleta_protocolo
├── auth/deps.py                                # + Actor(kind="coletor"), RequireColetor
├── notificacoes/models.py                      # + coleta_captcha, coleta_login, coleta_bloqueio, coleta_layout, coleta_parada, mercado_interesse_auto
├── integracoes.py                              # + bloco `coleta`
├── storage.py                                  # + bucket "mercado" (sociman-mercado)
├── mcp/mapa.py                                 # classificação das rotas novas
└── main.py                                     # routers + portão global

apps/api/migrations/versions/0025_mercado_shop.py
apps/api/tests/{fakes/coletor_fake.py, unit/test_mercado_*.py, unit/test_coleta_*.py, integration/test_mercado_*.py, integration/test_coleta_*.py, integration/test_migration_0025.py, unit/test_constitution_guards.py (seção 026)}

apps/web/src/
├── pages/mercado/{Mercado.tsx, ProdutoMercado.tsx, abas/*.tsx}
├── pages/perfis/tabs/MercadoTab.tsx
├── pages/configuracoes/Coleta.tsx
├── components/mercado/{CartaoProduto.tsx, SerieProduto.tsx, Estimado.tsx}
├── lib/mercado.ts                              # hooks TanStack Query
└── nav.ts                                      # "Mercado de produtos" (Analytics), "Coleta de mercado" (Configurações, só dono); aba "Mercado" de /app/metricas → "Fontes"

docker/nginx/default.conf.template              # locations: …/coletas/[^/]+/imagens (60m, sem buffer), …/coletas/[^/]+/itens (10m)
scripts/check-secrets.mjs                       # padrão scol_
e2e/{mercado.spec.ts, fakes/coletor_fake.py}    # coletor falso no openshorts-fake
```

**Structure Decision**: web existente (`apps/api` + `apps/web`) mais **um aplicativo novo fora do compose**
(`apps/coletor/`), porque o navegador real precisa da sessão gráfica do dono e nenhum container pode ganhar
automação de navegador (princípio IX). Na API, dois pacotes separados: `coleta/` (quem fala com o coletor:
token, portão, ingestão) e `mercado/` (o lago e a leitura), para o guarda "sem HTTP de saída" e "sem perfil
no lago" cobrirem os dois sem exceção.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Aplicativo novo fora do compose (`apps/coletor/`) | O princípio IX exige um serviço separado que use o navegador real do dono, com sessão gráfica; nenhum container pode automatizar navegador | Container com Chromium headless: mais detectável e sem como o dono resolver captcha; o dono também recusou perfil anônimo. Script solto em `tools/`: sem fila, sem token, sem testes |
| 20 tabelas novas | O lago separa identidade (produto, loja, categoria), ficha versionada por conteúdo, fotos só de inserção por fonte e turno, rankings, avaliações, vídeos, imagens deduplicadas, fila, rodadas, itens e eventos; e a camada de interesse fica à parte para o multi-tenant futuro | Uma tabela `mercado_fotos` genérica com jsonb: perde as unicidades (idempotência), os triggers só-inserção por tabela e os índices das consultas em < 2 s. Juntar ficha e foto: a ficha mudaria a cada dia |
| Bucket novo `sociman-mercado` | O bruto gzip não é imagem e não deve ser servido pelo imgproxy; precisa de prefixo e política próprios no HD | Guardar o bruto em jsonb no PG: 90 MB/dia no NVMe, contra a restrição NVMe × HD |
| Ator novo `coletor` e portão global | O token do coletor não é usuário nem cliente MCP; o portão global é o único jeito de recusar o token em qualquer rota fora da ingestão (como o do MCP) | Reaproveitar `mcp_clientes` com um escopo novo: misturaria dois atores com regras diferentes (o MCP lê o domínio; o coletor só ingere) e o `mapa.py` ficaria ambíguo |

## Riscos acompanhados no plano

| Risco | Onde está a mitigação |
|---|---|
| A rede restringe a conta de afiliado do dono | FR-015/016/017, aceite de risco (FR-034), kill switch (FR-019/033); registro em `docs/decisoes/coleta-mercado.md` |
| Layout ou API interna muda | parsers no coletor + bruto completo + `reprocessar --desde` (R8); evento `layout_mudou` |
| Orçamento de 300 páginas insuficiente | níveis e revezamento (FR-026), avaliações e vídeos só quentes (FR-040a), imagens com teto próprio (R6) |
| 012 chega depois da 026 | fase final condicionada; migration sem a coluna se a tabela não existir |
| Teste de tempo oscila sob carga | `test_mercado_desempenho` com 10× volume e meta de 2 s, como a 019; medir isolado |
