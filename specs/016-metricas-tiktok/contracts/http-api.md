# Contrato HTTP: 016-metricas-tiktok

Este arquivo é a fonte do desenho. Na implementação, a fonte passa a ser o OpenAPI do FastAPI
(princípio IV), gerado com `npm run gen:contract`. Convenções da 014 e da 015:
- tudo sob `/api`, com o envelope de erro da 001;
- JSON em camelCase;
- **nenhuma rota DELETE**;
- datas ISO com o offset de `APP_TZ` (`America/Sao_Paulo`).

**Nomes:** nenhum caminho nem `operationId` contém `tiktok`, `publish`, `share`, `post-to`,
`upload-to`, `youtube` ou `instagram`. O guarda `test_nenhuma_rota_de_publicacao` continua **sem
exceção**, e a rede aparece só no corpo (`rede: "tiktok"`). Por isso o link do post se chama
`url`, e não `shareUrl`.

Prefixos de `operationId`:
- `metricas_*` para `/api/metricas/*` e `/api/contas/{id}/metricas`;
- `destinos_*` para `/api/destinos/{id}/…`, como pede o guarda da 014;
- `conexoes_*` para as rotas da 015 que mudam.

**Permissões:**
- `RequireUser`: dono ou membro, sessão humana (ver métricas);
- `RequireOwner`: dono (exportar);
- **`RequireHumanOwner`** (**H**, da 015): dono **e** `actor.kind == "user"`. Serve para ligar,
  escolher, colar e desfazer vínculo, e para reconectar e desconectar. Qualquer outro ator → 403
  `somente_humano` + evento `publicacao_recusada`.

## Tipos
```text
Rede              "tiktok"
PermissaoColeta   "ok"|"faltando"|"sem_conexao"
EstadoColeta      { permissao: PermissaoColeta, escoposFaltando: string[],
                    coletando: bool,                          # série ativa agora
                    habilitada: bool,                         # METRICAS_COLETA_HABILITADA
                    ultimaColetaEm|null, proximaColetaEm|null,
                    erro: { codigo, motivo, em }|null,        # pt-BR
                    varreduraConcluida: bool,
                    videos: int, fotos: int }
Contadores        { views|null, likes|null, comments|null, shares|null }
FotoVideo         { coletadoEm, idadeS: int, alvoIdadeMin: int } & Contadores
FotoConta         { coletadoEm, janelaEm, seguidores|null, seguindo|null,
                    curtidas|null, videos|null }
MarcoValor        { valor: number|null, estimado: bool,
                    motivo: null|"ainda_nao"|"sem_dado" }
Marcos            { h1: {views, likes, comments, shares: MarcoValor},
                    h24: …, d7: …, d30: … }
Origem            "corte"|"video_proprio"|"fora"|"anonima"
VinculoMetodo     "envio"|"casamento"|"link"|"escolha"
VideoResumo       { id,                                       # uuid do SociMan (video_ref)
                    rede, contaId|null, conta: ContaRef|null, # null se anônimo
                    serieRotulo|null,                          # "Conta anônima N"
                    perfil: PerfilRef|null,
                    origem: Origem, publicadoEm, duracaoS,
                    legenda|null, url|null,                   # link do post (null se anônimo)
                    disponivel: bool, indisponivelDesde|null,
                    conteudoId|null, destinoId|null, vinculoMetodo|null,
                    miniaturaUrl|null,                        # a do conteúdo no SociMan (/img)
                    ultima: FotoVideo|null,
                    views24h: MarcoValor, views7d: MarcoValor,
                    engajamento: number|null,                  # (likes+comments+shares)/views
                    velocidade: number|null }                  # views/h nas últimas 24 h
VideoDetalhe      VideoResumo & { fotos: FotoVideo[], marcos: Marcos,
                    coletaParadaEm|null }                      # > 365 d
Ancora            "entrega"|"postado"|null                   # R10 (Q3 = A); null = lembrete antes do clique
Candidato         { video: VideoResumo, duracaoDiferencaS: number,
                    legenda: "compativel"|"neutra"|"incompativel",
                    minutosDaAncora: int|null }              # publicadoEm − âncora (pode ser < 0);
                                                              #   sem âncora: − planned_at (ou aprovado_em)
VinculoEstado     "vinculado"|"buscando"|"a_confirmar"|"sem_vinculo"|"indisponivel"
Vinculo           { estado: VinculoEstado, video: VideoResumo|null,
                    metodo: VinculoMetodo|null, vinculadoPor: UserRef|null,  # null = automático
                    vinculadoEm|null,
                    busca: { entregueEm, consultas: int, ate, fim|null }|null,
                    ancora: Ancora, ancoraEm|null,            # entregue_em ou posted_at
                    candidatos: Candidato[],                  # vazio se vinculado; no lembrete antes
                                                              #   do clique, a lista para escolher (R11)
                    bloqueado: bool,                           # houve vinculo_desfeito (R10)
                    automatico: bool,                          # false depois de desfeito
                    podeVincular: bool, motivo|null }          # ex.: "Este destino ainda não pode ser ligado a um post"
```

