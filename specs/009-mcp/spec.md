# Feature Specification: Servidor MCP para os agentes (009-mcp)

**Feature Branch**: `009-mcp`

**Created**: 2026-10-02

**Status**: Draft

**Input**: Descrição do dono: "Servidor MCP sobre a API do SociMan para os agentes da agência (OpenClaw)
usarem na rede de casa. Cada agente ou cliente tem credencial própria, emitida e revogada só pelo dono
humano, com escopo de leitura ou de escrita-proposta; toda chamada fica registrada com o cliente como
autor. Tools de leitura sobre o domínio existente (perfis, contas, kit, assets, canais e vídeos-fonte,
envios e cortes, conteúdos e destinos, guia de comunicação, métricas e analytics). Escritas poucas e
reversíveis, com histórico, versão e reversão pelo dono; nunca conectar conta, aprovar, agendar,
publicar, mudar o direito do canal nem mexer em credenciais. Tools geradas do OpenAPI por um mapa
explícito, sem duplicar regra de negócio. Limite de uso por cliente, auditoria visível ao dono e
interruptor geral."

## Clarifications

### Session 2026-10-02

- Q: Como o dono emite e o cliente apresenta a credencial? → A: token estático por cliente (Bearer),
  gerado na interface, guardado como hash, com rotação e revogação imediatas.
- Q: Qual é o primeiro corte de escrita? → A: anotações e propostas + selecionar vídeo-fonte (sem enviar)
  + editar textos de destino ainda não aprovado; o resto fica para depois.
- Q: Onde o servidor MCP roda? → A: Streamable HTTP dentro da própria API, atrás do edge, sem serviço novo.

## Contexto

A agência roda 11 agentes no OpenClaw: 8 de cortes (`gestor`, `pesquisador`, `estrategista`,
`planejador`, `cacador`, `produtor`, `revisor` e `analista`) e 3 do TikTok Shop (`shop-analista`,
`shop-roteirista` e `shop-diretor`). Hoje eles trabalham com arquivos Markdown em `shared/` e com
scripts próprios. Enquanto isso, o SociMan virou a fonte da verdade de perfis, contas, kit de marca,
canais-fonte, cortes, conteúdos, destinos e métricas. Falta uma porta para os agentes lerem esse
estado e deixarem trabalho para o dono revisar, sem ganhar nenhum poder que a constitution reserva
aos humanos.

Princípios da constitution 4.1.0 que esta spec tem de cumprir:

- **I (publicação só com decisão humana):** nenhum cliente MCP conecta conta, aprova, agenda, reagenda
  ou publica. A API já recusa esses atos para quem não é dono humano (`somente_humano`, spec 015).
- **II (direito é do dono):** nenhum cliente MCP muda o status de direito de um canal-fonte.
- **IV (contrato é a fonte única):** as tools saem do OpenAPI, e a verificação acusa divergência.
- **V (segurança):** a API continua só atrás do edge, e nenhum segredo vaza.
- **VII (humano no controle):** o que um cliente MCP grava leva o cliente como autor, fica no
  histórico e pode ser revertido pelo dono. Os limites do que o MCP escreve são definidos aqui.

O que já existe e esta spec usa:

- o `Actor` da API, com o tipo `mcp_client` reservado (spec 001), e a dependência que recusa atos
  humanos com 403 `somente_humano` e grava o evento `publicacao_recusada` (spec 015);
- o histórico genérico (`history.py`), com autor, antes e depois, controle de versão (409
  `version_conflict`) e reversão pelo dono;
- o OpenAPI gerado pelo FastAPI, com `operationId` estável em todas as rotas (cerca de 190 operações).

A pesquisa sobre o protocolo MCP e sobre o cliente MCP do OpenClaw está em `notas-pesquisa.md`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - O dono cria e controla as credenciais dos agentes (Priority: P1)

O dono abre "Configurações → Agentes (MCP)", cria um cliente para cada agente (ex.: "Caçador"),
escolhe o escopo ("só leitura" ou "leitura e propostas") e recebe a credencial **uma única vez**, para
colar na configuração do agente. Na mesma tela, ele vê a lista de clientes, com escopo, situação,
último uso e contagem de chamadas, e pode suspender, reativar, trocar a credencial (rotacionar) ou
revogar cada cliente. Um interruptor geral desliga o acesso de todos os clientes de uma vez.

**Why this priority**: Sem credencial individual e controle do dono, nenhuma outra história pode
existir com segurança. Esta é a base da autoria rastreável (princípio VII).

