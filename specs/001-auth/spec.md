# Feature Specification: Autenticação e papéis (001-auth)

**Feature Branch**: `001-auth`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "001-auth: portar a autenticação do volans para o FastAPI (JWT só em memória + refresh em cookie httpOnly, Argon2id). A UI de auth já existe no SPA (apps/web, copiada do volans) e a API TypeScript original está em reference/volans-api (só referência). Pontos em aberto: login só com os usuários da casa? verificação por e-mail? Deve suportar o papel de dono (constitution, princípio II) e identificar o autor de cada mutação (princípio VII)."

## Clarifications

### Session 2026-09-28

- Q: O que um usuário com papel `membro` pode fazer? → A: Tudo, exceto as ações marcadas como reservadas ao dono (cada spec marca as suas).
- Q: O dono vê os eventos de segurança numa tela? → A: Sim, já nesta spec: uma lista simples, só para o dono, filtrável por usuário, tipo e data.
- Q: O que o dono pode fazer quando um membro perde o acesso ou muda de e-mail? → A: Definir nova senha provisória (troca obrigatória no próximo login, sessões encerradas) e alterar o e-mail (exige nova verificação antes do próximo login).
- Q: O usuário vê os dispositivos logados e encerra sessões em outros aparelhos? → A: Não; só sai do dispositivo atual. Para derrubar todas as sessões, troca a senha (FR-015).
- Q (decisão técnica do dono, após a sessão de perguntas): onde ficam as sessões do backend? → A: No Redis (famílias de renovação e contadores de limite de tentativas), como no volans; constitution emendada para 1.1.0.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Entrar e sair do SociMan (Priority: P1)

O dono abre o SociMan, informa e-mail e senha e passa a ver as telas protegidas. A sessão continua
válida enquanto ele usa o app (inclusive ao recarregar a página ou reabrir o navegador dentro do
prazo), e ele pode sair a qualquer momento, encerrando a sessão daquele dispositivo.

**Why this priority**: sem login não existe nenhuma outra feature: todas as specs seguintes
(contas, kit de marca, MCP) dependem de saber quem está usando o sistema.

**Independent Test**: com um usuário já cadastrado, fazer login, recarregar a página, acessar uma
tela protegida, sair e confirmar que a tela protegida volta a exigir login.

**Acceptance Scenarios**:

1. **Given** um usuário ativo, **When** ele informa e-mail e senha corretos, **Then** entra no app
   e vê a tela inicial protegida.
2. **Given** um usuário logado, **When** ele recarrega a página ou reabre o navegador dentro do
   prazo da sessão, **Then** continua logado sem digitar a senha de novo.
3. **Given** um usuário logado, **When** ele clica em "Sair", **Then** a sessão daquele
   dispositivo é encerrada e as telas protegidas voltam a exigir login.
4. **Given** qualquer visitante, **When** ele informa e-mail inexistente ou senha errada,
   **Then** vê a mesma mensagem genérica ("e-mail ou senha inválidos"), sem revelar qual dos dois
   errou.
5. **Given** um visitante não logado, **When** ele tenta abrir uma tela protegida, **Then** é
   levado ao login e, depois de entrar, volta para a tela que pediu.

---

### User Story 2 - Papel de dono e usuários da casa (Priority: P1)

O sistema distingue o **dono** dos demais usuários. Só o dono pode executar ações reservadas
(como mudar o status de direito de um canal-fonte, na spec 008) e gerenciar quem tem acesso.
O primeiro dono é criado na instalação, sem depender de uma tela pública.

**Why this priority**: os princípios II (só o dono muda o status de direito) e VII (autor de toda
mutação) da constitution dependem de identidade e papel desde a primeira spec.

**Independent Test**: criar o dono pela rotina de instalação, criar um usuário comum e verificar
que uma ação marcada como "só dono" é aceita para o dono e recusada para o usuário comum.

**Acceptance Scenarios**:

1. **Given** uma instalação sem usuários, **When** o operador roda a rotina de criação do primeiro
   dono, **Then** existe exatamente um usuário com papel de dono e ele consegue entrar.
2. **Given** um usuário com papel comum, **When** ele tenta uma ação reservada ao dono, **Then** a
   ação é recusada com "sem permissão" e nada é alterado.
3. **Given** o dono logado, **When** ele cadastra um novo usuário da casa, **Then** o usuário
   recebe um e-mail de verificação; depois de verificar, entra com a senha provisória, é obrigado
   a trocá-la e passa a usar o app com o papel atribuído.
