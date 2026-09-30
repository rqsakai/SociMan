# Feature Specification: Rascunho e publicação agendados no TikTok (015-tiktok-rascunho)

**Feature Branch**: `015-tiktok-rascunho`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "Executar no TikTok os agendamentos da central de conteúdos (014):
conectar as contas TikTok (só donos) pelo login oficial com o app sandbox do dono; no horário,
criar o rascunho na conta (ou publicar, com as limitações da TikTok); acompanhar até o fim; nunca
enviar duas vezes; respeitar os limites. Primeiro teste real: rascunho para @atavernanerd e
@meusqueridinhos10 no sandbox. Modelo pronto para YouTube e Instagram depois."

## Clarifications

### Session 2026-09-29

- Q: Base de governança? → A: Constitution 4.0.0, princípio I "Publicação só com decisão humana":
  só para postagem aprovada e agendada por um dono; nenhuma IA, agente ou MCP conecta, aprova, agenda
  ou publica; só pelo módulo de integração; histórico; cancelamento antes do horário; interruptor
  geral.
- Q: Quem conecta contas e envia? → A: Só donos.
- Q: Onde fazer o login das contas? → A: Primeiro pelo endereço da casa; se o portal da TikTok não
  aceitar, pelo endereço local no computador do dono (sakai-desktop).
- Q: Quais modos o TikTok oferece? → A: "Criar rascunho no horário" disponível; "Publicar no horário"
  disponível com aviso (sem auditoria da TikTok, o post sai privado e a conta precisa estar privada);
  "Rascunho antes e publicar no horário" indisponível (a TikTok não permite publicar um rascunho).
  Base: `docs/pesquisa/publicacao-redes.md`.
- Q: Como contar o limite de "5 rascunhos pendentes em 24 h", se a TikTok não informa quando o
  dono finaliza um rascunho no app? → A: Contar localmente (opção A). Contam os rascunhos cujo
  envio começou nas últimas 24 h para a conta, mesmo que o dono já tenha finalizado algum no app.
  O 6º espera "aguardando vaga" até o mais antigo completar 24 h; se a TikTok recusar antes por
  excesso, também espera. Dá para afrouxar depois do teste real.
- Q: Quem edita os textos de um "Publicar no horário" já agendado? → A: Só um dono (opção A). A
  edição vale como nova confirmação: o SociMan regrava o que será publicado (snapshot) e registra
  no histórico. No rascunho e no lembrete, os textos continuam livres, como na 014.
- Q: Como é o interruptor geral? → A: Dois níveis (opção A): `PUBLICACAO_HABILITADA` no `.env` do
  servidor (desligado por padrão) **e** o botão "Envios automáticos" na tela. Só envia com os dois
  ligados; com qualquer um desligado, nada sai para a TikTok.
- Q: "Tentar de novo" quando a TikTok talvez tenha recebido (o SociMan caiu entre o pedido e a
  resposta)? → A: Permitido (opção A). O estado mostra "Falhou: a TikTok pode ter recebido", e
  qualquer ação que devolva o envio à fila (Tentar de novo, reagendar, agendar de novo) exige
  marcar "Conferi no app e o rascunho não chegou".

- Q: Com o interruptor desligado, um envio já em andamento termina? → A: **Não.** Com qualquer nível
  desligado, nada sai para a TikTok (nenhum início e nenhuma parte); o envio fica "pausado" e retoma
  ao religar, sem risco de duplicar (confirmado pelo dono).
- Q: Membro pode arquivar um conteúdo com envio automático agendado? → A: **Não.** Arquivar cancela o
  agendamento automático, então exige dono humano (confirmado pelo dono).

- Q: O portal da TikTok aceitou o redirect com o IP da casa? → A: **Sim** (dono, 2026-09-29):
  `https://192.168.86.47:8543/app/conexoes/retorno` está cadastrado e é o caminho principal; o
  `http://localhost:8180/app/conexoes/retorno` fica como reserva.

- Q: Dá para enviar na hora, sem agendar? → A: **Sim** (dono, 2026-09-29): ação **"Enviar agora"** no painel da conta
  e no diálogo Agendar, só para dono humano com a conta conectada, nos modos automáticos disponíveis
  (hoje "Criar rascunho"). Aprova se preciso e agenda para o horário atual; a trilha envia na próxima volta,
  com as mesmas regras (interruptor, limites, idempotência, histórico) e uma confirmação antes.

- Q: "Publicar no horário" fica para depois do teste? → A: **Não — correção do dono (2026-09-29):** um agendamento
  feito na interface por um dono **precisa ser respeitado**; a IA/agente/MCP nunca posta sozinha, mas o post
  aprovado e agendado por um humano é publicado no horário. A US3 passa a **P1** e entra agora. A única
  restrição que fica é a da TikTok (sem auditoria: só privado "Só eu" e conta privada), mostrada com
  honestidade na tela; ao auditar, basta mudar `TIKTOK_APP_SITUACAO=auditado`.
