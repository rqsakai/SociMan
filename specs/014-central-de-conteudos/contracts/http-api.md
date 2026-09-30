# Contrato HTTP: 014-central-de-conteudos

Este arquivo é a fonte de desenho. Na implementação, a fonte vira o OpenAPI do FastAPI (princípio
IV), gerado com `npm run gen:contract`.
- Tudo fica sob `/api`, com o envelope de erro da 001 e JSON em camelCase.
- **Não existe rota DELETE.**
- **Nenhum caminho nem `operationId` contém** `publish`, `share`, `post-to`, `upload-to`,
  `tiktok`, `youtube` ou `instagram` (guarda do princípio I, `test_nenhuma_rota_de_publicacao`).
  Por isso os recursos se chamam `conteudos`, `destinos` e `agendamentos`, e os `operationId`
  seguem `conteudos_*`, `destinos_*`, `agendamentos_*` e `contas_modos`. Os valores de enum
  `publicar`/`rascunho_e_publicar` aparecem só no corpo e nunca executam na 014.
- Salvo indicação, as rotas pedem `RequireUser` (dono ou membro). **`RequireOwner`** em aprovar,
  recusar, aprovar em lote e reverter.
- Datas e horas: ISO 8601 com o offset de `APP_TZ` (`America/Sao_Paulo`) na saída; na entrada,
  sem offset = horário local (como na 006).

## Tipos
```text
Origem         "corte"|"video_proprio"
Situacao       "em_revisao"|"processando"|"pronto"|"erro_marca"
DestinoEstado  "pendente"|"aprovacao_pedida"|"aprovado"|"agendado"|"postado"
               |"rascunho_criado"|"publicado"|"falhou"              # os 3 últimos: 015
EstadoEfetivo  "pronto"|"aprovacao_pedida"|"aprovado"|"agendado"|"a_postar"|"atrasado"|"atencao"
               |"postado"|"rascunho_criado"|"publicado"|"falhou"|"em_revisao"|"arquivado"
Modo           "lembrete"|"criar_rascunho"|"publicar"|"rascunho_e_publicar"
ModoInfo       { modo: Modo, disponivel: bool, motivo: str|null }   # motivo em pt-BR
ContaRef       { id, platform, platformName, handle, status }        # o da 006 + status

DestinoResumo  { id, conta: ContaRef, estado: DestinoEstado, estadoEfetivo: EstadoEfetivo,
                 motivoAtencao: str|null, modo: Modo, plannedAt|null, semTextos: bool,
                 videoMudou: bool, version }
ConteudoItem   { id, perfil: PerfilRef, origem: Origem, titulo, situacao: Situacao,
                 posterUrl|null (via /img), durationMs|null, createdAt, archived: bool,
                 corteId|null, envioId|null, destinos: DestinoResumo[],
                 semConta: bool }                                     # linha da lista
Conteudo       ConteudoItem + { width|null, height|null, naoVertical: bool, videoBytes|null,
                 originalFilename|null, version, updatedAt, updatedBy: UserRef|null,
                 destinos: Destino[] }                                # detalhe
Destino        { id, conteudoId, conta: ContaRef, titulo, descricao, hashtags: string[],
                 estado: DestinoEstado, estadoEfetivo: EstadoEfetivo, motivoAtencao|null,
                 modo: Modo, antecedenciaMin|null, plannedAt|null, lembrado: bool,
                 postedAt|null, postedUrl|null, falhaMotivo|null,
                 aprovacao: { por: UserRef, em } | null,
                 pedido: { por: UserRef, em, nota|null } | null,
                 recusa: { por: UserRef, em, motivo } | null,
                 videoMudou: bool, archived: bool, version, createdAt, updatedAt,
                 updatedBy: UserRef|null }
Textos         { titulo?: str (≤100), descricao?: str (≤2000), hashtags?: str[] (≤8) }
LoteResultado  { ok: Destino[], falhas: { conteudoId|null, destinoId|null, code, message }[] }
SlotSequencia  { conteudoId, plannedAt }
Previa         { intervaloMin: int, slots: SlotSequencia[],
                 pulados: { plannedAt, motivo: "passado"|"conflito", destinoId|null }[],
                 inelegiveis: { conteudoId, code, message }[] }
Atalhos        { prontosSemAgendamento, aprovadosSemData, aprovacaoPedida, agendadosHoje,
                 estaSemana, aPostar, atrasados, falharam: int }
```
- `semTextos`: título vazio. `videoMudou`: o vídeo final mudou depois da aprovação (research R5).
- `motivoAtencao`: "Conta arquivada", "Conta pausada" ou "Conta encerrada".
- `naoVertical`: largura ≥ altura (aviso, não bloqueia).
- `intervaloMin`: o intervalo mínimo da conta (minutos) usado para os conflitos.
- `ConflitoIntervalo { destinoId, conteudoId, titulo, plannedAt }`: vem em `details.conflitos` do 409
  `intervalo_conflito`, com `details.intervaloMin`.

