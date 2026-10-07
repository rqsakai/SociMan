# Feature Specification: Produtos do TikTok Shop (012-produtos-shop)

**Feature Branch**: `012-produtos-shop`

**Created**: 2026-10-06

**Status**: Draft

**Input**: User description: "Cadastro de produtos do perfil com padronização (insumo
`docs/insumos/012-produtos-shop.md`): o dono envia de 1 a 6 fotos (uma por cor/variante) e uma
observação; o SociMan gera a **ficha técnica** (Claude, 1 chamada com as fotos originais, gravada antes
de qualquer passo de GPU), o **recorte** em fundo branco por variante e, para roupa ou tecido
fotografado em forma 3D, a **versão deitada (flat lay)** com 2 opções para o dono escolher. Revisão numa
folha (originais | recortes | flats) com a ficha editável, e **Aprovar**. Só produto aprovado aparece
nos seletores. Depende da 021-geracao-local (`geracoes`, `geracao_candidatos`). Referência testada:
`../comfyui-docker/pipeline/PADROES.md` (seção Produto) e `pipeline/produtos.py`."

## Clarifications

### Session 2026-10-06

Decisões já tomadas pelo dono (vêm dos insumos 012 e 021; não perguntar de novo):

- Q: O produto é do perfil ou compartilhado entre perfis? → A: **Do perfil** (`perfil_id`), como os
  assets da 007.
- Q: Quem escolhe entre as opções geradas? → A: **Toda escolha de candidato é humana.** A exceção são os
  passos só de texto (**ficha técnica do produto**, e a checagem de identidade do avatar na 025), que vão
  direto para o alvo e ficam editáveis. Não existe "escolher a opção 1 sozinho" no SociMan.
- Q: Quanto tempo ficam as opções não escolhidas? → A: São apagadas (com os arquivos) **90 dias** depois
  que a geração termina. A escolhida **nunca** é apagada.
- Q: Como fica a memória do ComfyUI? → A: O limite de RAM do container sobe para **28 GB só durante o
  job** de imagem e volta para **12 GB** logo em seguida, inclusive quando o job falha ou é cancelado; o
  worker confere se voltou (regra da 021).
- Q: A GPU tem fila única com o OpenShorts? → A: **Não.** Antes de cada job de imagem, o worker confere
  se a GPU está livre; se não estiver, o job continua na fila com a mensagem **"Aguardando a GPU ficar
  livre"** e tenta de novo depois (regra da 021).
- Q: A voz entra no produto? → A: Não. A voz é **do perfil** (spec 025); o produto não tem voz.
- Q: Quem pode aprovar um produto? → A: **Dono e membro.** Aprovar o produto é controle de qualidade do
  material de criação, não decisão de publicação; reverter continua só do dono.
- Q: Guardar link da loja, preço e comissão já nesta spec? → A: **Só o `url_loja`**, opcional e
  informativo (sem chamada à loja). Preço e comissão ficam para uma spec futura de afiliados.
- Q: A cena ganha uma marcação de "produto deitado" para usar o flat como ingrediente? → A: **Não nesta
  spec** (não está no insumo; pode vir depois). A ponte com a cena é só produto e variante.

## Contexto

O produto é o centro do vídeo do TikTok Shop. Sem um padrão, os modelos erram, como mostraram os testes
da fábrica: a foto de "manequim invisível" deitada na cama parece vestida por alguém; o planejador
escreveu "jeans" para malha canelada; peças da mesma linha saíram de tamanhos diferentes. O pipeline local
(`pipeline/produtos.py`, produto `shorts_canelado`) já resolve isso em pastas: uma ficha escrita pelo
Claude a partir das fotos, com as palavras exatas para os prompts, um recorte em fundo branco e uma versão
deitada para as cenas em que o item aparece sobre uma superfície. Esta spec leva esse cadastro para o
SociMan, com histórico, revisão humana e o ciclo de geração da 021.

O que já existe e esta spec usa:

- **Geração local (021):** o job (`geracoes`) com passo, motor, parâmetros, progresso, mensagem, erros,
  opções (`geracao_candidatos`) e escolha; a trilha `geracao` do worker; a regra da GPU e da RAM; a
  limpeza de 90 dias.
- **Imagens (003/007):** a tabela `images` (imutável, MinIO no HD), a validação pelo conteúdo e o limite
  de 20 MB da biblioteca.