6. **Given** um usuário cadastrado que ainda não verificou o e-mail, **When** ele tenta entrar,
   **Then** o login é recusado com a orientação de verificar o e-mail e a opção de reenviar o link.
4. **Given** um usuário logado, **When** ele consulta "quem sou eu", **Then** vê nome, e-mail e
   papel.
5. **Given** o dono, **When** ele desativa um usuário, **Then** as sessões desse usuário deixam de
   valer e ele não consegue mais entrar. O sistema não permite desativar o último dono ativo.

---

### User Story 3 - Autor registrado em toda mutação (Priority: P1)

Toda alteração feita por um usuário autenticado fica associada a ele (quem e quando), para que as
specs seguintes possam montar histórico e reversão (princípio VII).

**Why this priority**: se a identidade do autor não estiver disponível desde o início, as tabelas
das próximas specs nascem sem rastreabilidade.

**Independent Test**: com dois usuários, cada um faz uma alteração de teste; o registro de cada
alteração mostra o autor e a data corretos.

**Acceptance Scenarios**:

1. **Given** um usuário logado, **When** ele faz qualquer alteração, **Then** o registro guarda o
   identificador do usuário e a data da alteração.
2. **Given** uma requisição de alteração sem sessão válida, **When** ela chega ao sistema,
   **Then** é recusada e nada é gravado.
3. **Given** os eventos de segurança (login ok, login falho, logout, troca de senha, criação ou
   desativação de usuário), **When** eles acontecem, **Then** ficam registrados com usuário (se
   houver), data e origem.
4. **Given** o dono logado, **When** ele abre a tela de eventos de segurança e filtra por usuário,
   tipo ou datas, **Then** vê só os eventos que atendem ao filtro, do mais recente para o mais
   antigo. Um `membro` que tenta abrir essa tela recebe "sem permissão".

---

### User Story 4 - Recuperar o acesso (Priority: P2)

Um usuário que esqueceu a senha consegue definir uma nova e voltar a entrar, sem ajuda de
desenvolvedor.

**Why this priority**: importante para não travar o dono, mas o login funciona sem isso, e no
início o dono pode redefinir a senha pela rotina de instalação.

**Independent Test**: pedir a recuperação para um e-mail cadastrado, usar o link recebido, definir
nova senha e entrar com ela; a senha antiga deixa de funcionar.

**Acceptance Scenarios**:

1. **Given** um e-mail cadastrado, **When** o usuário pede recuperação, **Then** recebe um link de
   uso único que expira em 15 minutos, e a tela mostra a mesma resposta que mostraria para um
   e-mail não cadastrado.
2. **Given** um link válido, **When** o usuário define uma nova senha, **Then** a senha é trocada,
   todas as sessões antigas desse usuário são encerradas e o link não pode ser reutilizado.
3. **Given** um link expirado ou já usado, **When** o usuário o abre, **Then** vê uma mensagem
   clara e pode pedir um novo.

Canal de entrega do link: e-mail real. Em desenvolvimento e testes, os e-mails são capturados por
uma caixa de testes local e não saem para a internet; o provedor de produção fica para depois.

---

### Edge Cases

- Muitas tentativas de login erradas seguidas para o mesmo e-mail ou do mesmo IP: o sistema passa a
  recusar por um tempo e informa quando tentar de novo.
- Uso de um token de renovação de sessão que já foi trocado (sinal de roubo): todas as sessões
  daquela família são encerradas e o usuário precisa entrar de novo.
- A sessão tem prazo máximo absoluto (7 dias); usar o app não estende esse prazo além do limite.
- Duas abas abertas renovando a sessão ao mesmo tempo não derrubam o usuário.
- E-mail com maiúsculas ou espaços é tratado como o mesmo e-mail.
- Tentativa de desativar ou rebaixar o último dono ativo é recusada.
- Link de verificação expirado ou já usado: mensagem clara e opção de pedir outro.
- O dono tenta cadastrar um e-mail que já existe (ativo ou desativado): o cadastro é recusado com
  aviso (aqui a revelação é aceitável, porque só o dono acessa essa tela).
- O dono troca o e-mail de um usuário para um endereço que já pertence a outro: a troca é recusada
  com aviso.
- Falha no envio do e-mail: o usuário é criado mesmo assim, e o dono vê o aviso e pode reenviar.
- Usuário desativado com sessão aberta perde o acesso na próxima requisição (no máximo em 15
  minutos, que é a validade do acesso curto).

## Requirements *(mandatory)*

### Functional Requirements

**Sessão**
- **FR-001**: O sistema DEVE autenticar usuários por e-mail e senha.
- **FR-002**: O sistema DEVE manter o usuário logado entre recarregamentos da página por até 7 dias
  (prazo absoluto), sem guardar credenciais em armazenamento acessível a scripts da página.
