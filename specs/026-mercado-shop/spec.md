# Feature Specification: Cockpit do TikTok Shop coletado pelo SociMan (026-mercado-shop)

**Feature Branch**: `026-mercado-shop`

**Created**: 2026-10-08

**Status**: Draft

**Input**: User description: "Cockpit do TikTok Shop coletado pelo próprio SociMan (insumo
`docs/insumos/026-mercado-shop.md`; registro de risco `docs/decisoes/coleta-mercado.md`; constitution 4.4.0,
princípio IX). Um serviço coletor no desktop do dono navega como pessoa no Chrome real, logado na conta de
afiliado do dono, e devolve por uma API de ingestão tudo o que as páginas do TikTok Shop expõem: produtos
(ficha completa e fotos diárias), lojas, categorias, rankings, avaliações e vídeos top. O SociMan guarda um
lago global e permanente, calcula na leitura vendas/dia, GMV estimado, crescimento, 'novo em alta' e 'alto
retorno com poucos afiliados', e mostra tudo em `/app/mercado`. Perfis só registram interesse. Fora do
escopo (027 e 028): vídeos por assunto, cruzamento com o YouTube, recomendações da IA, alertas, mineração de
avaliações e multi-tenant."

## Contexto

O SociMan já cuida das contas, do kit de marca, dos cortes, dos conteúdos, da publicação, das métricas das
próprias contas, do analytics, do aprendizado e da geração local. O que falta é a **inteligência de
mercado**: saber o que vende no TikTok Shop (quanto, em que ritmo, o que está subindo, o que paga bem e tem
poucos afiliados), por categoria do nicho de cada perfil, para decidir o que gravar. Hoje isso é manual: o
dono cola um JSON de produtos e o agente `shop-analista` busca no YouTube e na web, "sem números de venda".

Não existe API oficial de mercado do TikTok Shop, e as ferramentas pagas (Kalodata, FastMoss, EchoTik)
vivem de coleta em escala. Em 2026-10-08 o dono decidiu coletar por conta própria, em **ritmo humano** e no
**recorte do nicho** (algumas centenas de produtos acompanhados), com a **conta de afiliado dele**, ciente de
que a rede pode restringir essa conta. A constitution 4.4.0 (princípio IX) fixa as regras: só leitura,
serviço separado no desktop, ritmo ditado pelo servidor, aceite de risco registrado, terceiros só por
identificador público, lago permanente e neutro, tudo derivado marcado como estimado.

Esta spec entrega, numa sequência de três (026 → 027 virais → 028 IA e alertas), a base:
- **o coletor**: o robô no desktop do dono, que pega uma fila do servidor, navega como pessoa e devolve o
  que viu, com o bruto;
- **a ingestão**: a porta por onde o dado entra, com token próprio, idempotente, que grava fichas, fotos,
  imagens e bruto;
- **o lago**: produtos, lojas, categorias, rankings, avaliações e vídeos top, globais e permanentes;
- **o interesse**: o que cada perfil acompanha e em que categorias;
- **a leitura**: o cartão do produto (vendas, GMV, crescimento, comissão, retorno por afiliado), os rankings,
  as lojas e o cockpit em `/app/mercado`;
- **a ponte com o catálogo** (012): "Adotar do mercado" cria o produto do perfil a partir da ficha coletada.

## Clarifications

### Session 2026-10-08

- Q: As fotos que os clientes anexam às avaliações públicas devem ser guardadas no lago, ou só o texto, a
  nota e a data? → A: Guardar as fotos originais como vêm; o risco LGPD dessas imagens de terceiros é
  assumido pelo dono e registrado em `docs/decisoes/coleta-mercado.md`.
- Q: Quando a fila do dia tem mais tarefas do que o teto de páginas, como o orçamento é dividido entre os
  perfis? → A: Revezamento entre perfis dentro de cada nível de prioridade (um item de cada perfil por vez);
  um produto de interesse de vários perfis conta uma vez só e entra pelo perfil cuja vez chegar primeiro.
- Q: Com que frequência e em que volume o coletor deve visitar as avaliações e os vídeos top de um
  produto? → A: Só para produtos quentes: avaliações na primeira visita (até 2 páginas) e depois a cada 30
  dias; vídeos top a cada 7 dias (1 página). Produtos em cadência semanal ou parada não têm essas visitas.
- Q: Quem pode pausar ou encerrar um acompanhamento automático e seguir ou deixar de seguir uma loja: qualquer
  humano ou só o dono? → A: Qualquer humano (dono ou membro) cria, pausa, encerra e segue ou deixa de seguir;
  a reversão pelo histórico é só do dono; cliente MCP e agente só leem.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver o cartão do produto no cockpit (Priority: P1)

O dono abre `/app/mercado` e vê, para cada produto acompanhado, o cartão mínimo: preço, comissão, comissão
por venda, loja (com o selo "Loja oficial"), vendas no período, GMV no período, crescimento contra o período
anterior, vendas totais, GMV total e a projeção de lucro para 10, 100 e 1.000 vendas. Pode filtrar por
período, perfil, categoria, loja e origem do interesse, ordenar por qualquer número e abrir o detalhe. Tudo
que é derivado vem marcado como **estimado**; produto com menos de duas fotos aparece como "coletando", e
com menos de uma semana de fotos como "amostra pequena".

**Why this priority**: É o valor da spec. Sem o cartão, a coleta é só armazenamento.

**Independent Test**: Com um "coletor falso" que envia, pela API de ingestão, fotos sintéticas de 3 produtos
em 10 dias (um subindo, um estável, um sem comissão), a tela mostra os três cartões com os números
esperados, o estado correto e o selo "estimado"; o CSV de cada card contém as mesmas linhas da tabela.

**Acceptance Scenarios**:

1. **Given** um produto com fotos diárias de "vendidos" e preço nos últimos 10 dias, **When** o dono abre o
   cockpit com o período de 7 dias, **Then** o cartão mostra vendas no período (diferença entre a última foto
   do período e a última anterior a ele), GMV no período (soma dos deltas diários vezes o preço do dia),
   crescimento contra os 7 dias anteriores, vendas totais e GMV total, todos com o selo "estimado".
2. **Given** um produto com só uma foto, **When** o dono abre o cockpit, **Then** o cartão mostra
   "coletando" no lugar dos números de período, e o preço, a loja e a comissão continuam visíveis.
