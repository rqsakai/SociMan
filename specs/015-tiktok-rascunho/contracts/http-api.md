# Contrato HTTP: 015-tiktok-rascunho

Fonte de desenho; na implementação a fonte vira o OpenAPI do FastAPI (princípio IV), gerado com
`npm run gen:contract`. Convenções da 014: tudo sob `/api`, envelope de erro da 001, JSON em
camelCase, **nenhuma rota DELETE**, datas com o offset de `APP_TZ`.

**Nomes (research R21):** nenhum caminho nem `operationId` contém `tiktok`, `publish`, `share`,
`post-to`, `upload-to`, `youtube` nem `instagram`. O guarda `test_nenhuma_rota_de_publicacao`
continua **sem exceção**. A rede aparece só no corpo (`rede: "tiktok"`). Prefixos de
`operationId`: `conexoes_*`, `publicacao_config_*`, `destinos_*`.

**Permissões:**
- `RequireUser`: dono ou membro, sessão humana;
- `RequireOwner`: dono (014);
- **`RequireHumanOwner`** (novo, research R15): dono **e** `actor.kind == "user"`. Qualquer
  outro ator (cliente MCP da 009, `system:*`) → 403 `somente_humano` + evento
  `publicacao_recusada`. Marcado com **H** nas tabelas.

## Tipos
```text
Rede            "tiktok"                                     # cresce com as próximas specs
ConexaoEstado   "nao_conectada"|"conectada"|"precisa_reconectar"
Conexao         { contaId, rede, estado: ConexaoEstado, username|null, displayName|null,
                  avatarUrl|null (via /img), escopos: string[], conectadoPor: UserRef|null,
                  conectadoEm|null, motivo|null, refreshExpiraEm|null,
                  modos: ModoInfo[] }                         # os mesmos de GET /contas/{id}/modos
ModoInfo        { modo, disponivel, motivo|null, aviso|null } # 014 + `aviso` (R12)
Criador         { username, displayName, avatarUrl|null, podePostar: bool,
                  privacyLevelOptions: Privacidade[], comentarioDesligado: bool,
                  duetoDesligado: bool, costuraDesligada: bool, duracaoMaximaS: int,
                  situacaoApp: "sandbox"|"auditado" }
Privacidade     "PUBLIC_TO_EVERYONE"|"MUTUAL_FOLLOW_FRIENDS"|"FOLLOWER_OF_CREATOR"|"SELF_ONLY"
OpcoesTikTok    { privacidade: Privacidade, permitirComentario: bool, permitirDueto: bool,
                  permitirCostura: bool, comercial: "nenhum"|"sua_marca"|"parceria_paga",
                  conteudoIa: bool, consentimento: { texto: str, aceitoEm } }
PublicacaoConfig{ servidorHabilitado: bool,                  # PUBLICACAO_HABILITADA (só leitura)
                  enviosHabilitados: bool,                   # o interruptor da tela
                  tokensConfigurados: bool, appConfigurado: bool,
                  situacaoApp: "sandbox"|"auditado",
                  enderecosLogin: { web: str|null, desktop: str|null },
                  vencidos: int, emAndamento: int, version }
TentativaFase   "iniciando"|"enviando_partes"|"processando"|"entregue"|"publicada"
                |"recusada"|"incerta"|"sem_vaga"
Tentativa       { id, numero, modo, fase: TentativaFase, disparo, disparadoPor: UserRef|null,
                  iniciadaEm, concluidaEm|null, publishId|null, statusRede|null,
                  codigoRede|null, motivo|null, acao|null, redePostId|null,
                  partesEnviadas, totalPartes, video: { ref, bytes, sha256|null } }
```
Ampliações dos tipos da 014:
- `DestinoEstado` + `"enviando"`; `EstadoEfetivo` + `"enviando"|"pausado"|"vencido"|
  "aguardando_vaga"`;
