# Feature Specification: Assistente de IA para textos (008-assistente-ia)

**Feature Branch**: `008-assistente-ia`

**Created**: 2026-09-29

**Status**: Clarified (Q1–Q3 respondidas em 2026-09-29)

**Input**: User description: "Um botão 'Melhorar com IA' nos campos de texto (descrição para prompt do
avatar, tom de voz, regras de imagem, prompt do cenário, bio do perfil, bordões e séries, título,
descrição e hashtags das postagens, nomes e descrições de assets). O usuário escreve um comentário
opcional (vazio = melhorar ou criar do zero; preenchido = como melhorar ou o que criar) e envia ao
Claude. Cada tipo de campo tem seu system prompt, com o contexto do perfil e o valor atual. A IA
devolve uma proposta com uma breve explicação; o usuário aplica, edita, pede outra versão ou
descarta. Nada é salvo sem ação humana. Os system prompts são visíveis e ajustáveis pelo dono. Cada
chamada é registrada."

## Clarifications

### Session 2026-09-29

- Q: Onde fica a ajuda da IA? → A: Um botão "Melhorar com IA" ao lado de cada campo de texto
  relevante, que abre um painel junto do campo (sem sair da tela).
- Q: A IA pode salvar sozinha? → A: Não. A proposta só vira valor do campo quando o usuário aplica,
  e aplicar segue o mesmo caminho de salvar à mão (histórico, versão, reversão pelo dono).
- Q: O que o botão "Aplicar" faz? → A: **Salva na hora** (1 clique), só aquele campo, pelo caminho
  normal de salvar da entidade (validação, versão otimista com 409, histórico com autor humano e a
  marca "com ajuda da IA"), disparado pelo painel. As outras alterações não salvas do formulário
  continuam no formulário, sem salvar e sem se perder. "Editar e aplicar" edita a proposta no
  painel e salva do mesmo jeito. (Q1 = B)
- Q: Em que idioma saem as "Regras de imagem" do avatar? → A: No idioma do perfil (pt-BR). A
  descrição para prompt do avatar e o prompt do ambiente do cenário continuam em inglês. (Q2 = B)
- Q: Bordões e séries: a IA propõe a lista inteira ou um item? → A: Uma **lista de sugestões com
  seleção**: o usuário marca quais aceitar, e os aceitos entram na lista do kit ao aplicar. "Gerar
  mais" pede novas sugestões levando os itens já aceitos (os do kit e os marcados na sessão) e os
  rejeitados na sessão, para não repetir e manter o estilo. A lista do kit continua com no máximo
  20 itens. (Q3)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Melhorar ou criar um texto com IA (Priority: P1)

