# Contrato HTTP: 006-cortes-openshorts

Este arquivo é a fonte de desenho. Na implementação, a fonte vira o OpenAPI do FastAPI (princípio
IV), gerado com `npm run gen:contract`.
- Tudo fica sob `/api`, com o envelope de erro da 001 e JSON em camelCase.
- **Não existe rota DELETE.**
- **Nenhum caminho nem `operationId` contém** `publish`, `share`, `post-to`, `upload-to`,
  `tiktok`, `youtube` ou `instagram` (guarda do princípio I). Por isso as rotas se chamam
  `canais`, `videos-fonte` e `postagens`, e os `operationId` seguem `canais_*`, `videos_fonte_*`,
  `envios_*`, `postagens_*` e `notificacoes_*`.
- Salvo indicação, as rotas pedem `RequireUser` (dono ou membro).

## Tipos
```text
CanalFonte   { id, youtubeChannelId, handle|null, title, avatarUrl|null (via /img), subscribers|null,
               videoCount|null, direito: Direito, direitoEvidenciaUrl|null, direitoEvidenciaNota,
               perfis: PerfilRef[], sync: { status: "pendente"|"sincronizando"|"ok"|"pausado_cota"|"erro",
               lidos|null, total|null, erro|null, lastSyncedAt|null, nextSyncAt },
               videosConhecidos: int, archived: bool, version, createdAt, createdBy: UserRef|null }
Direito      "proprio"|"parceiro"|"programa_de_cortes"|"sem_acordo"
VideoFonte   { id, canal: { id, title, direito }, youtubeVideoId, url, title, thumbnailUrl|null (via /img),
               publishedAt, durationS|null, live: "nenhum"|"ao_vivo"|"agendado", disponivel: bool,
               views|null, likes|null, comments|null, vphRecente|null, score: number, scoreReason,
               scoreDetail: { v, e, r, d, componente }, recomendavel: bool,
               jaCortado: { perfilId, envioId, status }[]  # envios não descartados, por perfil
               selecionado: { perfilId, envioId }[] }
PadroesCorte { perfilId, version (0 = padrão), clipMinS, clipMaxS, quantidade|null,
               layout: "auto"|"none"|"split"|"screencast"|"speaker_cut", formato: "vertical"|"square",
               legenda: "kit"|"gerador"|"nenhuma", marcaAutomatica: bool, contaPadraoId|null,
               updatedAt|null, updatedBy|null }
EnvioConfig  { clipMinS, clipMaxS, quantidade|null, layout, formato, legenda, marcaAutomatica,
               kitVersion|null }       # o subtitle do kit fica só no servidor
Envio        { id, perfilId, origem: "canal"|"avulso_link"|"avulso_arquivo", video: VideoFonteRef|null,
               canal: { id, title, direito }|null, sourceUrl|null, sourceTitle,
               status: EnvioStatus, config: EnvioConfig|null, direitoNoEnvio: Direito|"avulso"|null,
               precisaAviso: bool,     # true se canal sem_acordo ou avulso (a UI mostra o aviso)
               progress: int, queuePosition|null, clipsTotal|null, clipsImportados: int,
               errorMessage|null, sentAt|null, finishedAt|null, archived: bool, version,
               createdAt, createdBy: UserRef|null }
EnvioStatus  "selecionado"|"na_fila"|"aguardando_openshorts"|"confirmar_qualidade"|"processando"
             |"importando"|"pronto"|"sem_clipes"|"falhou"|"descartado"
Corte        o da 004 + { origem: "upload"|"openshorts", envioId|null, clipIndex|null,
               sourceStartMs|null, sourceEndMs|null, openshortsTitle|null, openshortsDescription|null,
               openshortsScore|null, legenda|null, canal: { id, title }|null, direitoNoEnvio|null,
               archived: bool, postagens: PostagemResumo[] }
             # status ganha "revisao"; kitVersion passa a ser anulável
Postagem     { id, corteId, conta: ContaRef (plataforma, @), titulo, descricao, hashtags: string[],
               estado: "rascunho"|"agendado"|"postado", plannedAt|null, postedAt|null, postedUrl|null,
               lembrado: bool, archived: bool, version, updatedAt, updatedBy }
Sugestao     { id, plataforma, titulo, descricao, hashtags: string[], ajustes: string[], model, createdAt }
Notificacao  { id: int, tipo, titulo, corpo, link, createdAt, lida: bool }
Integracoes  { youtube: "ok"|"ausente"|"invalida", openshorts: "ok"|"fora", claude: "ok"|"ausente",
               cotaYoutube: { usadas: int, limite: int, renovaEm: datetime } }
```