## Conteúdos (`/api/conteudos`)
| Método e rota (`operationId`) | Corpo / query | 200 | Erros |
|---|---|---|---|
| `GET /api/conteudos` (`conteudos_list`) | query `perfilId*` (repetível), `contaId?`, `plataforma?`, `estado*` (`EstadoEfetivo` ou `sem_conta`; repetível), `origem?`, `agendadoDe?`/`agendadoAte?` (datas locais), `criadoDe?`/`criadoAte?`, `q?` (até 100), `atalho?` (`prontos_sem_agendamento`, `aprovados_sem_data`, `aprovacao_pedida`, `agendados_hoje`, `esta_semana`, `a_postar`, `atrasados`, `falharam`), `ordem?` (`recentes` \| `agenda`), `archived?` (padrão false), `cursor?`, `limit?` (1..100, padrão 50) | `{items: ConteudoItem[], total: int, nextCursor: str\|null}` | 400 `validation_error` (cursor inválido, período invertido) |
| `GET /api/conteudos/resumo` (`conteudos_resumo`) | query `perfilId*`, `contaId?` | `Atalhos` | |
| `GET /api/conteudos/{id}` (`conteudos_get`) | – | `{conteudo: Conteudo}` | 404 |
| `PATCH /api/conteudos/{id}` (`conteudos_update`) | `{version, titulo}` | `{conteudo}` | 409 `version_conflict`; 409 `conflict` (arquivado) |
| `POST /api/perfis/{id}/conteudos/arquivo` (`conteudos_video_proprio`) | multipart: `file` (vídeo até 2 GB, 1 s a 10 min), `titulo?` | `{conteudo}` (201, `situacao: pronto`) | 400 `invalid_video` (formato, duração); 404 perfil; 409 perfil arquivado; 413; 503/507 (HD) |
| `POST /api/conteudos/{id}/archive` · `/restore` (`conteudos_archive` · `conteudos_restore`) | `{version}` | `{conteudo}` (arquivar cancela os agendamentos ativos) | 409; na origem corte, as regras do corte (409 em `processando`) |
| `GET /api/conteudos/{id}/versions` (`conteudos_versions`) | – | `{items: Version[]}` | 404 |
| `POST /api/conteudos/{id}/revert` (`conteudos_revert`) | `{version, toVersion}` | `{conteudo}` (título e arquivamento) | **`RequireOwner`**; 409 |
| `POST /api/conteudos/{id}/destinos` (`conteudos_add_destino`) | `{contaId, titulo?, descricao?, hashtags?, ia?}` | `{destino}` (201, `pendente`) | 400 `conta_invalida` (outro perfil, arquivada); 409 `destino_exists`; 409 `conflict` (conteúdo arquivado) |

- Na origem corte, `archive`/`restore` do conteúdo chamam o service do corte (o arquivamento é do
  corte). A rota da 006 `POST /api/cortes/{id}/archive` passa a cancelar os agendamentos também.
- Mídia: `POST /api/midia/links` aceita o kind novo **`conteudo_video`** (vídeo próprio; com
  validade, `download=1` para baixar). A origem corte continua com `corte_marcado`.

## Destinos (`/api/destinos`)
| Método e rota (`operationId`) | Corpo | 200 | Erros |
|---|---|---|---|
| `GET /api/destinos/{id}` (`destinos_get`) | – | `{destino}` | 404 |
| `PATCH /api/destinos/{id}` (`destinos_update`) | `{version, titulo?, descricao?, hashtags?, ia?}` (textos; não muda a aprovação) | `{destino}` | 400 `validation_error`; 409 `version_conflict`; 409 `conflict` (`postado` ou arquivado) |
| `POST /api/destinos/{id}/pedir-aprovacao` (`destinos_pedir_aprovacao`) | `{version, nota?}` (≤500) | `{destino}` (`aprovacao_pedida`; notifica os donos) | 409 `conflict` (estado diferente de `pendente`); 409 `conteudo_nao_pronto` |
| `POST /api/destinos/{id}/aprovar` (`destinos_aprovar`) | `{version}` | `{destino}` (`aprovado`) | **`RequireOwner`**; 409 `conteudo_nao_pronto` ("Aplique a marca antes de aprovar"); 409 `conflict` |
| `POST /api/destinos/{id}/recusar` (`destinos_recusar`) | `{version, motivo}` (1..500) | `{destino}` (`pendente`, com a recusa) | **`RequireOwner`**; 400 `validation_error` (sem motivo); 409 `conflict` (agendado: cancele antes) |
| `POST /api/destinos/{id}/postado` (`destinos_marcar_postado`) | `{version, postedUrl?}` | `{destino}` (`postado`) | 409 `conflict` (não aprovado nem agendado) |
| `POST /api/destinos/{id}/archive` · `/restore` (`destinos_archive` · `destinos_restore`) | `{version}` | `{destino}` | 409 |
| `GET /api/destinos/{id}/versions` (`destinos_versions`) | – | `{items: Version[]}` | 404 |
| `POST /api/destinos/{id}/revert` (`destinos_revert`) | `{version, toVersion}` | `{destino}` (textos, modo, data; nunca `postado`, nunca restaura aprovação) | **`RequireOwner`**; 409 |
| `POST /api/destinos/lote/aprovar` (`destinos_lote_aprovar`) | `{contaId, conteudoIds: uuid[]}` (1..100) | `LoteResultado` (cria o destino que faltar) | **`RequireOwner`**; 400 `conta_invalida` |
| `POST /api/destinos/lote/pedir-aprovacao` (`destinos_lote_pedir_aprovacao`) | `{contaId, conteudoIds, nota?}` | `LoteResultado` (um aviso por destino) | 400 `conta_invalida` |
| `GET /api/contas/{id}/modos` (`contas_modos`) | – | `{modos: ModoInfo[]}` (os quatro, na ordem da spec) | 404 |

