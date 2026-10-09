# Feature Specification: Cadastro padronizado de avatar, voz e cenário (025-cadastro-padronizado)

**Feature Branch**: `025-cadastro-padronizado`

**Created**: 2026-10-06

**Status**: Draft

**Input**: User description: "Estender a biblioteca de assets da 007 (sem reescrevê-la) para que avatar,
voz e cenário saiam num padrão fixo que os modelos locais rendem bem: kit do avatar (rosto de origem,
rosto frontal, rostos 3/4, corpo-base e checagem de identidade com a descrição fixa para prompts), looks
e poses gerados a partir do kit, vozes do perfil (gravação ou voz sintética, referência de 8–13 s cortada
em fim de frase, aprovada e importada no shop-tts) com voz padrão por avatar, e cenário 9:16 sem pessoas
com variações por rótulo. Cada passo é uma geração da 021 (candidatos → escolha humana). Pessoa real só
com consentimento registrado; menores e famosos recusados. Nada publica." (insumo
`docs/insumos/007b-cadastro-padronizado.md`; o insumo chamava esta feature de 022, renumerada para 025
porque a 022 já existe)

## Clarifications

### Session 2026-10-06

Decisões já tomadas pelo dono (registradas aqui, sem nova pergunta):

- Q: A voz é do avatar ou do perfil? → A: **Do perfil.** Uma voz serve a vários avatares ou a nenhum
  (narração neutra). O avatar pode apontar uma **voz padrão** (`assets.voz_id`), trocável por vídeo.
- Q: Quem escolhe entre os candidatos de cada passo? → A: **Sempre um humano.** Não existe "escolher a
  opção 1 automaticamente" (o `--auto` do pipeline não existe no SociMan). A exceção são os passos **só
  de texto** (aqui, a **checagem de identidade** do avatar), cujo resultado vai direto para o alvo e
  continua editável.
- Q: O que acontece com os candidatos não escolhidos? → A: São apagados (com os arquivos) **90 dias**
  depois que a geração termina. O escolhido **nunca** é apagado.
- Q: Como fica a RAM do ComfyUI durante os passos de imagem? → A: (regra da 021) O limite do container
  sobe para 28 GB **só durante** o job `comfyui` e volta para 12 GB logo em seguida, inclusive quando o
  job falha ou é cancelado, conferindo que voltou.
- Q: A GPU tem fila única com o OpenShorts? → A: (regra da 021) **Não.** O passo só começa com a GPU
  desocupada; senão espera na fila com a mensagem "Aguardando a GPU ficar livre".
- Q: O produto é desta feature? → A: Não; o produto é do perfil e fica na 012.

Respostas do `/speckit-clarify` (dono aceitou as recomendações):

- Q: Guardar a gravação original completa da pessoa real ou só a referência cortada? → A: **A gravação
  original completa**, para refazer a referência sem pedir nova gravação e como prova do que a pessoa
  consentiu (FR-024).
- Q: O que acontece quando a pessoa real revoga o consentimento? → A: **"Revogar consentimento", só do
  dono:** arquiva o avatar ou a voz, tira a voz do shop-tts, bloqueia novas gerações e **apaga de fato**
  os arquivos da pessoa (rosto, gravação, referência, candidatos e prova), deixando no histórico só o
  registro do consentimento e da revogação. Coberto pela emenda da constitution 4.2.0 → 4.3.0 (o
  princípio VII ganha 2 exceções nomeadas e auditadas: limpeza de candidatos de 90 dias e revogação
  LGPD), aplicada como 1ª tarefa da implementação da 021 (FR-033a).
- Q: Toda gravação conta como pessoa real? → A: **Sim.** Toda voz `gravacao` pede consentimento antes de
  gerar candidatos; se for a voz do próprio dono, ele registra o próprio (FR-024).
- Q: Quem registra o consentimento? → A: **Um humano, dono ou membro; nunca um cliente MCP** (FR-033).

### Session 2026-10-07

- Q: Na revogação, limpar também o texto que descreve a pessoa nas versões antigas do histórico? → A:
  **Sim.** O texto da exceção 2 da constitution 4.3.0 foi ajustado antes de ser aplicado: "os arquivos e
  os textos que descrevem a pessoa (inclusive em versões antigas do histórico) são apagados; o registro de
  que houve consentimento e revogação fica, sem a mídia nem a descrição" (FR-033a).
- Q: E as cenas (010) que usam o avatar revogado? → A: **Só listar** na confirmação, sem mexer nelas.
- Q: "Testar" a voz e os rostos 3/4 em par? → A: Resolvidos com a 021: passo `voz.teste` (estado final
  `entregue`) e opção em par (`image_par_id`).

## Contexto

A 007 guarda o que o usuário envia, como enviou. Os modelos locais (testados em
`../comfyui-docker/pipeline/PADROES.md`) só rendem bem com entradas num padrão fixo: rosto frontal
limpo, corpo-base neutro, referência de voz de 8–13 s cortada em fim de frase e cena 9:16 sem pessoas. E
o avatar ainda não tem voz.

Esta feature **estende** a 007 (já implementada) e **não reescreve** o que existe: os uploads livres de
referências por look, poses, imagem principal, tags, busca, "Onde é usado", arquivar/restaurar, histórico
e reversão continuam iguais. O que entra:

- no **avatar**: origem, consentimento, kit padrão por slots, checagem de identidade, situação do kit e a
  voz padrão; looks e poses passam a poder ser **gerados** a partir do kit;
- no **cenário**: a cena padrão 9:16 e as variações por rótulo;
- uma entidade nova, **voz** (do perfil).