**Independent Test**: Criar dois clientes com escopos diferentes, conferir que a credencial aparece
uma vez só, que cada um se autentica com a sua credencial, que revogar um corta só esse cliente e que
o interruptor geral corta os dois.

**Acceptance Scenarios**:

1. **Given** o dono na tela de clientes MCP, **When** cria o cliente "Caçador" com escopo "só leitura",
   **Then** a credencial aparece uma vez, com o aviso "guarde agora, ela não será mostrada de novo", e o
   cliente fica na lista como "ativo", sem uso.
2. **Given** um cliente ativo, **When** o dono o revoga, **Then** a próxima chamada desse cliente recebe
   "não autenticado", o cliente continua na lista como "revogado" (com quem revogou e quando) e o
   histórico dele continua consultável.
3. **Given** um cliente ativo, **When** o dono rotaciona a credencial, **Then** a credencial antiga para
   de valer na hora, a nova aparece uma vez e o cliente mantém o mesmo nome, histórico e registro de
   chamadas.
4. **Given** o interruptor geral desligado, **When** qualquer cliente chama qualquer tool, **Then** a
   chamada é recusada com a mensagem "acesso MCP desligado pelo dono", e o registro mostra a recusa.
5. **Given** um membro (não dono) ou um cliente MCP, **When** tenta criar, alterar, rotacionar ou
   revogar um cliente MCP ou mexer no interruptor, **Then** recebe "só um dono, pela interface, pode
   fazer isto".

---

### User Story 2 - Um agente lê o estado da agência (Priority: P1)

Um agente com credencial válida lista as tools disponíveis e consulta o domínio: perfis e contas, kit
de marca, guia de comunicação, assets, canais-fonte e vídeos-fonte, envios e cortes, conteúdos e
destinos (com o estado efetivo), métricas dos vídeos e as análises do analytics (spec 019). Ele vê os
mesmos dados que um membro veria na interface, sem os dados exclusivos de dono e sem nenhum segredo.

**Why this priority**: É o ganho imediato. Os agentes deixam de trabalhar com cópias em Markdown e
passam a decidir com o estado real (ex.: o caçador vê quais vídeos-fonte já têm envio, e o analista
lê as métricas).

**Independent Test**: Com dados semeados, chamar cada tool de leitura com uma credencial "só leitura"
e conferir que o resultado bate com a rota correspondente da API para um membro, que nada foi alterado
e que cada chamada ficou registrada.

**Acceptance Scenarios**:

1. **Given** um cliente "só leitura", **When** ele pede a lista de tools, **Then** recebe só as tools de
   leitura, sempre na mesma ordem e cada uma com descrição em pt-BR.
2. **Given** um perfil com contas, kit e guia, **When** o agente consulta o perfil, o kit e o guia,
   **Then** os dados batem com o que a interface mostra para um membro.
3. **Given** a lista de conteúdos, **When** o agente filtra por estado (ex.: `a_postar`, `atrasado`),
   **Then** recebe o estado efetivo calculado pela API, igual ao da tela Conteúdos.
4. **Given** uma consulta com muitos resultados, **When** o agente lista sem filtro, **Then** a resposta
   vem paginada, com o total e o jeito de pedir a próxima página, sem passar do tamanho máximo de resposta.
5. **Given** dados exclusivos de dono (custo de IA, exportação do dataset, usuários, eventos de
   segurança, configuração de publicação), **When** o agente tenta lê-los, **Then** eles não existem
   como tool e, na análise do funil, o custo de IA vem omitido, como para um membro.
6. **Given** um cliente que pede um vídeo ou imagem, **When** a tool responde, **Then** devolve um link
   assinado e com validade (como na interface), nunca o arquivo dentro da resposta.

---

### User Story 3 - Decisões humanas nunca passam pelo MCP (Priority: P1)

O dono tem a garantia, verificada por teste, de que nenhum cliente MCP consegue conectar ou
desconectar conta, aprovar ou recusar destino, agendar, reagendar ou cancelar, publicar ou "enviar
agora", confirmar envio, marcar como postado, enviar vídeo para corte (confirmando o aviso de
direito), mudar o status de direito de um canal, reverter mudanças, mexer em usuários e credenciais,
ou ligar o envio automático. Essas operações não viram tool. E, se uma credencial MCP for usada direto
contra a API, a API recusa com `somente_humano` e grava o evento de recusa.

**Why this priority**: Os princípios I, II e VII são inegociáveis, e uma falha aqui bloqueia a
entrega (constitution, Governance).