- **FR-003**: A credencial de acesso de curta duração DEVE expirar em até 15 minutos e ser renovada
  de forma transparente enquanto a sessão estiver válida.
- **FR-004**: Cada renovação DEVE invalidar o token de renovação anterior; o reuso de um token já
  trocado DEVE encerrar toda a família de sessões daquele login.
- **FR-005**: O logout DEVE encerrar a sessão do dispositivo atual de forma que ela não possa ser
  renovada. Não há lista de dispositivos nem "sair de todos" nesta spec; encerrar todas as sessões
  é efeito da troca de senha (FR-015) ou de ação do dono (FR-013a, FR-014).
- **FR-006**: Mensagens de erro de login, recuperação e reenvio de verificação NÃO DEVEM revelar se um e-mail
  existe no sistema.

**Senhas e abuso**
- **FR-007**: Senhas DEVEM ser guardadas apenas como hash com algoritmo resistente a força bruta
  (padrão atual recomendado pela OWASP) e nunca aparecer em log.
- **FR-008**: Senhas DEVEM ter no mínimo 12 caracteres e ser recusadas se estiverem numa lista de
  senhas comuns.
- **FR-009**: O sistema DEVE limitar tentativas por IP e por conta: login (30 por IP e 10 por conta
  a cada 15 min), recuperação (10 por IP e 5 por conta por hora), redefinição e verificação (limites
  por IP por hora), respondendo com o tempo de espera.

**Usuários e papéis**
- **FR-010**: O sistema DEVE ter os papéis `dono` e `membro`. O `membro` pode ler e alterar os dados
  de negócio; só as ações marcadas como reservadas ao dono (nesta spec: gestão de usuários; nas
  próximas, o que cada spec marcar, como o status de direito na 008) DEVEM ser recusadas para ele
  no servidor, não só escondidas na interface.
- **FR-011**: DEVE existir uma rotina de instalação (fora da interface web) para criar o primeiro dono
  e para redefinir a senha de qualquer usuário em emergência.
- **FR-012**: Só o dono cria usuários, informando nome, e-mail, papel e uma senha provisória. NÃO
  DEVE existir cadastro público (a tela "Criar conta" herdada sai).
- **FR-012a**: No primeiro login, o usuário DEVE trocar a senha provisória antes de usar o app, para
  que só ele conheça a própria senha (autoria confiável, princípio VII).
- **FR-013**: O dono DEVE poder listar usuários, criar (conforme FR-012), mudar papel e desativar.
  O sistema NÃO DEVE permitir ficar sem nenhum dono ativo.
- **FR-013a**: O dono DEVE poder definir uma nova senha provisória para outro usuário; isso encerra
  todas as sessões desse usuário e obriga a troca no próximo login (FR-012a).
- **FR-013b**: O dono DEVE poder alterar o nome e o e-mail de outro usuário. A troca de e-mail marca
  o e-mail como não verificado, envia um novo link de verificação para o novo endereço e encerra as
  sessões do usuário; ele só volta a entrar depois de verificar (FR-020).
- **FR-014**: Usuário desativado NÃO DEVE conseguir entrar nem renovar sessão, e suas sessões
  abertas DEVEM ser encerradas.
- **FR-015**: Um usuário logado DEVE poder consultar seus próprios dados (nome, e-mail, papel) e
  trocar a própria senha informando a atual; a troca encerra as outras sessões dele.

**Rastreabilidade (princípio VII)**
- **FR-016**: Toda requisição de alteração DEVE exigir sessão válida, e a identidade do autor DEVE
  ficar disponível para que qualquer registro gravado guarde autor e data.
- **FR-017**: O sistema DEVE registrar eventos de segurança (login ok e falho, logout, renovação
  recusada por reuso, recuperação pedida, senha trocada, usuário criado, papel alterado, usuário
  desativado, senha redefinida pelo dono, e-mail alterado, e-mail verificado) com autor (se houver), data, IP e resultado.
- **FR-017a**: O dono DEVE ter uma tela com a lista de eventos de segurança, do mais recente para o
  mais antigo, filtrável por usuário, tipo de evento e intervalo de datas. A tela é reservada ao
  dono, e os eventos não podem ser editados nem apagados por ela.
- **FR-018**: Usuários NÃO DEVEM ser apagados de fato; a desativação preserva o vínculo com tudo o
  que ele alterou.

**Recuperação e verificação de e-mail**
- **FR-019**: O usuário DEVE poder recuperar o acesso por link de uso único que expira em 15 minutos
  (entrega conforme a clarificação da User Story 4).