3. **Given** um produto com fotos do Affiliate Center (comissão e nº de criadores), **When** o dono vê o
   cartão, **Then** a comissão por venda é o preço vezes a comissão, e a projeção de lucro para 10, 100 e
   1.000 vendas é a comissão por venda vezes cada quantidade.
4. **Given** um produto sem nenhuma foto do Affiliate Center, **When** o dono vê o cartão, **Then** comissão,
   comissão por venda, retorno por afiliado e projeção aparecem como "sem dado de afiliado", sem erro.
5. **Given** fotos em que "vendidos" diminuiu de um dia para o outro, **When** o cockpit calcula, **Then** o
   delta é tratado como zero, o cartão marca "inconsistente" e nada quebra.
6. **Given** o cockpit aberto, **When** o dono clica em "Ver tabela" ou "CSV" de um card, **Then** a tabela
   e o arquivo trazem exatamente os dados do card, com a data da última foto e o estado de cada produto.
7. **Given** um membro autenticado, **When** abre o cockpit, **Then** vê os mesmos cartões e números do dono
   (inclusive comissão e retorno), mas não vê as ações só de dono.

---

### User Story 2 - O coletor navega como pessoa e devolve o que viu (Priority: P1)

No desktop do dono roda um serviço que, dentro da janela de horário, pede ao SociMan a fila do dia, abre o
Chrome real num perfil dedicado (logado uma vez pelo dono na conta de afiliado), visita cada página como uma
pessoa (rola, espera entre 5 e 40 segundos, uma aba só), lê o que a página carregou e devolve ao SociMan os
campos normalizados, o bruto e as imagens. Nunca chama a API interna da rede diretamente, nunca clica em
nada que não seja navegação (nada de seguir, curtir, comentar, adicionar à vitrine, comprar ou pedir
amostra). Respeita o teto diário de páginas (padrão 300) e o teto diário de imagens. Se aparece um captcha,
se a sessão cai ou se a rede começa a recusar, o coletor para, avisa o dono pelo sino e deixa o Chrome
aberto para o dono resolver; só volta quando o dono clica "Continuar" e depois de esfriar uma hora.

**Why this priority**: Sem o robô, não há dado. É também onde mora o risco aceito pelo dono, então as
proteções (só leitura, ritmo, parada) são requisito, não detalhe.

**Independent Test**: Com um servidor falso da rede (páginas HTML sintéticas que carregam JSON pelos mesmos
caminhos) e o SociMan de teste, o coletor em modo `uma-vez --limite 3` visita 3 páginas, devolve 3
resultados aceitos, respeita as pausas (com relógio simulado), não executa nenhuma ação proibida (teste
estático da lista de ações) e, numa página de captcha sintética, para e registra o evento.

**Acceptance Scenarios**:

1. **Given** a coleta habilitada e a hora dentro da janela, **When** o coletor pede a fila, **Then** recebe as
   tarefas do dia em ordem de prioridade, os limites (páginas/dia, itens por rodada, pausas) e o orçamento
   restante, e abre uma rodada.
2. **Given** uma tarefa de produto, **When** o coletor visita a página, **Then** devolve título, descrição,
   atributos, variantes, preço, "vendidos", nota, nº de avaliações, selos, loja, categoria, as imagens
   originais (até o teto por produto) e o bruto interceptado, e o SociMan responde "gravado".
3. **Given** a mesma tarefa reenviada no mesmo dia, **When** o SociMan recebe, **Then** responde "repetido" e
   nada é gravado duas vezes.
4. **Given** o teto diário de páginas atingido, **When** o coletor pede mais fila, **Then** recebe fila vazia
   e dorme até a próxima janela.
5. **Given** uma página de verificação (captcha) ou um redirecionamento para o login, **When** o coletor a
   detecta, **Then** envia o evento, o dono recebe a notificação no sino, a rodada fica "pausada" e o
   coletor não tenta contornar nem recarregar em laço; depois que o dono resolve e clica "Continuar", o
   coletor espera o tempo de esfriamento e retoma.
6. **Given** o arquivo local de parada criado ou o serviço parado, **When** o coletor está no meio de uma
   rodada, **Then** termina a tarefa atual, fecha a rodada como "interrompida" e não abre outra.
7. **Given** respostas 429 ou 403 em série, ou cinco páginas seguidas sem nada reconhecível, **When** o
   coletor as recebe, **Then** registra "bloqueio suspeito" ou "layout mudou", recua por 24 horas e avisa o
   dono.
8. **Given** o código do coletor, **When** o teste estático roda, **Then** nenhuma ação fora da lista de
   navegação permitida existe, nenhuma chamada direta à API da rede existe e nenhum log leva cookie, nome
   ou texto de pessoa.

---

### User Story 3 - Ligar a coleta com aceite de risco, token e interruptor (Priority: P1)

Em `/app/configuracoes/coleta`, o dono lê o aviso de risco (a rede pode restringir a conta de afiliado dele),
clica no aceite (que grava quem e quando), cria um token para o coletor (mostrado uma única vez), ajusta
janela, teto de páginas e pausas, e liga o interruptor. Vê o estado do coletor (último contato, páginas de
hoje, rodada atual, eventos) e pode pausar por N horas, desligar, rotacionar ou revogar o token. Sem o
aceite, o interruptor não liga. Com o interruptor do `.env` desligado, nada coleta, independentemente do
botão.

**Why this priority**: A constitution exige o aceite registrado e o interruptor em dois níveis antes de
qualquer coleta.

**Independent Test**: Sem aceite, ligar o interruptor responde "aceite de risco pendente"; com aceite,
liga, o token é exibido uma vez e nunca mais, a fila passa a responder tarefas; desligar pelo botão ou pelo
`.env` esvazia a fila na hora; revogar o token faz o coletor receber "não autorizado".

**Acceptance Scenarios**:

1. **Given** a config sem aceite de risco, **When** o dono tenta ligar o interruptor, **Then** é recusado
   com "aceite de risco pendente" e o aviso de risco fica em destaque.
2. **Given** o dono clica no aceite, **When** confirma, **Then** a config grava quem aceitou e quando, com
   histórico, e o interruptor fica disponível.
3. **Given** um token criado, **When** a tela o mostra, **Then** é exibido uma única vez e a lista só mostra
   o prefixo, a situação, o último contato e a versão do coletor.
4. **Given** o interruptor ligado, **When** o `.env` tem a coleta desligada, **Then** a fila vem vazia, a
   tela mostra "desligada no servidor" e nenhuma rodada abre.
5. **Given** um membro, **When** abre a tela, **Then** vê o estado da coleta, mas não vê o aceite, o
   interruptor, os tokens nem os ajustes.