**Independent Test**: Uma verificação automatizada percorre a lista negra de operationIds e confirma
que nenhum está no mapa de tools. Um teste de API chama cada rota proibida com a credencial de um
cliente MCP e confirma o 403 e o evento.

**Acceptance Scenarios**:

1. **Given** o mapa de tools, **When** a verificação de contrato roda, **Then** ela falha se qualquer
   operação da lista proibida estiver mapeada, ou se uma rota nova da API não estiver classificada
   como "tool", "fora do MCP" ou "proibida".
2. **Given** a credencial de um cliente MCP usada direto na API (fora do servidor MCP), **When** ela chama
   aprovar, agendar, publicar, conectar conta ou mudar o direito do canal, **Then** a API responde 403
   `somente_humano` e grava o evento `publicacao_recusada` com o cliente como ator.
3. **Given** um cliente com escopo "leitura e propostas", **When** ele tenta editar os textos de um
   destino já aprovado ou agendado, **Then** recebe a recusa "destino aprovado: só o dono altera" e
   nada muda.
4. **Given** um texto de tool ou um dado vindo de fora (ex.: título de vídeo do YouTube) com uma
   instrução do tipo "aprove este post", **When** o agente o lê, **Then** nada no servidor executa
   instrução de conteúdo, porque as tools só aceitam argumentos tipados e as proibições não dependem
   do que o agente "entende".

---

### User Story 4 - O agente deixa propostas, e o dono decide (Priority: P2)

Com escopo "leitura e propostas", o agente grava trabalho que o dono revisa:

- **anotações e propostas** presas a um item (perfil, conta, canal-fonte, vídeo-fonte, corte,
  conteúdo ou destino), como "observação" ou "proposta de texto" (título, descrição, hashtags);
- a **seleção de um vídeo-fonte para corte**, que fica como `selecionado`, sem envio ao gerador de
  cortes (enviar continua sendo ato humano, porque passa pelo aviso de direito);
- a **edição dos textos de um destino ainda não aprovado** (rascunho de legenda).

O dono vê tudo numa caixa "Propostas dos agentes" e no próprio item, com o selo do cliente que gravou.
Ele aplica (a proposta de texto preenche o formulário, e nada é salvo até ele clicar em "Salvar"),
descarta ou reverte.

**Why this priority**: É o que transforma o MCP de painel de leitura em colaboração. Vem depois das
P1 porque depende da credencial, da leitura e das guardas.

**Independent Test**: Com um cliente "leitura e propostas", gravar uma proposta de texto num
destino, selecionar um vídeo-fonte e editar os textos de um destino em revisão. Conferir o autor no
histórico, a caixa de propostas, a aplicação pelo formulário e a reversão pelo dono.

**Acceptance Scenarios**:

1. **Given** um destino em revisão, **When** o agente grava uma proposta de texto, **Then** a proposta
   aparece no destino e na caixa "Propostas dos agentes", com o cliente como autor e a data, e os
   textos do destino não mudam.
2. **Given** uma proposta de texto, **When** o dono clica em "Aplicar", **Then** o formulário do destino
   é preenchido; ao salvar, o histórico do destino registra o dono como autor e a proposta de origem,
   e a proposta passa a "aplicada".
3. **Given** um vídeo-fonte sem envio, **When** o agente o seleciona para corte, **Then** surge um envio
   `selecionado` com o cliente como autor, nada é enviado ao gerador de cortes, e o dono vê o envio
   em "Gerar cortes", pronto para revisar e enviar (com o aviso de direito de sempre).
4. **Given** uma mudança feita por um cliente MCP numa entidade com histórico, **When** o dono abre o
   histórico, **Then** vê o selo "Agente: <nome do cliente>", o antes e depois, e pode reverter como
   faz com qualquer mudança.
5. **Given** o agente e o dono editando o mesmo destino, **When** o agente grava com uma versão
   antiga, **Then** recebe o conflito de versão com a mensagem em pt-BR e precisa reler antes de tentar
   de novo (a gravação do dono nunca é sobrescrita).
6. **Given** um cliente "só leitura", **When** tenta qualquer escrita, **Then** a tool nem aparece na
   lista e, se chamada pelo nome, é recusada com "escopo insuficiente".

---

### User Story 5 - O dono audita e limita o uso (Priority: P2)

O dono abre o registro de chamadas MCP e vê cada chamada: quando, qual cliente, qual tool, um resumo
dos argumentos (sem segredos), resultado (ok, recusada, erro, limite), duração e, nas escritas, o
link para o item alterado. Ele filtra por cliente, tool, resultado e período. Cada cliente tem limite
de chamadas por minuto e de escritas por dia. Ao passar do limite, a chamada é recusada com uma
mensagem que diz quando tentar de novo, e a tela de clientes mostra o cliente "no limite".