- `Destino` + `{ opcoesRede: OpcoesTikTok|null, agendadoPor: UserRef|null, agendadoEm|null,
  envioConfirmado: {por, em}|null, falhaIncerta: bool, redePostId|null, redePostUrl|null,
  ultimaTentativa: Tentativa|null, snapshotDesatualizado: bool, avisosRede: str[] }`
  (`snapshotDesatualizado`: textos mudaram depois do snapshot, só leitura; `redePostUrl` montado
  como `https://www.tiktok.com/@{username}/video/{redePostId}`);
- `DestinoResumo` + `ultimaFase: TentativaFase|null`;
- `ContaRef` + `conexao: ConexaoEstado` (só TikTok; demais redes `nao_conectada`);
- `Atalhos` + `vencidos`, `enviando`, `rascunhosCriados`.

## Conexão da conta
| Método e rota (`operationId`) | Perm. | Corpo | 200 | Erros |
|---|---|---|---|---|
| `GET /api/contas/{id}/conexao` (`conexoes_get`) | User | – | `{conexao: Conexao}` (membro vê o estado; os botões só para dono) | 404 |
| `POST /api/contas/{id}/conexao/iniciar` (`conexoes_iniciar`) | **H** | `{}` | `{autorizarUrl, expiraEm}` (state no Redis, 10 min) | 400 `conta_invalida` (não é TikTok, arquivada, encerrada); 409 `ja_conectada`; 409 `endereco_de_login` (`details.abrirEm`); 503 `publicacao_nao_configurada` (sem `TIKTOK_CLIENT_KEY`/`SECRET` ou `SOCIMAN_TOKENS_KEY`) |
| `POST /api/conexoes/retorno` (`conexoes_retorno`) | **H** | `{state, code?, error?, errorDescription?}` | `{conexao, contaId, perfilId}` | 400 `state_invalido` (expirado, usado, de outro usuário); 409 `autorizacao_negada`; 409 `escopo_faltando` (`details.faltando`); 409 `conta_diferente` (`details: {autorizado, esperado}`); 409 `conexao_em_uso`; 409 `identidade_indisponivel`; 502 `rede_indisponivel` |
| `POST /api/contas/{id}/conexao/desconectar` (`conexoes_desconectar`) | **H** | `{version}` | `{conexao}` (`nao_conectada`; revoga em melhor esforço; apaga a credencial) | 409 `version_conflict`; 409 `envio_em_andamento` (há destino `enviando`) |
| `GET /api/contas/{id}/conexao/criador` (`conexoes_criador`) | **H** | – | `{criador: Criador}` (consulta **na hora**; atualiza o avatar) | 409 `conta_nao_conectada`; 409 `precisa_reconectar`; 409 `escopo_faltando` (sem `video.publish`); 429 `tente_em_instantes`; 502 `rede_indisponivel` |
| `GET /api/contas/{id}/conexao/versions` (`conexoes_versions`) | User | – | `{items: Version[]}` | 404 |

- O retorno **não** é chamado pela TikTok: é o SPA (`/app/conexoes/retorno`) que faz o `POST` com
  o Bearer (research R1).
- `desconectar` com destinos automáticos agendados: responde 200 e os destinos passam a
  `atencao` ("Conta não conectada"); a resposta traz `details.agendamentosEmAtencao`.

## Interruptor e situação (`/api/publicacao/config`)
| Método e rota (`operationId`) | Perm. | Corpo | 200 | Erros |
|---|---|---|---|---|
| `GET /api/publicacao/config` (`publicacao_config_get`) | User | – | `{config: PublicacaoConfig}` | |
| `PUT /api/publicacao/config` (`publicacao_config_update`) | **H** | `{version, enviosHabilitados}` | `{config}` (ao ligar, `vencidos` diz quantos pedem confirmação) | 409 `version_conflict` |
| `GET /api/publicacao/config/versions` (`publicacao_config_versions`) | User | – | `{items: Version[]}` | |