6. **Given** um cliente MCP ou um agente, **When** tenta ligar, aceitar, pausar ou criar token, **Then** é
   recusado com "somente humano" e a recusa fica registrada.

---

### User Story 4 - Acompanhar produtos por perfil, com categorias do nicho (Priority: P2)

Na aba Mercado do perfil, o dono escolhe as categorias do nicho (da taxonomia que o coletor observou) e vê
a lista do que o perfil acompanha, com a origem de cada item: colado por link (manual), da vitrine do dono
(vale para todos os perfis), dos rankings das categorias (automático), de produtos novos de lojas ou
categorias já acompanhadas (automático, com limite diário e aviso) ou, no futuro, de vídeos virais. Pode
pausar ou encerrar um acompanhamento. O servidor decide a cadência: quente (1 foto por dia, 2 para novos em
alta e manuais), semanal quando o produto sai do ranking há 7 dias, e parada depois de 30 dias sem
interesse. Nada é apagado: parar só deixa de coletar.

**Why this priority**: Define o que o robô olha; sem isso só a lista manual funciona.

**Independent Test**: Com 2 perfis de teste e categorias diferentes, a trilha gera tarefas de ranking para a
união das categorias, um produto da vitrine vira interesse de ambos, um link colado vira interesse manual
do perfil 1, e um produto que sumiu do ranking há 8 dias passa a semanal sem perder nenhuma foto.

**Acceptance Scenarios**:

1. **Given** a taxonomia coletada, **When** o dono escolhe até cinco categorias para o perfil, **Then** a
   próxima fila inclui os rankings dessas categorias e os produtos do topo viram interesses "ranking" do
   perfil.
2. **Given** um link de produto colado, **When** o dono confirma, **Then** o produto entra no lago (se não
   existia) como interesse "manual" do perfil, com cadência quente, e a primeira visita traz a ficha
   completa e as imagens.
3. **Given** a vitrine do dono coletada, **When** a trilha roda, **Then** cada produto da vitrine vira um
   interesse "vitrine" válido para todos os perfis, sem duplicar.
4. **Given** uma loja de um produto acompanhado, **When** o coletor vê um produto novo dela, **Then** nasce
   um interesse "loja" automático (até o limite diário) e o dono é avisado uma vez por dia.
5. **Given** um produto fora do ranking há 7 dias e sem outro interesse, **When** a trilha recalcula,
   **Then** a cadência vira semanal; aos 30 dias vira parada; as fotos e a ficha continuam íntegras e
   visíveis.
6. **Given** um interesse manual ou de vitrine, **When** o produto some dos rankings, **Then** a cadência
   continua quente.
7. **Given** um cliente MCP, **When** tenta criar ou encerrar interesse ou escolher categorias, **Then** é
   recusado; leitura é permitida.

---

### User Story 5 - Ficha completa, lojas, rankings, avaliações e vídeos no detalhe (Priority: P2)

No detalhe de um produto o dono vê a ficha completa (título, descrição, especificação técnica, variantes,
argumentos de venda, selos, categoria completa), a galeria com as imagens originais, a série de "vendidos",
vendas/dia, preço e nº de criadores ao longo do tempo, as posições em rankings, os vídeos top que promovem
o produto (identificador público do criador e contadores) e as avaliações públicas (texto, nota, data, sem o
nome do autor). Na aba Lojas vê o cartão da loja (nota, seguidores, envio no prazo, nº de produtos, vendidos
total, GMV estimado) e pode seguir a loja para um perfil. Na aba Rankings vê a foto de cada ranking por
categoria e dia, com a variação de posição.

**Why this priority**: É o que transforma o número em decisão (argumentos, lojas para parceria, o que o
mercado já faz em vídeo), e alimenta a 012 e a 028.

**Independent Test**: Com o coletor falso enviando ficha, 6 imagens, 2 rankings em dias diferentes, 3 vídeos e
5 avaliações para um produto, o detalhe mostra tudo; mudar o título no segundo dia cria uma nova versão da
ficha sem apagar a anterior; a avaliação nunca mostra nome de autor.

**Acceptance Scenarios**:

1. **Given** um produto com ficha e imagens, **When** o dono abre o detalhe, **Then** vê a ficha completa,
   a galeria e a série de fotos com as datas.
2. **Given** a ficha mudou (título ou descrição) numa visita posterior, **When** o SociMan ingere, **Then**
   nasce uma nova versão da ficha e a anterior continua consultável no histórico.
3. **Given** dois rankings da mesma categoria em dias seguidos, **When** o dono abre a aba Rankings,
   **Then** vê a posição de cada produto e a variação (subiu, caiu, novo, saiu).
4. **Given** avaliações coletadas, **When** o dono as vê, **Then** há texto, nota, data e fotos do cliente,
   e nenhum nome, @ ou foto de perfil do autor.
5. **Given** vídeos top coletados, **When** o dono os vê, **Then** há o identificador público do criador, as
   views, a legenda e a data, e nada mais sobre a pessoa.
6. **Given** uma loja, **When** o dono clica em "Seguir loja neste perfil", **Then** produtos novos dela
   passam a virar interesses automáticos do perfil.

---

### User Story 6 - Adotar um produto do mercado no catálogo e ler pelo MCP (Priority: P3)

No detalhe do produto de mercado, o dono clica em "Adotar no catálogo" e escolhe o perfil: nasce um produto
do catálogo (012) com título, categoria, link da loja, argumentos e as imagens copiadas, apontando para o
produto de mercado de origem, e segue o fluxo normal da 012. Os agentes, pelo MCP, leem o cockpit (produtos,
rankings, lojas, categorias, interesses) para propor; não escrevem.

**Why this priority**: Fecha o ciclo "mercado → produto → vídeo" e prepara a 028, mas o cockpit tem valor sem
isso.

**Independent Test**: Adotar um produto de mercado cria o produto do perfil com as imagens copiadas e o
vínculo de origem; adotar de novo o mesmo produto para o mesmo perfil é recusado com o aviso de duplicidade;
um cliente MCP lista os produtos do mercado e é recusado ao tentar adotar.

**Acceptance Scenarios**:

1. **Given** um produto de mercado com ficha e imagens, **When** o dono o adota para um perfil, **Then** é
   criado um produto do catálogo com os campos copiados, as imagens copiadas para o perfil e o vínculo de
   origem, com histórico da origem.
2. **Given** um produto já adotado para o perfil, **When** o dono tenta adotar de novo, **Then** é avisado da
   duplicidade e pode abrir o produto existente.
