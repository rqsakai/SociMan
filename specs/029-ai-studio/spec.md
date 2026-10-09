# Feature Specification: AI Studio (biblioteca da agência)

**Feature Branch**: `004-kit-de-marca-poc` (branch de trabalho atual; a spec não cria branch)

**Created**: 2026-10-09

**Status**: Draft

**Input**: User description: "029-ai-studio: conforme docs/insumos/029-ai-studio.md (decisões do dono de 2026-10-09: biblioteca da agência com perfil base opcional; grupo AI Studio no menu com Avatares, Cenários, Vozes, Produtos, Cenas, Assets e Movimentos em breve; perfil base escolhido na hora de gerar; criação no lugar dentro da nova cena; abas do perfil saem com redirecionamento; clonagem de movimento fica na 030)"

## Contexto

Hoje, avatares, cenários, os outros assets (007), cenas (010), produtos (012) e vozes (025) pertencem obrigatoriamente a um perfil e ficam em abas da página do perfil. Isso traz três problemas:
- Para montar um vídeo, o dono entra no perfil e pula entre abas.
- Na criação de uma cena, não dá para criar o avatar, o cenário ou o produto que falta.
- Uma pessoa (avatar e voz) ou um cenário não pode ser reaproveitado em outro perfil.

A página provisória `/app/estudio` (correção de 2026-10-09) só junta as abas de um perfil e é substituída por esta spec.

**Decisões do dono (2026-10-09):**
1. A biblioteca é **da agência**, com **perfil base opcional**.
2. O AI Studio é um **grupo próprio no menu**, com os tipos separados.
3. O perfil base é **escolhido na hora de gerar**.
4. A clonagem de movimento fica para a **030**. Aqui ela só tem o lugar reservado no menu.

## Clarifications

### Session 2026-10-09

- Q: O nome de uma voz deve ser único na agência inteira ou pode repetir entre perfis base? → A: Único na agência inteira entre as vozes ativas; na migração os repetidos ganham o sufixo " (2)", registrado no histórico (FR-022).
- Q: O item "Assets" lista só os tipos sem item próprio ou a biblioteca inteira? → A: Só imagem, sticker, marca d'água e fundo; avatares e cenários ficam só nos itens deles. Tudo no menu lateral (grupo AI Studio), nada dentro do perfil (FR-001, FR-018).
- Q: Quem muda o perfil base do item e escolhe o da geração? → A: Dono e membro (como as outras edições e gerações); reverter continua só com o dono (FR-007, FR-008).
- Q: A cena pode ficar sem perfil base? → A: Sim, opcional como os outros itens; sem perfil, sem padrões nem guia, e a tela avisa antes de gerar (FR-005, FR-009, FR-012).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Biblioteca da agência no menu AI Studio (Priority: P1)