Num campo de texto (ex.: "descrição fixa para prompt" do avatar Achadinhos), o usuário clica em
"Melhorar com IA". Abre um painel com o texto atual, uma caixa "Como a IA deve ajudar?" (opcional) e
o botão "Gerar". Com a caixa vazia, a IA melhora o texto atual (ou cria um, se o campo estiver
vazio), seguindo as regras daquele tipo de campo. Com a caixa preenchida (ex.: "deixa mais curto e
acrescenta que ela usa avental rosa"), a IA segue a instrução. A resposta traz a proposta e uma
explicação curta do que mudou e por quê. O usuário vê o antes e o depois lado a lado e escolhe:
**Aplicar** (salva na hora só aquele campo), **Editar e aplicar** (ajusta a proposta no painel e
salva), **Outra versão** ou **Descartar**.

Nos **bordões** e nas **séries** do kit (listas), a IA devolve uma lista de sugestões. O usuário
marca as que quer, pode editar as marcadas, e "Aplicar" acrescenta as marcadas à lista do kit.
"Gerar mais" traz sugestões novas, diferentes das já aceitas e das rejeitadas na sessão.

**Why this priority**: é o valor central pedido pelo dono: textos melhores (prompts, títulos, bios)
com menos esforço, sem perder o controle.

**Independent Test**: no avatar Achadinhos, pedir "Melhorar com IA" na descrição para prompt com a
instrução "mais detalhes do rosto, mantendo o estilo 1950s", comparar, aplicar e ver a nova versão
no histórico do avatar, com o autor humano.

**Acceptance Scenarios**:

1. **Given** um campo com texto, **When** o usuário gera sem instrução, **Then** recebe uma proposta
   melhorada do mesmo texto e uma explicação curta do que mudou.
2. **Given** um campo vazio, **When** o usuário gera sem instrução, **Then** recebe um texto criado do
   zero a partir do contexto do perfil e da entidade (ex.: nome e tipo do asset).
3. **Given** uma instrução escrita, **When** o usuário gera, **Then** a proposta segue a instrução e a
   explicação diz como ela foi atendida.
4. **Given** uma proposta, **When** o usuário clica em Aplicar, **Then** a entidade é salva na hora
   só com aquele campo, pelo caminho normal (validação, versão e histórico), o campo mostra o valor
   salvo e a autoria é do usuário, com a marca "com ajuda da IA".
5. **Given** uma proposta, **When** o usuário clica em Outra versão, **Then** recebe uma alternativa
   diferente das anteriores daquela sessão, sem perder as já geradas.
6. **Given** uma proposta, **When** o usuário descarta ou fecha o painel, **Then** nada muda no campo
   nem na entidade.
7. **Given** alterações não salvas em outros campos do formulário, **When** o usuário aplica uma
   proposta, **Then** só aquele campo é salvo; o resto do que ele digitou continua no formulário,
   sem salvar e sem se perder, e o próximo "Salvar" da tela funciona sem conflito de versão.
8. **Given** uma proposta, **When** o usuário clica em Editar e aplicar, muda o texto no painel e
   salva, **Then** a entidade é salva com o texto editado e o registro marca a chamada como
   "editada".
9. **Given** o painel de bordões (ou séries) com sugestões, **When** o usuário marca algumas e
   aplica, **Then** só as marcadas entram no fim da lista do kit, sem repetir itens que já estão
   nela, e o kit é salvo com uma versão "com ajuda da IA".
10. **Given** sugestões marcadas e não marcadas na sessão, **When** o usuário clica em Gerar mais,
    **Then** as novas sugestões não repetem nenhum item já aceito (do kit ou marcado) nem os
    rejeitados na sessão, e as sugestões anteriores continuam visíveis.
11. **Given** uma lista do kit com 20 itens (ou marcações que a completariam), **When** o usuário
    tenta marcar mais, **Then** o painel avisa que a lista está cheia (máximo de 20) e não deixa
    marcar além do que cabe.

---

### User Story 2 - Regras (system prompts) por tipo de campo (Priority: P1)

Cada tipo de campo tem suas próprias regras de escrita (o "system prompt"), por exemplo:
- **descrição para prompt de imagem do avatar**: em inglês, pronta para o Flow/Veo, descreve rosto,
  cabelo, roupa e estilo de forma fixa, para manter a consistência da personagem entre gerações;
- **prompt de ambiente do cenário**: em inglês, luz, época, paleta e enquadramento;
- **título de postagem**: pt-BR, curto, com gancho, no limite da plataforma;
- **regras de imagem do avatar**: no idioma do perfil (pt-BR), frases curtas do que sempre e do que
  nunca mostrar;
- **bio do perfil**, **bordões**, **tom de voz**, **descrição de asset** etc.

O pedido à IA sempre leva: as regras do tipo de campo, o contexto do perfil (nome, nicho, idioma,
tom, bordões, paleta com nomes e, quando existir, a persona/avatar relacionado), o valor atual do
campo e a instrução do usuário. O dono vê e ajusta essas regras numa tela "Assistente de IA", com
histórico e "voltar ao padrão".

**Why this priority**: sem regras por tipo, a IA escreve genérico; é isso que faz o prompt de
imagem sair em inglês consistente e o título sair curto em pt-BR.

**Independent Test**: na tela "Assistente de IA", editar as regras de "título de postagem"
acrescentando "sempre termine com um emoji"; gerar um título e ver o emoji; voltar ao padrão.

**Acceptance Scenarios**:

1. **Given** a tela "Assistente de IA", **When** o dono abre, **Then** vê a lista de tipos de campo com
   as regras atuais de cada um, onde são usados e quando foram alteradas pela última vez.
2. **Given** um tipo de campo, **When** o dono edita e salva as regras, **Then** as próximas gerações
   daquele tipo usam as regras novas, e a mudança fica no histórico (reversão pelo dono).
3. **Given** um membro, **When** ele abre a tela, **Then** vê as regras, mas não pode editar.
4. **Given** regras alteradas, **When** o dono clica em "Voltar ao padrão", **Then** as regras voltam ao
   texto que vem com o SociMan (também registrado no histórico).

---

### User Story 3 - Registro e custo das chamadas (Priority: P2)

Toda geração fica registrada: quem pediu, quando, perfil, entidade e campo, tipo de campo, a
instrução, o texto de entrada, a proposta, se foi aplicada, descartada ou editada, a duração e o
custo aproximado. O dono vê um resumo do gasto do mês e a lista das últimas chamadas.

**Why this priority**: controle de custo e rastreabilidade do que a IA sugeriu (princípio VII), mas
não bloqueia o uso do dia a dia.

**Independent Test**: gerar 3 propostas (aplicar 1, descartar 1, pedir outra versão em 1) e ver as 4
chamadas no registro com o desfecho de cada uma e o custo somado no resumo do mês.

**Acceptance Scenarios**:

1. **Given** chamadas feitas, **When** o dono abre o registro, **Then** vê cada chamada com autor,
   campo, desfecho e custo aproximado, filtrável por perfil, tipo de campo e período.
2. **Given** o mês corrente, **When** o dono abre o resumo, **Then** vê o total de chamadas e o custo
   aproximado do mês.
3. **Given** uma chamada que falhou (IA fora do ar, chave ausente, tempo esgotado), **When** o usuário
   tenta, **Then** vê uma mensagem clara, o campo continua editável à mão e a falha fica registrada.

---

### User Story 4 - Os textos de postagem usam o mesmo assistente (Priority: P2)

A sugestão de título, descrição e hashtags da postagem (spec 006) passa a ser um caso deste
assistente: mesmo painel, mesmas ações (aplicar, editar, outra versão, descartar), com as regras do
tipo "texto de postagem" editáveis na mesma tela. A transcrição do clipe continua entrando como
contexto.

**Why this priority**: um jeito só de pedir ajuda à IA em todo o sistema; evita duas experiências
diferentes.

**Independent Test**: num corte pronto, usar "Melhorar com IA" no título com a instrução "mais
polêmico", aplicar, e ver a postagem salva com o novo título e a chamada no registro.

**Acceptance Scenarios**:

1. **Given** uma postagem, **When** o usuário gera os textos, **Then** recebe título, descrição e
   hashtags coerentes entre si, respeitando os limites da plataforma da conta.
2. **Given** as sugestões já feitas pela 006, **When** o registro é aberto, **Then** elas aparecem junto
   das novas chamadas, sem perda.

---

### Edge Cases

- Chave da IA ausente ou inválida: o botão aparece desabilitado com a explicação ("IA não
  configurada"), e todo campo continua editável à mão.
- Resposta acima do limite do campo (ex.: título maior que o permitido): a proposta vem ajustada ao
  limite ou marcada em vermelho, e não pode ser aplicada sem corrigir.
- Instrução do usuário que peça para ignorar as regras ou revelar o system prompt: a IA segue as
  regras do tipo de campo; conteúdo de terceiros (transcrição, textos de vídeos) entra como dado, não
  como instrução.
- Outra pessoa salvou a entidade enquanto o painel estava aberto: aplicar recusa com o aviso de
  conflito de versão (como nas outras telas), sem perder a proposta nem o que foi digitado no
  formulário.
- Aplicar falha (validação, rede, entidade arquivada): nada é salvo, a proposta continua no painel
  e o formulário fica como estava.
- Postagem ainda não criada (corte + conta): aplicar cria a postagem em rascunho só com aquele
  campo (ou os três, em "Sugerir textos").
- Lista do kit cheia (20 itens): o painel avisa e só deixa marcar o que cabe; com a lista cheia,
  "Gerar" fica desabilitado com o aviso.
- Tempo esgotado (mais de 30 s): mensagem clara, com "Tentar de novo".
- Perfil sem kit ou sem persona: a IA usa o que existir e a explicação diz o que faltou de contexto.
- Várias gerações seguidas no mesmo campo: todas ficam acessíveis na sessão do painel até fechar.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Os campos de texto listados em "Tipos de campo" (Key Entities) DEVEM ter o botão
  "Melhorar com IA", que abre um painel junto do campo, sem sair da tela.
- **FR-002**: O painel DEVE ter uma instrução opcional (até 1.000 caracteres); vazia, a IA melhora o
  texto atual ou cria um novo se o campo estiver vazio; preenchida, a IA segue a instrução.
- **FR-003**: Cada pedido DEVE enviar à IA as regras do tipo de campo, o contexto do perfil (nome,
  nicho, idioma, tom, bordões, paleta nomeada, persona/avatar relacionado quando houver), o contexto
  da entidade (ex.: tipo e nome do asset, conta e plataforma da postagem), o valor atual e a
  instrução. Conteúdo de terceiros DEVE entrar como dado delimitado, nunca como instrução.
- **FR-004**: A resposta DEVE trazer a proposta e uma explicação curta (até 3 frases) do que mudou e
  por quê, e respeitar os limites do campo (tamanho, idioma, formato).
- **FR-005**: O usuário DEVE poder Aplicar (salva na hora), Editar e aplicar (edita no painel e
  salva), pedir Outra versão (diferente das já geradas na sessão) ou Descartar. Nada é salvo sem o
  clique humano em Aplicar ou no salvar do Editar e aplicar; gerar nunca salva.
- **FR-006**: Aplicar DEVE salvar pelo mesmo caminho da edição manual (validação, versão, conflito
  409, histórico com autor humano e reversão pelo dono), marcando a versão como "com ajuda da IA".
  O salvar leva **só aquele campo** (atualização parcial; no kit, que é salvo inteiro, os tokens
  salvos com só aquele campo trocado). As outras alterações não salvas do formulário DEVEM
  continuar no formulário, e o formulário DEVE passar a usar a versão nova da entidade.
- **FR-007**: Cada tipo de campo DEVE ter regras (system prompt) padrão que vêm com o SociMan. O dono
  DEVE poder ver, editar e voltar ao padrão; o membro só vê. Mudanças nas regras ficam no histórico.
- **FR-008**: Toda chamada DEVE ser registrada com autor, data, perfil, entidade, campo, tipo de
  campo, instrução, entrada, proposta, desfecho (aplicada, editada, descartada, sem ação, erro),
  duração e custo aproximado. O dono DEVE ver o registro filtrável e o resumo de custo do mês.
- **FR-009**: Falhas (IA não configurada, fora do ar, tempo esgotado, resposta inválida) DEVEM mostrar
  mensagem clara, manter o campo editável e ficar no registro.
- **FR-010**: A sugestão de textos de postagem da spec 006 DEVE passar a usar este assistente (mesmo
  painel e registro), mantendo o histórico de sugestões já feitas.
- **FR-011**: O assistente NUNCA publica nem envia conteúdo para rede social (princípio I); só
  devolve texto para o usuário decidir.
- **FR-012**: Nos bordões e nas séries do kit, a IA DEVE devolver uma lista de sugestões que o
  usuário marca (e pode editar) antes de aplicar; aplicar DEVE acrescentar só as marcadas ao fim da
  lista, sem repetir itens (sem diferenciar maiúsculas) e sem passar de 20 itens (o painel avisa
  quando a lista está cheia). "Gerar mais" DEVE enviar à IA os itens já aceitos (os da lista e os
  marcados na sessão) e os rejeitados na sessão, e as sugestões novas não DEVEM repetir nenhum
  deles.

### Key Entities

- **Tipo de campo**: identificador estável (ex.: `avatar.descricao_prompt`, `avatar.tom_de_voz`,
  `avatar.regras_imagem`, `cenario.prompt_ambiente`, `perfil.bio`, `kit.bordoes`, `kit.series`,
  `postagem.titulo`, `postagem.descricao`, `postagem.hashtags`, `postagem.textos`, `asset.nome`,
  `asset.descricao`), com rótulo, idioma esperado, formato (texto, lista ou sugestões com
  seleção), limites e onde é usado.
- **Regras do tipo de campo** (system prompt): texto atual, texto padrão, autor e data da última
  mudança, versão e histórico.
- **Chamada ao assistente**: autor, data, perfil, entidade e campo, tipo, instrução, entrada,
  propostas geradas (uma ou mais na sessão), nos bordões e séries os itens já aceitos e os
  rejeitados enviados como contexto e os itens que entraram no kit, desfecho, duração, custo
  aproximado, erro.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Do clique em "Melhorar com IA" até ver a proposta leva menos de 15 segundos em 95% das
  chamadas.
- **SC-002**: Aplicar uma proposta (e salvá-la) leva 1 clique a partir da proposta visível.
- **SC-003**: 100% das propostas aplicadas aparecem no histórico da entidade com autor humano e a
  marca "com ajuda da IA"; 0 alterações salvas sem ação humana.
- **SC-004**: Em 10 gerações de "descrição para prompt de imagem", 100% saem em inglês e mantêm os
  traços fixos da persona quando a instrução não pede para mudá-los.
- **SC-005**: O dono consegue responder "quanto gastei com IA este mês e em quê" em menos de 1 minuto.
- **SC-006**: Todos os tipos de campo listados têm o botão e regras padrão na primeira entrega.

## Assumptions

- Usa a mesma integração com o Claude da spec 006 (chave no ambiente do SociMan, fora do git), e o
  mesmo registro de chamadas passa a cobrir todos os tipos de campo.
- As regras são globais por tipo de campo (valem para todos os perfis); o que muda por perfil é o
  contexto enviado. Regras por perfil ficam para depois, se forem necessárias.
- A interação é por gerações independentes na sessão do painel ("Outra versão", "Gerar mais" e
  nova instrução), sem conversa longa persistida; o histórico da sessão some ao fechar o painel,
  mas cada chamada fica no registro.
- Não há limite de gasto que bloqueie o uso; o controle é pelo resumo de custo do mês. Um aviso de
  teto mensal pode entrar depois.
- Imagens não são geradas aqui (a geração continua no Flow/Veo, decisão de 2026-09-24); a IA só
  escreve os textos e prompts.
- Os campos cobertos são os de texto do perfil, do kit, dos assets e das postagens; campos novos de
  specs futuras (cenas, roteiros) entram registrando um novo tipo de campo.