3. **Given** um cliente MCP, **When** lista produtos, rankings, lojas, categorias ou interesses, **Then**
   recebe os dados; **When** tenta adotar, acompanhar ou configurar, **Then** é recusado.

---

### Edge Cases

- "Vendidos" em faixa ("1,2 mil", "10 mil+"): a foto guarda mínimo, máximo e a marca de inexato; os cálculos
  usam o ponto médio e carregam a incerteza.
- Preço por variante: a foto guarda mínimo e máximo; o GMV usa o mínimo e informa a faixa.
- Produto indisponível ou removido da loja: a foto marca "indisponível", a ficha ganha a data, a cadência
  segue até parar; nada é apagado.
- Duas fotos no mesmo dia (cadência 2/dia): identificadas por turno (manhã/noite); uma terceira é "repetida".
- Coleta cruzando a meia-noite: o dia da foto é o do horário de coleta no fuso do mercado, decidido pelo
  servidor, não pelo relógio do coletor.
- Reprocessamento do bruto depois de uma mudança de layout: só preenche o que faltava; nunca altera uma foto
  gravada.
- Mesmo produto em dois mercados (países): são dois produtos do lago; só `BR` existe nesta spec.
- Imagem repetida entre produtos (mesma foto em anúncios diferentes): guardada uma vez, referenciada pelas
  duas fichas.
- Avaliação sem texto ou sem nota: aceita; o autor entra como hash mesmo assim.
- Chrome fechado pelo dono no meio da rodada: a rodada fica "interrompida"; as tarefas voltam à fila quando a
  reserva vence.
- Dois coletores com o mesmo token: o segundo recebe "rodada em andamento" e não coleta.
- Relógio do desktop errado: o servidor usa o próprio horário para o dia e para o orçamento.
- Fila vazia por falta de interesse: o coletor dorme; a tela mostra "nada a coletar hoje".
- Fila maior que o teto com vários perfis: nenhum perfil ativo fica sem coleta no dia (revezamento); o que
  sobra entra primeiro no dia seguinte.
- Teto de imagens atingido antes do de páginas: as visitas seguem sem baixar imagens; o produto fica marcado
  "imagens pendentes" e entra primeiro no dia seguinte.
- HD desmontado: a ingestão recusa imagens e bruto (como todo uso do HD), grava só a foto numérica e marca o
  item "bruto pendente".

## Requirements *(mandatory)*

### Functional Requirements

**Lago de mercado (global, permanente)**

- **FR-001**: O SociMan DEVE guardar os dados de mercado num **lago global**: nenhuma entidade do lago
  (produto, loja, categoria, ficha, foto, ranking, avaliação, vídeo, imagem, rodada, fila) pertence a perfil,
  conta, usuário ou tenant. Toda entidade do lago DEVE ter a rede e o mercado (país, código de duas letras),
  com `BR` como único mercado nesta spec.
- **FR-002**: O lago DEVE ser **permanente**: nenhuma entidade do lago é apagada, por nenhuma rotina,
  limpeza ou ação de usuário. "Esfriar" um produto só muda a cadência de coleta.
- **FR-003**: Cada **produto** DEVE ter identidade estável (rede, mercado, identificador na rede), a data em
  que foi visto pela primeira vez, a data de lançamento quando a página expõe, a última foto, o estado de
  coleta (cadência, próxima coleta, último erro) e a origem da descoberta.
- **FR-004**: A **ficha** do produto (título, descrição, especificação técnica/atributos, variantes com
  identificador e nome, argumentos de venda, selos, categoria completa, loja) DEVE ser versionada por
  conteúdo: uma nova versão só nasce quando o conteúdo muda, e as anteriores continuam consultáveis.
- **FR-005**: As **imagens** do produto DEVEM ser guardadas como originais (sem redimensionar), no
  armazenamento do HD, deduplicadas por conteúdo, imutáveis, com a ordem em que aparecem na página e a
  versão da ficha a que pertencem.
- **FR-006**: As **fotos diárias** do produto DEVEM registrar, por dia e turno (manhã/noite) e por fonte
  (página pública ou Affiliate Center): "vendidos" acumulado (com mínimo, máximo e marca de exato),
  preço mínimo e máximo, preço original, moeda, nota, nº de avaliações, comissão, nº de criadores
  promovendo, vendas em 7 e 30 dias quando a fonte expõe, estoque visível, disponibilidade e a referência
  ao bruto. Fotos são **só inserção**: nunca alteradas nem apagadas; uma segunda foto do mesmo dia, turno e
  fonte é "repetida".
- **FR-007**: As **lojas** DEVEM ter identidade estável, nome, selo oficial e fotos diárias só de inserção
  (nota, seguidores, envio no prazo, nº de produtos, vendidos total).
- **FR-008**: As **categorias** DEVEM ser a taxonomia observada na rede (níveis 1 a 3, com o caminho
  completo), atualizada semanalmente, sem lista fixa.
- **FR-009**: Os **rankings** DEVEM ser fotos só de inserção por rede, mercado, fonte, categoria, tipo
  (mais vendidos, em alta, novos, alta comissão), janela e dia, com a posição de cada produto e o valor que
  o ranking exibiu.
- **FR-010**: As **avaliações** públicas DEVEM ser só inserção, com texto, nota, data, variante e as fotos do
  cliente **guardadas como vêm** (originais, deduplicadas, imutáveis; o risco LGPD dessas imagens é assumido
  pelo dono e consta de `docs/decisoes/coleta-mercado.md`); o autor entra só como hash com segredo do
  servidor, nunca nome, @ ou foto de perfil.
- **FR-011**: Os **vídeos top** de um produto DEVEM ser só inserção, com identificador do vídeo, identificador
  público do criador, views, curtidas, legenda e data; nada mais sobre a pessoa.
- **FR-012**: O **payload bruto** de cada coleta DEVE ser guardado integralmente no armazenamento do HD,
  referenciado pela foto, para reprocessar sem recoletar quando o layout mudar; o reprocessamento só
  preenche o que faltava.

**Coletor (serviço no desktop do dono)**

- **FR-013**: A coleta DEVE rodar num serviço separado, no desktop do dono, fora dos containers, que
  controla o navegador real do dono num perfil dedicado, logado uma vez pelo dono na conta de afiliado
  dele, com uma única aba e uma tarefa por vez.
- **FR-014**: O coletor DEVE ler o que a página carrega e NÃO DEVE chamar diretamente a API interna
  assinada da rede.