- **Assistente de IA (008):** o registro de chamadas ao Claude (com custo aproximado no resumo do mês).
- **Histórico (princípio VII):** versões, autor, antes e depois, arquivar e restaurar, reversão pelo dono.
- **Cenas (010):** hoje a cena aponta o produto só por nome curto e uma foto opcional da biblioteca de
  assets. Esta spec é o catálogo de verdade e diz como a cena passa a apontar para ele.
- **Importação (013):** `shared/shop/produtos/` estava vazio; não há produto da agência a importar.

**Nada aqui publica, compra ou vende.** O produto é material de criação: dados e imagens para os prompts
e para o render. Não há pedido, carrinho, estoque, preço de venda nem integração com a loja.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cadastrar um produto e receber a ficha técnica (Priority: P1)

O dono abre a aba Produtos do perfil "Achadinhos" e cria "shorts canelado": envia 3 fotos (preto, cinza
e bege) e escreve a observação "shorts de cintura alta canelados, 3 cores, logo LS". O SociMan pede a
ficha técnica ao Claude com as 3 fotos originais e, em segundos, mostra: nome comercial "Short canelado
cintura alta", categoria, material para prompts "ribbed knit" (e em português "malha canelada"), formato e
corte, detalhes visíveis (logo "LS" bordado em branco na frente, cós largo), tamanho relativo ("all
variants identical in size and cut"), a frase em inglês para os prompts, os cuidados ("não trocar a malha
canelada por jeans", "manter o logo na mesma posição"), a descrição de venda e a cor de cada variante.
A ficha fica gravada antes de qualquer passo de GPU.

**Why this priority**: A ficha é o que corrige os erros de material, cor e tamanho. Sozinha, já serve
para copiar as palavras certas para um prompt, mesmo sem GPU.

**Independent Test**: Com o Claude falso, criar um produto com 3 fotos e conferir a ficha preenchida, as
cores por variante, o registro da chamada (com custo) e o histórico; derrubar a GPU e conferir que a
ficha continua lá e não é pedida de novo.

**Acceptance Scenarios**:

1. **Given** um perfil, **When** o dono cria um produto com nome, 3 fotos e uma observação, **Then** o
   produto nasce com as 3 variantes na ordem enviada, cada uma com a foto original intocada, e passa a
   `gerando`.
2. **Given** um produto em `gerando`, **When** a ficha chega, **Then** todos os campos da ficha e as
   cores (inglês e português) de cada variante ficam preenchidos, a origem da ficha é "IA" e a chamada
   aparece no registro do assistente com o custo aproximado.
3. **Given** uma ficha já gravada, **When** um passo de imagem falha ou a GPU está ocupada, **Then** a
   ficha continua gravada e, ao tentar de novo, o SociMan **não** chama o Claude outra vez.
4. **Given** a observação do dono diz "jeans" e as fotos mostram malha canelada, **When** a ficha chega,
   **Then** ela segue as fotos e registra a divergência em "cuidados".
5. **Given** uma foto menor que 512×512, maior que 20 MB ou num formato diferente de PNG, JPG ou WebP,
   **When** o dono envia, **Then** a foto é recusada com a explicação, antes de criar qualquer geração.

---

### User Story 2 - Recorte e versão deitada, com escolha humana (Priority: P1)

Depois da ficha, o SociMan faz o recorte de cada variante (produto em fundo branco, do mesmo tamanho da
foto). Como o shorts é roupa fotografada em forma 3D, a ficha marca "precisa da versão deitada", e o
SociMan gera, por variante, 2 opções do shorts deitado sobre fundo branco, visto de cima, sem volume de
manequim, mantendo cor, material, corte e logo da ficha. O dono vê as 2 opções lado a lado e clica em
"Usar opção 1" ou "Usar opção 2". Se nenhuma servir, "Refazer flat" gera outras opções para aquela
variante.

**Why this priority**: O recorte é a imagem do produto segurado e a versão deitada é a do produto sobre
a mesa; o render usa as duas sem gerar de novo. Sem elas, cada vídeo recria o produto e erra.

**Independent Test**: Com o ComfyUI falso, cadastrar um produto de roupa com 2 variantes e conferir os 2
recortes, as 2 × 2 opções de flat, a escolha de cada variante pelo dono, o "Refazer flat" de uma
variante e o histórico com a geração de origem; cadastrar um produto que não é roupa e conferir que não
há flat.

**Acceptance Scenarios**:

1. **Given** a ficha gravada, **When** o worker processa o produto, **Then** cada variante ganha 1
   recorte direto (sem escolha, porque o passo tem um resultado só), visível na folha de revisão.
2. **Given** um produto com "precisa da versão deitada", **When** os recortes terminam, **Then** cada
   variante ganha uma geração com 2 opções de flat, feita a partir do recorte e da ficha daquela
   variante (cor, material, corte e logo).
3. **Given** as 2 opções de uma variante, **When** o dono clica em "Usar opção 2", **Then** essa imagem
   vira o flat da variante, a variante guarda de qual geração ela veio (com a seed e a instrução) e o
   histórico do produto registra a escolha.
4. **Given** uma variante com flat escolhido, **When** o dono clica em "Refazer flat", **Then** nasce uma
   geração nova com seeds novas; a anterior fica "descartada" e o flat atual só muda quando o dono
   escolher uma das novas opções.
5. **Given** um produto que não precisa de flat (ex.: uma garrafa), **When** os recortes terminam,
   **Then** não há passo de flat e o produto vai direto para `revisao`.
6. **Given** a GPU ocupada pelo OpenShorts, **When** chega a vez de um recorte ou flat, **Then** o
   produto mostra "Aguardando a GPU ficar livre" e o passo começa sozinho quando a GPU liberar.

---

### User Story 3 - Revisar na folha, editar a ficha e aprovar (Priority: P1)

Com os recortes prontos e os flats escolhidos, o produto vai para `revisao`. O dono vê a folha: uma
linha com as fotos originais, uma com os recortes e uma com os flats, numeradas por variante, e a ficha
ao lado, editável. Ele corrige "cinza" para "cinza mescla" (`heather grey`), salva e clica em
**Aprovar**. A partir daí o produto aparece nos seletores.

**Why this priority**: É a decisão humana que fecha o cadastro. Sem aprovação, nada usa o produto.

**Independent Test**: Levar um produto até `revisao`, editar um campo da ficha, aprovar e conferir a
origem da ficha ("IA editada"), o estado, o histórico e o aparecimento no seletor; depois editar de novo
e conferir que ele volta para `revisao` e some do seletor.

**Acceptance Scenarios**:

1. **Given** um produto em `revisao`, **When** o dono abre o produto, **Then** vê a folha (originais,
   recortes e flats por variante) e a ficha completa, com os campos em inglês destacados como "vai
   literal para os prompts".
2. **Given** a ficha feita pela IA, **When** o dono edita um campo e salva, **Then** a origem passa a
   "IA editada", a versão sobe e o histórico guarda antes e depois.
3. **Given** um produto em `revisao` com todos os recortes e (se precisar) todos os flats escolhidos,
   **When** o dono clica em Aprovar, **Then** o produto vai para `aprovado` e aparece nos seletores.
4. **Given** um produto em `revisao` com uma variante ainda sem flat escolhido, **When** o dono tenta
   aprovar, **Then** a aprovação é recusada com a variante pendente indicada.
5. **Given** um produto `aprovado`, **When** alguém edita a ficha, refaz um flat ou adiciona uma
   variante, **Then** o produto volta para `revisao` e sai dos seletores até ser aprovado de novo.

---

### User Story 4 - Usar o produto aprovado nas cenas (Priority: P2)

Na cena "Achadinhos mostra o shorts" (010), o dono escolhe o produto "Short canelado cintura alta" e a
variante bege no seletor, que só lista produtos aprovados do perfil. A cena passa a usar a imagem do
produto daquela variante como ingrediente e as palavras exatas da ficha no prompt, em vez de um nome
digitado à mão.

**Why this priority**: É o primeiro uso real do catálogo, mas a cena já funciona com a referência leve
da 010; o ganho vem depois do cadastro existir.

**Independent Test**: Com um produto aprovado, ligar uma cena a ele e conferir o seletor (só aprovados),
o ingrediente, o texto do prompt, a seção "onde é usado" do produto e o comportamento de uma cena antiga
com só o nome do produto.

**Acceptance Scenarios**:

1. **Given** produtos em `rascunho`, `gerando`, `revisao` e `aprovado`, **When** o dono abre o seletor
   de produto da cena, **Then** só os aprovados (e não arquivados) do perfil aparecem.
2. **Given** uma cena ligada a um produto e a uma variante, **When** o prompt é montado, **Then** ele usa
   a frase da ficha para prompts e a cor em inglês da variante, e o ingrediente do produto é a imagem
   dessa variante.
3. **Given** um produto ligado a cenas, **When** o dono abre o produto, **Then** a seção "onde é usado"
   lista as cenas, sem bloquear o arquivamento.
4. **Given** uma cena criada antes desta spec, só com o nome do produto e uma foto da biblioteca, **When**
   o dono a abre, **Then** ela continua funcionando como antes e oferece ligar ao catálogo.

---

### User Story 5 - Lista, arquivo e histórico dos produtos (Priority: P2)

O dono vê os produtos do perfil numa lista com miniatura (recorte da primeira variante), nome comercial,
categoria, número de variantes, estado e data, filtra por estado e busca pelo nome. Arquiva o produto que
saiu de linha e restaura quando volta. Vê o histórico de cada produto e, sendo dono, reverte uma edição
errada da ficha.

**Why this priority**: Organização e segurança do cadastro; necessária, mas não bloqueia o primeiro
produto.

**Independent Test**: Criar produtos em estados diferentes e conferir filtros, busca, arquivar e
restaurar (voltando ao estado anterior), histórico e reversão pelo dono (recusada para membro).

**Acceptance Scenarios**:

1. **Given** produtos em vários estados, **When** o dono filtra por "revisão", **Then** só aparecem os
   produtos em `revisao`.
2. **Given** um produto `aprovado`, **When** o dono arquiva e depois restaura, **Then** ele volta para
   `aprovado`, sem gerar nada de novo.
3. **Given** uma edição errada da ficha, **When** o dono reverte para a versão anterior, **Then** a ficha
   volta e o histórico registra a reversão; **When** um membro tenta reverter, **Then** é recusado.

---

### User Story 6 - Agentes leem a ficha pelo MCP (Priority: P3)

O shop-roteirista, pelo MCP, lista os produtos aprovados do perfil e lê a ficha de um deles (frase para
prompts, material, cores por variante, detalhes, tamanho relativo e cuidados) para escrever o roteiro com
as palavras certas.

**Why this priority**: É a ponte para os agentes da fábrica ("a IA escreve via MCP"), mas a tela já
entrega o cadastro sem ela.

**Independent Test**: Com um cliente MCP "só leitura", listar os produtos aprovados e ler uma ficha;
conferir que produtos fora de `aprovado` não aparecem na listagem padrão e que nenhuma tool cria produto,
dispara geração, escolhe opção ou aprova.

**Acceptance Scenarios**:

1. **Given** um cliente MCP com acesso de leitura, **When** ele lista os produtos do perfil, **Then**
   recebe os aprovados com a ficha e as cores das variantes, e a chamada fica registrada (009).
2. **Given** um cliente MCP "leitura e propostas", **When** ele grava uma observação presa a um produto,
   **Then** ela aparece no produto e na caixa "Propostas dos agentes", sem mudar a ficha.
3. **Given** qualquer cliente MCP, **When** ele tenta criar, editar a ficha, escolher opção, aprovar ou
   arquivar um produto, **Then** a tool não existe para ele.

---

### Edge Cases

- **Claude sem chave ou fora do ar:** a geração da ficha falha com o erro da 021/008 (ex.:
  `claude_unconfigured`, `servico_fora`). O produto fica em `gerando` com "Tentar de novo" e com a opção
  de preencher a ficha à mão; ficha preenchida à mão tem origem "humano" e libera os passos de imagem.
- **Resposta do Claude sem ficha válida ou recusa:** a geração falha com a mensagem em pt-BR; nada é
  gravado na ficha, e a chamada fica no registro com desfecho de erro (008).
- **Falha num passo de imagem:** a geração daquele passo vai a `falhou` com o código (`sem_memoria`,
  `servico_fora`, `entrada_invalida`, `internal`); o produto continua em `gerando`, mostra o passo e a
  variante que falharam e "Tentar de novo" refaz só aquele passo. O limite de RAM volta a 12 GB (021).
- **Cancelar:** o dono cancela uma geração não final; o produto fica em `gerando` com o passo pendente e
  "Gerar de novo". Cancelar não apaga a ficha nem os recortes já prontos.
- **Ficha editada depois do flat:** como o flat é feito a partir da ficha (cor, material, corte, logo),
  mudar esses campos mostra o aviso "flat feito com a ficha anterior" na variante e sugere "Refazer
  flat", sem refazer sozinho.
- **"Precisa da versão deitada" ligado à mão:** passa a exigir flat escolhido em todas as variantes antes
  de aprovar; o SociMan oferece gerar os flats que faltam. **Desligado à mão:** os flats existentes ficam
  guardados, mas deixam de ser exigidos e não vão para o render.
- **Nova variante num produto aprovado:** a variante entra com a foto original, ganha recorte (e flat, se
  o produto precisar), as cores ficam para o dono preencher na revisão, e o produto volta para `revisao`.
- **Mais de 6 variantes ativas:** recusado ("no máximo 6 variantes por produto"); arquivar uma libera a
  vaga. Arquivar a última variante ativa é recusado ("arquive o produto").
- **Produto sem variantes ativas com recorte:** não pode ser aprovado.
- **Cena ligada a um produto que volta para `revisao` ou é arquivado:** a cena continua mostrando o
  produto e o ingrediente; ao montar o prompt de uma cena em rascunho, aparece o aviso "produto fora de
  aprovado". O seletor não oferece o produto para cenas novas.
- **Opções antigas:** 90 dias depois do fim da geração, as opções não escolhidas de flat somem (com os
  arquivos); a folha e o histórico continuam mostrando o flat escolhido.
- **Direito de imagem:** fotos de fornecedor ou de outra loja podem ter direito de uso restrito. O
  SociMan não bloqueia (como no princípio II): a responsabilidade é do dono, e a observação do produto é o
  lugar para registrar a origem das fotos.
- **Pessoa nas fotos:** a ficha descreve só o produto; o recorte remove o fundo e a pessoa. Foto de
  pessoa real não cria avatar nem consentimento (isso é da 025).
- **Duas edições ao mesmo tempo:** a segunda recebe conflito de versão e recarrega a ficha.
- **Celular:** a folha vira uma coluna por variante (original, recorte, flat empilhados), sem rolar a
  página na horizontal.

## Requirements *(mandatory)*

### Functional Requirements

**Cadastro**

- **FR-001**: O SociMan DEVE permitir criar um produto **do perfil** com nome interno (1 a 80
  caracteres), de 1 a 6 fotos (uma por cor ou variante, na ordem enviada) e uma observação livre, que
  entra no pedido da ficha.
- **FR-002**: Cada foto DEVE ser PNG, JPG ou WebP, com no mínimo 512×512 e até 20 MB, validada pelo
  conteúdo; a foto original fica guardada **intocada** e nunca é apagada.
- **FR-003**: O produto DEVE ter no máximo **6 variantes ativas**; cada variante tem posição (ordem), cor
  em inglês e em português (preenchidas pela ficha e editáveis), a foto original, o recorte, o flat (só
  quando o produto precisa) e a geração de onde o flat veio.

**Ficha técnica**

- **FR-004**: Ao enviar as fotos, o SociMan DEVE pedir a ficha ao Claude numa **única chamada** com as
  fotos originais, o nome e a observação, e gravar o resultado **antes** de qualquer passo de imagem. A
  ficha vai direto para o produto (passo só de texto, sem escolha) e fica editável.
- **FR-005**: A ficha DEVE ter: nome comercial (pt-BR); categoria (ex.: "roupa > shorts"); material para
  prompts em inglês (2 a 5 palavras exatas, ex.: "ribbed knit"); material em português; formato e corte;
  detalhes visíveis (logo com texto, cor e posição; cós; costuras); tamanho relativo (ex.: "all variants
  identical in size and cut"); descrição para prompts (1 frase em inglês, usada literalmente); cuidados
  (lista em pt-BR do que os modelos de vídeo erram neste produto); descrição de venda (pt-BR, 2 a 3
  frases, só o que se vê nas fotos); "precisa da versão deitada" (roupa ou tecido fotografado em forma
  3D); e a cor de cada variante.
- **FR-006**: O pedido da ficha DEVE instruir o modelo a seguir **o que se vê nas fotos** (material,
  cor, logo, corte), a preferir as fotos quando a observação divergir e registrar a divergência em
  "cuidados", a afirmar tamanho idêntico quando as fotos forem variantes de cor do mesmo item, e a nunca
  inventar o que não se vê (composição do tecido, medidas, preço, benefícios).
- **FR-007**: A chamada da ficha DEVE entrar no **registro de chamadas do assistente (008)**, com custo
  aproximado, entrada e desfecho, ligada ao produto. Uma falha em passo de imagem NÃO DEVE gerar nova
  chamada ao Claude.
- **FR-008**: A ficha DEVE guardar sua **origem**: `ia` (como veio), `ia_editada` (veio da IA e uma
  pessoa editou) ou `humano` (preenchida à mão, sem IA). Editar à mão muda a origem e, num produto
  `aprovado`, devolve o produto a `revisao`.

**Imagens (recorte e flat)**

- **FR-009**: Para cada variante, o SociMan DEVE gerar o **recorte**: o produto em fundo branco, do mesmo
  tamanho da foto, em uma geração de resultado único, que vai direto para a variante; a revisão humana
  dele acontece na folha, antes da aprovação.
- **FR-010**: Quando a ficha marca "precisa da versão deitada", o SociMan DEVE gerar, por variante, uma
  geração de **flat** com **2 opções**, a partir do recorte e com a instrução montada da ficha daquela
  variante (cor em inglês, material, formato e corte, detalhes visíveis): o mesmo item deitado,
  relaxado, sobre fundo branco liso, visto de cima, sem volume de corpo ou manequim.
- **FR-011**: O flat de cada variante DEVE ser **escolhido por uma pessoa** ("Usar opção N"). Escolher
  grava a imagem na variante, a geração de origem (com seed e instrução) e uma versão do produto com a
  geração no histórico.
- **FR-012**: "Refazer flat" de uma variante DEVE criar uma geração nova com seeds novas; a anterior fica
  descartada, e o flat vigente só muda com a nova escolha.
- **FR-013**: Produto que não precisa de flat (inclusive todo produto que não é roupa ou tecido) NÃO
  DEVE ter passo de flat.
- **FR-014**: Os passos de imagem DEVEM seguir a trilha de geração da 021: no máximo um job de GPU por
  vez, só com a GPU livre ("Aguardando a GPU ficar livre" enquanto espera), limite de RAM do ComfyUI em
  28 GB só durante o job e de volta a 12 GB ao fim (também em falha e cancelamento), progresso e mensagem
  em pt-BR, "Tentar de novo" e "Cancelar".
- **FR-015**: As opções não escolhidas DEVEM ser apagadas (com os arquivos) 90 dias depois do fim da
  geração; as escolhidas, os recortes e as fotos originais NUNCA são apagados.

**Estados e revisão**

- **FR-016**: O produto DEVE ter os estados `rascunho` (criado, fotos ainda não enviadas) → `gerando`
  (ficha, recortes e flats em andamento) → `revisao` (ficha gravada, todos os recortes prontos e, se
  preciso, todos os flats escolhidos) → `aprovado`; e `arquivado`, alcançável de qualquer estado, que ao
  restaurar volta ao estado anterior.
- **FR-017**: A tela do produto DEVE mostrar a **folha de revisão**: originais, recortes e flats, uma
  linha cada, numerados por variante, com a ficha completa ao lado e editável, e os campos em inglês
  marcados como "vai literal para os prompts".
- **FR-018**: **Aprovar** DEVE exigir ficha completa, ao menos uma variante ativa, recorte em todas as
  variantes ativas e, se o produto precisa de flat, flat escolhido em todas. Faltando algo, a aprovação é
  recusada indicando o que falta.
- **FR-019**: Editar a ficha, refazer um flat ou adicionar variante num produto `aprovado` DEVE
  devolvê-lo a `revisao`.
- **FR-020**: Só produto `aprovado` e não arquivado DEVE aparecer nos seletores de vídeo, cena e roteiro.
- **FR-021**: **Aprovar** é de dono e membro (controle de qualidade, não publicação). Criar, editar, enviar fotos,
  escolher opções, refazer flat e arquivar são de dono e membro; **reverter** é só do dono.

**Lista, histórico e uso**

- **FR-022**: A aba Produtos do perfil DEVE listar os produtos com miniatura (recorte da primeira variante
  ativa), nome comercial (ou o nome interno, antes da ficha), categoria, número de variantes, estado e
  data, com filtro por estado, busca por nome e a opção de ver os arquivados.
- **FR-023**: Produtos e variantes NUNCA são apagados: arquivar e restaurar. Toda mutação (criar, editar
  a ficha, escolher flat, adicionar, reordenar ou arquivar variante, aprovar, arquivar, restaurar) DEVE
  registrar autor, antes e depois, com versão (conflito em edição concorrente) e reversão pelo dono
  (princípio VII), num histórico de tipo `produto`. A reversão NÃO DEVE gerar imagens de novo.
- **FR-024**: O produto DEVE mostrar **onde é usado** (padrão da 007): as cenas ligadas a ele, sem
  bloquear o arquivamento.

**Ponte com as cenas (010)**

- **FR-025**: A cena DEVE poder apontar para um **produto do catálogo** e, opcionalmente, para uma
  **variante** dele, escolhidos num seletor que só lista produtos aprovados do perfil. Com produto do
  catálogo, o prompt da cena DEVE usar a descrição para prompts da ficha e a cor em inglês da variante, e
  o ingrediente do produto DEVE ser o recorte da variante (ou da primeira variante ativa, sem variante).
- **FR-026**: A referência leve da 010 (nome curto e foto da biblioteca) DEVE continuar valendo para as
  cenas existentes, sem migração forçada; a cena com referência leve DEVE oferecer "Ligar ao catálogo".
  Cenas `pronta` e `usada` mantêm o prompt congelado; ligar ao catálogo segue as regras de edição e
  "Remontar prompt" da 010.

**MCP (009)**

- **FR-027**: O MCP DEVE expor, em leitura, a lista dos produtos do perfil (por padrão só os aprovados) e
  a ficha de um produto com as cores das variantes e os links das imagens. Com o escopo "leitura e
  propostas", o agente PODE gravar uma observação presa a um produto (anotação da 009). Nenhuma tool DEVE
  criar produto, editar a ficha, disparar geração, escolher opção, aprovar ou arquivar.

**Limites**

- **FR-028**: Nada nesta spec DEVE publicar, comprar, vender, consultar ou alterar loja, estoque ou
  pedido.
- **FR-029**: O produto PODE guardar o **link do produto no TikTok Shop** (`url_loja`), opcional e só
  informativo: o SociMan não acessa a loja por ele. Preço e comissão não entram nesta spec (spec futura
  de afiliados).

### Key Entities

- **Produto:** item de venda do perfil, material de criação para os vídeos. Nome interno, ficha técnica
  (nome comercial, categoria, material em inglês e português, formato e corte, detalhes visíveis, tamanho
  relativo, descrição para prompts, cuidados, descrição de venda, precisa da versão deitada), observação
  do dono, link da loja (opcional, FR-029), estado, origem da ficha, versão, arquivamento e autoria.
- **Variante do produto:** uma por foto ou cor, em ordem. Cor em inglês e português, foto original,
  recorte, flat (quando o produto precisa) e a geração de onde o flat veio. Até 6 ativas.
- **Geração (021):** o job de cada passo (`produto.ficha`, `produto.recorte`, `produto.flat`), com motor,
  parâmetros, progresso, erro e a opção escolhida; o alvo é o produto.
- **Opção de geração (021):** cada candidato de flat (imagem e seed); as não escolhidas expiram em 90
  dias.
- **Imagem (003/007):** arquivo imutável no MinIO; ganha a classe técnica `produto`.
- **Cena (010):** ganha o vínculo opcional com produto e variante do catálogo, ao lado da referência leve.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O dono vai de "criar produto" à folha de revisão de um produto de 3 fotos sem sair da tela
  do produto e sem nenhum passo manual entre a ficha e os recortes (com a GPU livre).
- **SC-002**: Em 100% dos testes com falha ou cancelamento de passo de imagem, a ficha não é pedida de
  novo ao Claude (uma chamada de ficha por cadastro) e o limite de RAM volta a 12 GB.
- **SC-003**: 100% dos produtos oferecidos nos seletores estão `aprovado` e não arquivados.
- **SC-004**: 100% dos flats em uso foram escolhidos por uma pessoa, com a geração de origem no
  histórico.
- **SC-005**: Nenhuma opção não escolhida com mais de 90 dias continua guardada, e nenhuma escolhida,
  recorte ou foto original é apagada.
- **SC-006**: Achar e copiar a descrição para prompts de um produto aprovado leva menos de 15 segundos a
  partir da aba Produtos.
- **SC-007**: No celular (390 px), a folha de revisão e a ficha cabem sem rolar a página na horizontal.

## Assumptions

- **Dependência:** a 021-geracao-local entrega `geracoes`, `geracao_candidatos`, a trilha `geracao` do
  worker (GPU, RAM, backoff, cancelar) e a limpeza de 90 dias antes ou junto desta spec. Esta spec só
  acrescenta os passos `produto.*` e o alvo `produto`.
- **Modelo da ficha:** o mesmo padrão testado em `pipeline/produtos.py` (Claude com as fotos e saída
  estruturada validada); a escolha exata de modelo e esforço fica no plano.
- **Blocos de imagem:** recorte com o bloco `cutout` (BiRefNet) e flat com o bloco de edição do pipeline
  (Qwen Edit), pelos contratos de `workflows/api/*.params.json`, como a 021 define.
- **Sem importação:** não há produtos da agência para importar (013) nem catálogo do TikTok Shop
  (fora do escopo).
- **Fora do escopo:** importar catálogo do TikTok Shop; preço e estoque; flat lay para o que não é roupa
  (fica sem flat); render de vídeo e storyboard (spec futura do motor de cenas); roteiros (011).
- **Uso futuro:** o planejador de vídeo (spec futura) recebe, por produto, as fotos originais, a
  descrição para prompts, o material em inglês, as cores, os detalhes visíveis, o tamanho relativo e os
  cuidados; o render usa o recorte (produto segurado) e o flat (produto deitado), sem gerar de novo; e
  "onde é usado" ganha a origem `video`.
- **Direito de imagem do produto:** risco do dono, sem bloqueio nem campo próprio nesta spec (ver Edge
  Cases).

## Notas para o plano

> **Resolvido no plano (2026-10-07):** `detalhes_visiveis` vira `text[]` e `formato_corte` é em
> inglês (research R2); a seed fica na opção da 021 e a variante guarda só `flat_geracao_id` (R3); o
> `produto_status` não tem `arquivado`, que é estado efetivo por `archived_at`, e restaurar mantém o status
> (R4). O modelo final está em `data-model.md`; a lista abaixo é o insumo original.

Do insumo `docs/insumos/012-produtos-shop.md` (levar ao `data-model.md` sem inventar campo):

- **`produtos`:** `id`, `perfil_id` (FK), `name` (1..80), `nome_comercial`, `categoria`, `material_en`,
  `material_pt`, `formato_corte`, `detalhes_visiveis`, `tamanho_relativo`, `descricao_prompt`,
  `cuidados` (text[]), `descricao_venda`, `precisa_flat` (bool), `obs`, `url_loja` (text null, FR-029), `status` (enum `produto_status`: `rascunho`, `gerando`, `revisao`, `aprovado`, `arquivado`),
  `ficha_por` (enum `ia`, `humano`, `ia_editada`), `version`, `archived_*`, AuditMixin; histórico em
  `entity_versions` com `entity_type = produto`. Restaurar volta ao estado anterior: o plano decide onde
  guardar esse estado (o insumo tem `status = arquivado` **e** `archived_*`).
- **`produto_variantes`:** `id`, `produto_id` (FK), `position` (smallint), `cor_en`, `cor_pt`,
  `original_image_id` (FK images), `recorte_image_id` (null), `flat_image_id` (null, só com
  `precisa_flat`), `flat_geracao_id` (null, FK geracoes), `archived_*`. Como os `asset_files` da 007, sem
  versão própria: toda mudança é uma versão do produto (snapshot com as variantes).
- **`images.kind`** ganha `produto` (PNG/JPG/WebP, mínimo 512×512, 20 MB). O edge precisa de uma
  `location` com `client_max_body_size` próprio (como os assets, 21m) para a recusa vir da API.
- **021:** `alvo_tipo = produto`; passos `produto.ficha` (motor `claude`, só texto, resultado no alvo),
  `produto.recorte` (`comfyui`, `n_opcoes = 1`), `produto.flat` (`comfyui`, `n_opcoes = 2`). A chamada
  da ficha também vai para `ia_chamadas` (008) com `entity_type = produto`.
- **010:** a cena hoje tem `produto_nome` (≤ 120) e `produto_imagem_id` (FK **assets**, tipo `imagem`,
  com CHECK que exige o nome). A ponte acrescenta `produto_id` e `produto_variante_id` (null) sem remover
  os dois campos antigos; o plano define o CHECK entre os dois modos e a mudança na montagem do prompt
  (FR-003 da 010: "exactly as in the reference image" mais a frase da ficha), e o provedor de uso
  `origem: "cena"` para o produto.
- **Uso:** provedor "onde é usado" do produto (cenas agora; `video` na spec do motor de cenas).

## Divergências entre o insumo e a referência (para o plano decidir)

- **Flat:** o pipeline gera **1** flat por variante (seed 42) e "refazer" troca direto; o insumo pede
  **2 opções** com escolha humana. Esta spec segue o insumo e a regra do dono (escolha humana).
- **Recorte:** o insumo diz "sem escolha: 1 resultado direto", e a regra do dono diz que toda escolha de
  candidato é humana. Conciliação desta spec: com um resultado só não há escolha; o controle humano é a
  revisão da folha antes de aprovar. Não há "refazer recorte" no insumo.
- **Tipos:** no pipeline, `detalhes_visiveis` e `cuidados` são listas, e `formato_corte` e
  `detalhes_visiveis` são em inglês (vão para a instrução do flat); no insumo, `detalhes_visiveis` é
  `text` e o idioma de `formato_corte` não é dito. O exemplo de `categoria` também difere ("roupa >
  shorts" × "moda feminina / shorts").
- **Seed do flat:** o pipeline guarda `fotos[].flat_seed`; o insumo guarda `flat_geracao_id` (a seed fica
  na opção da 021).
- **Catálogo na 010:** a spec 010 diz que a 012 traria "USPs, fotos oficiais, preços"; o insumo deixa
  preço fora do escopo e não tem USP. Esta spec segue o insumo.