- **FR-020**: Ao criar um usuário, o sistema DEVE enviar um link de verificação de e-mail, de uso
  único e válido por 24 horas. O usuário NÃO DEVE conseguir entrar antes de verificar o e-mail.
- **FR-021**: Um usuário ainda não verificado DEVE poder pedir um novo link na tela de login (com a
  mesma resposta genérica de FR-006), e o dono DEVE poder reenviá-lo pela gestão de usuários.
- **FR-022**: Todos os e-mails do sistema (verificação e recuperação) DEVEM ser enviados por um
  canal de e-mail configurável; em desenvolvimento e testes, esse canal DEVE entregar numa caixa
  local de testes, sem envio para fora.

### Key Entities *(include if feature involves data)*

- **Usuário**: pessoa da casa com acesso ao SociMan. Nome, e-mail único (normalizado), hash da senha,
  papel (`dono` ou `membro`), situação (ativo ou desativado), e-mail verificado (sim/não), datas de
  criação e alteração. Nunca é apagado.
- **Sessão (família de renovação)**: um login em um dispositivo. Pertence a um usuário, tem prazo
  absoluto e o token de renovação atual; pode ser encerrada individualmente ou em bloco.
- **Token de uso único**: recuperação de senha ou verificação de e-mail.
  Pertence a um usuário, tem finalidade, validade e data de uso. Só o hash é guardado.
- **Evento de segurança**: registro imutável de uma ação de autenticação ou de gestão de usuários,
  com autor, data, IP, tipo e resultado.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O dono entra no SociMan em menos de 15 segundos a partir da tela de login.
- **SC-002**: Um usuário ativo permanece logado por 7 dias de uso sem precisar digitar a senha, e
  nunca depois do prazo absoluto.
- **SC-003**: 100% das ações reservadas ao dono são recusadas para usuários `membro` nos testes
  automatizados.
- **SC-004**: 100% das alterações gravadas nos testes têm autor e data preenchidos.
- **SC-005**: Um usuário que esqueceu a senha volta a entrar em menos de 3 minutos, sem ajuda.
- **SC-006**: Nenhum teste consegue descobrir se um e-mail está cadastrado pelas respostas públicas
  de login, recuperação ou reenvio de verificação.
- **SC-007**: Depois de 10 senhas erradas para uma conta em 15 minutos, novas tentativas são
  recusadas até o fim da janela.
- **SC-008**: Um usuário recém-criado pelo dono recebe o e-mail de verificação em menos de 1 minuto
  e começa a usar o app em menos de 5 minutos.
- **SC-009**: O dono encontra um evento de segurança específico (por usuário e data) em menos de
  30 segundos.

## Assumptions

- Público: o dono e poucas pessoas da casa (menos de 10 usuários). Não há multi-tenant nem
  organizações nesta spec.
- A interface de login, recuperação e redefinição já existe no SPA (herdada do volans) e será
  reaproveitada, com ajustes de texto em pt-BR; o comportamento de referência é o do volans.
- Restrição técnica do dono: o estado das sessões (famílias de renovação) e os contadores de limite
  de tentativas ficam num armazenamento em memória compartilhado (Redis), não no banco principal.
  Se ele for reiniciado sem persistência, a consequência aceita é os usuários entrarem de novo;
  usuários, tokens de uso único e eventos de segurança ficam no banco principal.
- Em desenvolvimento e testes, os e-mails são capturados pelo Mailpit (caixa local); o provedor de
  produção (SMTP/Resend) será escolhido quando o SociMan sair do ambiente de casa.
- O primeiro dono, criado pela rotina de instalação, já nasce com e-mail verificado e sem exigência
  de troca de senha (quem roda a rotina tem acesso à máquina).
- Prazos herdados do volans: acesso curto de 15 min, sessão de 7 dias absoluta, link de recuperação de
  15 min, link de verificação de 24 h.
- Login social (Google etc.), autenticação em dois fatores e "lembrar dispositivo" ficam fora desta
  spec.
- Autenticação de clientes MCP (tokens para IA) fica para a spec `009-mcp`; esta spec só garante que
  o autor de uma mutação pode ser um usuário humano e deixa espaço para um cliente MCP identificado.
- O registro de consentimento de cookies do volans fica fora: o SociMan não usa cookies de
  rastreamento, só o cookie essencial da sessão.
- O histórico completo e a reversão de dados de negócio (princípio VII) são implementados em cada
  spec de domínio; esta spec entrega a identidade do autor e o log de eventos de segurança.