- **FR-015**: O coletor NÃO DEVE executar nenhuma ação que escreva na rede: seguir, curtir, comentar,
  adicionar à vitrine, comprar, pedir amostra ou qualquer envio de formulário. As ações permitidas (abrir
  página, rolar, esperar, fechar aviso, trocar aba de categoria ou paginação) formam uma lista fechada
  verificada por teste estático.
- **FR-016**: O coletor DEVE navegar em **ritmo humano**: janela de horário (padrão 08h–23h no fuso do
  mercado), pausa aleatória entre 5 e 40 segundos entre ações, pausa longa aleatória a cada bloco de
  páginas, rolagem em passos, teto diário de páginas (padrão 300) e teto diário de imagens (padrão 1.500,
  até 9 por produto). Os limites efetivos vêm do servidor; o coletor aplica o menor entre os seus e os do
  servidor.
- **FR-017**: O coletor DEVE parar e avisar, nunca contornar, ao detectar captcha ou verificação, perda da
  sessão (redirecionamento para login), bloqueio suspeito (recusas em série) ou layout desconhecido (cinco
  páginas seguidas sem campos reconhecíveis). Em bloqueio ou layout, recua por 24 horas.
- **FR-018**: Depois de captcha ou login resolvidos pelo dono, o coletor só retoma quando o dono clica
  "Continuar" na tela e depois de um esfriamento de 60 minutos; sem clique em 2 horas, a rodada é encerrada
  com o motivo "pausa vencida".
- **FR-019**: O coletor DEVE parar em três níveis: fila vazia por interruptor do servidor, arquivo local de
  parada e parada do serviço do sistema; em qualquer um, termina a tarefa atual e fecha a rodada.
- **FR-020**: O coletor DEVE baixar as imagens dentro do próprio contexto do navegador e enviá-las ao
  SociMan com o resumo criptográfico do conteúdo.
- **FR-021**: O coletor NÃO DEVE gravar em log, em disco ou em tela nenhum cookie, token, nome de pessoa,
  @ de criador, texto de avaliação ou URL com parâmetros; só contagens, identificadores de produto,
  durações e códigos. Capturas de tela ficam desligadas por padrão e nunca são enviadas.
- **FR-022**: O coletor DEVE oferecer, em linha de comando: rodar contínuo, rodar uma vez com limite de
  páginas, simulação sem navegar, autoteste da conexão e do token, iniciar o perfil (abre o Chrome para o
  dono logar), parar e reprocessar o bruto já guardado a partir de uma data (FR-012), sem navegar.
- **FR-023**: O coletor DEVE enviar um batimento periódico ao SociMan com páginas e imagens do dia, tarefa
  atual e estado, e NÃO DEVE abrir nenhuma URL que não tenha vindo da fila, salvo a navegação interna da
  própria página.

**Ingestão e segurança**

- **FR-024**: O dado DEVE entrar no SociMan só por uma **API de ingestão**, autenticada por token próprio do
  coletor, do qual o SociMan guarda só o resumo criptográfico; o token é exibido uma única vez, pode ser
  rotacionado (troca o identificador) e revogado (final). A verificação de segredos do repositório DEVE
  reconhecer o formato do token.
- **FR-025**: O token do coletor só DEVE valer nas rotas de ingestão; em qualquer outra rota é recusado. O
  portão DEVE recusar, nesta ordem: credencial inválida, coleta desligada (fila vazia ou serviço
  indisponível), token revogado/vencido ou suspenso, requisição vinda de navegador, rota fora da ingestão,
  excesso de requisições.
- **FR-026**: Quem decide o que coletar é o **servidor**: a fila do dia é calculada a partir dos interesses,
  das categorias dos perfis, da cadência e do orçamento, em ordem de prioridade (manual e vitrine; produtos
  novos de lojas seguidas; rankings das categorias; quentes; semanais; lojas; vídeos; avaliações), reservada
  por tempo quando entregue, e devolvida à fila se a reserva vence. Dentro de cada nível, quando a fila
  passa do teto, o orçamento é dividido por **revezamento entre perfis** (um item de cada perfil ativo por
  vez, em ordem fixa); um produto de interesse de vários perfis entra uma vez só, pelo primeiro perfil cuja
  vez chegar; tarefas sem perfil (vitrine, categorias, lojas globais) entram no revezamento como um
  "perfil" a mais.
- **FR-027**: A ingestão DEVE ser **idempotente** por fonte, chave e dia (e turno quando houver): o mesmo
  resultado reenviado responde "repetido" sem gravar; a data do dia é decidida pelo servidor no fuso do
  mercado, a partir do horário da coleta.
- **FR-028**: A ingestão DEVE validar e normalizar cada resultado por rede (adaptador de fonte), gravar a
  ficha (nova versão só se mudou), as fotos, as imagens (recusando as que não são imagem pelo conteúdo), o
  bruto e os vínculos; um resultado inválido é registrado com o erro e não derruba o lote.
- **FR-029**: A ingestão DEVE podar do bruto qualquer campo de dados pessoais de terceiros (nome, apelido,
  foto de perfil, bio) e recusar o item que ainda os traga depois da poda feita pelo coletor.
- **FR-030**: Todo uso do HD (imagens e bruto) DEVE seguir as regras do armazenamento do projeto (marcador do
  volume e piso de espaço livre); sem HD, a foto numérica é gravada e o item fica "bruto pendente".
- **FR-031**: Cada rodada do coletor DEVE ficar registrada (início, fim, resultado, páginas, itens ok, com
  erro e repetidos, versão do coletor) e cada evento (captcha, login perdido, bloqueio, layout, parada
  local, retomada) DEVE ficar registrado. Geram notificação no sino dos donos, sem repetir no mesmo dia
  para o mesmo tipo, só captcha, login perdido, bloqueio e layout; parada local e retomada ficam só no
  registro, e o aviso "coleta parada" é o de FR-041 (48 horas sem resultado).
- **FR-032**: As rotas de ingestão DEVEM aceitar lotes de até 50 itens e imagens em envio separado, com
  limites de tamanho na borda e na API; o cabeçalho de versão do protocolo DEVE ser exigido, e uma versão
  desconhecida DEVE ser recusada com mensagem clara.

**Configuração da coleta (só dono humano)**

- **FR-033**: A coleta DEVE ter um interruptor em dois níveis: variável do servidor (padrão desligada) **e**
  botão da tela. Com qualquer um desligado, a fila vem vazia e nenhuma rodada abre.