Cada passo de geração é uma **geração** da spec **021-geracao-local** (entidades `geracoes`,
`geracao_candidatos` e `audios`, worker, fila da GPU, limpeza de 90 dias). Esta spec define **quais**
passos existem, em que ordem abrem e o que a escolha grava no avatar, na voz ou no cenário; o ciclo do job
(fila, progresso, falha, cancelar, "gerar outras") é o da 021.

Esta feature substitui, para avatar, voz e cenário, duas premissas da 007 ("geração por IA fica fora,
continua no Flow/Veo" e "vozes ficam fora"), por decisão do dono registrada nos insumos de 2026-10-06. A
geração de **vídeo** continua fora.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Kit padrão de um avatar sintético (Priority: P1)

O usuário cria um avatar e monta o kit passo a passo. Primeiro descreve a pessoa (sintética) e a IA local
gera **4** opções de **rosto de origem**; ele escolhe uma. Abre então o **rosto frontal** (2 opções), depois
os **rostos 3/4** (2 opções, cada uma um par esquerda + direita), depois o **corpo-base** (2 opções). Cada
passo só abre depois que o anterior foi escolhido. Com os slots escolhidos, roda sozinha a **checagem de
identidade**: a IA compara cada imagem do kit com a origem, dá uma nota de 0 a 10 por slot (só identidade,
não roupa, ângulo ou luz) com uma observação curta, e escreve a **descrição fixa para prompts** em inglês.
O kit fica **completo**, ou **atenção** se alguma nota ficou abaixo de 7, com o botão "Refazer este passo"
no slot fraco.

**Why this priority**: o kit é a base de tudo o que vem depois (looks, poses, storyboards, vídeo). Sem ele,
as gerações erram a identidade da persona.

**Independent Test**: com o ComfyUI e o Claude falsos, criar o avatar "Ana", pedir o rosto de origem, ver
4 opções, escolher a 2; seguir até o corpo-base escolhendo sempre uma opção; conferir os 5 slots ativos,
as notas por slot, a descrição para prompts preenchida e `kit_status = completo`; semear uma nota 6 e ver
`atencao` com "Refazer este passo" no slot certo.

**Acceptance Scenarios**:

1. **Given** um avatar novo sem kit, **When** o usuário abre a seção "Kit", **Then** só o passo "Rosto de
   origem" está disponível e os demais aparecem bloqueados com o motivo ("escolha o rosto de origem
   antes").
2. **Given** uma descrição da pessoa, **When** o usuário pede o rosto de origem, **Then** é criada uma
   geração de 4 opções e, ao terminar, ele vê as 4 lado a lado com "Usar opção N", "Gerar outras" e
   "Cancelar".
3. **Given** as opções de um passo, **When** o usuário escolhe uma, **Then** ela vira o arquivo do slot
   (`kit`), o asset ganha uma versão no histórico com a referência da geração, e o próximo passo abre.
4. **Given** o passo dos rostos 3/4, **When** as opções aparecem, **Then** cada opção mostra o par
   (esquerda e direita da imagem) e escolher uma opção preenche os dois slots `rosto_34_esq` e
   `rosto_34_dir`.
5. **Given** o corpo-base escolhido, **When** a checagem de identidade termina, **Then** o avatar mostra a
   nota e a observação de cada slot, a descrição para prompts aparece preenchida (editável) e a situação
   do kit vira `completo` (todas as notas ≥ 7) ou `atencao` (alguma < 7).
6. **Given** um kit em `atencao`, **When** o usuário clica em "Refazer este passo" num slot, **Then** uma
   nova geração daquele passo é pedida, e ao escolher a nova opção a checagem anterior é apagada e roda de
   novo.
7. **Given** uma descrição da pessoa com termo de menoridade (ex.: "teen", "criança", "16 years old"),
   **When** o usuário pede a geração, **Then** ela é recusada com "Menores de idade não são permitidos",
   sem criar job.
8. **Given** a GPU ocupada pelo OpenShorts, **When** o usuário pede um passo de imagem, **Then** o passo
   fica na fila com "Aguardando a GPU ficar livre" e começa sozinho quando a GPU libera (021).

---

### User Story 2 - Voz do perfil e voz padrão do avatar (Priority: P1)

O usuário cadastra uma voz no perfil de um de dois jeitos: **envia uma gravação** (wav, m4a, ogg ou mp3;
recomendado 15–30 s, 2–4 frases completas no tom de venda, com pausa entre elas) ou **descreve uma voz
sintética** em inglês (idade, energia, ritmo, papel). A gravação passa por uma **análise** que mostra
avisos em pt-BR (áudio comprimido do WhatsApp, taxa de amostragem baixa, ruído, clipping, duração curta)
sem bloquear. A IA local gera **até 3 candidatos** de referência (8–13 s, cortados no começo e no fim de
uma frase), cada um com um **áudio de teste** de 2 frases de venda. O usuário ouve, escolhe um, e a voz
fica **aprovada** e é **importada no shop-tts**. Depois ele pode **testar** a voz narrando um texto livre
e escolhê-la como **voz padrão** de um ou mais avatares.

**Why this priority**: o avatar ainda não tem voz; a narração dos vídeos depende de uma referência curta,
limpa e no tom certo, e hoje ela vive em pastas do pipeline.

**Independent Test**: com o shop-tts falso, enviar uma gravação comprimida e ver os avisos; receber 3
candidatos com duração, transcrição e teste; escolher o 2; conferir `aprovada`, a referência ligada, a
transcrição exata e a data de sincronização; testar com um texto livre; marcar a voz como padrão do
avatar "Ana" e ver, na voz, "Usada por: Ana".

**Acceptance Scenarios**:

1. **Given** um perfil, **When** o usuário cria uma voz com nome e tom (ex.: "vendas animada") e envia uma
   gravação, **Then** a voz sai de `rascunho` para `gerando`, e a análise aparece com codec, bitrate, taxa
   de amostragem, piso de ruído, SNR, clipping, duração e os avisos, sem bloquear o envio.
2. **Given** uma gravação acima de 25 MB ou fora de wav/m4a/ogg/mp3, **When** o usuário envia, **Then** é
   recusada com o motivo, e nada é gerado.
3. **Given** a geração terminou, **When** a voz entra em `revisao`, **Then** cada candidato mostra o número,
   a duração, a transcrição, a similaridade da retranscrição e o player do áudio de teste.
4. **Given** os candidatos, **When** o usuário escolhe um, **Then** a voz fica `aprovada` com a referência
   (mono, 24 kHz, -18 LUFS) e a transcrição exata gravadas, e a importação no shop-tts é feita; ao
   concluir, a voz mostra "Sincronizada em <data>".
5. **Given** uma voz sintética, **When** o usuário descreve a voz em inglês, **Then** a descrição é
   guardada, até 3 candidatos são gerados (sem limpeza de ruído) e o fluxo segue igual ao da gravação.
6. **Given** uma voz aprovada, **When** o usuário clica em "Testar" e escreve um texto, **Then** ouve a
   narração desse texto com a voz.
7. **Given** um avatar, **When** o usuário escolhe uma voz aprovada do mesmo perfil como voz padrão,
   **Then** o avatar mostra a voz padrão e a voz mostra o avatar em "Onde é usada".
8. **Given** uma voz aprovada, **When** o usuário pede para trocar a referência, **Then** a voz volta para
   `revisao` com os novos candidatos e, ao escolher, a referência nova substitui a anterior no SociMan e
   no shop-tts (a anterior fica no histórico).

---

### User Story 3 - Pessoa real com consentimento (Priority: P1)

O usuário quer um avatar a partir da **foto de uma pessoa real** (ou uma voz a partir da **gravação** de
uma pessoa real). Antes de qualquer geração, ele registra o **consentimento** dessa pessoa: nome, data,
quem registrou, observação e, opcionalmente, a prova (uma imagem ou um áudio). Sem esse registro, o
SociMan não deixa usar a foto como rosto de origem nem gerar candidatos da gravação. Menores de idade e
pessoas famosas são proibidos.

**Why this priority**: imagem e voz de pessoa real são dado pessoal (LGPD) e direito de personalidade; o
princípio II põe a responsabilidade no dono, mas o sistema não pode deixar o uso passar sem rastro.

**Independent Test**: tentar usar uma foto como origem `pessoa_real` sem consentimento e ver a recusa;
registrar o consentimento com uma imagem de prova; usar a foto como rosto de origem (sem gerar opções) e
seguir para o rosto frontal; conferir no histórico quem registrou e quando.

**Acceptance Scenarios**:

1. **Given** um avatar, **When** o usuário escolhe a origem "Pessoa real" e envia a foto sem registrar o
   consentimento, **Then** é recusado com "Registre o consentimento da pessoa antes de usar a foto".
2. **Given** o consentimento registrado, **When** o usuário envia a foto, **Then** ela vira o slot
   `rosto_origem` direto (sem 4 opções) e o passo do rosto frontal abre.
3. **Given** o formulário de consentimento, **When** ele abre, **Then** avisa que menores de idade e
   pessoas famosas não são permitidos e que registrar o consentimento é responsabilidade de quem registra.
4. **Given** uma voz do tipo gravação, **When** o usuário tenta gerar os candidatos sem consentimento,
   **Then** é recusado com o mesmo aviso.
5. **Given** uma imagem enviada que **não** é de pessoa real (feita em outra ferramenta), **When** o
   usuário escolhe a origem "Upload", **Then** ela vira o rosto de origem sem pedir consentimento.

---

### User Story 4 - Looks e poses gerados a partir do kit (Priority: P2)

Com o kit pronto, o usuário pede um **look** (rótulo e descrição da roupa toda) ou uma **pose** (rótulo,
"quando usar" e a descrição da roupa vestida). A IA local gera **2** opções a partir do corpo-base (ou de
uma pose existente), usando o rosto frontal como referência de identidade e mantendo fundo,
enquadramento e postura. O usuário escolhe uma, que entra no avatar como referência daquele look ou como
pose, igual às enviadas à mão na 007.

**Why this priority**: looks e poses consistentes são o que os vídeos usam no dia a dia; dependem do kit
(US1).

**Independent Test**: com o kit semeado, pedir o look "Cozinha" com a descrição da roupa, escolher a
opção 1 e ver a imagem no grupo do look "Cozinha"; pedir a pose "apontando para o produto" a partir do
corpo-base e vê-la na grade de poses, com a origem "gerada" e o link para a geração.

**Acceptance Scenarios**:

1. **Given** um avatar sem corpo-base ou sem rosto frontal, **When** o usuário abre "Gerar look" ou "Gerar
   pose", **Then** a ação aparece bloqueada com "Monte o kit até o corpo-base antes".
2. **Given** o kit, **When** o usuário pede um look com rótulo e descrição, **Then** 2 opções são geradas e
   a escolhida vira um arquivo `referencia` com aquele `look`.
3. **Given** o kit, **When** o usuário pede uma pose com rótulo já usado por outra pose ativa, **Then** é
   recusado antes de gerar ("Já existe uma pose com esse rótulo neste avatar").
4. **Given** uma pose existente, **When** o usuário pede um look ou pose partindo dela, **Then** a geração
   usa a pose como base, e o rosto frontal continua como referência.
5. **Given** um look ou pose gerado, **When** o usuário abre o arquivo, **Then** vê de qual geração ele veio
   (instrução e opção); arquivos enviados à mão aparecem como "enviado".

---

### User Story 5 - Cenário padrão e variações (Priority: P2)

O usuário cria um cenário a partir de uma **foto** enviada ou de um **prompt** do ambiente. A IA local
gera **2** opções de **cena** 9:16 (768×1344), **sem pessoas**, com área livre para o produto; o usuário
escolhe uma. Depois pede **variações** por rótulo ("noite", "outro ângulo"), derivadas da cena aprovada,
cada uma com 2 opções.

**Why this priority**: cenários se repetem entre vídeos; o padrão evita que cada geração invente um
ambiente diferente.

**Independent Test**: criar o cenário "Cozinha retrô" pelo prompt, escolher uma das 2 cenas e ver o slot
`cena` e `kit_status = completo`; pedir a variação "noite", escolher e vê-la na lista de variações; tentar
outra variação "Noite" e ver a recusa de rótulo repetido.

**Acceptance Scenarios**:

1. **Given** um cenário novo, **When** o usuário pede a cena pelo prompt ou por uma foto, **Then** 2 opções
   9:16 de 768×1344 são geradas e a escolhida vira o slot `cena`, com a situação `completo`.
2. **Given** um cenário sem cena escolhida, **When** o usuário abre "Variações", **Then** a ação aparece
   bloqueada até a cena ser escolhida.
3. **Given** a cena, **When** o usuário pede uma variação com rótulo, **Then** 2 opções são geradas a partir
   da cena e a escolhida vira um arquivo `variacao` com aquele rótulo.
4. **Given** uma variação ativa "noite", **When** o usuário pede outra com o rótulo "Noite", **Then** é
   recusado antes de gerar (rótulo repetido, sem diferença de caixa).

---

### User Story 6 - Trocar um slot e manter o kit coerente (Priority: P3)

O usuário troca uma imagem do kit (refazendo o passo ou enviando outra no lugar). O SociMan arquiva o
arquivo antigo do slot, apaga a checagem de identidade (que não vale mais) e pede uma nova checagem. A
troca fica no histórico e pode ser revertida pelo dono, como qualquer mudança da 007.

**Why this priority**: mantém a regra "kit checado = kit confiável", mas é manutenção, depois que o fluxo
principal existe.

**Independent Test**: com o kit completo, refazer o `rosto_34_esq`, escolher uma opção nova; conferir o
arquivo antigo arquivado, a checagem apagada, uma nova checagem pedida e as duas versões no histórico.

**Acceptance Scenarios**:

1. **Given** um kit `completo`, **When** o usuário troca qualquer slot, **Then** o arquivo antigo do slot é
   arquivado (nunca apagado), a `identidade` é apagada, a situação volta a `incompleto` e uma nova
   checagem é pedida.
2. **Given** a troca do `rosto_origem` ou do `rosto_frontal`, **When** ela é salva, **Then** o SociMan avisa
   que os slots derivados (e os looks e poses gerados depois) foram feitos a partir da imagem anterior, sem
   apagá-los nem regerá-los sozinho.
3. **Given** uma troca de slot, **When** o dono reverte o asset para a versão anterior, **Then** o arquivo
   antigo volta a ser o do slot e a checagem gravada naquela versão volta junto.

---

### Edge Cases

- **Avatar da 007 sem kit:** avatares criados antes desta feature continuam funcionando como hoje
  (uploads livres); a situação do kit aparece como "sem kit padrão" e o usuário pode começar o kit quando
  quiser, sem perder looks e poses existentes.
- **Passo pedido de novo com um job do mesmo passo em andamento:** recusado com "Já existe uma geração
  deste passo em andamento" (cancelar ou esperar).
- **"Gerar outras" num passo:** a geração anterior vira `descartada` (021); as opções antigas deixam de ser
  escolhíveis e entram na limpeza de 90 dias.
- **Geração falhou ou foi cancelada:** o slot continua como estava (vazio ou com o arquivo anterior), a voz
  volta ao estado de antes do pedido (`rascunho` ou `revisao`) e o erro aparece em pt-BR com "Tentar de
  novo" (021).
- **Checagem de identidade falhou** (Claude fora): o kit fica `incompleto` com "Checagem pendente" e o
  botão "Checar de novo"; os slots escolhidos não se perdem.
- **Descrição para prompts editada à mão e depois uma nova checagem:** a nova checagem reescreve o
  campo (é passo de texto, vai direto); o texto anterior fica no histórico e pode ser restaurado.
- **Gravação sem fala** ou sem trecho de 8–13 s que comece e termine numa frase: o SociMan relaxa para
  6–15 s e avisa; sem fala nenhuma, a geração falha com "Não encontrei fala na gravação".
- **shop-tts fora ao aprovar a voz:** a voz fica `aprovada` no SociMan com "Não sincronizada" e a
  sincronização é tentada de novo; o "Testar" fica indisponível até sincronizar.
- **Voz arquivada que é padrão de um avatar:** o avatar mostra "Voz padrão arquivada" e o usuário escolhe
  outra; arquivar não é bloqueado (como na 007, só o kit de marca bloqueia).
- **Voz padrão de outro perfil:** recusada (a voz padrão precisa ser do mesmo perfil do avatar).
- **Nome de voz repetido** entre as vozes ativas do perfil: recusado; uma voz arquivada libera o nome.
- **HD indisponível ou sem espaço:** pedidos de geração, uploads e downloads recusam com a mensagem de
  armazenamento (004); leitura continua.
- **Candidato com mais de 90 dias:** some da tela da geração antiga com "Opções expiradas"; o escolhido e o
  arquivo do slot continuam.
- **Cliente MCP:** só lê (vozes, kit, notas, situação); não pede geração, não escolhe candidato, não
  registra consentimento (FR-023 da 009 mantido).

## Requirements *(mandatory)*

### Functional Requirements

**Transversais**

- **FR-001**: Esta feature DEVE estender a biblioteca da 007 sem remover nada: uploads livres, looks,
  poses, imagem principal, tags, busca, "Onde é usado", arquivar/restaurar, histórico e reversão
  continuam como estão.
- **FR-002**: Todo passo de geração desta feature DEVE ser uma geração da 021, com o `passo`
  correspondente (`avatar.rosto_origem`, `avatar.rosto_frontal`, `avatar.rostos_34`, `avatar.corpo_base`,
  `avatar.look`, `avatar.pose`, `avatar.identidade`, `voz.gravacao`, `voz.design`, `voz.teste`,
  `cenario.cena`, `cenario.variacao`) e o número de opções do insumo: rosto de origem 4; voz até 3;
  `voz.teste` 1 (sem escolha, só para ouvir); os demais 2.
- **FR-003**: Toda escolha de candidato DEVE ser feita por um humano; o único passo que grava sem escolha
  é a checagem de identidade (`avatar.identidade`, só texto), cujo resultado vai direto para o avatar e
  continua editável.
- **FR-004**: Escolher um candidato DEVE gravar o resultado no alvo (arquivo do slot, look, pose,
  variação, ou a referência da voz) e uma nova versão do alvo no histórico com a referência da geração,
  na mesma transação (princípio VII).
- **FR-005**: Pedidos de geração com termo de menoridade na descrição ou na instrução (lista fixa em
  código, em pt-BR e inglês, como no pipeline) DEVEM ser recusados antes de criar o job, com "Menores de
  idade não são permitidos".
- **FR-006**: Nenhuma ação desta feature publica, agenda ou envia conteúdo a rede social (princípio I).
- **FR-007**: Clientes MCP DEVEM poder só ler o que esta feature cria (vozes, kit, notas, situação,
  consentimento registrado sem a prova); pedir geração, escolher candidato, registrar consentimento e
  editar continuam proibidos a eles (FR-023 da 009).

**Avatar: origem, consentimento e kit (US1, US3, US6)**

- **FR-008**: O avatar DEVE ter uma **origem**: `upload` (imagem enviada que não é de pessoa real),
  `sintetico` (rosto de origem gerado no SociMan) ou `pessoa_real`. Avatares anteriores a esta feature
  ficam sem origem.
- **FR-009**: Origem `pessoa_real` DEVE exigir **consentimento** registrado antes de usar a foto: nome da
  pessoa, data, quem registrou, observação e, opcionalmente, a prova (imagem ou áudio). O registro DEVE
  ficar no histórico com o autor.
- **FR-010**: O kit do avatar DEVE ter 5 slots: `rosto_origem`, `rosto_frontal`, `rosto_34_esq`,
  `rosto_34_dir` e `corpo_base`, cada um com no máximo **um** arquivo ativo; trocar um slot DEVE arquivar
  o arquivo anterior.
- **FR-011**: Os passos DEVEM abrir em ordem: rosto de origem (4 opções geradas, ou upload, ou foto de
  pessoa real com consentimento) → rosto frontal (2) → rostos 3/4 (2 opções, cada uma um par esquerda +
  direita que preenche os dois slots) → corpo-base (2) → checagem de identidade. Um passo só abre com o
  anterior escolhido.
- **FR-012**: Os slots DEVEM seguir o padrão do pipeline: fundo cinza-claro liso, luz de estúdio suave e
  uniforme, camiseta cinza-clara lisa; rosto frontal com cabeça, ombros e alto do peito, de frente,
  olhando para a lente, expressão neutra com sorriso leve; rostos 3/4 virados para a esquerda e a direita
  da imagem, gerados do frontal; corpo-base 9:16, da cabeça aos pés com margem, em pé, braços ao lado do
  corpo, mãos vazias, camiseta cinza-clara justa, legging cinza-escura e tênis branco liso.
- **FR-013**: Com os slots escolhidos, a **checagem de identidade** DEVE rodar sozinha: uma chamada ao
  Claude compara cada slot com a origem e grava, por slot, uma **nota de 0 a 10 só de identidade** e uma
  observação curta, com o modelo e a data; na mesma chamada, escreve a **descrição fixa para prompts** do
  avatar (`prompt`, em inglês, 40–80 palavras: faixa de idade adulta, tom de pele, rosto, olhos,
  sobrancelhas, nariz, lábios, cabelo, porte e traços marcantes; sem roupa, pose ou fundo). A chamada
  entra no registro de chamadas da 008.
- **FR-014**: A **situação do kit** DEVE ser `incompleto` (falta slot ou checagem), `completo` (todos os
  slots e a checagem com todas as notas ≥ 7) ou `atencao` (alguma nota < 7). Em `atencao`, o slot com
  nota baixa DEVE mostrar "Refazer este passo".
- **FR-015**: Trocar **qualquer** slot do kit DEVE apagar a checagem de identidade, voltar a situação para
  `incompleto` e pedir uma nova checagem.
- **FR-016**: A descrição para prompts DEVE continuar editável pelo usuário. Ela **não** DEVE entrar nas
  instruções de edição de imagem desta feature (rosto frontal, 3/4, corpo-base, looks, poses), porque faz
  o modelo dar zoom no rosto e cortar o corpo; ela serve à geração do zero, ao vídeo e à cópia.

**Looks e poses gerados (US4)**

- **FR-017**: O usuário DEVE poder pedir um **look** (rótulo do look e descrição da roupa toda) ou uma
  **pose** (rótulo, "quando usar" e descrição da roupa vestida), com 2 opções geradas a partir do
  corpo-base ou de uma pose existente, com o rosto frontal como referência, mantendo fundo, enquadramento
  e postura.
- **FR-018**: Pedir look ou pose DEVE exigir `corpo_base` e `rosto_frontal` ativos. O rótulo de pose DEVE
  seguir a unicidade da 007 e ser conferido antes de gerar.
- **FR-019**: A opção escolhida DEVE entrar como arquivo `referencia` com o `look`, ou `pose` com o rótulo,
  como os enviados à mão, e guardar de qual geração veio (sem geração = enviado).

**Vozes do perfil (US2, US3)**

- **FR-020**: Cada perfil DEVE ter vozes com: nome (1..60, único entre as ativas do perfil), origem
  (`gravacao` ou `sintetica`), tom (ex.: "vendas animada"), descrição em inglês (só sintética), gravação
  original (só gravação; ver FR-024), referência aprovada, transcrição exata da referência, análise,
  consentimento, situação e data da última sincronização com o shop-tts. Voz é arquivada e restaurada,
  nunca apagada, com histórico e reversão pelo dono.
- **FR-021**: A gravação DEVE aceitar wav, m4a, ogg e mp3 até 25 MB (021). A **análise** DEVE mostrar
  codec, bitrate, taxa de amostragem, piso de ruído, SNR, clipping e duração, com avisos em pt-BR (áudio
  comprimido abaixo de 64 kb/s: "regrave pelo gravador"; taxa < 22 kHz; piso > -50 dBFS ou SNR < 25 dB;
  clipping > 0,05% das amostras; duração < 8 s), **sem bloquear**.
- **FR-022**: A geração DEVE produzir até 3 candidatos de referência: mono 24 kHz, -18 LUFS (gravação com
  limpeza de ruído suave; sintética sem ela), trecho de **8 a 13 s** que começa no início e termina no fim
  de uma frase (relaxa para 6–15 s com aviso), cada um com a transcrição, a similaridade da retranscrição
  e um áudio de teste de 2 frases de venda.
- **FR-023**: Escolher um candidato DEVE deixar a voz `aprovada`, gravar a referência e a transcrição e
  **importar** a voz no shop-tts, registrando a data da sincronização; falha na importação DEVE deixar a
  voz aprovada e "Não sincronizada", com nova tentativa.
- **FR-024**: Toda voz de origem `gravacao` é de pessoa real e DEVE exigir consentimento registrado
  (mesma forma do avatar) antes de gerar candidatos; se for a voz do próprio dono, ele registra o próprio.
  A **gravação original completa** DEVE ser guardada (nunca entra na limpeza de 90 dias), para refazer a
  referência sem nova gravação e como prova do que a pessoa consentiu; só a revogação (FR-033a) a apaga.
- **FR-025**: "Testar" DEVE narrar um texto livre com a voz aprovada e sincronizada, para o usuário ouvir.
- **FR-026**: "Trocar referência" DEVE levar a voz aprovada de volta a `revisao` com novos candidatos; até
  a escolha, a referência anterior continua valendo no shop-tts; ao escolher, a nova substitui a anterior
  (que fica no histórico).
- **FR-027**: O avatar DEVE poder apontar uma **voz padrão** do mesmo perfil, só entre vozes aprovadas; a
  voz DEVE mostrar em "Onde é usada" os avatares que a têm como padrão (origem `voz`), sem bloquear o
  arquivamento.

**Cenário (US5)**

- **FR-028**: O cenário DEVE ter o slot `cena`: 9:16, 768×1344, sem pessoas, com área livre para produto,
  gerado com 2 opções a partir de uma foto enviada ou do prompt do ambiente.
- **FR-029**: Com a cena escolhida, o usuário DEVE poder pedir **variações** por rótulo (obrigatório,
  único entre as variações ativas do cenário sem diferença de caixa), com 2 opções derivadas da cena.
- **FR-030**: A situação do kit do cenário DEVE ser `incompleto` sem a cena e `completo` com ela.

**Telas e permissões**

- **FR-031**: O detalhe do avatar DEVE ganhar a seção "Kit" (passos em ordem, slots, notas, situação,
  "Refazer este passo"), "Origem e consentimento" e "Voz padrão"; o cenário ganha "Cena" e "Variações";
  o perfil ganha a lista de **Vozes** com o detalhe de cada voz (análise, candidatos, teste, uso,
  histórico).
- **FR-032**: Cada passo em andamento DEVE mostrar o progresso e a mensagem da 021 ("Gerando opção 2 de
  2", "Aguardando a GPU ficar livre"), com "Cancelar".
- **FR-033**: Registrar consentimento e escolher origem `pessoa_real` DEVEM ser atos de um humano, dono
  ou membro; um cliente MCP DEVE ser recusado. O registro grava o autor no histórico.
- **FR-033a**: "Revogar consentimento" DEVE existir só para o dono humano, no avatar `pessoa_real` e na
  voz `gravacao`, com confirmação explícita. Revogar DEVE, na mesma operação auditada: arquivar o avatar
  ou a voz; tirar a voz do shop-tts; bloquear novas gerações, restauração e reversão para versões com os
  arquivos; e **apagar de fato** os arquivos da pessoa (foto de origem e slots derivados dela, gravação
  original, referência, candidatos, áudios de teste e prova) **e os textos que descrevem a pessoa**
  (descrição para prompts, checagem de identidade, transcrição da referência e as instruções das gerações
  e chamadas de IA do alvo), inclusive nas **versões antigas do histórico**. O histórico DEVE manter só o
  registro de que houve consentimento (nome, data, quem registrou) e a revogação (quem, quando), sem a
  mídia nem a descrição. A confirmação DEVE listar as cenas (010) que usam o avatar, sem alterá-las.
  É uma das 2 exceções nomeadas do princípio VII na constitution 4.3.0 (a outra é a limpeza de 90 dias
  da 021).
- **FR-034**: As demais ações (pedir geração, escolher candidato, editar, arquivar) seguem as permissões
  da 007: dono e membro; reverter, só dono.

### Key Entities

- **Asset (da 007), novos atributos — só avatar:** origem (`upload`, `sintetico`, `pessoa_real`),
  consentimento (nome, data, registrado por, observação, prova opcional), voz padrão, identidade (modelo,
  data, nota 0–10 e observação por slot; apagada quando um slot muda) e situação do kit (`incompleto`,
  `completo`, `atencao`). **Avatar e cenário:** situação do kit. A descrição para prompts (`prompt`, já
  existente) passa a ser preenchida pela checagem e continua editável.
- **Arquivo do asset (da 007), novos atributos:** papéis `kit` (com o **slot**: avatar `rosto_origem`,
  `rosto_frontal`, `rosto_34_esq`, `rosto_34_dir`, `corpo_base`; cenário `cena`) e `variacao` (cenário,
  com rótulo obrigatório); e a geração de onde o arquivo veio (vazio = enviado).
- **Voz (nova, do perfil):** nome, origem (`gravacao`, `sintetica`), descrição (sintética), tom, gravação
  original, referência aprovada, transcrição da referência, análise (codec, bitrate, taxa, piso de ruído,
  SNR, clipping, duração, avisos), consentimento, situação (`rascunho`, `gerando`, `revisao`, `aprovada`),
  data de sincronização com o shop-tts, versão, arquivamento e autoria.
- **Geração, candidato e áudio (da 021):** o job de cada passo, as opções e os arquivos de som; esta
  feature só os usa.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Montar o kit completo de um avatar sintético exige no máximo 5 decisões humanas (4 escolhas
  e a descrição inicial), e o tempo de interação (fora a espera da GPU) fica abaixo de 5 minutos.
- **SC-002**: 100% dos arquivos de kit, looks, poses, variações e referências de voz gerados chegam ao
  alvo por uma escolha humana registrada no histórico; zero escolhas automáticas fora da checagem de
  identidade.
- **SC-003**: Zero avatares com origem `pessoa_real` e zero vozes de gravação com candidatos gerados sem
  consentimento registrado (verificado por teste no backend).
- **SC-004**: 100% das trocas de slot apagam a checagem de identidade e voltam a situação para
  `incompleto`.
- **SC-005**: 100% das referências de voz aprovadas têm entre 8 e 13 s (ou entre 6 e 15 s com o aviso
  registrado), mono 24 kHz, e transcrição gravada.
- **SC-006**: 100% dos pedidos com termo de menoridade são recusados sem criar job.
- **SC-007**: Os avatares, cenários, looks e poses da 007 continuam abrindo, editando e sendo usados no
  kit de marca e nas cenas (010) sem mudança visível depois da migração.

## Assumptions

- **Depende da 021-geracao-local** (job, candidatos, áudios, worker, fila da GPU, RAM do ComfyUI,
  backoff, limpeza de 90 dias, mudança de contrato do shop-tts para enviar e receber arquivos e importar
  voz aprovada). Esta feature não implementa nada disso.
- **Mesmo perfil:** avatar, voz, cenário, gerações e áudios de um perfil só se referenciam dentro dele.
- **Pessoa famosa:** não há detecção automática; a proibição é aviso no formulário e responsabilidade de
  quem registra (como no pipeline). Menores têm a recusa por termos (FR-005), que não pega uma foto real de
  menor: essa também fica na responsabilidade de quem registra o consentimento.
- **Voz sintética** não tem problema de direito de uso e não pede consentimento (a gravação sempre pede,
  FR-024).
- **Constitution 4.3.0:** a emenda que nomeia as 2 exceções do princípio VII é a 1ª tarefa da
  implementação da 021; esta feature depende dela para o FR-033a.
- **Upload sem pessoa real** (origem `upload`) é declaração de quem envia; o SociMan não verifica.
- **Tom de voz do avatar (007)** (`voice_tone`, texto para roteiro e IA) continua; o **tom da voz** é o
  rótulo da referência gravada ou sintética. São campos diferentes.
- **Fora do escopo:** LoRA por avatar; vídeo do avatar (motor de cenas); edição manual de áudio; troca da
  voz por vídeo (usa a voz padrão como ponto de partida, numa spec futura); produto (012).

## Notas para o plano

Detalhe técnico do insumo que a spec não precisa expor, para o `/speckit-plan` não perder nada:

- **`assets`, colunas novas:** `origem` enum `asset_origem` (`upload`, `sintetico`, `pessoa_real`) null,
  só `avatar`; `consentimento` jsonb null (`{nome, data, registrado_por, observacao, audio_id|image_id da
  prova opcional}`); `voz_id` uuid null FK → `vozes`, só `avatar`; `identidade` jsonb null, só `avatar`
  (`{modelo, data, notas: {<slot>: {nota 0..10, observacao}}}`); `kit_status` enum (`incompleto`,
  `completo`, `atencao`) null, só `avatar`/`cenario`. Estender `ck_assets_campos_por_tipo` e os
  `__versioned_fields__` (as colunas novas e o `slot`/`geracao_id` no snapshot `files`).
- **`asset_files`:** `asset_file_role` ganha `kit` e `variacao`; coluna `slot` text null, obrigatória em
  `kit`, com a lista por tipo; UNIQUE parcial `(asset_id, slot) WHERE role='kit' AND archived_at IS NULL`;
  `variacao` com `label` obrigatório e o mesmo UNIQUE de rótulo das poses (`lower(label)`, ativo); coluna
  `geracao_id` uuid null FK → `geracoes`. Ajustar `ck_asset_files_campos_por_papel` e o
  `_ROLE_ORDER`/`sorted_files`.
- **`vozes`:** `id`, `perfil_id`, `name` (1..60, único por perfil entre as ativas), `origem`
  (`gravacao`, `sintetica`), `descricao` null, `tom`, `gravacao_audio_id` null FK → `audios`,
  `ref_audio_id` null FK → `audios`, `ref_texto` null, `analise` jsonb null (codec, bitrate, sample rate,
  piso de ruído, SNR, clipping, duração, `avisos[]`), `consentimento` jsonb null, `status`
  (`rascunho`, `gerando`, `revisao`, `aprovada`), `sincronizada_em` timestamptz null, `version`,
  `archived_*`, AuditMixin; histórico `entity_type = "voz"`.
- **Estados (insumo):**
  ```
  avatar.kit_status: incompleto ──último slot escolhido──▶ completo | atencao ──refazer──▶ incompleto
  voz: rascunho ──enviar/descrever──▶ gerando ──▶ revisao ──escolher──▶ aprovada ──trocar referência──▶ revisao
  ```
- **Uso:** "Onde é usado" ganha `origem: "voz"`. Os provedores atuais de `assets/usos.py` são indexados
  por **imagem** (`UsoImagem` por `image_id`); o uso de uma voz é por entidade, então precisa de um
  provedor/rota próprio na voz.
- **Pontos que o plano resolveu** (ver plan.md, "Contradições resolvidas no plano"):
  1. `rostos_34` é **um** passo com opções em **par** (esquerda + direita), mas o check da 021 exige
     exatamente um `image_id` por candidato: decidir entre dois candidatos por opção (`numero` + lado) ou
     duas imagens por candidato.
  2. O nome da voz é texto livre de 1..60, mas o shop-tts só aceita `[a-z0-9_]{2,40}` e chama a voz pelo
     nome: o identificador no shop-tts deve ser derivado e estável (ex.: do `id`), não o `name`, senão
     renomear quebraria a voz importada.
  3. "Testar" a voz não tem `passo` na lista da 021 (`voz.teste`?); decidir se é geração com 1 resultado
     sem escolha (e entra na limpeza) ou chamada direta sem registro.
  4. A 003/007 dizem que `images` é imutável e **nunca apagada**, e o `storage.py` não tem delete; a
     limpeza de 90 dias da 021 (candidatos) e a revogação (FR-033a) apagam de fato: as 2 exceções
     nomeadas do princípio VII (constitution 4.3.0); o plano define o delete restrito no `storage.py`
     só para esses dois caminhos, com auditoria, e como o snapshot do histórico deixa de apontar
     para os arquivos apagados.
  5. A checagem grava a `prompt` direto (passo de texto), enquanto o assistente da 008 só aplica por
     clique; registrar a origem no histórico (`details.geracao_id`) e aplicar as proibidas do guia (017,
     `usa_guia = so_proibidas` em `avatar.descricao_prompt`) também nesse caminho.
  6. A 007 guarda `prompt` "exatamente como enviado"; a escrita pela checagem deve manter isso.
  7. `images.kind` do cenário é `fundo` (mínimo 540×540): a cena de 768×1344 cabe; confirmar o `kind`
     das variações e das imagens de kit do avatar (`avatar`).
- **Referência técnica:** `../comfyui-docker/pipeline/PADROES.md`, `pipeline/avatares.py` (instruções
  do kit, `NOTA_MINIMA = 7`, regex `PROIBIDO`), `pipeline/voz.py` e `tts_service/app.py` (`_analyze`,
  janela 8–13 s, testes de 2 frases, `/voices/approve` com `substituir`). Só leitura.

## Correção do dono (2026-10-09): menu AI Studio
- O dono pediu uma entrada própria para montar vídeos, sem passar pela página do perfil: o item **AI Studio** no menu (`/app/estudio`, logo abaixo de Perfis). Nele se escolhe o **perfil do vídeo** (`?perfil=`, lembrado no aparelho; com um perfil só, ele já vem escolhido) e as abas seguem a ordem de montar o vídeo: 1. Avatares e cenários (kit padrão), 2. Produtos (012), 3. Vozes, 4. Cenas (010). As abas são as mesmas telas da página do perfil (sem cópia); trocar de aba ou de perfil limpa os filtros. Nada muda na API.
