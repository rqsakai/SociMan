# Implementation Plan: Rascunho e publicação agendados no TikTok (015-tiktok-rascunho)

**Branch**: `015-tiktok-rascunho` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/015-tiktok-rascunho/spec.md`

## Summary

A 015 executa na TikTok os agendamentos automáticos que a 014 só modelou. É a primeira spec sob o
princípio I da constitution 4.0.0 ("Publicação só com decisão humana"). Tem cinco blocos:

- **Conexão (US1):** o dono conecta uma conta TikTok pelo Login Kit. O retorno cai numa rota do
  SPA, que conclui com um `POST` autenticado. Há dois endereços configuráveis: Web pelo IP da casa
  (HTTPS) e Desktop em `localhost` (PKCE). O `state` fica no Redis, é de uso único e fica preso ao
  dono. A conta autorizada tem de ser a cadastrada (`username` = `contas.handle` e o mesmo
  `open_id`). Os tokens ficam cifrados com AES-256-GCM (`SOCIMAN_TOKENS_KEY`) numa tabela fora do
  histórico. A renovação roda sob `SELECT … FOR UPDATE`, porque a TikTok rotaciona o refresh
  (research R1 a R5).
- **Execução (US2, US3):** uma trilha nova, `publicacao`, no agendador. Ela reivindica os destinos
  automáticos vencidos com `SKIP LOCKED` e grava cada passo **antes** de chamar a rede: tentativa
  `iniciando`, depois `publish_id`, depois partes enviadas. O vídeo vai do MinIO (HD) para a TikTok
  em partes de 16 MB, com `FILE_UPLOAD`, e o `status/fetch` acompanha até `rascunho_criado`,
  `publicado` ou `falhou`. **O `init` nunca é repetido automaticamente.** Um corte entre o envio e a
  resposta vira `incerta`, e só o dono tenta de novo (R6 a R9).
- **Limites (FR-007):** o limite de 5 rascunhos em 24 h é contado localmente, com espera
  "aguardando vaga". As taxas por token passam por um limitador no Redis compartilhado pela API e
  pelo agendador (R10).
- **Controle (US4):** o interruptor tem dois níveis, `PUBLICACAO_HABILITADA` no `.env` e o botão na
  tela. Agendamentos vencidos há mais de 1 h pedem confirmação do dono. `RequireHumanOwner` recusa
  e registra qualquer ator que não seja um dono humano. A trilha confere de novo a decisão humana
  antes de enviar (R11, R15).
- **Publicar (US3):** a tela obrigatória da TikTok usa `creator_info` na hora, privacidade sem
  padrão, toggles, divulgação comercial e consentimento. A 015 guarda um **snapshot** do que o dono
  confirmou e revalida esse snapshot no horário. No sandbox, só `SELF_ONLY`. A situação do app
  (`sandbox` ou `auditado`) é configuração (R12, R13).

O módulo `publicacao/` é o único lugar que fala com a TikTok. Ele tem uma interface de executor
por rede (R20), para YouTube e Instagram entrarem depois sem mudar a central (FR-013). Detalhes em
[research.md](research.md), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md) e [quickstart.md](quickstart.md). As perguntas ao
dono foram respondidas em 2026-09-29 (spec, Clarifications: Q1 A, Q2 A, Q3 A, Q4 A);
[open-questions.md](open-questions.md) está resolvido.

## Technical Context

**Language/Version**: Python 3.12 (API e agendador) · TypeScript 5 / React 19 (SPA)

**Primary Dependencies**:
- **Python:** **`cryptography`** (nova, só para `AESGCM`; ver Complexity Tracking). `httpx`, a
  fonte de dados do agendador, o MinIO e o Redis já existem. Nenhum SDK de rede social (o guarda
  `test_nenhum_sdk_de_rede_social` continua).
- **SPA:** nada novo.

**Storage**:
- PostgreSQL (NVMe): tabelas novas `conexoes`, `conexao_credenciais`, `publicacao_config` e
  `publicacao_tentativas`; `postagens` ampliada; enums `conexao_estado` e `tentativa_fase`;
  `destino_estado` + `enviando`; `notificacao_tipo` com 5 valores novos. Migration
  **`0010_publicacao_tiktok`** (down_revision `0009_central_conteudos`).
- MinIO (HD): leitura em partes do vídeo final (`sociman-videos`) e avatar do criador (`sociman`).
- Redis: `state` do OAuth (10 min) e contadores de taxa por minuto.

**Testing**:
- pytest na stack efêmera (`npm run test:api`), sempre com a **TikTok falsa**
  (`tests/fakes/tiktok_fake.py`, R18):
  - `test_migration_0010.py` (sobe com destinos da 014 em todos os estados e desce; CHECKs);
  - `unit/test_cifra.py` (AES-GCM, AAD, `key_id`, chave anterior);
  - `unit/test_oauth.py` (URL de autorização, PKCE, `state`);
  - `unit/test_opcoes_tiktok.py` (combinações proibidas, sandbox);
  - `unit/test_erros_tiktok.py` (todo código conhecido tem motivo e ação);
  - `test_conexoes.py` (conectar pelos dois endereços, conta diferente, escopo faltando, `state`
    expirado ou de outro usuário, desconectar revoga e apaga, membro sem botões);
  - `test_renovacao.py` (rotação, duas renovações concorrentes com `FOR UPDATE` e só um refresh
    gasto, `invalid_grant` → `precisa_reconectar` e aviso);
  - `test_trilha_publicacao.py` (rascunho de ponta a ponta, publicar, falhas traduzidas, sem
    vaga, taxa, interruptor nos dois níveis, vencidos e confirmação, conta desconectada, vídeo
    mudou no meio);
  - `test_idempotencia_envio.py` (SC-003: queda injetada depois de cada commit e antes de cada
    chamada; exatamente um `init` por destino, ou `incerta`);
  - `test_guardas_015.py` (SC-004: atores não humanos em cada rota **H**, execução sem decisão
    humana, interruptor);
  - `test_logs_sem_segredo.py` (caplog de um ciclo completo);
  - os testes da 014 ajustados (`test_agendamentos`, `test_destinos`, `unit/test_capacidades`,
    guardas da 014);
- `unit/test_constitution_guards.py`, seção "spec 015" (research R16);
- ruff; `npm run check:web` (contrato regenerado; `check:secrets` com os padrões novos; CSP igual);
- Playwright `e2e/publicacao.spec.ts` na stack efêmera, com a TikTok falsa (R18): conectar,
  conta diferente, rascunho no horário com progresso até "rascunho criado", "Copiar textos",
  falha com "Tentar de novo", interruptor → pausado → religar → vencido → confirmar, membro sem
  botões, tela do Publicar sem valores padrão;
- **teste real no sandbox com o dono** (quickstart §3; SC-002 e SC-005). Nenhum teste
  automatizado chama a TikTok real.

**Target Platform**: a mesma stack. **Sem serviço novo** e sem `location` nova no edge. Os
serviços `api` e `agendador` recebem as variáveis novas no `docker-compose.yml` (o `worker`, não).

**Project Type**: web application (SPA + API + worker + agendador)

**Performance Goals**:
- SC-001: conectar = 1 clique + login na TikTok + 1 `POST` (menos de 2 min, quase todo na TikTok);
- SC-002: rascunho na caixa de entrada em até 5 min: reivindicação em até 15 s (intervalo da
  trilha), init menor que 2 s, upload de um corte típico (20 a 100 MB) em 5 a 30 s pela conexão
  da casa, e status consultado a cada 10 s (recuo até 60 s);
- a trilha nunca bloqueia as outras (thread própria, 014/006).

**Constraints**:
- princípio I: só destino **aprovado e agendado por dono humano**, no modo que ele escolheu; só
  por `publicacao/`; interruptor em dois níveis; histórico completo;
- nunca repetir `init` sem um humano; nunca dois rascunhos para o mesmo destino;
- tokens cifrados e nunca em log, resposta, histórico ou MCP;
- CSP e edge sem mudança; nenhum endereço público (FILE_UPLOAD + consulta de status);
- sem DELETE no domínio; a única exclusão física é a credencial (segredo), ao desconectar.

**Scale/Scope**:
- 2 contas TikTok hoje (sandbox, até 10 usuários-alvo), cerca de 5 rascunhos por conta por dia
  (o limite da TikTok);
- cerca de 10 rotas novas e 8 rotas da 014 com regras novas;
- telas: `ConexaoCard`, `/app/conexoes/retorno`, configuração de publicação, `TikTokPostForm`
  no `AgendarDialog`, execução e histórico no `DestinoPanel`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|---|---|---|
| **I. Publicação só com decisão humana** | ✅ | **Só destino aprovado e agendado por dono:** a trilha reivindica apenas `agendado` com `aprovado_por` e `agendado_por` preenchidos (CHECK `ck_postagens_auto_decisao`), confere que a última versão de agendamento tem `actor_kind = 'user'` e envia o **snapshot** que o dono confirmou (R13, R15). **Nenhuma IA, agente ou MCP:** `RequireHumanOwner` (`kind == "user"` + dono) em conectar, desconectar, interruptor, tentar de novo e confirmar vencido; no service, em agendar, reagendar (inclusive em lote), editar snapshot, cancelar e arquivar em modo automático. Recusa → 403 `somente_humano` + `SecurityEvent`. **Só pelo módulo autorizado:** `open.tiktokapis.com` só em `publicacao/tiktok/`; só `publicacao/registro.py` importa o executor; o cliente tem `ALLOWED` fechado (R16, R21). **Histórico:** cada transição do destino tem `history.record` (humano ou `system:publicacao`), e as tentativas guardam início, fim, `publish_id`, versão do arquivo e motivo (FR-011). **Cancelar antes do horário:** o dono cancela em `agendado` (e em `falhou`); em `enviando` o post já existe na TikTok, e a tela explica. **Interruptor:** `PUBLICACAO_HABILITADA` (servidor) **e** "Envios automáticos" (tela); qualquer um desligado deixa os vencidos `pausado`, visíveis, e impede todo init e todo PUT de parte, inclusive dos envios em andamento (R11). **Guardas:** as rotas continuam sem `tiktok`/`publish`; as listas só crescem; exceções só por pasta de `publicacao/` (R16) |
| II. Direito é responsabilidade do dono | ✅ (não afetado) | O envio para a rede não bloqueia por status de direito. O aviso da 006 para `sem_acordo` continua no envio para corte. O histórico da tentativa liga o vídeo enviado ao corte, e o corte ao canal-fonte |
| III. Marca em tokens | ✅ | O arquivo enviado é o vídeo final com a marca do worker (004). "Aplicar marca" fica bloqueado durante o envio (R9). Nenhuma marca d'água do app é acrescentada (regra da TikTok, pesquisa §1.4) |
| IV. Contrato é a fonte única | ✅ | Rotas novas e ampliadas no OpenAPI → `gen:contract`. `OpcoesTikTok` é um schema Pydantic (sem tipo copiado no SPA) |
| **V. Segurança e segredos** | ✅ | **Tokens cifrados:** AES-256-GCM com AAD por linha e campo, nonce aleatório e `key_id` para rotação (R4). **Chave no `.env`:** `SOCIMAN_TOKENS_KEY` (`SecretStr`), só em `api` e `agendador`. Sem ela, nada conecta nem envia. **Nunca no log:** `redact()` em todo erro, logger `httpx` em WARNING, corpo e `upload_url` (que leva `upload_token`) nunca registrados, `upload_url` cifrado no banco e apagado ao fim do upload, credencial fora do histórico e fora de qualquer schema de saída, teste de caplog. **Segredos no repo:** `check:secrets` com os padrões novos. **CSP:** igual; o avatar vai pelo MinIO + `/img` (R14). **Edge:** sem `location` nova; a API continua sem porta publicada. **OAuth:** `state` de uso único preso ao dono, PKCE no Desktop, conferência da conta autorizada (R2, R3) |
| VI. Testes antes de pronto | ✅ | pytest (migração, cifra, OAuth, renovação concorrente, trilha, idempotência, guardas, logs), ruff, `check:web` e e2e com a TikTok falsa. Os princípios I e VII têm teste automatizado. O teste real no sandbox é passo do quickstart, com o dono |
| VII. Humano no controle | ✅ com uma exceção justificada | `conexoes`, `publicacao_config` e destinos com `version`, `check_version` e `history.record`. A trilha é um autor identificado (`system:publicacao`). A reversão nunca restaura estados de execução nem snapshots. **Exceção:** `conexao_credenciais` é **apagada** ao desconectar, porque FR-002 exige apagar as credenciais e segredo não é dado de domínio. O fato ("desconectada por X em Y") fica na versão da `conexao`. Nenhuma rota DELETE |
| VIII. Simplicidade | ✅ com justificativa | Uma dependência (`cryptography`), quatro tabelas, uma trilha e nenhum serviço novo. Estados que dependem de relógio ou configuração são derivados. A interface de executor tem uma só implementação e é o mínimo para isolar a TikTok. Ver Complexity Tracking |

**Reavaliação pós-design:** mantida. Pontos a confirmar no sandbox, sem impacto no gate: aceite
do IP privado no portal (R1), formato do `code_challenge` (R1), PUT repetido da mesma parte (R8),
contagem de rascunhos pendentes (R10) e se o rascunho vira post público pelo app (SC-005).

### Guardas (testes automatizados do princípio I)
Em `tests/unit/test_constitution_guards.py` (seção "spec 015") e
`tests/integration/test_guardas_015.py` (detalhes em research R16):
1. `open.tiktokapis.com` só em `publicacao/tiktok/`; os demais endpoints continuam proibidos em
   todo o `src/`;
2. só `publicacao/registro.py` importa `publicacao.tiktok`;
3. `ALLOWED` fechado; PUT só para o host de upload; inbox sem `post_info`; init direto só com o
   snapshot;
4. AST: `rascunho_criado`/`publicado`/`falhou` só em `publicacao/trilha.py::_concluir`,
   `enviando` só em `_reivindicar`, `postado` só em `marcar_postado`;
5. rotas sem termos proibidos (sem exceção) e as rotas **H** com `require_human_owner`;
6. trilhas = `{sync, openshorts, importacao, lembretes, publicacao}`; com qualquer nível do
   interruptor desligado, nenhuma chamada ao fake e nenhum destino muda;
7. CHECKs da 0010 com `INSERT`/`UPDATE` direto;
8. `Actor(kind="mcp_client")` com usuário dono em cada rota **H** e em agendar em modo automático
   → 403 `somente_humano`, sem mudança, com evento;
9. um destino `agendado` gravado direto no banco com `agendado_por` de uma versão `system:*` →
   a trilha recusa e registra o evento;
10. `test_listas_do_guarda_nao_encolheram` inalterado.

Fora do escopo, de propósito:
- YouTube e Instagram (specs próprias, com executor em `publicacao/<rede>/`);
- `rascunho_e_publicar` (a TikTok não permite; continua bloqueado no banco);
- webhooks da TikTok (exigem endereço público);
- link de produto do TikTok Shop (não existe na API; o dono põe no app);
- auditoria do app na TikTok (improvável, pesquisa §1.7); a mudança é só `TIKTOK_APP_SITUACAO`;
- exposição no MCP (009): nenhuma rota **H** vira tool.

## Project Structure

### Documentation (this feature)

```text
specs/015-tiktok-rascunho/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── open-questions.md
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── pyproject.toml                                   # + cryptography
├── migrations/versions/0010_publicacao_tiktok.py    # NOVO
├── src/sociman_api/
│   ├── publicacao/                                  # NOVO pacote: o ÚNICO que fala com rede social
│   │   ├── models.py        # Conexao, ConexaoCredencial, PublicacaoConfig, Tentativa; enums
│   │   ├── cifra.py         # AES-256-GCM, key_id, chave anterior, AAD (R4)
│   │   ├── conexoes.py      # iniciar, retorno, desconectar, token_valido (FOR UPDATE, R5)
│   │   ├── limites.py       # taxa no Redis, contagem de rascunhos 24 h (R10)
│   │   ├── executor.py      # Protocol ExecutorRede + tipos de resultado (R20)
│   │   ├── registro.py      # EXECUTORES = {Platform.tiktok: TikTokExecutor}; único import de tiktok/
│   │   ├── trilha.py        # rodar(db, client=None): retomar, _reivindicar, _concluir, _devolver (R6–R9)
│   │   ├── service.py       # config (interruptor), tentar_de_novo, confirmar_envio, exigir_humano_dono
│   │   ├── schemas.py       # Conexao, Criador, OpcoesTikTok, PublicacaoConfig, Tentativa
│   │   ├── router.py        # /api/contas/{id}/conexao*, /api/conexoes/retorno, /api/publicacao/config,
│   │   │                    #   /api/destinos/{id}/{tentativas,tentar-de-novo,confirmar-envio}
│   │   └── tiktok/
│   │       ├── cliente.py   # httpx, ALLOWED, URL base, hosts de upload/CDN, redact, erros tipados
│   │       ├── oauth.py     # URL de autorização, PKCE, troca, refresh, revogação, user/info
│   │       ├── executor.py  # TikTokExecutor: init inbox/direto, partes, status, creator_info
│   │       ├── opcoes.py    # regras da tela obrigatória (R13)
│   │       └── erros.py     # código → (motivo pt-BR, ação) (R19)
│   ├── conteudos/
│   │   ├── capacidades.py   # camadas 2 e 3 reais; ModoInfo.aviso; TIKTOK_APP_SITUACAO (R12)
│   │   └── consulta.py      # estados efetivos pausado/vencido/aguardando_vaga/enviando; atalhos
│   ├── postagem/
│   │   ├── models.py        # DestinoEstado.enviando; colunas novas
│   │   ├── service.py       # agendar/reagendar/cancelar/textos com regras do modo automático,
│   │   │                    #   snapshot, marcar_postado de rascunho_criado, bloqueio em enviando
│   │   └── schemas.py       # Destino/DestinoResumo ampliados
│   ├── cortes/service.py    # "Aplicar marca" e arquivar: 409 envio_em_andamento
│   ├── storage.py           # sem mudança: reusa get_range(key, offset, length, bucket) e stat(key, bucket)
│   ├── auth/deps.py         # + require_human_owner / RequireHumanOwner
│   ├── notificacoes/models.py   # + 5 tipos
│   ├── config.py            # variáveis novas (SecretStr), sem URL da TikTok
│   ├── agendador.py         # trilha `publicacao` + _registrar_modelos(publicacao)
│   ├── cli.py               # `sociman tokens recifrar`
│   └── main.py              # inclui o router de publicacao
└── tests/
    ├── fakes/tiktok_fake.py, fixtures/tiktok/*.json     # NOVOS (R18)
    ├── unit/                # test_cifra, test_oauth, test_opcoes_tiktok, test_erros_tiktok; guardas 015
    └── integration/         # test_migration_0010, test_conexoes, test_renovacao, test_trilha_publicacao,
                             #   test_idempotencia_envio, test_guardas_015, test_logs_sem_segredo; 014 ajustados

apps/web/src/
├── pages/conexoes/Retorno.tsx                        # NOVA (/app/conexoes/retorno)
├── pages/configuracoes/Publicacao.tsx                # NOVA (interruptor, situação, vencidos)
├── components/publicacao/
│   ├── {ConexaoCard,TikTokPostForm,ExecucaoStatus,HistoricoEnvio,CopiarTextos}.tsx
├── components/conteudos/{AgendarDialog,DestinoPanel,EstadoBadge}.tsx   # modo automático, execução
├── pages/perfis/ContasTab.tsx                        # ConexaoCard nas contas TikTok
├── App.tsx, components/shell/nav.ts                  # rotas e item de configuração (dono)
└── lib/publicacao.ts                                 # queries e rótulos pt-BR (fases, estados, motivos)

docker-compose.yml, docker-compose.e2e.yml   # variáveis novas em api/agendador; e2e aponta ao fake
e2e/fakes/server.py                          # + /tiktok/v2/* (R18)
e2e/publicacao.spec.ts                       # NOVO
scripts/check-secrets.mjs                    # padrões SOCIMAN_TOKENS_KEY / TIKTOK_CLIENT_SECRET
```

**Structure Decision:**
- `publicacao/` é o **único** pacote que fala com rede social (princípio I). Dentro dele, uma
  subpasta por rede (`tiktok/`) e uma parte genérica (trilha, conexões, cifra, limites) que não
  conhece a TikTok, só o `ExecutorRede`;
- a central da 014 (`conteudos/`, `postagem/`) só ganha regras: capacidades reais, estados
  derivados, permissões por modo e snapshot. Nenhuma importação de `publicacao.tiktok` fora de
  `registro.py`;
- a trilha fica no agendador existente (R6), sem serviço novo.

**Migration:** `0010_publicacao_tiktok`, `down_revision = "0009_central_conteudos"` (data-model).

### O que muda na 014
| Onde | Mudança |
|---|---|
| CHECKs `ck_postagens_modo_014` e `ck_postagens_estados_015` | trocados por `ck_postagens_modo_015` (`rascunho_e_publicar` continua proibido), `ck_postagens_execucao`, `ck_postagens_auto_decisao` e `ck_postagens_publicar_snapshot` (R17) |
| `destino_estado` | + `enviando` |
| `capacidades.py` | camada 2 com `registro.executor_para`, camada 3 com a conexão e os escopos, `ModoInfo.aviso` (R12) |
| `consulta.py` (estado efetivo) | + `pausado`, `vencido`, `aguardando_vaga`, `enviando`; `atencao` com motivos de conexão; atalhos novos |
| Permissões (014 Q1) | membro continua agendando **lembrete**; modo automático, cancelar e editar o snapshot passam a exigir **dono humano** (FR-010) |
| Textos (014 Q2) | continuam editáveis sem nova aprovação no lembrete e no rascunho; em `publicar` agendado, só dono, e a edição regrava o snapshot (R13) |
| `marcar_postado` | aceita `rascunho_criado` |
| Arquivar, reverter, "Aplicar marca" | 409 `envio_em_andamento` com destino `enviando` |
| Sequência | aceita `criar_rascunho`; `publicar` fica fora do lote (a tela é por vídeo) |
| Guardas da 014 | lista de trilhas + `publicacao`; lugares permitidos do AST de estados = a trilha; capacidades testadas com e sem conexão |
| `lembretes.py` | sem mudança (já filtra `modo = 'lembrete'`) |

**Ordem sugerida para o `/speckit-tasks`:**
0. migration `0010` + modelos + `test_migration_0010`; `cryptography`; variáveis no compose;
1. `cifra.py` + `cliente.py`/`oauth.py` + fake da TikTok + testes de unidade;
2. conexões (iniciar, retorno, desconectar, renovação com `FOR UPDATE`) + `RequireHumanOwner` +
   testes; `ConexaoCard` e `/app/conexoes/retorno` (US1, P1);
3. capacidades + agendar em `criar_rascunho` (permissões, CHECKs) + guardas 1 a 8;
4. trilha: reivindicar, init, partes do MinIO, status, concluir, retomada + idempotência (US2,
   P1);
5. limites (taxa, sem vaga) + interruptor em dois níveis + vencidos + tela de configuração (US4,
   P1);
6. `DestinoPanel`/histórico do envio/Copiar textos + e2e do rascunho → **teste real no sandbox
   com o dono (quickstart §3)**;
7. Publicar: `creator_info`, `OpcoesTikTok`, snapshot, revalidação, `TikTokPostForm` (US3, P2);
8. e2e completo, caplog, `check:web`, `CLAUDE.md`.

As fases 0 a 6 fecham US1, US2 e US4 (P1) e bastam para o primeiro teste real. US3 vem depois.

## Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| O portal da TikTok recusa `https://192.168.86.47:8543/...` | login pela casa impossível | endereço Desktop (`localhost` + PKCE) já previsto e configurável à parte (R1); quickstart §2 testa os dois |
| Formato do `code_challenge` do Desktop diferente do esperado | login Desktop falha | função única com teste; troca de uma linha; quickstart §2 |
| Refresh aceito pela TikTok e commit perdido (queda) | conta vira "precisa reconectar" | commit imediato; aviso; reconectar leva menos de 2 min (R5) |
| Queda entre o `init` e a resposta | rascunho possivelmente criado sem registro | fase `incerta`, nunca reenvio automático, "Tentar de novo" com confirmação (R8) |
| Contagem local de "5 pendentes" diferente da real | espera demais ou erro da TikTok | contam as tentativas com init nas últimas 24 h (abertas, entregues e incertas); o erro da TikTok também leva a `sem_vaga`; ajuste após o teste real (Q1 = A) |
| Rascunho do sandbox não pode virar post público no app | o fluxo só serve para testes | é justamente o SC-005; registrado no quickstart §3.6; decide o próximo passo do dono |
| O vídeo muda durante o envio (marca reaplicada) | arquivo corrompido na TikTok | bloqueio de "Aplicar marca" + conferência de `etag` por parte (R9) |
| Interruptor desligado com envio em andamento | envio continuar com o interruptor desligado (contra o princípio I e a Q3) | nenhum init nem PUT com qualquer nível desligado; a parte em curso para, o destino aparece `pausado` e retoma ao religar, ou vira `recusada` se o link expirou (sem upload completo não há rascunho); a tela avisa quantos ficaram pausados (R11) |
| Chave `SOCIMAN_TOKENS_KEY` perdida | tokens ilegíveis | todas as contas vão para "precisa reconectar" com aviso; nenhum dado de domínio se perde; quickstart §0 manda guardar a chave junto do backup |
| Chave vazada | tokens decifráveis por quem tem o banco | rotação com `SOCIMAN_TOKENS_KEY_ANTERIOR` + `sociman tokens recifrar`; revogar e reconectar as contas |
| Uso da API marca as contas (cortes de terceiros) | denúncia ou banimento | princípio II (o dono decide), limites respeitados, rascunho como padrão, nenhum envio sem dono |
| A TikTok muda códigos de erro ou limites | motivo genérico | fallback "A TikTok recusou (código X)"; o código cru fica na tentativa |
| Upload lento na conexão da casa | SC-002 perto do limite | partes de 16 MB com recuo; tempos por parte em `details` para diagnóstico |

## Complexity Tracking

| Item | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| Dependência `cryptography` | FR-002 e princípio V: tokens cifrados com AAD por linha | stdlib sem AES; `pgcrypto` expõe a chave nas queries; Fernet não tem AAD (R4) |
| Tabela `conexao_credenciais` separada | segredos nunca no histórico nem em schema; apagar sem apagar a conexão | colunas em `conexoes`: `snapshot` e reversão tocariam os tokens |
| `publicacao_tentativas` com fases gravadas | FR-006/SC-003: retomar após reinício sem repetir o `init` | estado só no destino: não diferencia "init enviado sem resposta" de "nunca enviado" |
| Interruptor em dois níveis | constitution (`PUBLICACAO_HABILITADA`) + spec (botão na tela) | só a tela: um token roubado liga tudo; só o `.env`: contra US4 |
| Snapshot do envio (`envio_snapshot`) | princípio I: enviar o que o dono confirmou na tela obrigatória | textos vivos: um membro mudaria a legenda publicada depois da confirmação |
| Interface `ExecutorRede` + `registro.py` | FR-013 e guarda R16.2: a trilha não importa a TikTok | trilha chamando a TikTok direto: o próximo executor duplicaria a máquina de estados |
| Limitador de taxa no Redis | FR-007: API e agendador são processos diferentes | em memória: não é compartilhado |
| Dois endereços de retorno (Web e Desktop) | FR-003 e o risco de o portal recusar o IP | um só: se o portal recusar, o login fica impossível |