- **FR-034**: O botão só DEVE ligar depois de um **aceite de risco** registrado (quem e quando), com
  histórico; sem aceite, a tentativa responde "aceite de risco pendente". O texto do aceite DEVE citar o
  registro legível em `docs/decisoes/coleta-mercado.md`.
- **FR-035**: O dono DEVE poder ajustar janela, teto de páginas, teto de imagens, pausas e itens por rodada,
  pausar a coleta por N horas, e gerenciar os tokens; tudo com histórico e reversão. Essas ações e o
  aceite são **só de dono humano**: membro, cliente MCP e agente são recusados, e a recusa de ator não
  humano fica registrada.
- **FR-036**: A tela DEVE mostrar o estado do coletor (último contato, páginas e imagens de hoje, rodada
  atual, eventos recentes, versão) e o bloco "coleta" DEVE aparecer no painel de integrações.

**Interesse e cadência (por perfil)**

- **FR-037**: Cada perfil DEVE poder escolher **categorias do nicho** (até cinco, da taxonomia observada) e
  o SociMan DEVE gerar rankings para a união das categorias de todos os perfis ativos, uma coleta por
  categoria por dia.
- **FR-038**: Um **interesse** liga um produto do lago a um perfil, com origem (manual, vitrine, ranking,
  vídeo, loja, categoria), situação (ativo, pausado, encerrado), motivo e nota; é versionado com histórico;
  encerrar nunca apaga. A vitrine do dono gera interesses válidos para **todos** os perfis.
- **FR-039**: Qualquer humano (dono ou membro) DEVE poder acompanhar um produto por link (interesse manual),
  pausar ou encerrar qualquer acompanhamento (inclusive os automáticos) e seguir ou deixar de seguir uma
  loja para um perfil; a reversão pelo histórico é só do dono; cliente MCP e agente só leem (recusa
  "somente humano"); o SociMan DEVE criar automaticamente interesses "ranking" para os
  primeiros 30 de cada ranking das categorias do perfil e interesses "loja"/"categoria" para produtos novos
  (vistos há até 30 dias) de lojas seguidas e das categorias do perfil, até 10 por perfil por dia, avisando
  o dono uma vez por dia.
- **FR-040**: A **cadência** DEVE ser calculada pelo servidor: quente = 1 foto por dia, e 2 por dia (manhã e
  noite) para "novo em alta" e interesses manuais; semanal (estado `morna`) quando o produto está fora dos
  rankings há 7 dias e sem interesse manual ou de vitrine; parada depois de 30 dias sem ranking e sem interesse ativo;
  manual e vitrine nunca esfriam; um produto parado volta a quente ao reaparecer.
- **FR-040a**: Avaliações e vídeos top só são coletados para produtos em cadência **quente**: avaliações na
  primeira visita (até 2 páginas) e depois a cada 30 dias; vídeos top a cada 7 dias (1 página). Essas
  visitas ficam nos dois últimos níveis de prioridade da fila e contam no teto diário de páginas.
- **FR-041**: A **trilha** do agendador DEVE, a cada volta: recalcular a cadência, montar a fila do dia,
  criar os interesses automáticos, devolver reservas vencidas, marcar rodadas sem batimento há 10 minutos
  e avisar "coleta parada" quando a coleta está ligada e não há resultado há 48 horas. A trilha NÃO DEVE
  apagar nada nem falar com a rede.

**Leitura e indicadores (calculados na leitura, sempre marcados)**

- **FR-042**: Todo número derivado DEVE sair com o valor, a marca **estimado**, os motivos da estimativa, a
  marca de amostra pequena e o nº de fotos usadas. Nenhuma tabela agregada é gravada; as leituras não
  escrevem.
- **FR-043**: O filtro comum DEVE aceitar período (padrão 30 dias, até 400, no fuso do mercado), perfil (só
  restringe aos interesses e categorias do perfil), mercado, rede, categoria, loja, origem, "só
  acompanhados", busca por texto e ordenação.
- **FR-044**: **Vendas no período** = diferença entre o "vendidos" da última foto no período e o da última
  foto anterior ao período; delta negativo vale zero e marca "inconsistente". Quando o Affiliate Center
  expõe vendas em 7 ou 30 dias e a janela coincide, esse valor tem precedência e a página pública é reserva.
- **FR-045**: **Vendas/dia** exige ao menos duas fotos com um dia de distância; abaixo disso o valor é nulo e
  o produto aparece como "coletando". **GMV no período** = soma dos deltas entre fotos consecutivas vezes o
  preço vigente no início de cada par; faixas de preço ou de "vendidos" geram mínimo, máximo e ponto médio.
- **FR-046**: **Crescimento** = vendas/dia dos últimos 7 dias contra os 7 anteriores; base menor que 3
  vendas/dia dá nulo. **Vendas totais** = "vendidos" da última foto; **GMV total** = vendas totais vezes o
  preço atual, marcado "grosseiro".
- **FR-047**: **Comissão por venda** = preço vezes comissão (marcada estimada, porque a rede desconta
  cupons); **retorno por afiliado** = vendas/dia vezes comissão por venda dividido por (criadores + 5);
  **saturação** = criadores por venda/dia. "Alto retorno com poucos afiliados" exige comissão de ao menos
  5%, foto do Affiliate Center com até 3 dias e, na categoria com ao menos 10 produtos comparáveis,
  criadores no quartil inferior e retorno no quartil superior (sem amostra, 50 criadores e a mediana
  global). A projeção de lucro para 10, 100 e 1.000 vendas é calculada na tela.
- **FR-048**: **Novo em alta** = visto pela primeira vez há até 30 dias, vendas/dia de ao menos 10 e
  (crescimento de ao menos 50%, ou presença em ranking "em alta"/"novos", ou subida de 10 posições em 7
  dias); exige estado "ok" (não "coletando").
- **FR-049**: Por **loja**: GMV estimado (soma dos produtos acompanhados), concentração no produto nº 1,
  ritmo de lançamentos, nota e envio no prazo, comissão média. Por **categoria**: medianas de comissão e
  preço, nº de produtos em alta e "espaço em branco" (subcategoria com vendas crescendo e poucos
  criadores). Por **ranking**: posição atual, melhor posição, dias no topo, variação em 7 dias, entrada e
  saída.
- **FR-050**: Todos os limiares e constantes dos indicadores DEVEM ser nomeados em um só lugar do código, e
  as leituras DEVEM responder em menos de 2 segundos com dez vezes o volume esperado (300 fotos/dia por um
  ano).

