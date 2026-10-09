# Feature Specification: Guia de comunicação por perfil e conta (017-guia-de-comunicacao)

**Feature Branch**: `017-guia-de-comunicacao`

**Created**: 2026-09-30

**Status**: Draft

**Input**: User description: "Gestão de prompts do assistente de IA por conta: poder melhorar a nível de conta,
por exemplo dizer o tom na hora de criar título, descrição ou hashtags. Não precisa ser todos os prompts;
talvez um system prompt para todos os prompts do assistente, como uma definição de comunicação: regras,
jargões, palavras usadas."

## Clarifications

### Session 2026-09-30

- Q: Em que nível o guia existe? → A: **Perfil e conta.** O do perfil vale para todas as contas dele; o da
  conta complementa para aquela rede. Em conflito, o mais específico (conta) vence.
- Q: Quem edita? → A: **Só o dono**; o membro vê.
- Q: O guia tem exemplos? → A: **Sim**, até 5 exemplos aprovados por guia.
- Q: O guia entra nos campos visuais (descrição para prompts do avatar, prompt do ambiente do cenário,
  regras de imagem do avatar)? → A: **"Sim, mas não deixa de ser relacionado."** A **voz** do guia (tom,
  faça/não faça, vocabulário, emojis, exemplos, hashtags fixas) **não** entra nesses 3 campos, mas eles
  continuam ligados ao guia: recebem as **palavras proibidas** efetivas do perfil (nunca aparecem num prompt
  de imagem; mesma detecção e mesmo bloqueio do Aplicar dos outros campos), e a tela desses campos mostra o
  link **"Ver guia de comunicação do perfil"**.
- Q: Proposta com palavra proibida pode ser aplicada depois de editada? → A: **Sim (opção A).** O bloqueio
  vale só para aplicar **sem editar**: o servidor recusa apenas o campo salvo **igual à proposta** que contém
  a palavra; editado por um humano, a decisão é dele.
- Q: Quantas hashtags fixas no máximo? → A: **Padrão de 5, configurável por conta** (ex.: YouTube 3, Instagram
  mais), sempre dentro do limite de hashtags da postagem (8 hoje, em todas as redes). O guia da conta ganha o
  campo **"máximo de hashtags fixas"** (vazio = 5). Regra de soma: as fixas do perfil (até 5) e as da conta,
  sem repetir, não passam do máximo da conta; o perfil não tem máximo próprio além do padrão.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Escrever o guia do perfil e da conta (Priority: P1)

Na aba do perfil (e em cada conta), o dono abre **Guia de comunicação** e preenche:
- **Tom de voz** (texto curto);
- **Regras**: "faça" e "não faça" (listas);
- **Vocabulário da casa**: jargões e palavras preferidas;
- **Palavras proibidas**;
- **Emojis**: não usar / usar com moderação / livre, com os preferidos;
- **Hashtags fixas** (que devem sempre aparecer nas hashtags geradas); no guia da conta, também o **máximo
  de hashtags fixas** daquela conta (padrão 5; até o limite de hashtags da postagem);
- **Exemplos aprovados**: até 5 textos (título, legenda ou bordão) que são "a cara" da conta.

O membro vê o guia, mas não edita. Toda mudança fica no histórico, com reversão pelo dono.

**Why this priority**: é o pedido central: dizer à IA como aquela conta fala.

**Independent Test**: no perfil A Taverna Nerd, escrever tom "narrador de RPG, íntimo e bem-humorado",
vocabulário "taverneiro, aventureiro, rolar dados", proibida "clickbait"; na conta TikTok @atavernanerd,
acrescentar "no TikTok, frase curta com gancho na 1ª linha" e 2 exemplos; salvar e ver as versões no
histórico.

**Acceptance Scenarios**:

1. **Given** um perfil sem guia, **When** o dono preenche e salva, **Then** o guia do perfil passa a valer para
   todas as contas do perfil.
2. **Given** uma conta, **When** o dono cria o guia da conta, **Then** ele complementa o do perfil (a tela
   mostra o que vem do perfil e o que é da conta).
3. **Given** um membro, **When** ele abre o guia, **Then** vê tudo, sem poder editar.
4. **Given** mais de 5 exemplos ou textos acima dos limites, **When** o dono salva, **Then** é recusado
   campo a campo com a razão.