## Canais (`/api/canais`)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `POST /api/canais/resolver` | `{entrada}` (link, `@` ou ID) | `{candidato: {youtubeChannelId, title, handle, avatarUrl, subscribers, videoCount}, custo: int, existente: {id}|null}`, sem gravar (a tela confirma) | 400 `invalid_channel_input`; 404 `canal_not_found`; 409 é tratado com `existente`; 429 `youtube_quota`; 502 `youtube_error`; 503 `youtube_unconfigured` |
| `POST /api/canais` | `{youtubeChannelId, perfilIds: uuid[]}` | `{canal}` (201; sync `pendente`, que começa sozinha) | 409 `canal_exists` (`details.id`) (US1-2); 400 `validation_error`; 429/502/503 como acima |
| `GET /api/canais` | query `archived?`, `perfilId?`, `q?` | `{items: CanalFonte[]}` | |
| `GET /api/canais/{id}` | – | `{canal}` | 404 |
| `PATCH /api/canais/{id}` | `{version, perfilIds?}` | `{canal}` | 409 `version_conflict`; 400 (perfil arquivado) |
| `PUT /api/canais/{id}/direito` | `{version, direito, evidenciaUrl?, evidenciaNota?}` | `{canal}` | **`RequireOwner`** (403 para membro, princípio II); 409 `version_conflict` |
| `POST /api/canais/{id}/sincronizar` | – | `{canal}` (`next_sync_at = now`) | 409 `sync_running`; 429 `youtube_quota` |
| `POST /api/canais/{id}/archive` · `/restore` | `{version}` | `{canal}` | 409 |
| `GET /api/canais/{id}/versions` | – | `{items: Version[]}` | 404 |
| `POST /api/canais/{id}/revert` | `{version, toVersion}` | `{canal}` | **`RequireOwner`**; 409 |

## Descoberta (`/api/videos-fonte`)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `GET /api/videos-fonte` | query: `perfilId?` (liga o "já cortado" e filtra os canais do perfil), `canalId?` (repetível), `q?`, `publicadoDesde?`, `publicadoAte?`, `duracaoMin?`, `duracaoMax?` (s), `naoCortados?` (bool, exige `perfilId`), `recomendaveis?` (padrão true), `ordem?` = `score`\|`views`\|`vph`\|`data` (padrão `score`), `limit?` (50, até 100), `cursor?` | `{items: VideoFonte[], nextCursor|null, total: int}` | 400 (filtro inválido) |
| `GET /api/videos-fonte/{id}` | – | `{video, metricas: {observedAt, views, likes, comments}[]}` (últimas 50) | 404 |

O score exibido com `perfilId` já tem o fator "já cortado" (× 0,3). A ordenação é estável por
`(ordem, id)`, e o cursor é opaco.

## Padrões de corte
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `GET /api/perfis/{id}/padroes-corte` | – | `{padroes}` (padrão com `version: 0` se nunca salvo) | 404 |
| `PUT /api/perfis/{id}/padroes-corte` | `{version, …PadroesCorte}` | `{padroes}` | 400 `invalid_padroes` (`field`); 409 `version_conflict` |
| `GET /api/perfis/{id}/padroes-corte/versions` | – | `{items: Version[]}` | 404 |
| `POST /api/perfis/{id}/padroes-corte/revert` | `{version, toVersion}` | `{padroes}` | **`RequireOwner`** (princípio VII); 409 `version_conflict` |