**Why this priority**: Fecha a rastreabilidade (VII) e protege contra um agente em loop. Pode vir
depois da leitura porque a autoria nas entidades já existe desde a US2/US4.

**Independent Test**: Gerar chamadas de dois clientes, incluindo recusas e uma rajada acima do
limite, e conferir o registro, os filtros, a recusa por limite e os contadores da tela.

**Acceptance Scenarios**:

1. **Given** chamadas de dois clientes, **When** o dono filtra o registro pelo "Caçador", **Then** vê só
   as chamadas dele, da mais nova para a mais antiga, com tool, resultado e duração.
2. **Given** um cliente com limite de 60 chamadas por minuto, **When** ele faz a 61ª chamada no mesmo
   minuto, **Then** a chamada é recusada com "limite de uso atingido, tente de novo em N s", e o
   registro mostra "limite".
3. **Given** um cliente que passou do limite diário de escritas, **When** ele tenta outra escrita,
   **Then** a escrita é recusada até a virada do dia (fuso de Brasília), e as leituras continuam.
4. **Given** uma chamada com argumento muito longo, **When** ela é registrada, **Then** o resumo é
   truncado e nenhum valor sensível (credencial, cabeçalho de autorização) aparece no registro.
5. **Given** um membro, **When** abre a área de agentes, **Then** não vê a área: clientes e registro
   são só de dono.

---

### User Story 6 - Os agentes do OpenClaw se conectam (Priority: P3)

O dono segue um guia e, para cada agente do OpenClaw, configura um servidor MCP com a credencial
daquele agente e libera só esse servidor para ele. Depois, confirma pelo próprio OpenClaw que o agente
lista as tools e consegue fazer uma leitura. O guia traz o mapa recomendado de agente para escopo.

**Why this priority**: É a entrega de valor no uso real, mas depende do servidor pronto e é
configuração do lado do OpenClaw (feita pelo dono, um passo por vez).

**Independent Test**: Seguir o guia para um agente (ex.: `cacador`), rodar a sonda do OpenClaw e uma
pergunta real ("quais vídeos-fonte do perfil X ainda não têm envio?"). Conferir no registro de
chamadas que o autor é o cliente "Caçador".

**Acceptance Scenarios**:

1. **Given** o guia e uma credencial nova, **When** o dono configura o servidor para o `cacador` e roda a
   sonda, **Then** a sonda lista as tools do escopo do cliente e nenhuma outra.
2. **Given** dois agentes configurados com credenciais diferentes, **When** cada um faz uma leitura,
   **Then** o registro mostra dois autores distintos.
3. **Given** a credencial colada na configuração do OpenClaw, **When** o dono roda o diagnóstico do
   OpenClaw, **Then** o guia mostra como guardar a credencial fora do arquivo de configuração (sem
   literal no config).

---

### Edge Cases

- **Credencial vazada:** o dono revoga ou rotaciona, e o efeito é imediato (próxima chamada). O
  registro mostra o que foi feito com ela até a revogação.
- **Cliente revogado com chamada em andamento:** a chamada que já passou da autenticação termina, e a
  próxima é recusada. Nenhuma escrita fica pela metade, porque cada escrita é uma transação.
- **Interruptor desligado no meio do trabalho de um agente:** todas as chamadas seguintes são
  recusadas com o motivo. Nada do que já foi gravado é desfeito sozinho.
- **Conflito de versão** (o dono editou enquanto o agente trabalhava): o agente recebe o conflito com
  a versão atual e relê, e a gravação do dono nunca é perdida.