## Agendamentos (`/api/agendamentos`)
| Método e rota (`operationId`) | Corpo | 200 | Erros |
|---|---|---|---|
| `POST /api/agendamentos` (`agendamentos_create`) | `{conteudoId, contaId, plannedAt, modo, antecedenciaMin?, destinoVersion?, textos?: Textos, ia?, ignorarIntervalo?: bool}` | `{destino}` (201 se criou o destino; `agendado`). Dono: aprova no mesmo passo | 403 `aprovacao_necessaria` (membro, destino não aprovado); 400 `planned_in_past`; 409 `conteudo_nao_pronto`; 409 `modo_indisponivel` (`details.motivo`); 409 `conta_em_atencao`; 409 `intervalo_conflito` (sem `ignorarIntervalo`; nada gravado); 409 `version_conflict` (com `destinoVersion`); 409 `conflict` (já `postado`) |
| `PATCH /api/destinos/{id}/agendamento` (`agendamentos_update`) | `{version, plannedAt?, modo?, antecedenciaMin?, ignorarIntervalo?: bool}` | `{destino}` | 409 `nao_aprovado` (não está `agendado`); 400 `planned_in_past`; 409 `modo_indisponivel`; 409 `intervalo_conflito`; 409 `version_conflict` |
| `POST /api/destinos/{id}/agendamento/cancelar` (`agendamentos_cancelar`) | `{version}` | `{destino}` (`aprovado`, sem data) | 409 `conflict` (não agendado) |
| `POST /api/agendamentos/lote/reagendar` (`agendamentos_lote_reagendar`) | `{itens: {destinoId, version, plannedAt}[]}` (1..100), `ignorarIntervalo?: bool` | `LoteResultado` (o intervalo é conferido contra o estado final do lote: trocar os horários de dois itens não conflita entre eles) | (por item, em `falhas`, inclusive `intervalo_conflito`) |
| `POST /api/agendamentos/lote/cancelar` (`agendamentos_lote_cancelar`) | `{itens: {destinoId, version}[]}` | `LoteResultado` | (por item) |
| `POST /api/agendamentos/sequencia/previa` (`agendamentos_sequencia_previa`) | `{contaId, conteudoIds: uuid[] (1..100, na ordem), inicio: date, horarios: "HH:MM"[] (1..6), modo}` | `Previa` (não grava; pula os horários a menos de `intervaloMin` de outro agendamento da conta ou da própria sequência) | 400 `validation_error` (horário repetido, mais de 180 dias); 409 `modo_indisponivel`; 400 `conta_invalida` |
| `POST /api/agendamentos/sequencia` (`agendamentos_sequencia`) | o corpo da prévia + `esperado: SlotSequencia[]` | `LoteResultado` | 409 `previa_desatualizada` (`details.previa: Previa`) |

## Contas (ampliação da 002)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `PATCH /api/contas/{id}` (`contas_update`, mantido) | o corpo da 002 + `intervaloMinMinutos?: int` (0..1440) | `{conta}` com `intervaloMinMinutos` | 400 `validation_error` (fora de 0..1440); **403 `forbidden`** se um membro mudar `intervaloMinMinutos` (os outros campos seguem as regras da 002); 409 `version_conflict` |

O schema `Conta` da 002 (dentro de `ContaOut`) ganha `intervaloMinMinutos`; o `ContaRef` não. `POST /api/perfis/{id}/contas` não recebe
o campo: a conta nasce com 30. A reversão da conta (`contas_revert`, dono) volta o valor quando a
versão alvo o tem.