O dono abre o grupo **AI Studio** no menu principal e encontra, separados:
- **Avatares**, **Cenários**, **Vozes**, **Produtos**, **Cenas** e **Assets** (imagem, sticker, marca d'água e fundo);
- **Movimentos**, marcado como "em breve" (030).

Cada lista mostra os itens de **todos** os perfis e os que não têm perfil, com filtro por perfil base (incluindo "Sem perfil"), busca, tags e arquivados.

**Why this priority**: É a mudança que o dono pediu: tirar a montagem do vídeo de dentro do perfil. As outras histórias dependem destas listas.

**Independent Test**: Com itens de dois perfis e um item sem perfil, abrir cada item do grupo AI Studio e conferir que a lista traz os três, que o filtro por perfil base separa cada um e que o filtro fica na URL.

**Acceptance Scenarios**:

1. **Given** avatares do perfil A, do perfil B e um sem perfil, **When** o dono abre AI Studio › Avatares, **Then** os três aparecem, cada um com o perfil base (ou "Sem perfil") e a situação do kit (025).
2. **Given** a lista de Avatares, **When** o dono filtra por perfil base A, **Then** só o avatar de A aparece, e o filtro fica na URL (voltar e recarregar mantêm).
3. **Given** o menu, **When** o dono clica em "Movimentos", **Then** vê uma página "em breve" que explica a clonagem de movimento e que não tem ação.
4. **Given** um membro (não dono), **When** abre o AI Studio, **Then** vê as mesmas listas e as mesmas ações que já tem hoje em cada tipo.

---

### User Story 2 - Criar e gerar com perfil base escolhido (Priority: P1)

Ao criar um item, o dono escolhe o **perfil base**, ou nenhum. Ao pedir um passo de geração (kit do avatar, cena do cenário, ficha ou flat do produto, voz, ajuste da cena), o formulário mostra o **perfil base** que será usado. O padrão é o perfil base do item, e o dono pode trocar só para aquela geração. O guia de comunicação e as palavras proibidas desse perfil entram na geração. Sem perfil base, a geração usa só as regras do tipo.

**Why this priority**: Sem isso, mover os itens para fora do perfil faria a geração perder o guia e as proibidas.

**Independent Test**: Criar um avatar sem perfil e gerar a origem (sem guia). Depois gerar com o perfil base A, cujo guia tem a palavra proibida "x", e conferir no registro do assistente que a chamada usou o guia de A, e que a proposta com "x" foi tratada como proibida (017).

**Acceptance Scenarios**:

1. **Given** o formulário de novo avatar, **When** o dono deixa o perfil base vazio e salva, **Then** o avatar nasce sem perfil e aparece em "Sem perfil".
2. **Given** um cenário com perfil base A, **When** o dono pede "Gerar cena" sem mexer no campo, **Then** a geração usa o perfil A, e o registro grava qual guia e qual versão foram usados.
3. **Given** o mesmo cenário, **When** o dono troca o perfil base para B só nessa geração, **Then** a geração usa o guia de B, e o perfil base do cenário continua A.
4. **Given** um item com perfil base A, **When** o dono troca o perfil base para B e salva, **Then** a mudança vira uma versão no histórico, com autor, antes e depois, e pode ser revertida pelo dono.

---

### User Story 3 - Usar itens de qualquer perfil e criar no lugar (Priority: P1)

Na nova cena (010), o dono escolhe avatar, cenário e produto de **qualquer** perfil (ou sem perfil). Se faltar um, clica em "+ Novo avatar", "+ Novo cenário" ou "+ Novo produto", cadastra num diálogo sem sair da cena e volta com o item já escolhido.

**Why this priority**: É a queixa direta do dono ("na criação de cena, onde ficou para criar o cenário e os outros assets?") e a razão de ter a biblioteca da agência.

**Independent Test**: Criar uma cena com perfil base B usando um cenário do perfil A e um avatar sem perfil. Depois, na mesma cena, criar um produto novo pelo diálogo e conferir que ele vem escolhido e que o prompt da cena o inclui.

**Acceptance Scenarios**:

1. **Given** um cenário do perfil A, **When** o dono cria uma cena com perfil base B e escolhe esse cenário, **Then** a cena é salva, sem a recusa de hoje para asset de outro perfil.
2. **Given** a nova cena sem nenhum cenário cadastrado, **When** o dono clica em "+ Novo cenário", preenche nome e prompt e salva, **Then** o diálogo fecha, o cenário aparece escolhido na cena e o que já estava preenchido na cena continua lá.
3. **Given** o diálogo de novo avatar aberto a partir da cena, **When** o dono cancela, **Then** nada é criado e a cena continua como estava.
4. **Given** uma cena que usa um avatar arquivado depois, **When** o dono abre a cena, **Then** vê o aviso de item arquivado, como hoje.

---

### User Story 4 - A página do perfil sem as abas de criação (Priority: P2)

A página do perfil perde as abas Assets, Cenas, Produtos e Vozes. No lugar, há atalhos "Ver no AI Studio" (avatares, cenários, cenas, produtos e vozes deste perfil) que abrem as listas já filtradas pelo perfil base. Os links antigos (`?aba=assets`, `?aba=cenas`, `?aba=produtos`, `?aba=vozes`) e a página provisória `/app/estudio` redirecionam para o lugar novo.

**Why this priority**: Fecha a mudança sem quebrar favoritos, mas não bloqueia o uso do AI Studio.

**Independent Test**: Abrir `/app/perfis/<id>?aba=vozes` e conferir que vai para AI Studio › Vozes filtrado pelo perfil. Conferir que a página do perfil não tem mais as quatro abas e tem os atalhos.

**Acceptance Scenarios**:

1. **Given** um link salvo `/app/perfis/<A>?aba=assets`, **When** o dono abre, **Then** vai para AI Studio › Assets filtrado pelo perfil base A.
2. **Given** a página do perfil A, **When** o dono clica em "Ver no AI Studio" para cenas, **Then** abre AI Studio › Cenas com o filtro do perfil A.
3. **Given** o kit de marca do perfil A (fundo e marca d'água), **When** o dono escolhe a imagem, **Then** o seletor lista a biblioteca da agência, e o item em uso no kit continua bloqueando o arquivar.

---

### User Story 5 - Agentes e leitura continuam funcionando (Priority: P3)

Os agentes (MCP) continuam lendo a biblioteca (assets, cenas, produtos e vozes) com o filtro de perfil base, e as leituras por perfil que eles já usam continuam respondendo. As propostas dos agentes para cenas continuam iguais (010).

**Why this priority**: Evita quebrar os agentes da agência, mas não muda nada para o dono.

**Independent Test**: Com um token de leitura, listar os assets sem perfil e os do perfil A pelos dois caminhos (o antigo, por perfil, e o novo, da agência) e conferir que os resultados batem.

**Acceptance Scenarios**:

1. **Given** um cliente MCP de leitura, **When** lista a biblioteca filtrando pelo perfil A, **Then** recebe os mesmos itens que a leitura antiga por perfil.
2. **Given** um cliente MCP, **When** tenta criar ou mudar o perfil base de um item, **Then** recebe a recusa de hoje, porque as escritas continuam fora do alcance dos agentes.

### Edge Cases

- **Perfil base arquivado:** os itens continuam na biblioteca, com o perfil marcado "arquivado". Gerar com ele como base é recusado, com a mensagem "o perfil base está arquivado: escolha outro ou nenhum".
- **Nomes repetidos entre perfis:** dois avatares "Ana" de perfis diferentes podem existir (os nomes de asset não são únicos hoje). As listas mostram o perfil base ao lado do nome para separar.
- **Vozes:** o nome da voz passa a ser único **na agência inteira** entre as ativas. Na migração, se dois perfis tiverem vozes ativas com o mesmo nome, a mais nova ganha o sufixo " (2)", e o ajuste fica no histórico.
- **Cena sem perfil base:** a cena funciona, mas sem os padrões de estilo e negativo do perfil (010) e sem as proibidas de nenhum perfil. A tela avisa: "sem perfil base: sem padrões nem guia".
- **Conteúdo (014):** o vídeo próprio e os destinos continuam do perfil e da conta da postagem. Usar uma cena com perfil base A num conteúdo do perfil B é permitido, e o histórico do conteúdo registra a cena.
- **Consentimento e revogação (025):** continuam do item e não mudam com o perfil base. Revogar um avatar usado em cenas de vários perfis lista todas as cenas afetadas.
- **Limpeza de 90 dias (021):** continua igual. O "em uso" vale para qualquer perfil.
- **Aprendizado e analytics:** contam pelo perfil do **conteúdo**, nunca pelo perfil base do asset.
- **Página provisória `/app/estudio`:** redireciona para AI Studio › Avatares (com o perfil lembrado como filtro, quando houver).

## Requirements *(mandatory)*

### Functional Requirements

**Biblioteca e menu**
- **FR-001**: O menu lateral principal MUST ter o grupo **AI Studio** com os itens abaixo, nesta ordem. Nenhum deles fica dentro da página do perfil.
  - Avatares
  - Cenários
  - Vozes
  - Produtos
  - Cenas
  - Assets: só os tipos imagem, sticker, marca d'água e fundo; avatares e cenários aparecem só nos itens próprios
  - Movimentos (página "em breve", sem ação)
- **FR-002**: Cada lista MUST mostrar os itens de todos os perfis e os sem perfil, com:
  - o perfil base de cada item (ou "Sem perfil");
  - filtro por perfil base (com "Sem perfil" como opção), busca, tags (onde o tipo tem) e arquivados;
  - os filtros na URL;
  - paginação por cursor com "Carregar mais", como as listas de hoje.
- **FR-003**: Avatares MUST mostrar a situação do kit (025). Vozes MUST mostrar o estado e a sincronização (025). Produtos MUST mostrar o status (012). Cenas MUST mostrar o status (010).
- **FR-004**: O detalhe de cada item MUST continuar no endereço de hoje (`/app/assets/:id`, `/app/vozes/:id`, `/app/produtos/:id` e o da cena). A tela agora mostra o perfil base e o menu marca o item do AI Studio como ativo.

**Perfil base**
- **FR-005**: Avatares, cenários, outros assets, cenas, produtos e vozes MUST ter um **perfil base opcional**. Todo item que existe hoje MUST manter o perfil atual como perfil base.
- **FR-006**: Criar um item MUST permitir escolher o perfil base ou nenhum. O padrão é o filtro de perfil ativo na lista, quando houver.
- **FR-007**: Dono e membro MUST poder mudar o perfil base de um item. A mudança MUST ser uma edição versionada, com autor, antes e depois, e só o dono reverte, como nas outras edições (princípio VII).
- **FR-008**: O pedido de qualquer passo de geração (021, 012, 025) e de qualquer sugestão do assistente sobre o item (008) MUST:
  - usar o perfil base escolhido no pedido, por dono ou membro (o padrão é o do item; "nenhum" é permitido);
  - aplicar o guia e as proibidas daquele perfil;
  - gravar na chamada ou na geração qual perfil base foi usado.

  Trocar o perfil base no pedido MUST NOT mudar o item.
- **FR-009**: Sem perfil base, a geração MUST usar só as regras do tipo, sem guia e sem proibidas. A tela MUST dizer isso antes de gerar.
- **FR-010**: Um perfil base arquivado MUST ser recusado como base de geração, com mensagem clara. Os itens dele continuam visíveis e editáveis.

**Usos cruzados**
- **FR-011**: A cena MUST aceitar avatar, cenário e produto de qualquer perfil base ou sem perfil. A recusa de hoje para item de outro perfil MUST ser retirada; continuam valendo as outras regras (tipo certo, produto aprovado com recorte, arquivado avisa).
- **FR-012**: O perfil base da cena MUST ser opcional, como nos outros itens. Os padrões de estilo e negativo (010) que entram na cena MUST vir do perfil base da cena. Sem perfil base, nenhum padrão nem guia é usado, e a tela da cena MUST avisar isso.
- **FR-013**: O kit de marca do perfil MUST escolher fundo e marca d'água na biblioteca da agência. O uso no kit MUST continuar bloqueando o arquivar do asset.
- **FR-014**: Conteúdos, destinos, postagens, métricas, analytics e aprendizado MUST continuar ligados ao perfil e à conta do conteúdo. Nada passa a depender do perfil base do asset.
- **FR-015**: "Onde é usado" de cada item MUST listar os usos em todos os perfis, mostrando o perfil de cada uso.

**Criação no lugar**
- **FR-016**: Na nova cena e na edição de cena, os seletores de avatar, cenário e produto MUST ter "+ Novo …", que abre o cadastro do tipo num diálogo. Ao salvar, o item volta já escolhido. Ao cancelar, nada é criado. O que estava preenchido na cena MUST continuar.
- **FR-016a**: O produto criado pelo "+ Novo produto" da cena ainda não está aprovado (012), então não entra no catálogo da cena na hora. A cena MUST guardar a referência leve (nome) e mostrar "O produto <nome> foi criado e ainda precisa ser aprovado no catálogo. Depois de aprovado, ligue-o a esta cena." A regra da 012 (só produto aprovado, com recorte, no catálogo da cena) não muda.
- **FR-017**: O item criado pelo diálogo MUST nascer com o perfil base da cena (pode ser trocado no diálogo) e seguir as mesmas regras do cadastro normal (consentimento, menoridade, nome único das vozes etc.).

**Página do perfil e links antigos**
- **FR-018**: A página do perfil MUST perder as abas Assets, Cenas, Produtos e Vozes e ganhar o bloco "Ver no AI Studio", com um atalho por tipo filtrado pelo perfil e a contagem de itens.
- **FR-019**: Os links `?aba=assets|cenas|produtos|vozes` do perfil e a página `/app/estudio` MUST redirecionar para a lista correspondente do AI Studio, com o filtro do perfil.

**Agentes e contrato**
- **FR-020**: As leituras da biblioteca MUST existir sem perfil obrigatório, com filtro opcional de perfil base (incluindo "sem perfil"). As leituras antigas por perfil MUST continuar respondendo, os mesmos itens, marcadas como obsoletas.
- **FR-021**: Os agentes (MCP) MUST continuar só lendo a biblioteca. Criar, editar, mudar o perfil base, escolher opções e revogar continuam fora do alcance deles, e toda rota nova MUST estar classificada para o MCP.
- **FR-022**: O nome de voz MUST ser único entre as vozes ativas da agência inteira. A migração MUST resolver os repetidos de hoje com sufixo e registrar o ajuste no histórico.

**Regras que não mudam**
- **FR-023**: Consentimento e revogação (025), escolha só humana das opções (021), aprovação de produto (012), limpeza de 90 dias (021) e a regra de nada publicar (princípio I) MUST continuar exatamente como estão.

### Key Entities

- **Item da biblioteca**: avatar, cenário, outro asset, cena, produto ou voz.
  - Ganha o **perfil base** (opcional): só uma referência, que indica o guia, as proibidas e os padrões usados por padrão nas gerações.
  - Os itens existentes ficam com o perfil atual como base.
- **Perfil base da geração**: o perfil (ou nenhum) usado num pedido de geração ou sugestão específico. Fica gravado na geração ou na chamada, ao lado da versão do guia usada.
- **Perfil**: continua dono de contas, conteúdos, kit de marca, guia, padrões de corte e de cena. Deixa de ser dono da biblioteca.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O dono monta uma cena nova com avatar, cenário e produto, criando um item que faltava, sem sair da tela da cena, em até 3 minutos.
- **SC-002**: 100% dos itens que existem antes da mudança continuam acessíveis no AI Studio com o perfil atual como perfil base, sem perder versões, arquivos nem usos.
- **SC-003**: Um avatar ou cenário de um perfil pode ser usado numa cena de outro perfil em 100% dos casos que hoje são recusados só por ser de outro perfil.
- **SC-004**: Toda geração e toda sugestão registram qual perfil base foi usado, conferível no registro do assistente e no histórico da geração.
- **SC-005**: Todos os links antigos das abas do perfil e o `/app/estudio` chegam à lista certa do AI Studio, sem página de erro.
- **SC-006**: As listas do AI Studio abrem em até 1 s com 5 mil itens na biblioteca.
- **SC-007**: Nenhuma escrita na biblioteca fica ao alcance dos agentes: o teste de classificação das rotas para o MCP continua passando.

## Assumptions

- Dono e membro continuam vendo a biblioteca inteira, sem permissão por perfil. O multi-tenant é uma spec futura (decisão de 2026-10-08): quando ele chegar, os itens da biblioteca também ganham `tenant_id`, porque o perfil base nulo não serve de dono.
- Os nomes de asset continuam sem unicidade (como hoje). Só as vozes passam a ter o nome único na agência inteira, porque o nome é o rótulo usado para escolher a voz.
- Os rótulos únicos dentro de um item (pose, look e variação) continuam únicos dentro do item.
- As telas de detalhe dos itens não mudam além do perfil base e do menu ativo. A 029 mexe nas listas, nos seletores, nos formulários de criação e de geração e na página do perfil.
- A clonagem de movimento (030) só ganha o item "Movimentos" no menu, sem dados nem ações.
- Depende das specs 007, 010, 012, 017, 021 e 025, todas implementadas. A 011 (roteiros) ainda não foi implementada e deve ser revista depois desta: o roteiro usa a biblioteca.