## Envios
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `POST /api/perfis/{id}/envios` | `{videoFonteId}` ou `{url, titulo?}` (avulso por link); `confirmarDuplicado?` | `{envio}` (201, `selecionado`) | 409 `already_selected` / `already_sent` (`details.envioId`) sem `confirmarDuplicado`; 409 `video_unavailable` (indisponível); 400 `invalid_url`; 409 `perfil_archived` |
| `POST /api/perfis/{id}/envios/arquivo` | `multipart/form-data`: `file`, `titulo` | `{envio}` (201, `selecionado`, origem `avulso_arquivo`) | 413 `payload_too_large` ("Arquivo maior que 2 GB"); 400 `invalid_video` ("Não é um vídeo aceito" \| "Vídeo com menos de 45 segundos" \| "Vídeo com mais de 3 horas"); 503/507 (HD). O volume e o tamanho são conferidos antes de ler o corpo (como na 004) |
| `GET /api/envios` | query `perfilId?`, `status?` (repetível), `limit?`, `before?` | `{items: Envio[]}` | |
| `GET /api/envios/{id}` | – | `{envio, cortes: Corte[]}` (os clipes, para a revisão) | 404 |
| `POST /api/envios/enviar` | `{items: [{envioId, version}], config?: Partial<EnvioConfig>, confirmarAviso?: bool, confirmarDuplicado?: bool}` (até 20; `config` sobrescreve os padrões do perfil em todos) | `{items: Envio[]}` (`na_fila`) | **409 `aviso_direito`** ("O direito autoral deste vídeo é de sua responsabilidade", `details.envioIds`) quando algum item precisa de aviso e falta `confirmarAviso` (princípio II; nada é enviado); 409 `already_sent`; 400 `invalid_config`; 409 `version_conflict`; 409 `conflict` (status diferente de `selecionado`). Tudo ou nada |
| `POST /api/envios/{id}/confirmar-qualidade` | `{version, enviar: bool}` | `{envio}` (`na_fila` com `forceLowQuality`, ou `descartado`) | 409 (status diferente de `confirmar_qualidade`) |
| `POST /api/envios/{id}/retry` | `{version}` | `{envio}` (`falhou` → `na_fila` com novo job, ou → `importando` se o job ainda existe e faltam clipes) | 409 |
| `POST /api/envios/{id}/archive` | `{version}` | `{envio}` (`descartado`; só em `selecionado`, `falhou`, `sem_clipes` e `pronto`) | 409 `conflict` (em andamento) |
| `GET /api/envios/{id}/versions` | – | `{items: Version[]}` | 404 |

O SPA faz polling de `GET /api/envios?status=na_fila&status=processando&…` a cada 5 s enquanto
há envios em andamento na tela.

## Cortes (ampliação da 004)
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `GET /api/perfis/{id}/cortes` | + query `origem?`, `envioId?`, `archived?` (padrão false) | `{items: Corte[]}` | |
| `PATCH /api/cortes/{id}` | `{version, hookText}` (só em `revisao`) | `{corte}` | 400 `invalid_hook`; 409 |
| `POST /api/cortes/aplicar-marca` | `{items: [{corteId, version}]}` (até 30) | `{items: Corte[]}` (`na_fila`, com o kit atual resolvido) | 400 `invalid_hook` (`details.corteId`); 409 `conflict` (status diferente de `revisao`); 503/507 (HD) |
| `POST /api/cortes/{id}/archive` · `/restore` | `{version}` | `{corte}` | 409 (`processando`) |

## Postagens
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `POST /api/cortes/{id}/sugestoes` | `{contaId}` (a plataforma vem da conta) | `{sugestao: Sugestao}` (não altera a postagem) | 503 `claude_unconfigured`; 504 `textos_timeout`; 502 `textos_invalidos` / `claude_error` (mensagem clara; os campos continuam editáveis) |
| `GET /api/cortes/{id}/sugestoes` | – | `{items: Sugestao[]}` (mais recentes primeiro) | 404 |
| `POST /api/cortes/{id}/postagens` | `{contaId, titulo?, descricao?, hashtags?, plannedAt?, sugestaoId?}` | `{postagem}` (201; `agendado` se vier `plannedAt`) | 409 `postagem_exists`; 409 `corte_not_ready` (com `plannedAt` e o corte fora de `pronto`); 400 `planned_in_past`; 400 `validation_error` (limites) |
| `PATCH /api/postagens/{id}` | `{version, titulo?, descricao?, hashtags?, plannedAt?|null, contaId?}` (`plannedAt` → `agendado`; `null` → `rascunho`) | `{postagem}` | 409 `version_conflict`; 409 `corte_not_ready`; 400 `planned_in_past`; 409 `conflict` (já `postado`) |
| `POST /api/postagens/{id}/postado` | `{version, postedUrl?}` | `{postagem}` (`postado`, `postedAt = now`) | 409 |
| `POST /api/postagens/{id}/archive` · `/restore` | `{version}` | `{postagem}` | 409 |
| `GET /api/postagens/{id}/versions` | – | `{items: Version[]}` | 404 |
| `POST /api/postagens/{id}/revert` | `{version, toVersion}` | `{postagem}` (volta textos, conta e data; não desfaz `postado`) | **`RequireOwner`** (princípio VII); 409 `version_conflict`; 409 `conflict` (já `postado`) |
| `GET /api/calendario` | query `de`, `ate` (datas locais, até 62 dias), `perfilId?`, `plataforma?` | `{items: Postagem & {corte: {id, posterUrl, perfilId, durationMs, status}, perfil: PerfilRef}[], semData: {corteId, perfilId, posterUrl, titulo}[]}` (cortes prontos sem postagem agendada) | 400 |