## Destinos: execução (ampliação de `/api/destinos`)
| Método e rota (`operationId`) | Perm. | Corpo | 200 | Erros |
|---|---|---|---|---|
| `GET /api/destinos/{id}/tentativas` (`destinos_tentativas`) | User | – | `{items: Tentativa[]}` (mais nova primeiro) | 404 |
| `POST /api/destinos/{id}/tentar-de-novo` (`destinos_tentar_de_novo`) | **H** | `{version, confirmoQueNaoChegou?: bool}` | `{destino}` (`agendado`, `planned_at = agora`, reivindicado na próxima volta) | 409 `conflict` (não está `falhou`); 409 `confirmacao_necessaria` (`falhaIncerta` sem `confirmoQueNaoChegou`); 409 `conta_nao_conectada`; 409 `version_conflict` |
| `POST /api/destinos/{id}/confirmar-envio` (`destinos_confirmar_envio`) | **H** | `{version}` | `{destino}` (vencido liberado para a próxima volta) | 409 `conflict` (não está `vencido`); 409 `version_conflict` |

## Mudanças nas rotas da 014
| Rota da 014 | Mudança |
|---|---|
| `GET /api/contas/{id}/modos` | `ModoInfo.aviso`; camadas 2 e 3 preenchidas (research R12) |
| `POST /api/agendamentos`, `PATCH /api/destinos/{id}/agendamento`, `POST /api/agendamentos/lote/reagendar`, `POST /api/agendamentos/sequencia` | modo automático (o pedido ou o atual do destino): exige **H** no service; no lote, a recusa vai por item em `falhas` (membro → 403 `somente_dono`; não humano → 403 `somente_humano`); modo `publicar` exige `opcoes: OpcoesTikTok` (400 `opcoes_invalidas` com `details.problemas`); grava `agendado_por` e `envio_snapshot`; devolve `avisosRede` (duração, tamanho, proporção). Na sequência, `publicar` é recusado (409 `modo_indisponivel`, "Publicar exige a tela da TikTok para cada vídeo"): só `criar_rascunho` e `lembrete` em lote |
| `POST /api/destinos/{id}/agendamento/cancelar`, `POST /api/agendamentos/lote/cancelar` | modo automático: **H**; aceita também `falhou` (vira `aprovado`); `enviando` → 409 `envio_em_andamento` |
| `PATCH /api/destinos/{id}/agendamento`, `POST /api/agendamentos/lote/reagendar`, `POST /api/agendamentos` (destino existente) | aceitam também `falhou` (vira `agendado`); com `falhaIncerta`, exigem `confirmoQueNaoChegou: true` no corpo (por item no lote), senão 409 `confirmacao_necessaria` (Clarifications Q4) |
| `POST /api/destinos/{id}/archive`, `POST /api/conteudos/{id}/archive`, `POST /api/cortes/{id}/archive` | arquivar cancela: com destino automático `agendado`, exige **H** (membro → 403 `somente_dono`) |
| `PATCH /api/destinos/{id}` (textos) | destino `agendado` em modo `publicar`: só **H**, e regrava o snapshot (`details.acao = snapshot_atualizado`; Clarifications Q2); `enviando` → 409 `envio_em_andamento` |
| `POST /api/destinos/{id}/postado` | aceita também `rascunho_criado` |
| `POST /api/destinos/{id}/revert`, `/archive`; `POST /api/conteudos/{id}/archive`; `POST /api/cortes/{id}/archive`; "Aplicar marca" do corte | `enviando` → 409 `envio_em_andamento` |
| `POST /api/destinos/{id}/aprovar`, `/lote/aprovar` | sem mudança de rota; o service registra `aprovado_por` (já na 014) — a trilha confere que é humano |
| `GET /api/conteudos` | `estado` aceita os derivados novos; `atalho` aceita `vencidos`, `enviando`, `rascunhos_criados` |

**Códigos de erro novos:** `somente_humano`, `somente_dono`, `publicacao_nao_configurada`,
`endereco_de_login`, `state_invalido`, `autorizacao_negada`, `escopo_faltando`,
`conta_diferente`, `conexao_em_uso`, `identidade_indisponivel`, `ja_conectada`,
`conta_nao_conectada`, `precisa_reconectar`, `rede_indisponivel`, `tente_em_instantes`,
`opcoes_invalidas`, `envio_em_andamento`, `confirmacao_necessaria`.