Ampliações dos tipos da 015:
- `Conexao` + `metricas: EstadoColeta|null` (`null` em rede sem leitor). `GET
  /api/contas/{id}/conexao` e o `ContaRef` do `ConexaoCard` passam a trazê-lo;
- `DesconectarIn { version: int, confirmoAnonimizar: bool = false }` (antes era o `VersionIn`).

## Rotas novas

### Métricas de conta
| Método e caminho | `operationId` | Perm. | Corpo / query | Resposta |
|---|---|---|---|---|
| `GET /api/contas/{id}/metricas` | `metricas_conta` | User | `?de&ate&resolucao=auto\|hora\|dia` (`auto`: hora até 14 dias, dia além disso, com a última foto de cada dia) | `{ coleta: EstadoColeta, fotos: FotoConta[], publicacoes: [{videoId, publicadoEm, conteudoId\|null}] }` |

### Vídeos, ranking e curva
| Método e caminho | `operationId` | Perm. | Corpo / query | Resposta |
|---|---|---|---|---|
| `GET /api/metricas/videos` | `metricas_videos_list` | User | `?perfilId&contaId&origem=corte,video_proprio,fora,anonima&de&ate` (período de **publicação**) `&ordem=views24h\|views7d\|engajamento\|velocidade\|publicadoEm&direcao=desc\|asc&cursor&limite≤100` (padrão 50) | `{ items: VideoResumo[], nextCursor\|null, total }` |
| `GET /api/metricas/videos/{id}` | `metricas_videos_get` | User | | `VideoDetalhe` |

### Métricas e vínculo do destino
| Método e caminho | `operationId` | Perm. | Corpo | Resposta |
|---|---|---|---|---|
| `GET /api/destinos/{id}/metricas` | `destinos_metricas` | User | | `{ vinculo: Vinculo, video: VideoDetalhe\|null }` |
| `GET /api/destinos/{id}/vinculo` | `destinos_vinculo_get` | User | | `Vinculo` |
| `POST /api/destinos/{id}/vinculo` | `destinos_vinculo_criar` | **H** | `{ version, videoId }` **ou** `{ version, link }` (exatamente um) | `{ destino: Destino, vinculo: Vinculo }`. Num lembrete em `aprovado`/`agendado`, também marca o destino como `postado` (`marcar_postado` da 014, com `posted_url = link` ou `null`; R12, Q3 = A) |
| `POST /api/destinos/{id}/vinculo/desfazer` | `destinos_vinculo_desfazer` | **H** | `{ version }` | `{ destino: Destino, vinculo: Vinculo }` |

### Exportação
| Método e caminho | `operationId` | Perm. | Query | Resposta |
|---|---|---|---|---|
| `GET /api/metricas/export` | `metricas_export` | Owner | `formato=csv\|jsonl`, `de`, `ate` (período das **fotos**, obrigatório, até 400 dias), `perfilId?`, `contaId?`, `incluirAnonimas=false` | `200 application/zip`, com `Content-Disposition: attachment; filename="sociman-metricas-AAAAMMDD-AAAAMMDD.zip"`. Os arquivos estão em research R16 |

## Rotas da 015 que mudam
| Rota | Mudança |
|---|---|
| `POST /api/contas/{id}/conexao/iniciar` (**H**) | com a conexão `conectada` e **faltando** os escopos de métricas, inicia o login (antes: 409 `ja_conectada`). Com todos os escopos, continua 409 `ja_conectada`. Com destino `enviando` na conta, 409 `envio_em_andamento` |
| `POST /api/conexoes/retorno` (**H**) | a conexão `conectada` com o mesmo `open_id` é reusada (`acao: "ampliada"`) e a credencial trocada. A resposta traz `conexao.metricas`. `sem_permissao_desde` da série é limpo |
| `POST /api/contas/{id}/conexao/desconectar` (**H**) | corpo `DesconectarIn`. Com a série com dados e sem `confirmoAnonimizar: true` → 409 `confirmar_anonimizacao` com `details: {videos, fotos, conta: "@x"}`. Com a confirmação, anonimiza na mesma transação (R13). A resposta ganha `metricasAnonimizadas: {videos, fotos}\|null` |
| `GET /api/contas/{id}/conexao` | + `metricas: EstadoColeta` |