## Calendário (ampliação da 006)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `GET /api/calendario` (`postagens_calendario`, mantido) | query `de`, `ate` (até 62 dias), `perfilId?`, `plataforma?`, `contaId?` (novo) | `{items: (Destino & {conteudo: {id, origem, titulo, posterUrl, durationMs, situacao}, perfil: PerfilCalendario})[], semData: {conteudoId, destinoId\|null, contaId\|null, perfilId, posterUrl, titulo, perfilCor, aprovado: bool}[]}` (aprovados sem data primeiro) | 400 |

## Rotas removidas (da 006)
`GET/POST /api/cortes/{id}/postagens`, `GET/PATCH /api/postagens/{id}`, `POST
/api/postagens/{id}/{postado,archive,restore,revert}` e `GET /api/postagens/{id}/versions`. Os
equivalentes estão em `/api/destinos` e `/api/agendamentos`. O `Corte` da 006 troca
`postagens: PostagemResumo[]` por `destinos: DestinoResumo[]`.

## Assistente de IA (ampliação da 008)
- `Alvo.entityType` ganha `"conteudo"` (`{entityType: "conteudo", entityId, contaId}`) para os tipos
  `postagem.*` antes de o destino existir. `"corte"` continua aceito (mesmo id). O alvo
  `"postagem"` usa o id do destino.
- O campo `ia` (`IaAplicacao[]`) vale em `POST /api/conteudos/{id}/destinos`, `PATCH
  /api/destinos/{id}` e `POST /api/agendamentos` (com `textos`).

**Códigos de erro novos:** `conteudo_nao_pronto`, `nao_aprovado`, `aprovacao_necessaria`,
`modo_indisponivel`, `conta_em_atencao`, `conta_invalida`, `destino_exists`, `intervalo_conflito` e
`previa_desatualizada`. Continuam da 006: `planned_in_past`, `invalid_video`, `version_conflict`,
`conflict`.

**Edge:**
- `location ~ ^/api/perfis/[^/]+/conteudos/arquivo$` com `client_max_body_size 2100m`,
  `proxy_request_buffering off` e timeouts longos, como a do envio avulso da 006;
- a CSP não muda (o player usa `/api/midia/`, mesma origem).

## Rotas do SPA
| Rota | Conteúdo |
|---|---|
| `/app/conteudos` | atalhos com contagem no topo; filtros (perfil, conta, rede, estado, origem, período agendado, período criado, busca) na URL; tabela com miniatura, título, perfil, origem, duração e **chips por conta** (estado efetivo, data); seleção em lote com a barra "Aprovar", "Pedir aprovação", "Agendar em sequência", "Trocar horários", "Cancelar agendamento"; "Carregar mais"; "Enviar vídeo próprio" |
| `/app/conteudos/:id` | player; título editável; origem (link para o corte/envio); aviso "o vídeo mudou desde a aprovação"; **uma aba por conta** (`?conta=` seleciona): textos com o IA, aprovação (pedir, aprovar, recusar com motivo, a recusa visível), agendamento (Agendar, Reagendar, Cancelar, modos com motivo), "Copiar", "Baixar vídeo", "Postado" (link opcional); "Adicionar conta"; histórico do conteúdo e de cada destino |
| `/app/cortes/:id` | a seção Postagem da 006 vira o mesmo painel de destinos, com o botão **Agendar** no corte pronto |
| `/app/perfis/:id` aba **Cortes** | botão **Agendar** nas linhas prontas; "Ver em Conteúdos" |
| `/app/calendario` | cartões com modo e estado efetivo (`a_postar`/`atrasado` em destaque); filtro de conta; coluna "Sem data" com aprovados primeiro; soltar abre o `AgendarDialog`; arrastar para perto de outro post da conta mostra o aviso do intervalo com "Manter mesmo assim" |
| `/app/perfis/:id` aba **Contas** | campo "Intervalo mínimo entre posts (min)" no formulário da conta; editável só por dono, leitura para membro |
| `AgendarDialog` (componente) | conta (só as do perfil), data e hora (APP_TZ), **modo** (os quatro, indisponíveis desabilitados com o motivo), textos com "Gerar com IA"; dono vê "Aprovar e agendar", membro diante de item não aprovado vê "Pedir aprovação"; em `intervalo_conflito`, mostra os posts próximos com "Manter mesmo assim" e "Escolher outro horário" |
| `SequenciaDialog` (componente) | conta, primeira data, horários por dia (chips `HH:MM`), modo, "Gerar textos com IA para os que não têm"; **prévia** (tabela dia × item, pulados e inelegíveis) antes de "Confirmar"; depois, barra de progresso dos textos |