- Q: Onde aparece o rascunho enviado? → A: status final `SEND_TO_USER_INBOX` (teste real 2026-09-29): vai para a
  caixa de entrada do **app** da conta (notificações do sistema / rascunhos), não para o TikTok Studio web.

- Q: Título e descrição na TikTok? → A: **Regra do dono (2026-09-29):** a TikTok não tem título, só **legenda** =
  descrição + hashtags (até 2.200 caracteres). Em destinos TikTok o SPA não mostra "Título"; mostra "Legenda"
  (descrição) + hashtags e a prévia da legenda final. A **descrição é obrigatória** para agendar (qualquer modo),
  "Enviar agora" e aprovar e agendar: sem ela, a API recusa (400 `legenda_obrigatoria`, "Descreva o post: na
  TikTok a legenda (descrição + hashtags) é obrigatória"); na sequência, o item sem descrição é pulado com esse
  motivo (salvo se a geração por IA estiver marcada). No "Publicar" a legenda composta vai no post; no rascunho,
  "Copiar textos" copia a mesma legenda composta.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Conectar uma conta TikTok (Priority: P1)

Na conta TikTok de um perfil (ex.: @atavernanerd), um dono clica em **Conectar**. O SociMan abre o
login oficial da TikTok; o dono entra com a conta e autoriza o app. De volta ao SociMan, a conta
aparece como **conectada**, com o nome e a foto que a TikTok informa, a data da conexão e os modos que
ela passa a oferecer. O dono pode **desconectar** a qualquer momento. A conexão se renova sozinha;
se a TikTok a revogar ou ela expirar, a conta aparece como "precisa reconectar" e os agendamentos
dela ficam em atenção.

**Why this priority**: sem a conta conectada, nada pode ser enviado.

**Independent Test**: conectar @atavernanerd e @meusqueridinhos10 no sandbox, ver as duas como
conectadas com nome e foto, desconectar uma e reconectar.

**Acceptance Scenarios**:

1. **Given** uma conta TikTok cadastrada, **When** um dono conecta e autoriza, **Then** a conta fica
   "conectada", com nome, foto, data e modos disponíveis, e a conexão fica no histórico.
2. **Given** um membro, **When** ele abre a conta, **Then** não vê "Conectar" nem "Desconectar" (só o
   estado da conexão).
3. **Given** o login feito com uma conta TikTok diferente da cadastrada (outro @), **When** volta ao
   SociMan, **Then** a conexão é recusada com a explicação, sem guardar nada.
4. **Given** uma conta conectada, **When** o dono desconecta, **Then** as credenciais são apagadas do
   SociMan, a conta volta a "não conectada" e os agendamentos automáticos dela ficam em atenção.
5. **Given** a autorização expirada ou revogada na TikTok, **When** o SociMan tenta usá-la, **Then** a
   conta vira "precisa reconectar", os donos recebem aviso e nenhum envio é tentado.

---

### User Story 2 - Rascunho criado no horário (Priority: P1)

Na central (014), um dono agenda um conteúdo aprovado para a conta TikTok conectada no modo **Criar
rascunho no horário**. No horário, o SociMan envia o vídeo final para a caixa de entrada da conta e
acompanha até a TikTok confirmar. O estado vira **rascunho criado**; o dono recebe o aviso no
SociMan e a notificação no app da TikTok, onde finaliza legenda, privacidade e produto do TikTok
Shop e publica. Os textos preparados no SociMan (título, descrição, hashtags) ficam à mão para
copiar.

**Why this priority**: é o modo viável hoje e o primeiro teste real pedido pelo dono.

**Independent Test**: agendar um corte da Taverna para daqui a 5 minutos em "Criar rascunho"; no
horário, ver o estado passar por "enviando" e chegar a "rascunho criado", receber a notificação no
app da TikTok e conseguir abrir o rascunho lá.

**Acceptance Scenarios**:

1. **Given** um agendamento "criar rascunho" com a conta conectada, **When** chega o horário, **Then** o
   vídeo é enviado, o estado passa por "enviando" e vira "rascunho criado", e os donos são avisados
   com um botão "Copiar textos".
2. **Given** a TikTok recusando (formato, tamanho, limite), **When** o envio falha, **Then** o estado
   vira "falhou" com o motivo em português e a ação "Tentar de novo" (que o dono dispara).
3. **Given** um envio já iniciado, **When** o agendador reinicia no meio, **Then** o SociMan retoma o
   acompanhamento e **nunca** envia o mesmo vídeo duas vezes para a mesma conta.
4. **Given** o limite de rascunhos pendentes da conta atingido (5 em 24 h), **When** chega o horário,
   **Then** o envio espera, o estado mostra "aguardando vaga na TikTok" e o dono é avisado.
5. **Given** o dono cancela antes do horário, **When** o horário chega, **Then** nada é enviado.

---

### User Story 3 - Publicar no horário, com as regras da TikTok (Priority: P1)

Num conteúdo aprovado, o dono escolhe **Publicar no horário**. Antes de confirmar, o SociMan mostra o
aviso da situação do app ("sem auditoria da TikTok, o post sai **só para você** e a conta precisa
estar privada") e a tela exigida pela TikTok: nome e foto da conta, privacidade **sem valor
padrão**, permitir comentários/dueto/costura (desmarcados e bloqueados se a conta os desligou),
declaração de conteúdo comercial (marca própria ou parceria paga) e a frase de consentimento de uso
de música. No horário, o SociMan publica e acompanha até a confirmação.

**Why this priority**: o dono quer o modo disponível, mas ele só é útil de verdade se a TikTok um
dia auditar o app.

**Independent Test**: com uma conta de teste privada, agendar um conteúdo para publicar como "só
eu" daqui a 5 minutos, preenchendo a tela obrigatória; ver o estado chegar a "publicado" e o post
privado na conta.

**Acceptance Scenarios**:

1. **Given** o modo publicar, **When** a tela abre, **Then** mostra os dados da conta consultados na
   hora e os campos obrigatórios, sem valor padrão na privacidade, e não deixa agendar sem preencher.
2. **Given** o app sem auditoria, **When** o dono escolhe privacidade pública, **Then** a opção aparece
   indisponível com a explicação.
3. **Given** conteúdo comercial marcado como "parceria paga", **When** o dono tenta privacidade "só
   eu", **Then** a combinação é recusada com a regra da TikTok.
4. **Given** o horário, **When** a publicação termina, **Then** o estado vira "publicado", com o link
   quando a TikTok informar.

---

### User Story 4 - Segurança e controle do envio (Priority: P1)

O dono tem um interruptor geral **Envios automáticos** (ligado/desligado). Desligado, nenhum
agendamento automático executa; eles ficam "pausados" e visíveis. Todo envio fica no histórico: quem
aprovou, quem agendou, quando enviou, o resultado e o identificador da TikTok. Nenhuma IA, agente ou
cliente MCP consegue conectar, aprovar, agendar ou disparar envio: as rotas recusam.

**Why this priority**: é o que a constitution 4.0.0 exige para liberar os envios.

**Independent Test**: desligar o interruptor, ver um agendamento para daqui a 2 minutos ficar
"pausado" sem enviar; religar e ver o envio acontecer; tentar agendar pela credencial de um cliente
MCP e ver a recusa.

**Acceptance Scenarios**:

1. **Given** o interruptor desligado, **When** chega o horário, **Then** o agendamento fica "pausado" e
   nada é enviado; ao religar, os vencidos pedem confirmação do dono antes de enviar.
2. **Given** qualquer envio, **When** o histórico é aberto, **Then** mostra aprovação, agendamento,
   início, fim, resultado e o identificador da TikTok.
3. **Given** um pedido vindo de IA, agente ou MCP, **When** tenta conectar, aprovar, agendar em modo
   automático ou disparar envio, **Then** é recusado e registrado.

---

### Edge Cases

- Vídeo fora das regras da TikTok (duração, tamanho, proporção): detectado ao agendar, com aviso; se
  passar e a TikTok recusar, "falhou" com o motivo.
- Conteúdo alterado (marca reaplicada) depois de agendado: envia a versão final vigente no horário e
  registra qual foi.
- Agendamento vencido com o SociMan desligado (ex.: queda de energia): ao voltar, os vencidos há mais
  de 1 hora pedem confirmação do dono em vez de enviar sozinhos.
- Duas contas do mesmo perfil no mesmo horário: cada envio é independente.
- Rede lenta: o envio em partes tolera falhas de uma parte e retoma, sem duplicar o post.
- Conta TikTok ficou pública enquanto o modo "publicar" exige privada: falha com a explicação.
- O app da TikTok deixa de ser sandbox (auditado): as capacidades mudam por configuração, sem nova
  versão do SociMan.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Donos DEVEM poder conectar e desconectar contas TikTok pelo login oficial da TikTok; a
  conexão só vale se a conta autorizada for a mesma cadastrada no perfil.
- **FR-002**: As credenciais da conexão DEVEM ser guardadas cifradas, nunca exibidas, renovadas
  automaticamente e apagadas ao desconectar; falha de renovação DEVE marcar "precisa reconectar" e
  avisar os donos.
- **FR-003**: O login DEVE funcionar pelo endereço da casa quando a TikTok aceitar e ter o caminho
  alternativo pelo endereço local no computador do dono.
- **FR-004**: As capacidades da conta TikTok DEVEM declarar: "criar rascunho" disponível;
  "publicar" disponível com o aviso de restrição (privado, conta privada) enquanto o app não for
  auditado; "rascunho e publicar" indisponível com o motivo. A situação do app (sandbox, auditado)
  DEVE ser configuração.
- **FR-005**: No horário de um agendamento automático, o SociMan DEVE enviar o arquivo final do
  conteúdo a partir da rede local (em partes), acompanhar até a confirmação e atualizar o estado para
  "rascunho criado", "publicado" ou "falhou" com motivo em pt-BR.
- **FR-006**: O envio DEVE ser idempotente: nunca criar dois rascunhos ou dois posts para o mesmo
  agendamento, inclusive após reinício ou falha no meio.
- **FR-007**: O SociMan DEVE respeitar os limites da TikTok (5 rascunhos pendentes por 24 h por conta
  e a taxa de requisições), esperando com o estado "aguardando vaga" em vez de falhar.
- **FR-008**: O modo "publicar" DEVE exigir a tela da TikTok: dados da conta consultados na hora,
  privacidade sem padrão, opções de interação respeitando as da conta, declaração de conteúdo
  comercial e consentimento de música; combinações proibidas pela TikTok DEVEM ser recusadas.
- **FR-009**: O interruptor geral `Envios automáticos` DEVE pausar todos os envios; vencidos há mais de
  1 hora, ao religar ou após o SociMan voltar, DEVEM pedir confirmação do dono.
- **FR-010**: Só donos (humanos) DEVEM conectar, aprovar, agendar em modo automático, cancelar e
  tentar de novo; pedidos de IA, agente ou MCP DEVEM ser recusados e registrados (princípio I).
- **FR-011**: Todo envio DEVE ficar no histórico com aprovação, agendamento, início, fim, resultado,
  versão do arquivo enviado e identificador da TikTok.
- **FR-012**: Nenhum código fora do módulo de integração do TikTok DEVE falar com a TikTok; o
  teste-guarda do princípio I DEVE verificar isso.
- **FR-013**: O desenho DEVE permitir acrescentar YouTube e Instagram como novos módulos, com suas
  capacidades, sem mudar a central (014).

### Key Entities

- **Conexão de conta**: conta social × app da rede, estado (conectada, precisa reconectar,
  desconectada), dados informados pela rede (nome, foto, identificador), credenciais cifradas,
  validade, autor e datas.
- **Envio para a rede**: agendamento × tentativa, identificador da rede, estado (enviando, rascunho
  criado, publicado, falhou, aguardando vaga, pausado), motivo, versão do arquivo, início e fim.
- **Configuração da rede**: situação do app (sandbox, auditado), capacidades por modo, interruptor
  geral.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Conectar uma conta TikTok leva menos de 2 minutos para o dono.
- **SC-002**: 95% dos rascunhos agendados aparecem na caixa de entrada do app da TikTok em até 5
  minutos após o horário.
- **SC-003**: 0 envios duplicados em testes com reinício do SociMan no meio do envio.
- **SC-004**: 0 envios executados com o interruptor desligado, sem aprovação de dono ou por pedido
  de IA/agente/MCP (verificado por teste).
- **SC-005**: No teste real do sandbox, as duas contas (@atavernanerd e @meusqueridinhos10) recebem
  o rascunho; fica registrado se o dono conseguiu publicar em público pelo app.
- **SC-006**: 100% das falhas mostram um motivo compreensível em pt-BR e uma ação possível.

## Assumptions

- Depende da spec 014 (central de conteúdos, aprovação, agendamento e modos) e do corte com marca
  aplicada como arquivo final.
- O app sandbox do dono e as credenciais dele já existem no ambiente do SociMan (fora do git); as duas
  contas já foram liberadas no sandbox.
- A TikTok não tem agendamento nativo: quem agenda é o SociMan, que envia no horário.
- A TikTok provavelmente não audita ferramenta interna; por isso "publicar" fica restrito a
  privado. Se o app for auditado, basta mudar a configuração.
- O SociMan roda na rede de casa, sem endereço público; por isso o envio é feito a partir dele
  (não por link) e o acompanhamento é por consulta, não por aviso da TikTok.
- O produto do TikTok Shop (afiliado) é definido pelo dono no app ao finalizar o rascunho; a API não
  oferece esse campo.
- YouTube e Instagram ficam para specs próprias, usando o mesmo desenho.