**Telas**

- **FR-051**: `/app/mercado` DEVE ter as abas Cockpit (cards Mais vendidos, Novos em alta, Alto retorno com
  poucos afiliados, Estado da coleta), Produtos (tabela com o cartão mínimo, paginação no servidor),
  Rankings, Lojas e Acompanhamentos, com filtros na URL; todo card com "Ver tabela" e "CSV" gerados dos
  mesmos dados exibidos. O menu Analytics ganha "Mercado de produtos"; a aba Mercado de `/app/metricas`
  (YouTube de origem) passa a se chamar "Fontes".
- **FR-052**: O detalhe do produto DEVE mostrar ficha, galeria, série (vendidos, vendas/dia, preço,
  criadores), rankings, vídeos top, avaliações, e as ações "Acompanhar neste perfil" e "Adotar no catálogo".
- **FR-053**: A aba Mercado do perfil DEVE mostrar as categorias do nicho e os acompanhamentos do perfil com
  origem, situação e ações; `/app/configuracoes/coleta` é só de dono (membro vê só o estado).
- **FR-054**: Leitura do cockpit, do detalhe, dos rankings e das lojas é para dono e membro, inclusive
  comissão e retorno; os gráficos usam a biblioteca de gráficos do projeto, carregada sob demanda, com
  tooltips em texto escapado.

**Ponte com o catálogo (012) e MCP**

- **FR-055**: Um produto do catálogo (012) DEVE poder apontar para um produto de mercado (vínculo opcional,
  versionado). "Adotar no catálogo" (só humano) DEVE criar o produto do perfil com título, categoria, link da
  loja, argumentos e as imagens **copiadas** para o perfil, gravar o vínculo e a origem no histórico, e
  criar o interesse manual se não existir; adotar de novo para o mesmo perfil é recusado com a opção de
  abrir o existente.
- **FR-056**: As leituras de mercado (produtos, detalhe, série, rankings, lojas, categorias, interesses)
  DEVEM existir como ferramentas MCP de leitura; a ingestão fica fora do MCP ("serviço do coletor"), e
  toda escrita (interesses, categorias, seguir loja, adotar, configuração, tokens, reversões) é proibida ao
  MCP com "somente humano".

**Guardas e conformidade (princípio IX)**

- **FR-057**: Testes automatizados DEVEM garantir: a API sem biblioteca de automação de navegador e sem
  endereços da rede fora do módulo de publicação; os pacotes de mercado e coleta sem HTTP de saída e sem
  importar a publicação; nenhuma tabela do lago com coluna de perfil, conta, usuário ou tenant; nenhuma
  remoção nos pacotes de mercado e coleta; as tabelas de foto, ficha, ranking, avaliação, vídeo, imagem, item
  da rodada e evento só de inserção (a rodada em si muda de estado); o portão do token só nas rotas de ingestão; o token só como hash; a trilha nova
  registrada; as leituras só por GET; nenhum nome de rede em rotas e identificadores de operação. No
  coletor: ações permitidas, poda de dados pessoais, ritmo dentro dos limites e log sem dado pessoal.

### Key Entities

- **Produto de mercado**: observação de um produto da rede num mercado; identidade estável, datas de
  primeira vez, lançamento e última foto, estado de coleta, origem da descoberta; dono de fichas, fotos,
  imagens, avaliações, vídeos e posições em rankings. Sem perfil.
- **Ficha do produto**: versão do conteúdo descritivo (título, descrição, atributos, variantes, argumentos,
  selos, categoria, loja), criada só quando o conteúdo muda; aponta o bruto de origem.
- **Imagem de mercado**: arquivo original deduplicado por conteúdo, imutável, com ordem e versão da ficha.
- **Foto do produto**: medição de um dia, turno e fonte ("vendidos", preço, nota, avaliações, comissão,
  criadores, vendas 7/30 d, estoque, disponibilidade); só inserção; aponta a rodada e o bruto.
- **Loja** e **Foto da loja**: identidade e selo; medições diárias só de inserção.
- **Categoria**: nó da taxonomia observada (níveis 1 a 3), com caminho completo.
- **Foto de ranking** e **Item de ranking**: a lista de um ranking num dia, com posição, produto e valor.
- **Avaliação**: texto, nota, data, variante, fotos do cliente, autor como hash; só inserção.
- **Vídeo top**: vídeo que promove o produto; identificadores públicos e contadores; só inserção.
- **Tarefa da fila**: o que o servidor pediu (tipo, chave, prioridade, dia, reserva, estado); nunca apagada.
- **Rodada**: uma execução do coletor (cliente, início, fim, resultado, contagens, versão).
- **Evento de coleta**: captcha, login perdido, bloqueio, layout, parada, retomada; só inserção.
- **Interesse**: vínculo perfil ↔ produto com origem, situação, motivo e nota; versionado; perfil nulo para a
  vitrine (todos). É a camada onde o tenant entrará no futuro.
- **Configuração de mercado do perfil**: categorias do nicho, limite de interesses automáticos por dia,
  aviso de novo em alta; versionada.
- **Cliente de coleta**: o token do coletor (só hash), situação, validade, último contato, versão.
- **Configuração da coleta**: interruptor, aceite de risco (quem, quando), janela, tetos, pausas, pausa até;
  versionada; linha única.
- **Produto do catálogo (012)**: ganha o vínculo opcional ao produto de mercado de origem.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Com o coletor falso enviando 10 dias de fotos, 100% dos cartões mostram vendas no período,
  GMV, crescimento e comissão por venda iguais aos valores calculados à mão no teste, todos marcados
  "estimado", e 100% dos produtos com menos de duas fotos aparecem como "coletando".
- **SC-002**: 0 ações de escrita na rede no código do coletor (teste estático) e 0 chamadas diretas à API
  interna da rede; 100% dos cenários de captcha, login perdido e bloqueio param a coleta e geram
  notificação.
- **SC-003**: Em 100% dos testes, nenhuma rodada abre com o interruptor do servidor ou o botão desligado,
  nem sem aceite de risco registrado; 0 ligações, aceites, tokens ou configurações aceitos de membro, MCP
  ou agente.
- **SC-004**: 100% dos reenvios do mesmo resultado (fonte, chave, dia, turno) respondem "repetido" sem gravar;
  0 linhas alteradas ou apagadas nas tabelas só de inserção em todos os testes.
- **SC-005**: Depois de 30 dias simulados sem interesse, 100% das fotos e fichas do produto continuam
  consultáveis, e o produto não gera tarefa; ao reaparecer num ranking, volta à cadência quente no mesmo
  dia.