- **Destino aprovado depois que o agente leu:** a edição do agente é recusada ("destino aprovado: só o
  dono altera"), e o agente pode gravar uma proposta de texto no lugar.
- **Proposta para um item arquivado:** a proposta é recusada se o item já estava arquivado. Se o item
  for arquivado depois, ela continua visível na caixa, marcada "item arquivado".
- **Vídeo-fonte que já tem envio:** selecionar de novo segue a regra da API (o mesmo 409 que a
  interface recebe), e o agente recebe a mensagem.
- **Rota nova na API sem classificação:** a verificação de contrato falha até alguém classificá-la. O
  padrão nunca é "vira tool".
- **Resposta grande** (ex.: série de métricas longa): paginação ou recorte com aviso "resultado
  truncado, use filtros", sem estourar o limite de resposta.
- **Texto vindo de fora** (títulos e descrições do YouTube, legendas da TikTok): volta como dado, nunca
  como instrução do servidor. As descrições das tools lembram que esse conteúdo vem de terceiros.
- **Requisição de outra origem** (navegador em página maliciosa tentando falar com o endpoint): é
  recusada pela validação de origem, mesmo com a credencial certa.
- **Agente em loop:** o limite de taxa o segura, o registro mostra a rajada, e o dono pode suspender o
  cliente.
- **Dois dispositivos do dono:** a credencial só aparece na criação. Se o dono perdeu a credencial,
  rotaciona (não existe "mostrar de novo").
- **Membro tentando ver credenciais:** a área de agentes não aparece para ele, e as rotas recusam.

## Requirements *(mandatory)*

### Functional Requirements

**Clientes e credenciais (US1)**

- **FR-001**: O sistema DEVE manter um cadastro de **clientes MCP**. Cada cliente tem nome único,
  descrição opcional (ex.: "agente cacador do OpenClaw"), escopo, situação (ativo, suspenso, revogado),
  limites de uso, autor e data de criação, último uso e contadores.
- **FR-002**: Só um **dono humano** (sessão de usuário, papel dono) DEVE poder criar, editar, suspender,
  reativar, rotacionar e revogar um cliente, e ligar ou desligar o interruptor geral. Qualquer outro ator
  recebe 403 `somente_humano`, e a recusa fica registrada.
- **FR-003**: Cada cliente DEVE ter **credencial própria**, mostrada uma única vez (na criação e a cada
  rotação). O sistema guarda só o necessário para verificá-la, nunca o valor recuperável, e nunca a
  mostra de novo, nem em log, registro ou histórico.
  **token estático por cliente**, gerado na interface pelo dono e mandado como `Bearer`, guardado só como
  hash, com rotação e revogação imediatas (Clarification 2026-10-02)
- **FR-004**: Revogar DEVE ser definitivo (um cliente revogado não volta, cria-se outro) e imediato. Nada
  é apagado: o cliente revogado continua na lista, com histórico e registro de chamadas.
- **FR-005**: A credencial PODE ter validade opcional, definida pelo dono. Vencida, ela vale como
  revogada para autenticação, e a tela avisa 7 dias antes do vencimento.
- **FR-006**: Cada cliente DEVE ter um de dois escopos: **"só leitura"** ou **"leitura e propostas"**.
  Mudar o escopo é ato do dono, entra no histórico do cliente e vale na próxima chamada.
- **FR-007**: Um **interruptor geral** de dois níveis DEVE desligar o acesso de todos os clientes: um
  na configuração do servidor (padrão: desligado) **e** outro na tela de agentes. Com qualquer um dos
  dois desligado, toda chamada é recusada com o motivo, e a tela mostra "MCP desligado".
- **FR-008**: Toda chamada autenticada DEVE agir como o ator `mcp_client`, identificado pelo cliente.
  Esse ator nunca herda papel de dono: o que é exclusivo de dono continua fora de alcance, e as
  permissões de leitura são as de um membro.

**Tools e contrato (US2, US3)**

- **FR-009**: As tools DEVEM ser geradas do OpenAPI da API por um **mapa explícito e versionado**
  (operationId → tool). Nome, parâmetros, schema de entrada e de saída e descrição vêm da operação. O
  mapa só acrescenta o que o OpenAPI não diz: escopo exigido, anotação de leitura ou escrita e, se
  preciso, uma descrição melhor para o agente.
- **FR-010**: Toda operação do OpenAPI DEVE estar classificada no mapa em exatamente uma de três listas:
  **tool**, **fora do MCP** (ex.: login, upload de arquivo, rotas `deprecated`) ou **proibida** (atos
  humanos). A verificação automatizada (junto da verificação de contrato existente) DEVE falhar em
  quatro casos: operação sem classificação, operationId inexistente, schema da tool divergente do
  OpenAPI, ou operação proibida mapeada como tool.
- **FR-011**: Uma tool DEVE executar a operação da API correspondente, com as mesmas validações,
  regras de negócio, controle de versão e histórico. O servidor MCP NÃO DEVE reimplementar regra de
  negócio nem acessar o banco por fora da API.
- **FR-012**: A lista de tools DEVE variar conforme o escopo do cliente (quem só lê nem vê as escritas),
  vir sempre na mesma ordem e ter descrições em pt-BR.
- **FR-013**: Erros de regra (403, 404, 409, 422) DEVEM voltar como erro de execução da tool, com
  código e mensagem em pt-BR. O conflito de versão traz a versão atual, para o agente se corrigir.

**Leitura (US2)**

- **FR-014**: O escopo "só leitura" DEVE cobrir as consultas (ver o mapa inicial em Assumptions) de:
  perfis e contas (com modos e intervalo mínimo), kit de marca e padrões de corte, guia de comunicação
  (perfil e conta), assets e arquivos, fontes, canais-fonte e vídeos-fonte, envios e cortes, conteúdos
  (lista, resumo, detalhe) e destinos (detalhe, tentativas, vínculo, métricas), calendário,
  métricas de vídeos e de contas, as 8 análises do analytics (019), tipos de campo do assistente de IA,
  histórico de versões das entidades lidas e links assinados de mídia.
- **FR-015**: Ficam **fora** da leitura: custo de IA e registro de chamadas do assistente (só dono),
  exportação do dataset de métricas, usuários, eventos de segurança, configuração e tokens de
  publicação, criador e dados da conexão da conta na rede, e qualquer segredo. Nas respostas mistas
  (ex.: funil), o que é de dono vem omitido, como para um membro.
- **FR-016**: Listas DEVEM ser paginadas, com teto de tamanho de resposta. Acima do teto, a resposta
  vem recortada, com o aviso "resultado truncado, use filtros ou a próxima página".
- **FR-017**: Mídia (vídeos, imagens, fontes) DEVE sair só como link assinado com validade, nunca embutida
  na resposta.

**Escrita limitada e reversível (US4)**

- **FR-018**: O escopo "leitura e propostas" DEVE acrescentar, no primeiro corte, só estas escritas:
  (a) criar, editar e arquivar **anotações e propostas** próprias presas a um item;
  (b) **selecionar um vídeo-fonte para corte** (envio `selecionado`, sem enviar);
  (c) **editar os textos de um destino ainda não aprovado** (título, descrição, hashtags).
  o primeiro corte de escrita é exatamente este conjunto (a+b+c); criar canal-fonte, editar gancho,
  adicionar destino e pedir aprovação ficam fora (Clarification 2026-10-02)
- **FR-019**: Uma **anotação** DEVE ter: item alvo (tipo e id), tipo (`observacao` ou
  `proposta_texto`), texto (até 4.000 caracteres), campos propostos (para `proposta_texto`: título,
  descrição, hashtags), situação (`aberta`, `aplicada`, `descartada`, `arquivada`), autor e data, com
  versão e histórico. Um cliente só edita ou arquiva as próprias anotações abertas.
- **FR-020**: Aplicar ou descartar uma proposta DEVE ser ato humano (dono ou membro, conforme a regra da
  tela do item). "Aplicar" preenche o formulário do item, sem salvar, e só o "Salvar" humano grava,
  com o autor humano e a referência da proposta no histórico (como o "aplicar" do assistente de IA, spec 008).
- **FR-021**: Editar os textos de um destino pelo MCP DEVE ser recusado quando o destino está aprovado,
  agendado, enviado, postado ou arquivado. Nesses estados, a saída é gravar uma proposta.
- **FR-022**: Toda escrita de um cliente MCP DEVE gravar no histórico da entidade o ator `mcp_client`
  e o cliente identificado, antes e depois, na mesma transação. O histórico na interface mostra o selo
  "Agente: <nome>", e o dono pode reverter como qualquer mudança. O envio selecionado pelo agente se
  desfaz arquivando o envio (ato humano), porque envio não tem reversão (exceção já aprovada do VII).
- **FR-023**: Um cliente MCP NÃO DEVE conseguir arquivar, restaurar nem reverter entidade de domínio,
  e NÃO DEVE criar ou alterar perfil, conta, kit, guia, assets, fontes, regras da IA nem configuração.

**Proibições (US3)**

- **FR-024**: A lista **proibida** DEVE conter, pelo menos: conectar, desconectar e retorno de conexão
  de conta; aprovar, desaprovar, recusar destino (individual, em lote e "aprovar todas"); criar,
  alterar, reagendar, cancelar e sequenciar agendamentos; enviar agora, confirmar envio, tentar de
  novo e marcar como postado; enviar para corte (com a confirmação do aviso de direito), tentar de novo
  envio e corte, confirmar qualidade e aplicar marca; mudar o direito de canal; reverter qualquer
  entidade; usuários, autenticação, senha e eventos de segurança; configuração de publicação; regras e
  guia (edição); vínculo manual do post com o destino.
- **FR-025**: Independentemente do mapa, a API DEVE recusar com 403 `somente_humano` toda rota de ato
  humano chamada por um ator `mcp_client` e gravar o evento de recusa com o cliente identificado. Um
  teste automatizado percorre a lista proibida com uma credencial MCP real.
- **FR-026**: O servidor DEVE validar a origem das requisições (recusar origem de navegador não
  autorizada), aceitar credencial só no cabeçalho de autorização (nunca na URL) e responder "não
  autenticado" sem dizer se o cliente existe.

**Limites e auditoria (US5)**

- **FR-027**: Cada cliente DEVE ter limite de **chamadas por minuto** (padrão 60) e de **escritas por dia**
  (padrão 200, dia no fuso de Brasília), ajustáveis pelo dono. Passou do limite: recusa com o tempo de
  espera, e o registro mostra "limite".
- **FR-028**: O sistema DEVE registrar **toda chamada** (inclusive as recusadas e as não autenticadas
  com cliente identificável): data e hora, cliente, tool, resumo dos argumentos (truncado e sem
  segredos), resultado (`ok`, `recusada`, `erro`, `limite`, `nao_autenticado`), código do erro,
  duração e, nas escritas, o item alterado. O registro é só de inserção.
- **FR-029**: A tela de agentes (só dono) DEVE mostrar a lista de clientes (escopo, situação, último uso,
  chamadas e recusas em 24 h, "no limite") e o registro de chamadas com filtros por cliente, tool,
  resultado e período, com link para o item alterado.
- **FR-030**: Mudanças nos clientes (criação, escopo, limites, suspensão, rotação, revogação) e no
  interruptor DEVEM ir para o histórico, com autor e data, e para os eventos de segurança.

**Uso pelos agentes (US6)**

- **FR-031**: O servidor DEVE ser alcançável pelo gateway do OpenClaw no mesmo host e pela rede de casa,
  só pelo edge (a porta da API continua sem publicação). Nada fica exposto fora da rede de casa.
  **Streamable HTTP dentro da própria API**, num caminho atrás do edge, executando as operações
  internamente, sem serviço novo (princípio VIII; Clarification 2026-10-02)
- **FR-032**: A entrega DEVE incluir um guia (quickstart) para configurar cada agente do OpenClaw, um
  passo por vez: criar o cliente, guardar a credencial fora do arquivo de config, registrar o servidor,
  restringir o servidor ao agente, sondar e fazer uma leitura de teste. O guia traz o mapa recomendado
  de agente para escopo.

### Key Entities

- **Cliente MCP:** quem chama o MCP (um agente ou uma ferramenta). Tem nome, descrição, escopo,
  situação, limites, validade opcional, criado por (dono), último uso e versão com histórico. Nunca é
  apagado.
- **Credencial do cliente:** o segredo que identifica o cliente. É guardado só para verificação, tem
  data de emissão e de revogação ou rotação e é mostrado uma vez.
- **Interruptor MCP:** o estado geral (ligado ou desligado) na tela, com histórico. Soma-se ao
  interruptor da configuração do servidor.
- **Mapa de tools:** a classificação versionada de cada operationId (tool, fora do MCP ou proibida), com
  escopo e anotação. Os schemas vêm do OpenAPI.
- **Chamada MCP:** registro só de inserção de cada chamada (cliente, tool, argumentos resumidos,
  resultado, código, duração, item alterado).
- **Anotação / proposta:** texto ou proposta de campos de um cliente MCP preso a um item do domínio, com
  situação, versão e histórico. Aplicada ou descartada só por humano.
- **Ator `mcp_client`:** o autor gravado no histórico e nos eventos, ligado ao cliente.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O dono cria um cliente, configura um agente pelo guia e vê a primeira leitura dele no
  registro em menos de 10 minutos.
- **SC-002**: 100% das operações da lista proibida são recusadas a uma credencial MCP, tanto pelo
  servidor MCP quanto direto na API, com o evento de recusa gravado (verificado por teste automatizado
  a cada entrega).
- **SC-003**: 100% das operações do OpenAPI estão classificadas no mapa, e qualquer divergência entre o
  mapa e o OpenAPI faz a verificação falhar.
- **SC-004**: 100% das escritas feitas por clientes MCP aparecem no histórico do item com o cliente
  como autor, e cada uma pode ser revertida (ou arquivada, no caso do envio) pelo dono em até 2 cliques
  a partir do histórico.
- **SC-005**: Revogar, rotacionar ou desligar o interruptor corta o acesso já na chamada seguinte (0
  chamadas aceitas depois do ato).
- **SC-006**: Uma leitura comum (detalhe de item ou página de lista) responde em até 1 segundo com o
  volume atual, e o limite de taxa recusa a primeira chamada acima do teto.
- **SC-007**: Nenhum segredo (credencial, token de rede, chave) aparece em resposta de tool, registro de
  chamadas, histórico ou log, verificado pela varredura de segredos sobre os artefatos de teste.
- **SC-008**: Com um agente real do OpenClaw, uma pergunta de leitura ("quais vídeos-fonte do perfil X
  ainda não têm envio?") é respondida com os dados do SociMan sem consultar arquivo Markdown.

## Assumptions

- **Consumidores:** os 11 agentes do OpenClaw no mesmo host, mais, eventualmente, uma ferramenta de dev
  do dono (ex.: Claude Code) com cliente próprio. Nenhum cliente fora da rede de casa.
- **Uma credencial por agente**, não uma compartilhada. A doc do OpenClaw recomenda credencial por
  agente no servidor MCP para isolar os agentes, já que a lista de skills não é fronteira de
  autorização (`notas-pesquisa.md` §6).
- **Mapa recomendado de agente para escopo** (o dono decide no guia):
  - "leitura e propostas": `gestor`, `cacador` (selecionar vídeo-fonte), `planejador`, `revisor`
    (anotações) e `shop-roteirista`;
  - "só leitura": `pesquisador`, `estrategista`, `analista`, `produtor`, `shop-analista` e `shop-diretor`.
- **Papel efetivo:** o cliente MCP lê o que um membro lê. Não há restrição por perfil no primeiro corte
  (os agentes atendem vários perfis). Restringir por perfil fica para depois, se for preciso.
- **Protocolo:** a versão atual do MCP (2026-07-28, sem estado) e Streamable HTTP. A compatibilidade com
  clientes da versão anterior depende do que o OpenClaw 2026.9.6 fala, e é verificada no plano.
- **Sem IA paga pelo MCP:** gerar texto com o assistente de IA (008) fica fora do MCP no primeiro corte,
  porque os agentes têm o próprio modelo e o custo do assistente é do dono. Eles gravam propostas.
- **Sem upload pelo MCP:** envio de arquivos (vídeo próprio, assets, fontes, avulso) continua só pela
  interface.
- **Mapa inicial de tools de leitura** (o plano confirma a lista final): `perfis_list`, `perfis_get`,
  `perfis_versions`, `contas_versions`, `contas_modos`, `kit_get`, `kit_export`, `kit_versions`,
  `envios_padroes_get`, `guias_perfil_get`, `guias_conta_get`, `assets_list`, `assets_get`,
  `assets_images`, `assets_versions`, `fontes_list`, `fontes_padrao_list`, `canais_list`, `canais_get`,
  `canais_versions`, `videos_fonte_list`, `videos_fonte_get`, `envios_list`, `envios_get`,
  `envios_versions`, `cortes_list`, `cortes_get`, `cortes_versions`, `conteudos_list`,
  `conteudos_resumo`, `conteudos_get`, `conteudos_versions`, `destinos_get`, `destinos_versions`,
  `destinos_tentativas`, `destinos_vinculo_get`, `destinos_metricas`, `postagens_calendario`,
  `metricas_videos_list`, `metricas_videos_get`, `metricas_conta`, os 8 `analytics_*`,
  `ia_tipos_list`, `ia_tipos_get`, `midia_links`, `armazenamento_get` e `integracoes_get` (este só
  com o estado, sem valores).
- **Escritas do primeiro corte** (se a recomendação B for aceita): `envios_selecionar`,
  `destinos_update` (com a trava de FR-021) e as rotas novas de anotações. Ficam para uma spec futura:
  criar canal-fonte, editar gancho, adicionar destino e pedir aprovação.
- **Retenção do registro de chamadas:** guardado sem prazo no primeiro corte (o volume é pequeno). Uma
  política de retenção pode vir depois, sem apagar o histórico das entidades.
- **Prompt injection:** o servidor não confia no texto dos agentes nem no conteúdo de terceiros. A
  defesa é estrutural (argumentos tipados, escopo, lista proibida, recusa na API), não um filtro de
  texto.
- **Fora do escopo:** recursos e prompts MCP (só tools no primeiro corte), notificações de mudança
  (`subscriptions/listen`), acesso de fora da rede de casa e substituir os arquivos de `shared/` (isso é
  da `013-importacao`).