5. **Given** uma alteração, **When** o dono reverte para uma versão anterior, **Then** o guia volta e a
   reversão fica no histórico.
6. **Given** uma conta YouTube com máximo de 3 hashtags fixas e o perfil com 2, **When** o dono põe 2 fixas na
   conta, **Then** é recusado ("perfil e conta somam 4 hashtags fixas; o máximo desta conta é 3").

---

### User Story 2 - O guia entra em todo pedido do assistente (Priority: P1)

Em qualquer "Melhorar com IA" (título, legenda, hashtags, bio, bordões, séries, descrição de asset…) de
uma conta ou perfil (exceto os 3 campos visuais, que recebem só as palavras proibidas), o pedido leva,
nesta ordem: as regras fixas (formato, limites, segurança), a regra
do tipo de campo, o **guia do perfil** e o **guia da conta** (quando o campo é de uma conta), e só então o
contexto e a instrução do usuário. As hashtags fixas sempre aparecem nas hashtags geradas; palavras
proibidas não aparecem; o texto gerado segue o tom e imita os exemplos.

**Why this priority**: sem isso, o guia é só documentação.

**Independent Test**: com o guia da Taverna preenchido, pedir "Sugerir textos" num corte do TikTok e ver a
legenda no tom definido, com uma palavra do vocabulário, sem as proibidas e com as hashtags fixas; a
explicação da IA cita o guia.

**Acceptance Scenarios**:

1. **Given** guias do perfil e da conta, **When** o assistente gera um texto daquela conta, **Then** os dois
   entram no pedido, e a conta prevalece em conflito.
2. **Given** um campo do perfil (ex.: bio), **When** o assistente gera, **Then** entra só o guia do perfil.
3. **Given** hashtags fixas, **When** o assistente gera hashtags, **Then** elas estão sempre incluídas (e
   contam no limite).
4. **Given** uma palavra proibida na resposta, **When** a proposta chega, **Then** ela é marcada com aviso e
   não pode ser aplicada sem editar; **editada** por um humano, pode ser aplicada (a decisão é dele).
5. **Given** a instrução do usuário pedindo para ignorar o guia, **When** gera, **Then** a instrução muda o
   conteúdo, mas não remove as regras fixas nem as palavras proibidas.
6. **Given** o registro de chamadas (008), **When** o dono abre uma chamada, **Then** vê quais versões dos
   guias foram usadas.
7. **Given** um campo visual (descrição para prompts do avatar, prompt do ambiente do cenário, regras de
   imagem), **When** o assistente gera, **Then** o pedido leva só as palavras proibidas do guia do perfil
   (sem tom, vocabulário, emojis nem exemplos), a proibida na resposta é marcada como nos outros campos, e a
   tela do campo tem o link "Ver guia de comunicação do perfil".

---

### User Story 3 - Montar e testar o guia com ajuda da IA (Priority: P2)