**MCP (009):** nenhuma rota marcada **H** pode virar tool. O MCP pode, no máximo, ler
`GET /api/contas/{id}/conexao` (sem os botões) e `GET /api/destinos/{id}/tentativas`.

## Edge e CSP
- **Nenhuma `location` nova.** O retorno do OAuth é uma rota do SPA servida pelo `location /`
  nos dois endereços (HTTPS pelo IP da casa, HTTP em `localhost`); o `POST` de retorno cai no
  `location /api/`.
- **CSP igual** (`img-src 'self' data:`): o avatar do criador é servido pelo `/img` a partir do
  MinIO (research R14). A navegação para `www.tiktok.com` é de topo (não é afetada por
  `connect-src` nem `form-action`).
- Saída HTTPS dos containers `api` e `agendador` para `open.tiktokapis.com`, o host de upload e a
  CDN do avatar (a rede do compose já tem saída; nada muda).

## Variáveis de ambiente (nomes; valores só no `.env` da raiz, gitignored)
| Variável | Serviços | Padrão | Uso |
|---|---|---|---|
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` | api, agendador | vazio | app do portal (já existem no `.env`); `SecretStr` |
| `SOCIMAN_TOKENS_KEY` | api, agendador | vazio | chave AES-256-GCM (R4); `SecretStr` |
| `SOCIMAN_TOKENS_KEY_ANTERIOR` | api, agendador | vazio | rotação (R4) |
| `PUBLICACAO_HABILITADA` | api, agendador | `false` | nível do servidor do interruptor (R11) |
| `TIKTOK_APP_SITUACAO` | api, agendador | `sandbox` | `sandbox` \| `auditado` (R12) |
| `TIKTOK_REDIRECT_WEB` | api | vazio | ex.: `https://192.168.86.47:8543/app/conexoes/retorno` |
| `TIKTOK_REDIRECT_DESKTOP` | api | vazio | ex.: `http://localhost:8180/app/conexoes/retorno` (PKCE) |
| `TIKTOK_SCOPES` | api | `user.info.basic,user.info.profile,video.upload,video.publish` | R3 |
| `TIKTOK_API_URL`, `TIKTOK_UPLOAD_HOSTS` | api, agendador | vazio (= constantes de `publicacao/tiktok/cliente.py`) | só o e2e aponta para o fake |
| `AGENDADOR_PUBLICACAO_S` | agendador | `15` | intervalo da trilha |

## Rotas do SPA
| Rota / componente | Conteúdo |
|---|---|
| `/app/conexoes/retorno` | página sem layout: lê `code`, `state`, `error` da URL, faz o `POST /api/conexoes/retorno` e volta para a conta; mostra o erro em pt-BR (ex.: conta diferente) com "Tentar de novo" |
| Aba **Contas** do perfil (`/app/perfis/:id`) | por conta TikTok: `ConexaoCard` com estado, @, apelido, avatar, data, modos; **Conectar** / **Desconectar** / **Reconectar** só para dono (membro vê só o estado) |
| `/app/configuracoes/publicacao` (dono) | interruptor "Envios automáticos", estado do nível do servidor, situação do app, endereços de login configurados, "Revisar vencidos" |
| `AgendarDialog` (014) | modo com `aviso`; em **Publicar**, o `TikTokPostForm`: apelido e avatar do `criador` consultado na hora, privacidade em lista **sem padrão**, três toggles desmarcados (bloqueados quando a conta desligou), divulgação comercial, conteúdo de IA, frase de consentimento, pré-visualização e "a TikTok leva alguns minutos"; sem preencher, **Agendar** fica desabilitado |
| `DestinoPanel` (014) | estado de execução (enviando com progresso de partes, rascunho criado, publicado, falhou com motivo e ação, aguardando vaga, pausado, vencido com **Confirmar envio**); **Copiar textos**; **Histórico do envio** (aprovação, agendamento, tentativas) |
| Calendário e lista (014) | chips com os estados novos; atalhos `Vencidos`, `Enviando`, `Rascunhos criados` |