## Erros novos
| HTTP | `code` | Quando | Mensagem (pt-BR) |
|---|---|---|---|
| 409 | `confirmar_anonimizacao` | desconectar sem confirmar, com a série com dados | "As métricas de @x serão anonimizadas. Confirme para desconectar" |
| 409 | `video_ja_vinculado` | escolher ou colar um vídeo já ligado a outro destino | "Este post já está ligado a outro conteúdo; desfaça lá primeiro" (`details.destinoId`) |
| 409 | `destino_ja_vinculado` | ligar um destino que já tem vínculo | "Este destino já está ligado a um post; desfaça antes de trocar" |
| 409 | `destino_sem_post` | ligar um destino num estado fora da tabela de R12 (ex.: rascunho em revisão, `enviando`, `falhou` sem incerteza, arquivado) | "Este destino ainda não pode ser ligado a um post" |
| 409 | `sem_vinculo` | desfazer sem vínculo | "Este destino não está ligado a nenhum post" |
| 400 | `link_invalido` | link sem `/video/<id>`, ou encurtado | "Cole o link completo do post (tiktok.com/@conta/video/…)" / "Abra o link e copie o endereço completo" |
| 409 | `link_outra_conta` | `@` do link diferente do `@` da conta | "O link é de @x; este destino é de @y" |
| 404 | `post_nao_encontrado` | o `video/query` não devolve o id | "Não achamos este post em @y (é de outra conta, privado ou foi apagado)" |
| 409 | `metricas_indisponiveis` | ligar ou colar com a conta sem série ativa | "Conecte a conta e libere as métricas para ligar o post" |
| 502 | `rede_indisponivel` | a TikTok não respondeu à validação do link | "A TikTok não respondeu; tente de novo em instantes" |
| 503 | `storage_unavailable` | exportação que passa de 32 MB sem o HD (`datadir`, sentinela) | "O HD de dados não está disponível" (o do `datadir`) |
| 507 | `storage_full` | idem, com o HD abaixo do piso de espaço | "Pouco espaço no HD de dados" (o do `datadir`) |
| 400 | `periodo_invalido` | exportação sem `de`/`ate`, com `de > ate` ou com mais de 400 dias | "Escolha um período de até 400 dias" |

`version_conflict` (409), `somente_humano` (403) e `not_found` (404) seguem a 014 e a 015.

## Variáveis de ambiente
| Nome | Serviços | Padrão | Uso |
|---|---|---|---|
| `METRICAS_COLETA_HABILITADA` | `api`, `agendador` | `true` | `false` deixa a trilha `metricas` ociosa, sem apagar nem anonimizar nada. O `EstadoColeta.habilitada` mostra o valor |
| `AGENDADOR_METRICAS_S` | `agendador` | `60` | intervalo da trilha (o e2e usa `2`) |
| `TIKTOK_SCOPES` | `api` | `user.info.basic,user.info.profile,video.upload,video.publish,user.info.stats,video.list` | o padrão ganha os 2 escopos de métricas |

Nenhuma variável nova é segredo. O `check:secrets` não muda.

## O que o SPA consome
- `ConexaoCard` → `conexao.metricas` (`ColetaStatus`), e o botão "Reconectar para liberar
  métricas" (dono) chama `iniciar`. O `DesconectarDialog` repete com `confirmoAnonimizar` depois
  do 409 `confirmar_anonimizacao`;
- `DestinoPanel` → `GET /destinos/{id}/metricas` (seção "Desempenho", com `VinculoPanel`);
- `/app/metricas` → `GET /metricas/videos` (Ranking) e `GET /contas/{id}/metricas` (Contas);
- `/app/metricas/videos/:id` → `GET /metricas/videos/{id}`;
- `ExportarDialog` → `GET /metricas/export` por `fetch` com Bearer, salvo como `Blob`.

As queries são invalidadas pelo TanStack Query depois de ligar, desfazer, reconectar e
desconectar.