Baixar o vídeo para postar usa a rota da 004: `POST /api/midia/links` com o kind `corte_marcado`
e `download=1`.

## Notificações
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `GET /api/notificacoes` | query `after?` (id), `limit?` (30), `naoLidas?` | `{items: Notificacao[], naoLidas: int}` (do usuário logado) | |
| `POST /api/notificacoes/lidas` | `{ids: int[]}` ou `{todas: true}` | `{naoLidas: int}` | |

## Integrações
| Método e rota | Corpo | 200 | Erros |
|---|---|---|---|
| `GET /api/integracoes` | – | `Integracoes` (sem valores de chave; o OpenShorts é consultado em `/health` com timeout de 2 s e cache de 30 s) | |

**Códigos de erro novos:** `invalid_channel_input`, `canal_not_found`, `canal_exists`,
`youtube_quota`, `youtube_error`, `youtube_unconfigured`, `sync_running`, `invalid_padroes`,
`already_selected`, `already_sent`, `video_unavailable`, `invalid_url`, `aviso_direito`,
`invalid_config`, `postagem_exists`, `corte_not_ready`, `planned_in_past`, `claude_unconfigured`,
`claude_error`, `textos_timeout` e `textos_invalidos`.

**Edge:**
- `location = /api/perfis/…/envios/arquivo` (regex), com `client_max_body_size 2100m`,
  `proxy_request_buffering off` e timeouts longos, como a de cortes da 004;
- o imgproxy ganha as fontes remotas do YouTube (R13);
- a CSP não muda.

## Rotas do SPA
| Rota | Conteúdo |
|---|---|
| `/app/fontes` | lista de canais (avatar, nome, inscritos, vídeos, selo de direito com aviso em `sem_acordo`, perfis ligados, estado da sync); "Adicionar canal" (colar → prévia → perfis → salvar) |
| `/app/fontes/:id` | detalhe: direito (editável só pelo dono) com evidência, perfis, sync ("Sincronizar agora"), vídeos do canal e histórico |
| `/app/descobrir` | seletor de perfil no topo; filtros (canal, período, duração, "não cortados", texto); cartões ou tabela com miniatura, título, canal, duração, publicação, views, views/h, pontuação e **motivo**; "Selecionar para corte" (um clique, desfazível) e seleção em lote; "Colar link" e "Enviar arquivo" (avulso); barra fixa "N selecionados → Enviar para corte" |
| `/app/envios` | aba **Selecionados** (por perfil, com "Enviar para corte": diálogo com os padrões do perfil editáveis, aviso de direito quando cabe, confirmação de duplicado) e aba **Envios** (status ao vivo: "Na fila (2º)", "Processando: 3 clipes prontos", "Importando 4/6", "Pronto", "Sem clipes", "Falhou" com "Tentar de novo") |
| `/app/envios/:id` | revisão: clipes lado a lado (player, trecho, gancho editável, título do OpenShorts, score), "Arquivar", "Aplicar marca" (um, vários ou todos), status da marca por clipe |
| `/app/calendario` | semana/mês, filtros de perfil e plataforma, coluna "Prontos sem data", arrastar para marcar ou remarcar (toque → diálogo) |
| `/app/cortes/:id` | + seção **Postagem**: uma aba por conta de destino; "Sugerir textos" / "Outra versão"; título (contador 100), descrição (2.000), hashtags (chips, 3–8 recomendadas); data e hora; "Salvar"; "Copiar título / descrição / hashtags / tudo"; "Baixar vídeo"; "Marcar como postado" (link opcional); histórico |
| `/app/perfis/:id` aba **Padrões de corte** | formulário dos padrões, com histórico |
| Topbar | **sino** com contagem, lista, "marcar todas como lidas" e "Avisar também pelo navegador" |