- **SC-006**: 0 nomes, @ de autor de avaliação, fotos de perfil ou textos pessoais de terceiros no banco, no
  bruto gravado e nos logs do coletor (teste de poda e de log).
- **SC-007**: Toda leitura do cockpit responde em menos de 2 segundos com dez vezes o volume de um ano de
  coleta.
- **SC-008**: O dono liga a coleta pela primeira vez (aceite, token, perfil do Chrome, serviço) seguindo o
  guia em menos de 30 minutos, e a primeira rodada real com 3 páginas devolve 3 fotos visíveis no cockpit.
- **SC-009**: "Adotar no catálogo" cria o produto da 012 com 100% das imagens copiadas e o vínculo de
  origem, e a segunda adoção para o mesmo perfil é recusada.
- **SC-010**: Com 3 perfis e uma fila do dia 3 vezes maior que o teto, cada perfil recebe ao menos um terço
  (menos um) das tarefas de cada nível, e nenhum produto comum a dois perfis é coletado duas vezes.

## Assumptions

- **Conta e navegador:** a conta de afiliado do dono já existe e tem acesso ao Affiliate Center brasileiro; o
  Chrome está instalado no desktop; o perfil dedicado é logado pelo dono uma vez (e relogado quando a sessão
  cair). O serviço só coleta com a sessão gráfica ativa; não há modo sem tela.
- **Risco:** o risco de a rede restringir a conta foi explicado e aceito pelo dono em 2026-10-08
  (`docs/decisoes/coleta-mercado.md`); o aceite na tela é o registro operacional. O mesmo registro cobre a guarda
  das fotos de clientes anexadas às avaliações (dado pessoal de terceiros), decidida pelo dono na clarificação. A spec não oferece
  perfil anônimo nem conta separada, por decisão do dono.
- **Fonte de "vendidos":** o Affiliate Center, quando expõe vendas em 7/30 dias, tem precedência; a página
  pública (acumulado) é a reserva. Os campos reais do Affiliate Center brasileiro são confirmados numa
  sonda guiada com o dono (primeira tarefa prática do plano); a sonda pode ajustar nomes de campos, não as
  regras.
- **Relacionados automáticos:** interesses "ranking", "loja" e "categoria" são criados pelo próprio sistema
  (autor de sistema), com o limite diário por perfil e um aviso por dia; o dono pode pausar ou encerrar.
- **Permissões:** leitura do cockpit (inclusive comissão e retorno) para dono e membro; acompanhar por link,
  pausar e encerrar acompanhamentos, seguir e deixar de seguir loja e adotar são de qualquer humano; a
  reversão pelo histórico, as categorias do perfil, a configuração da coleta, o aceite e os tokens são só
  de dono humano.
- **Taxonomia:** a observada na rede, sem lista fixa; o dono escolhe entre as categorias vistas.
- **Dia da foto:** o do horário da coleta no fuso do mercado, decidido pelo servidor.
- **Orçamento:** 300 páginas/dia comportam cerca de 25 rankings, 200 produtos quentes, 40 primeiras visitas
  e 35 páginas de lojas, vídeos (a cada 7 dias, só quentes) e avaliações (1ª visita e a cada 30 dias, só
  quentes); as imagens têm teto próprio. Armazenamento estimado em 70 GB
  por ano no HD.
- **Mercado:** só `BR`; outro país exige outra conta e outro perfil, e o mercado acompanha o cliente de
  coleta. A dimensão existe desde já para não migrar depois.
- **Multi-tenant:** fora do escopo; o lago nasce neutro e a camada de interesse é a que receberá o tenant.
  Hoje todo usuário autenticado lê toda entidade, como no resto do produto.
- **Fora do escopo (027 e 028):** busca de vídeos por assunto ou hashtag, cruzamento com o YouTube,
  recomendações da IA, alertas, mineração de avaliações, notificação de "novo em alta" por IA.
- **Dependências:** constitution 4.4.0 (princípio IX); histórico e versionamento (VII); token e portão do
  MCP (009) como molde; fotos só de inserção e cadência (016); armazenamento no HD (constitution 2.1.0);
  notificações (006); afinidade e temas (023) só como gancho futuro; a 012 (produtos) implementada antes da
  ponte "adotar".

## Notas para o plano

Detalhes do insumo que a spec não fixa como regra de negócio, mas que o plano deve seguir
(`docs/insumos/026-mercado-shop.md`, seções "Arquitetura da 026" em diante):

- **Serviço `apps/coletor/`** (Python 3.12 + uv, `pyproject` próprio, deps `playwright` só para
  `connect_over_cdp`, `httpx`, `pydantic`); Chrome do sistema com perfil dedicado e porta de depuração
  efêmera só em loopback; interceptação das respostas da API interna por lista fechada de padrões de URL;
  cliques só em `navegacao.py` dentro de `CLIQUES_PERMITIDOS`; unidade systemd de usuário; CLI `rodar |
  uma-vez | dry-run | autoteste | perfil-iniciar | parar`; parsers no coletor com `reprocessar --desde`.
- **Pacotes `mercado/` e `coleta/`** na API com os módulos listados no insumo; `fontes/registro.py` como
  único importador do adaptador por rede (molde `publicacao/registro.py`); `coleta/portao.py` como
  dependência global (molde `mcp/portao.py`); token `scol_<8>_<43>` (molde `mcp/credenciais.py`).
- **Migration** `0025_mercado_shop` (o gate confere o próximo número livre): tabelas do lago com `rede` e
  `mercado`, trigger só-inserção reaproveitando a função da 016, bucket `sociman-mercado` no HD para imagens
  e bruto, `produtos.mercado_produto_id` na 012.
- **Trilha `mercado`** do agendador (`AGENDADOR_MERCADO_S`), `COLETA_HABILITADA`, `MERCADO_HASH_PEPPER`,
  `test_agendador_sem_trilha_nova` += `mercado`.
- **Contrato da ingestão** e **fórmulas com constantes nomeadas** exatamente como no insumo (seções
  "Contrato da ingestão" e "Cálculo na leitura"); `mcp/mapa.py` conforme a seção correspondente.
- **Guardas** da seção "Emenda da constitution" do insumo, na seção "spec 026" de
  `test_constitution_guards.py`, e `apps/coletor/tests/`.
- **Dependências do dono** X1 a X7 e a sonda do Affiliate Center como primeira tarefa prática do quickstart.