- **Montar**: o dono descreve a conta em poucas palavras ("perfil de achadinhos de cozinha, fala como
  amiga") e a IA propõe um guia inicial (tom, regras, vocabulário, emojis), que ele revisa e salva.
- **Testar**: botão "Testar guia" gera 3 títulos/legendas de exemplo para um conteúdo escolhido, com o guia
  ainda não salvo, para comparar antes de salvar.

**Why this priority**: acelera a criação e evita salvar um guia ruim; o guia manual já resolve o essencial.

**Independent Test**: na Queridinhos, pedir o guia inicial, ajustar o tom, clicar "Testar guia" com um
corte e comparar as 3 legendas; salvar.

**Acceptance Scenarios**:

1. **Given** uma descrição curta, **When** o dono pede o guia inicial, **Then** recebe uma proposta
   preenchendo os campos, que só vira guia ao salvar.
2. **Given** um guia em edição, **When** o dono clica "Testar guia", **Then** vê 3 exemplos gerados com o guia
   do formulário (não o salvo), sem alterar nenhum conteúdo.

---

### Edge Cases

- Perfil sem guia e conta com guia: vale só o da conta (mais as regras fixas).
- Guia muito longo: limite de tamanho por campo e total, para não estourar o pedido; a tela mostra o
  contador.
- Conta arquivada: o guia fica guardado, sem uso.
- Conflito entre perfil e conta (ex.: emojis "não" no perfil e "livre" na conta): vale a conta; a tela
  avisa o conflito.
- Hashtags fixas acima do máximo da conta (perfil + conta, sem repetir; padrão 5) ou máximo da conta acima
  do limite de hashtags da postagem: recusado ao salvar. Salvar o perfil com mais fixas do que o máximo de
  alguma conta ativa também é recusado, citando a conta.
- Estado inválido herdado (ex.: conta restaurada depois de o perfil mudar): na geração, ficam as primeiras
  fixas até o máximo da conta, com aviso, e a página da conta mostra o conflito.
- Exemplo com palavra proibida: recusado ao salvar.
- Guia editado enquanto um painel do assistente está aberto: a próxima geração usa a versão nova.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Cada perfil e cada conta DEVEM poder ter um guia de comunicação com: tom de voz, regras
  "faça" e "não faça", vocabulário da casa, palavras proibidas, uso de emojis (e preferidos), hashtags fixas
  e até 5 exemplos aprovados, com limites de tamanho por campo. O guia da conta DEVE ter também o máximo de
  hashtags fixas da conta (padrão 5, até o limite de hashtags da postagem), e as fixas do perfil somadas às
  da conta, sem repetir, NÃO DEVEM passar desse máximo.
- **FR-002**: Só o dono DEVE editar e reverter os guias; o membro DEVE ver. Toda mudança DEVE ficar no
  histórico (princípio VII).
- **FR-003**: Todo pedido do assistente de IA (spec 008) DEVE incluir, depois das regras fixas e da regra do
  tipo de campo, o guia do perfil e, quando o campo pertence a uma conta, o guia da conta, com a conta
  prevalecendo em conflito. **Exceção:** os 3 campos visuais (descrição para prompts do avatar, prompt do
  ambiente do cenário, regras de imagem do avatar) DEVEM receber só as palavras proibidas do guia, e a tela
  deles DEVE ter o link "Ver guia de comunicação do perfil".
- **FR-004**: As hashtags fixas DEVEM estar sempre nas hashtags geradas; palavras proibidas na proposta
  DEVEM ser apontadas e impedir o Aplicar até o usuário editar. O servidor DEVE recusar só o campo salvo
  igual à proposta que contém a palavra; o texto editado por um humano pode ser aplicado.
- **FR-005**: A instrução do usuário e o guia NÃO DEVEM anular as regras fixas (formato, limites, segurança)
  nem as palavras proibidas.
- **FR-006**: O registro de chamadas do assistente DEVE guardar as versões dos guias usadas em cada
  chamada.
- **FR-007**: O dono DEVE poder pedir à IA um guia inicial a partir de uma descrição curta (proposta que só
  vale ao salvar) e testar o guia do formulário gerando 3 exemplos, sem alterar conteúdos.
- **FR-008**: O guia só orienta textos; nada é publicado nem enviado às redes (princípio I).

### Key Entities

- **Guia de comunicação**: dono (perfil ou conta), tom, regras faça/não faça, vocabulário, proibidas, emojis,
  hashtags fixas, máximo de hashtags fixas (só na conta), exemplos (até 5), versão e histórico.
- **Chamada do assistente** (008): passa a registrar as versões dos guias do perfil e da conta usadas.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Escrever um guia de perfil com a ajuda da IA leva menos de 5 minutos.
- **SC-002**: Em 10 gerações de legenda de uma conta com guia, 100% trazem as hashtags fixas e 0 trazem
  palavras proibidas **aplicáveis sem edição** (a proposta que ainda traz uma proibida depois da segunda
  tentativa chega marcada e com o Aplicar bloqueado).
- **SC-003**: O dono consegue ver, em qualquer chamada do assistente, quais versões de guia foram usadas.
- **SC-004**: 100% das mudanças de guia aparecem no histórico com autor e data, e podem ser revertidas.

## Assumptions

- Complementa a spec 008 (assistente de IA): as regras por tipo de campo continuam globais e editáveis pelo
  dono; o guia é a camada "de voz" por perfil e conta.
- O contexto do perfil que a 008 já envia (nicho, bordões, paleta, persona) continua; o guia se soma a ele.
- Os exemplos são escritos ou colados pelo dono; sugerir exemplos a partir dos posts que mais
  performaram (métricas da spec 016) fica para depois.
- Custo por chamada sobe um pouco com o texto do guia; o registro de custo da 008 mostra o efeito.
