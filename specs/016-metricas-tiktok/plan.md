# Implementation Plan: Métricas do TikTok para análise e machine learning (016-metricas-tiktok)

**Branch**: `016-metricas-tiktok` | **Date**: 2026-09-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/016-metricas-tiktok/spec.md`

## Summary

A 016 lê da TikTok, pela Display API do app que já existe (spec 015), os números públicos das
contas conectadas e dos vídeos públicos delas, e guarda tudo como **série temporal só de
inserção** para as telas e para o dataset de machine learning. Ela não envia nada à rede. Tem
cinco blocos:

- **Permissões (US1):** o login passa a pedir `user.info.stats` e `video.list`. Uma conexão da
  015 sem esses escopos continua publicando, mas mostra "Reconectar para liberar métricas". O
  `iniciar` da 015 passa a aceitar uma conexão `conectada` que não tem esses escopos, e o retorno
  reusa a linha, com o mesmo `open_id` (research R1).
- **Coleta (US2):** uma trilha nova, `metricas`, no agendador. Ela **não** depende de
  `PUBLICACAO_HABILITADA`, porque só lê, mas tem o próprio desligamento
  (`METRICAS_COLETA_HABILITADA`). Por conta, faz 3 coisas:
  - `video/list` (1ª página a cada hora e varredura completa na primeira vez) para descobrir
    vídeos;
  - `video/query` com até 20 ids para os vídeos vencidos na fila `proxima_coleta_em`;
  - `user/info` com os campos de stats para a foto da conta.

  A agenda de cada vídeo é **ancorada na idade**: fotos com 1 h, 2 h … 48 h, depois 3 d … 30 d,
  semanal até 90 d e mensal até 365 d. Uma foto por vídeo por janela: `UNIQUE (video_id,
  alvo_idade_min)` + `ON CONFLICT DO NOTHING`. Um trigger impede UPDATE e DELETE nas tabelas de
  fotos (research R2 a R8, R18).
- **Vínculo (US3):** o vídeo coletado é ligado ao destino em três níveis:
  1. o `status/fetch` do `publish_id`, consultado por até 14 dias com recuo, numa tabela de
     buscas própria (a tentativa da 015 é final e não muda);
  2. o casamento na lista, por data, duração ±1 s e legenda, com candidato único **nos dois
     sentidos**;
  3. o link colado, ou a escolha entre os candidatos.

  Ligar move `rascunho_criado → publicado`; desfazer volta o estado. As duas transições ficam
  numa função só de `postagem/service.py`, que entra na lista do guarda de AST. Num destino de
  **lembrete** (Q3 = A), o casamento automático só roda depois de "Marcar como postado", com a
  âncora no `posted_at` (post até 24 h antes ou 1 h depois); antes do clique, o dono escolhe um
  candidato em 1 clique, e a escolha usa o `marcar_postado` humano de sempre (R9 a R12).
- **Telas (US4):** um gráfico SVG próprio, sem dependência nova e com a CSP igual. Há 4 lugares:
  - a página `/app/metricas`, com o ranking e as contas;
  - a seção "Desempenho" no `DestinoPanel`;
  - a página do vídeo de fora do SociMan;
  - o estado da coleta no `ConexaoCard`.

  Os marcos 1 h/24 h/7 d/30 d são calculados por interpolação linear na idade, com a âncora
  (0, 0) e a marca "estimado" quando as fotos estão longe do marco (R14, R15).
- **Dataset (US5) e desconexão:** a exportação é um ZIP com `fotos_videos`, `videos` (com as
  características do SociMan), `fotos_conta` e `dicionario`, em CSV ou JSON Lines (R16). Ao
  **desconectar**, a série da conta é **anonimizada** por UPDATE, de forma irreversível e com
  confirmação explícita. Os ids, links e textos da TikTok e o elo com conta e destino somem, e
  as características não identificadoras ficam congeladas no vídeo (R13).

O código novo fica em `metricas/`, que é genérico, e em `publicacao/tiktok/leitor.py`, que só
lê. A parte genérica chega ao leitor **só** por `publicacao/registro.py` (o guarda R16.2 da 015
continua valendo). Detalhes em [research.md](research.md), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md) e [quickstart.md](quickstart.md). As 4 perguntas
ao dono estão resolvidas (todas A, spec → Clarifications; [open-questions.md](open-questions.md)).

## Technical Context

**Language/Version**: Python 3.12 (API e agendador) · TypeScript 5 / React 19 (SPA)

**Primary Dependencies**:
- **Python:** nada novo. `httpx`, o cliente da TikTok com lista fechada, `conexoes.token_valido`
  e o limitador no Redis vêm da 015; `zipfile` e `csv` vêm da stdlib;
- **SPA:** nada novo. O gráfico é um componente SVG próprio (R14), sem biblioteca de gráficos.

**Storage**:
- PostgreSQL (NVMe), com a migration **`0011_metricas_tiktok`** (down_revision
  `0010_publicacao_tiktok`):
  - tabelas novas `metricas_series`, `metricas_videos`, `metricas_video_fotos`,
    `metricas_conta_fotos` e `metricas_buscas_post`;
  - enum `vinculo_metodo`;
  - `notificacao_tipo` com 2 valores novos;
  - trigger `metricas_so_insercao` nas duas tabelas de fotos.
- **Volume** (R8): cerca de **95 fotos por vídeo** na vida inteira (48 + 28 + 9 + 10 + 1):
  | Cenário | Vídeos por ano | Fotos de vídeo | Fotos de conta | Espaço (com índices) |
  |---|---|---|---|---|
  | 2 contas, ~2 posts/dia cada | ~1.500 | ~140 mil | ~17 mil | **~30 MB/ano** |
  | 20 contas, ~2 posts/dia cada | ~15.000 | ~1,4 milhão | ~175 mil | **~300 MB/ano** |

  Não há particionamento nem TimescaleDB. O ponto de revisão fica em cerca de 20 milhões de
  fotos.
- **Só PostgreSQL, sem MongoDB nem híbrido** (research R20, open-questions Q4): as métricas são
  pequenas e relacionais (juntam com corte, canal e destino). Vínculo e anonimização precisam
  da mesma transação que o destino. Um segundo banco pediria emenda da stack, outro backup e
  outro serviço nos testes efêmeros. As respostas cruas da API não são guardadas.
- Redis: só os contadores de taxa da 015 (chaves novas `leitura` e `status`, compartilhada);
- MinIO/HD: só a pasta temporária da exportação, quando ela passa de 32 MB
  (`SpooledTemporaryFile` em `work/exports`).

**Testing**:
- pytest na stack efêmera (`npm run test:api`), sempre com a **TikTok falsa** ampliada (R17):
  - `test_migration_0011.py`: sobe e desce, CHECKs, trigger recusando UPDATE e DELETE;
  - `unit/test_agenda_metricas.py`: cadência por idade, recuperação de atraso, fim em 365 d e
    agenda da conta;
  - `unit/test_marcos.py`: interpolação, âncora (0, 0), estimado, "ainda não" e queda de
    contagem;
  - `unit/test_casamento.py`: normalização da legenda, duração ±1 s, unicidade nos dois
    sentidos e as duas âncoras (entrega −5 min/+14 d; `posted_at` do lembrete −24 h/+1 h);
  - `unit/test_link_tiktok.py`: formatos de link aceitos e recusados;
  - `test_coleta_metricas.py`: varredura inicial, fila, lote de 20, indisponível, 429, conexão
    perdida, `scope_not_authorized`, isolamento por conta e idempotência com queda injetada;
  - `test_vinculo.py`: os três níveis, ambiguidade, link de outra conta, desfazer/refazer,
    histórico e bloqueio do automático depois de desfazer; lembrete (Q3 = A): nada automático
    antes do clique, candidatos listados, escolha → `postado`, automático depois do clique
    dentro da janela e fora dela não;
  - `test_anonimizacao.py`: desconectar exige confirmação; nada identificável sobra nas tabelas
    `metricas_*`; os números ficam; reconectar começa uma série nova;
  - `test_reconectar_escopos.py`: `iniciar` numa conexão sem os escopos, reuso da linha e
    `ja_conectada` quando os escopos já existem;
  - `test_rotas_metricas.py`: ranking, curvas, filtros e permissões;
  - `test_export_metricas.py`: cabeçalho igual ao dicionário, características, anônimas e tempo
    de um mês;
  - `test_guardas_016.py`: a coleta com os dois níveis do interruptor de publicação desligados
    só faz pedidos de leitura; um cliente MCP não liga vínculo;
  - ajustes nos testes da 015: `test_conexoes` (desconectar com série), `test_trilha_publicacao`
    (o `ALLOWED` cresceu) e o fake.
- `unit/test_constitution_guards.py`, seção "spec 016" (R2), com 4 guardas:
  - `ALLOWED` = R21 ∪ `LEITURA_016`;
  - `metricas/` só importa `registro`, `conexoes`, `models` e `limites` de `publicacao/`;
  - AST: nenhuma chamada de envio (`iniciar`, `enviar_parte`, `put_parte`) fora da trilha de
    publicação;
  - trilhas = 015 + `metricas`; estados da 015 também permitidos em
    `postagem/service.py::publicacao_pelo_vinculo`.
- ruff; `npm run check:web` (contrato regenerado, CSP igual e bundle sem segredo);
- Playwright `e2e/metricas.spec.ts` na stack efêmera, com a TikTok falsa:
  - conta sem escopos → aviso → reconectar → "coletando" e a 1ª foto;
  - rascunho publicado no fake → destino "publicado" com o link;
  - casamento ambíguo → escolher o post;
  - lembrete: candidatos antes do clique; "Marcar como postado" → ligado sozinho (Q3 = A);
  - link de outra conta recusado; desfazer;
  - ranking com fotos semeadas por SQL e curva com os marcos;
  - exportar ZIP (dono) e membro sem os botões de dono;
  - desconectar com confirmação → série anônima.
- **teste real com o dono** (quickstart §3 e §4): reconectar as 2 contas, conferir a 1ª foto,
  medir a latência do `view_count` e publicar 1 rascunho para o vínculo. Nenhum teste
  automatizado chama a TikTok real.

**Target Platform**: a mesma stack. **Sem serviço novo** e sem `location` nova no edge. O
`agendador` e a `api` ganham `METRICAS_COLETA_HABILITADA` e `AGENDADOR_METRICAS_S`. O
`TIKTOK_SCOPES` padrão ganha `user.info.stats,video.list`.

**Project Type**: web application (SPA + API + worker + agendador)

**Performance Goals**:
- SC-001: a 1ª foto sai em até 1 volta da trilha (60 s) depois da reconexão, bem abaixo de 1 h;
- SC-002: a fila `proxima_coleta_em` é lida a cada 60 s e a janela aceita até 15 min de atraso.
  O custo por conta é de ~3 pedidos por hora (list + query + user/info), menos de 0,1% do
  limite de 600/min;
- SC-003: o `status/fetch` roda a cada 10 min nas 2 primeiras horas depois da entrega e a cada
  30 min até 24 h (R9). O casamento roda a cada descoberta de vídeo, e isso acontece a cada
  hora;
- SC-004: o ranking vem de uma consulta SQL com `LATERAL` por marco, sobre o índice
  `(video_id, idade_s)`, em menos de 300 ms para 2 contas e 1 ano;
- SC-005: a exportação de 1 mês de 1 conta (~60 vídeos, ~4 mil fotos, ~0,5 MB) sai em menos de
  2 s, montada por streaming a partir do banco.

**Constraints**:
- princípio I: só leitura. O cliente recebe 2 entradas novas de leitura. Nada de init nem de
  PUT sai da coleta, e isso é provado por teste;
- fotos só de inserção, garantidas no banco (trigger) e no código;
- a anonimização é UPDATE, nunca DELETE. É irreversível e exige confirmação do dono;
- sem `tiktok`/`publish`/`share` nos caminhos e `operationId`s;
- sem dependência nova; CSP igual. Nenhuma imagem da CDN da TikTok vai para a tela, porque a
  capa expira em 6 h; a tela usa a miniatura do próprio SociMan.

**Scale/Scope**:
- 2 contas hoje (sandbox, até 10 usuários-alvo) e desenho validado para 20;
- 8 rotas novas, 3 da 015 ampliadas (`iniciar`, `retorno` e `desconectar`, mais o `GET
  .../conexao` com `metricas`) e 1 schema ampliado (`Conexao.metricas`);
- telas: `/app/metricas` (ranking e contas), `/app/metricas/videos/:id`, a seção "Desempenho"
  no `DestinoPanel`, o estado da coleta no `ConexaoCard`, `ExportarDialog` e
  `DesconectarDialog` com a confirmação.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|---|---|---|
| **I. Publicação só com decisão humana** | ✅ | A 016 **não envia nada**. **Só leitura:** o `ALLOWED` do cliente cresce só com `POST /v2/video/list/` e `POST /v2/video/query/` (leitura por especificação da API; o `user/info` já estava), agrupados em `LEITURA_016`. O leitor (`publicacao/tiktok/leitor.py`) só chama `user/info`, `video/list`, `video/query` e `status/fetch`. `metricas/` chega ao leitor **só** pelo `registro` e não importa trilha, executor nem service de publicação (guarda de import). **Teste que prova:** um ciclo completo de coleta e de vínculo contra o fake, com `PUBLICACAO_HABILITADA=false` e o botão desligado, registra só `token`, `user_info`, `video_list`, `video_query` e `status` (`test_guardas_016`); a AST confere que `iniciar`, `enviar_parte` e `put_parte` não aparecem em `metricas/` nem no leitor. **Estado `publicado`:** o destino muda por uma observação da rede depois de um humano publicar no app. Isso não é envio, e a única função que faz a mudança (`postagem/service.py::publicacao_pelo_vinculo`) entra na lista do guarda de AST, com teste de que ela só aceita `rascunho_criado ↔ publicado` e só com um vídeo da mesma conta (R12). **Nenhuma IA, agente ou MCP:** ligar, escolher, colar e desfazer vínculo são rotas **H** (`RequireHumanOwner`); o reconectar já era **H**. **Rotas:** `/api/metricas/*`, `/api/contas/{id}/metricas`, `/api/destinos/{id}/{metricas,vinculo}`, sem termos proibidos e sem exceção no guarda. **Trilhas:** a lista do guarda passa a `{sync, openshorts, importacao, lembretes, publicacao, metricas}` |
| II. Direito é responsabilidade do dono | ✅ (não afetado) | O status do canal-fonte entra só como característica informativa na exportação. Nada é bloqueado |
| III. Marca em tokens | ✅ (não afetado) | Nenhuma marca muda. O gancho e o estilo entram como característica, lidos do corte |
| IV. Contrato é a fonte única | ✅ | Rotas e schemas novos no OpenAPI → `gen:contract`. O dicionário das colunas é uma constante única no backend (`metricas/dicionario.py`): o ZIP e o teste de cabeçalho usam a mesma fonte |
| V. Segurança e segredos | ✅ | Nenhum segredo novo; os tokens continuam só em `conexoes.token_valido`. Logs: o leitor registra método, caminho e status (como na 015), nunca legenda, link nem token. **CSP igual:** gráfico SVG próprio; nada de `cover_image_url`, porque as imagens vêm do MinIO/imgproxy do SociMan. A exportação baixa por `fetch` com Bearer (sem link público) e só vai para o dono. O Redis continua só com contadores |
| VI. Testes antes de pronto | ✅ | pytest (migração, agenda, marcos, casamento, coleta, vínculo, anonimização, guardas), ruff, `check:web` e e2e com a TikTok falsa. I e VII têm teste automatizado: guardas de leitura, trigger de só inserção e anonimização sem DELETE. O teste real é passo do quickstart, com o dono |
| **VII. Humano no controle** | ✅ com duas exceções justificadas | **Vínculo:** toda mudança (automática, `system:metricas`, ou humana) grava `history.record` no **destino** (`entity_type = "postagem"`), com autor, método e estado antes e depois. O controle otimista usa o `version` do destino. Desfazer e refazer são ações do dono. **Exceção 1 (sem histórico por linha):** as tabelas `metricas_*` são **observações da rede escritas pelo sistema**, não entidades editadas por gente, como as `publicacao_tentativas` da 015. As fotos são só de inserção (trigger), e o que muda no vídeo (legenda atual, disponível, próxima coleta) é metadado da observação. **Exceção 2 (anonimização):** o princípio diz "nada é apagado de fato". A anonimização **não apaga linhas**: é um UPDATE que troca identificadores por nulos e congela as características. Ela remove, de forma irreversível, os ids, links e textos da TikTok e o elo com conta e destino. Isso cumpre a decisão do dono (Clarifications) e os termos da TikTok (dados obtidos pela API deixam de identificar a conta quando o acesso termina). Salvaguardas: só um dono humano, só ao desconectar, com confirmação explícita (`confirmoAnonimizar`), uma versão da **conexão** com `details.acao = "metricas_anonimizadas"` e a contagem, e nenhuma cópia dos identificadores no histórico (R13). **Nenhuma rota DELETE** |
| VIII. Simplicidade | ✅ com justificativa | 5 tabelas, 1 trilha, 1 variável de ambiente, 0 dependência e 0 serviço. Sem particionamento (volume em R8). Marcos e ranking calculados na leitura, sem tabela de cache. Gráfico próprio em vez de biblioteca. Ver Complexity Tracking |

**Reavaliação pós-design:** mantida. Pontos a confirmar no teste real, sem impacto no gate:
- os escopos novos no sandbox e o comportamento da TikTok ao ampliar escopos (R1);
- se o `status/fetch` continua consultável dias depois (R9);
- se o `publicaly_available_post_id` é o mesmo `id` do `video.list` (R9);
- a latência do `view_count` (R19);
- se o `video/query` recusa ids de outra conta (R11).

### Guardas (testes automatizados do princípio I e do VII)
Em `tests/unit/test_constitution_guards.py` (seção "spec 016") e
`tests/integration/test_guardas_016.py`:
1. `cliente.ALLOWED == TIKTOK_ALLOWED_R21 | LEITURA_016`, e `LEITURA_016` só tem `video/list` e
   `video/query` (as listas só crescem por spec);
2. `metricas/*.py` não importa `publicacao.tiktok`, `publicacao.trilha`, `publicacao.service`
   nem `publicacao.executor` (só `registro`, `conexoes`, `models` e `limites`); `httpx` não
   aparece em `metricas/`;
3. AST: `put_parte`, `.iniciar(` e `.enviar_parte(` não aparecem em `metricas/` nem em
   `publicacao/tiktok/leitor.py`; o leitor só cita caminhos de `LEITURA_016` ∪
   {`/v2/user/info/`, `/v2/post/publish/status/fetch/`};
4. estados da 015: `ESTADOS_015_PERMITIDOS` ganha `("postagem/service.py",
   "publicacao_pelo_vinculo")`, e o guarda continua vivo;
5. trilhas = `{sync, openshorts, importacao, lembretes, publicacao, metricas}` (ajusta o
   `test_agendador_sem_trilha_nova` existente; o `test_cliente_da_tiktok_com_lista_fechada_do_r21`
   passa a comparar com `R21 ∪ LEITURA_016`);
6. integração: ciclo de coleta e de vínculo com os dois níveis do interruptor desligados → só
   pedidos de leitura no fake, nenhum destino muda para `enviando` e nenhuma tentativa é criada;
7. rotas de vínculo com `require_human_owner`; `Actor(kind="mcp_client")` → 403
   `somente_humano`, sem mudança e com evento;
8. trigger: `UPDATE` e `DELETE` direto em `metricas_video_fotos` e `metricas_conta_fotos` →
   erro do banco;
9. anonimização: depois de desconectar, nenhuma coluna identificadora das tabelas `metricas_*`
   da série fica preenchida, e nenhuma linha some (as contagens antes e depois são iguais);
10. `test_listas_do_guarda_nao_encolheram` sem mudança.

Fora do escopo, de propósito:
- a Business API (alcance, retenção, fontes, audiência), que é a etapa 2 e exige outro app e
  aprovação (pesquisa §2);
- métricas de YouTube e Instagram; o desenho (`rede`, `leitor_para`) já as comporta;
- MCP/IA lendo métricas (FR-010, spec futura);
- apagar métricas de verdade (a decisão do dono é anonimizar);
- capas da TikTok (`cover_image_url` expira);
- webhook da TikTok (exige endereço público);
- TikTok Shop (vendas de afiliado).

## Project Structure

### Documentation (this feature)

```text
specs/016-metricas-tiktok/
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
├── migrations/versions/0011_metricas_tiktok.py      # NOVO
├── src/sociman_api/
│   ├── metricas/                                    # NOVO pacote (genérico; não fala HTTP)
│   │   ├── __init__.py
│   │   ├── models.py        # Serie, VideoRede, FotoVideo, FotoConta, BuscaPost; VinculoMetodo
│   │   ├── agenda.py        # cadência por idade, próxima coleta, janela da conta (R4, R6)
│   │   ├── coleta.py        # trilha `metricas`: rodar(db, client=None, agora=None) (R3, R5, R7)
│   │   ├── vinculos.py      # níveis 1 a 3, candidatos, desfazer, bloqueio (R9 a R11)
│   │   ├── casamento.py     # normalização de legenda e regra de candidato único (R10)
│   │   ├── anonimizar.py    # UPDATE da série ao desconectar (R13)
│   │   ├── consulta.py      # curvas, marcos (LATERAL), ranking, resolução da conta (R15)
│   │   ├── dicionario.py    # colunas do dataset: nome, tipo, significado (R16)
│   │   ├── export.py        # ZIP de CSV/JSONL em streaming (R16)
│   │   ├── schemas.py
│   │   └── router.py        # /api/metricas/*, /api/contas/{id}/metricas, /api/destinos/{id}/…
│   ├── publicacao/
│   │   ├── tiktok/cliente.py   # ALLOWED + LEITURA_016 (video/list, video/query)
│   │   ├── tiktok/leitor.py    # NOVO: LeitorTikTok (stats, listar, consultar, post_publicado)
│   │   ├── tiktok/executor.py  # + `leitor` (atributo); nada muda no envio
│   │   ├── executor.py         # + Protocol LeitorRede e tipos (VideoLido, StatsConta)
│   │   ├── registro.py         # + leitor_para(platform)
│   │   ├── conexoes.py         # iniciar/retorno aceitam ampliar escopos; desconectar anonimiza
│   │   ├── schemas.py          # Conexao.metricas (EstadoColeta); DesconectarIn
│   │   ├── router.py           # desconectar com DesconectarIn
│   │   └── limites.py          # TAXAS + "leitura"
│   ├── postagem/service.py     # + publicacao_pelo_vinculo (rascunho_criado ↔ publicado)
│   ├── notificacoes/models.py  # + post_detectado, vinculo_a_confirmar
│   ├── config.py               # METRICAS_COLETA_HABILITADA, AGENDADOR_METRICAS_S, TIKTOK_SCOPES
│   ├── agendador.py            # trilha `metricas` + _registrar_modelos(metricas)
│   └── main.py                 # inclui o router de metricas
└── tests/
    ├── fakes/tiktok_fake.py, fixtures/tiktok/video_*.json   # + stats, list, query, post_id
    ├── unit/   # test_agenda_metricas, test_marcos, test_casamento, test_link_tiktok; guardas 016
    └── integration/  # test_migration_0011, test_coleta_metricas, test_vinculo, test_anonimizacao,
                      #   test_reconectar_escopos, test_rotas_metricas, test_export_metricas,
                      #   test_guardas_016; 015 ajustados

apps/web/src/
├── pages/metricas/{Metricas,VideoMetricas}.tsx      # NOVAS (/app/metricas, /app/metricas/videos/:id)
├── components/metricas/
│   ├── LinhaChart.tsx        # SVG próprio: linhas, eixos, marcadores, tooltip por teclado/mouse
│   ├── MarcosCard.tsx        # 1 h / 24 h / 7 d / 30 d ("ainda não", "estimado")
│   ├── RankingTable.tsx      # DataTable (TanStack v9) com ordenação e filtros
│   ├── VinculoPanel.tsx      # estado, candidatos, colar link, desfazer (dono)
│   ├── ColetaStatus.tsx      # no ConexaoCard: coletando / reconectar / erro
│   └── ExportarDialog.tsx
├── components/conteudos/DestinoPanel.tsx      # seção "Desempenho"
├── components/publicacao/ConexaoCard.tsx      # ColetaStatus + "Reconectar para liberar métricas"
│                                              #   + confirmação da anonimização ao desconectar
├── App.tsx, components/shell/nav.ts           # rota e item "Métricas"
└── lib/metricas.ts                            # queries, rótulos pt-BR, formatação (SP)

docker-compose.yml, docker-compose.e2e.yml, docker-compose.test.yml   # variáveis novas
e2e/fakes/server.py            # + /tiktok/v2/video/{list,query}/, stats no user/info, post_id
e2e/metricas.spec.ts           # NOVO
```

**Structure Decision:**
- `metricas/` é genérico: não conhece a TikTok nem fala HTTP. Chega ao `LeitorRede` por
  `registro.leitor_para(rede)` e ao token por `conexoes.token_valido`. A TikTok fica toda em
  `publicacao/tiktok/` (exceção por pasta do guarda R16.1);
- o leitor fica na pasta da rede, e não num pacote novo de rede, porque **a exceção do guarda é
  por pasta** e o cliente com `ALLOWED` é um só. Criar outro cliente dividiria a lista fechada em
  duas;
- a trilha fica no agendador existente, com thread própria, e não bloqueia a de publicação.

**Migration:** `0011_metricas_tiktok`, `down_revision = "0010_publicacao_tiktok"` (data-model).

### O que muda na 015 e na 014
| Onde | Mudança |
|---|---|
| `cliente.ALLOWED` | + `("POST", "/v2/video/list/")`, `("POST", "/v2/video/query/")` (`LEITURA_016`) |
| `TIKTOK_SCOPES` (padrão) | + `user.info.stats,video.list` (o `.env` pode sobrescrever: o quickstart confere) |
| `conexoes.iniciar` | aceita `conectada` sem os escopos de métricas (antes: sempre 409 `ja_conectada`) |
| `conexoes._validar_e_gravar` | `conectada` + mesmo `open_id` + ampliação → reusa a linha (`details.acao = "ampliada"`) e troca a credencial sob `FOR UPDATE` |
| `conexoes.desconectar` | exige `confirmoAnonimizar` quando a série tem dados; anonimiza na mesma transação (R13) |
| `schemas.Conexao` | + `metricas: EstadoColeta` (null em outras redes) |
| `limites.TAXAS` | + `"leitura": 120` por minuto e token (muito abaixo de 600); `"status"` compartilhado com a trilha de publicação |
| `postagem/service.py` | + `publicacao_pelo_vinculo` (a única transição automática fora da trilha, R12) |
| `consulta.py` (014) | sem mudança no estado efetivo. O destino ganha só `vinculo` resumido no detalhe (R12) |
| Guardas da 015 | `TIKTOK_ALLOWED_R21` passa a ser comparado com `R21 ∪ LEITURA_016`; trilhas + `metricas`; `ESTADOS_015_PERMITIDOS` + a função do vínculo |

**Ordem sugerida para o `/speckit-tasks`:**
0. migration `0011` + modelos + trigger + `test_migration_0011`; variáveis no compose;
1. leitor (`LEITURA_016`, `leitor.py`, `registro.leitor_para`) + fake ampliado + guardas 1 a 3;
2. escopos: `TIKTOK_SCOPES`, `iniciar`/`retorno` com ampliação, `EstadoColeta` no `ConexaoCard`
   (US1, P1);
3. agenda + coleta (varredura, fila, conta, erros, idempotência) + trilha no agendador (US2,
   P1);
4. vínculo nível 1 (buscas) + `publicacao_pelo_vinculo` + guarda 4, depois níveis 2 e 3 +
   desfazer + `VinculoPanel` (US3, P1);
5. anonimização no desconectar + confirmação na tela;
6. **teste real com o dono (quickstart §3 e §4):** reconectar, 1ª foto, latência e 1 rascunho
   publicado;
7. consultas (curvas, marcos, ranking) + `/app/metricas` + "Desempenho" (US4, P2);
8. exportação + dicionário (US5, P2);
9. e2e completo, `check:web`, `CLAUDE.md` (seção "Métricas") e `docs/visao.md`.

As fases 0 a 6 fecham as P1 e começam a juntar dados cedo, que é o ponto da spec. As telas vêm
depois, sobre dados reais.

## Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| O sandbox não libera `user.info.stats`/`video.list`, ou libera sem dados reais | nada é coletado | a spec diz que as permissões estão ativas; o quickstart §3 confere a 1ª foto antes das telas; o erro `scope_not_authorized` vira "sem permissão" na conta, sem derrubar a conexão |
| O `.env` sobrescreve `TIKTOK_SCOPES` com a lista antiga | o reconectar não pede os escopos novos | o quickstart §0 confere o nome e o conteúdo (sem valores secretos, é só a lista); a tela mostra os escopos que faltam depois do retorno |
| Ampliar escopos numa conexão viva invalida os tokens antigos no meio de um envio | um envio da 015 falha | `iniciar` recusa (409 `envio_em_andamento`) com um destino `enviando` na conta; a credencial é trocada sob `FOR UPDATE` |
| O `status/fetch` deixa de responder dias depois, ou o id é diferente do `video.list` | o nível 1 não vincula | o nível 2 (casamento) roda independente, e o nível 3 (link) sempre existe; o quickstart §4 mede isso |
| Casamento errado (dois cortes com a mesma duração no mesmo dia) | métrica no conteúdo errado | candidato único nos **dois** sentidos, legenda compatível, nunca sozinho na dúvida; desfazer com histórico e bloqueio do automático |
| O `view_count` só atualiza de tempos em tempos | fotos horárias repetidas | medir no quickstart §3.4; a cadência é constante no código (`agenda.py`) e muda numa linha; repetir não quebra nada |
| A TikTok corrige contagens para baixo | a curva "cai" | gravar como veio (spec); os marcos usam a interpolação sem forçar monotonia; a exportação traz o bruto |
| Anonimização acidental | perda irreversível do elo com a conta | só o dono humano, só ao desconectar, com `confirmoAnonimizar` e um texto explícito na tela; para parar a coleta sem perder dados existe `METRICAS_COLETA_HABILITADA` |
| Dados identificáveis que ficam fora da 016 (`postagens.rede_post_id` e `posted_url` da 014/015 e o histórico deles) | a anonimização não é total no banco inteiro | a 016 não copia nada da TikTok para o destino (o link é lido pelo vínculo). O limite fica escrito em R13, e o que é da 014/015 é registro de execução (princípio I) ou texto digitado pelo dono |
| Volume maior que o previsto (muitas contas) | consultas lentas | índices `(video_id, idade_s)` e `(serie_id, janela_em)`; revisão em cerca de 20 milhões de fotos (R8) |
| Relógio do agendador parado (container fora) | janelas perdidas | a agenda recupera só a janela atual, sem inventar fotos passadas; a tela mostra "última coleta" e o atraso |
| O ID da TikTok passa de 64 bits ou vem como número JSON | perda de precisão | `rede_video_id` é `text`; o leitor converte para string na hora de ler |

## Complexity Tracking

| Item | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| Trigger `metricas_so_insercao` nas fotos | SC-006 ("0 fotos sobrescritas ou apagadas") garantido no banco, não só no código | só no código: um `UPDATE` de manutenção ou de outra spec passaria sem ninguém ver |
| Tabela `metricas_buscas_post` | o nível 1 precisa lembrar das consultas e do recuo por 14 dias | gravar na `publicacao_tentativas`: a tentativa é final e não muda (015); recalcular a agenda sem estado repetiria consultas depois de um reinício |
| `metricas_series` separada de `conexoes` | a série sobrevive à conexão (anonimizada) e recomeça como nova ao reconectar | colunas em `conexoes`: a conexão é histórico da 015 (com `open_id` e `username`), e a série anônima não pode apontar para ela |
| Variável `METRICAS_COLETA_HABILITADA` | parar a coleta **sem** desconectar (desconectar anonimiza, e isso é irreversível) | sem variável: o único jeito de parar seria destrutivo |
| Função `publicacao_pelo_vinculo` na lista do guarda | a spec exige "publicado" ao vincular, e o guarda da 015 só permitia a trilha | estado derivado: espalharia a regra por calendário, filtros e atalhos da 014, e o estado gravado mentiria |
| **Nenhum banco novo** (MongoDB/TimescaleDB rejeitados, R20) | registro da decisão: as métricas cabem no Postgres (30 a 300 MB/ano), com junção e transação com o destino e com a anonimização | MongoDB (time series) ou híbrido: emenda da stack, serviço, `mongodump` coordenado, Mongo nos testes efêmeros e anonimização em dois bancos, sem ganho nesse volume. Reavaliar com brutos heterogêneos de várias APIs ou com mais de ~20 milhões de fotos (TimescaleDB primeiro) |
| Gráfico SVG próprio (~200 linhas) | o SPA não tem biblioteca de gráficos, e o princípio VIII pede o mínimo | Recharts (usado pelo `chart` do shadcn): dependência grande (d3), que só entra com justificativa; 3 gráficos de linha não justificam |
