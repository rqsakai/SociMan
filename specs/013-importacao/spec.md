# Feature Specification: Importação da agência (013-importacao)

**Feature Branch**: `013-importacao`

**Created**: 2026-10-06

**Status**: Draft

**Input**: User description: "Migrar `../shared/perfis/*` e `../shared/shop/*` (o markdown que os agentes do
OpenClaw usam como banco até ~3 perfis) para o banco do SociMan. Importação idempotente e auditável
(princípio VII: autor, histórico, nada apagado; reexecutar não duplica), mapeamento explícito
arquivo→entidade, pré-visualização antes de gravar (o que entra, o que conflita com dado já editado no
SociMan, o que fica de fora), só o dono humano dispara, status de direito vindo do `fontes.md` mapeado
para os 4 status atuais (princípio II: o SociMan registra e avisa, o dono decide), imagens da persona e
dos avatares para a biblioteca de assets (MinIO no HD), destino dos arquivos markdown depois da
importação (com o MCP da 009 os agentes podem ler do SociMan) e escopo delimitado em relação às specs
010 (cenas), 011 (scripts) e 012 (produtos)."

## Contexto

A agência roda com 8 agentes de cortes e 3 da fábrica TikTok Shop no OpenClaw, que leem e gravam
markdown em `../shared/` (regra da agência: markdown é o "banco" até ~3 perfis; depois, migrar). Com a
009, os agentes já podem ler e propor pelo MCP do SociMan, mas o estado da agência continua espalhado
nos arquivos.

**O que existe em `../shared/` (levantamento de 2026-10-06, só leitura):** 71 arquivos, 5,1 MB, sendo 53
markdown (≈3.050 linhas) e 18 imagens JPEG.

| Grupo | Arquivos | Conteúdo |
|---|---|---|
| `perfis/INDEX.md` | 1 | tabela dos perfis: `queridinhos` e `atavernanerd`, ambos `ativo` |
| `perfis/<slug>/perfil.md` | 2 | 8 seções fixas (molde `_modelo/perfil.md`): identidade e @, nicho e pilares, público, tom e expressões da casa, estilo visual (prosa), monetização, metas, decisões (tabela com 11 e 13 linhas) |
| `perfis/<slug>/fontes.md` | 2 | tabela de fontes com status de direito: 15 linhas em `queridinhos`, 14 em `atavernanerd` |
| `perfis/<slug>/pesquisa.md` | 2 | pesquisa de nicho em prosa e tabelas (183 e 72 linhas) |
| `perfis/atavernanerd/ideias-gravacao.md` | 1 | pautas para o dono gravar |
| `perfis/<slug>/registro-clipes.md` | 2 | 47 e 21 clipes do lote de teste de 25/09 (fonte, trecho, título, status, métricas "sem dado") |
| `candidatos/`, `semana/`, `dia/`, `clipes/` | 7 | saídas operacionais da rodada de teste (caçada, planos, pacotes de clipes) |
| `perfis/atavernanerd/assets/` | 16 imagens | logo, foto de perfil, avatar em 5 poses (1 grade + 5 avulsas), 6 stickers e 2 rascunhos marcados `CHECKERBOARD-nao-usar-ainda` |
| `perfis/_modelo/`, `modelos/` | 10 | moldes vazios |
| `agencia.md`, `aprendizados.md`, `custos.md` | 3 | manual dos agentes; aprendizados e custos vazios |
| `shop/persona.md` + `shop/persona/` | 1 + 2 imagens | persona "Achadinhos": descrição fixa para prompt, 2 cenários, voz, regras de imagem e 2 imagens de referência |
| `shop/nicho.md` | 1 | tudo "A DEFINIR" |
| `shop/README.md`, `fontes-dados.md` | 2 | processo da fábrica e pesquisa de fontes de dados de produto |
| `shop/avatares.md`, `avatares-candidatos.md`, `vozes-pt.md` | 3 | HeyGen (pausado desde 24/09) |
| `shop/produtos/`, `roteiros/`, `pacotes/` | 0 | ainda não existem |

Nenhum arquivo de `shared/` tem chave ou token; mesmo assim, a importação nunca copia um arquivo fora do
mapeamento (FR-006).

**Boa parte já foi passada à mão para o SociMan** (conferido no banco de dev, só leitura, em
2026-10-06):

- os 2 perfis (`queridinhos`, `atavernanerd`), com nicho, bio e logo, e as 3 contas (`@meusqueridinhos10`
  na TikTok; `@atavernanerd` na TikTok e no YouTube);
- **21 das 29 fontes** como canais-fonte, com a nota "fontes.md: status `…`" na evidência. O mapeamento
  feito à mão foi: canal próprio → `proprio`; `programa-de-cortes` → `programa_de_cortes`; `autorizado`
  → `parceiro`; e **3 fontes `pendente` também viraram `parceiro`** (Fofocalizando, Vênus Podcast, De
  Frente com Blogueirinha). As 8 que faltam não têm canal do YouTube identificável (handle "não
  confirmado", site, Twitch, canal "a confirmar", ou "Material original próprio", que é uma pasta);
- **todas as 16 imagens utilizáveis**, idênticas byte a byte (mesmo SHA-256): o avatar "Dragão da
  Taverna" com as poses, a foto de perfil, os 6 stickers (como `imagem`), o logo, e em `queridinhos` o
  avatar "Achadinhos" com as 2 imagens e os 2 cenários. Só os 2 rascunhos `CHECKERBOARD` ficaram de fora;
- os kits de marca dos 2 perfis com 6 bordões cada.

O que **não** está no SociMan: o **guia de comunicação** (017) dos 2 perfis, que está vazio; público,
monetização, metas e decisões dos perfis; a pesquisa e as pautas; as 8 fontes restantes; e os 70
clipes prontos do lote de 25/09 (em `../media/clipes/<slug>/2026-09-25/`, 896 MB; 48 + 22 vídeos para 47 + 21 linhas de registro), que nunca entraram
na Central de conteúdos (014).

Por isso, esta spec é menos uma "carga inicial" e mais uma **conciliação**: lê os arquivos, encontra o
que já existe, mostra o que é igual, o que diverge do que o dono editou e o que falta, e grava só o que
o dono confirmar. Ela também serve para os próximos perfis criados pelos agentes antes de migrarem de
vez para o MCP.

### Mapeamento arquivo → entidade

| Origem em `shared/` | Destino no SociMan | Chave de conciliação | Observação |
|---|---|---|---|
| `perfis/INDEX.md` + `perfil.md` (frontmatter, §1 e §2) | **Perfil** (003): slug, nome, idioma, status, nicho (até 200 caracteres) | slug | status: `ativo` → `ativo`; `pausado` → `pausado`; `onboarding`, `pesquisa` e `aguardando-aprovacao` → `em_preparacao` |
| `perfil.md` §1 (@ no YouTube e no TikTok) | **Conta** (003): plataforma, @ e URL | plataforma + @ normalizado | "Nenhum" não cria conta |
| `perfil.md` §4 (tom, expressões da casa, proibido) | **Guia de comunicação do perfil** (017): tom, vocabulário e "não faça" | perfil | só preenche guia vazio (FR-019) |
| `perfil.md` §4 (expressões da casa) | **Bordões do kit** (004) | texto normalizado | só compara e sugere; nunca troca o kit (FR-020) |
| `perfil.md` §3 (público), §6 (monetização), §7 (metas), §8 (decisões) | **Anotação** de observação no perfil (009) | impressão digital do trecho | uma por seção; uma por linha de decisão |
| `perfil.md` §5 (estilo visual) | fora | — | prosa não vira token (princípio III); só a referência ao logo é usada |
| `fontes.md` (cada linha) | **Canal-fonte** (006) + vínculo com o perfil + direito e evidência | canal do YouTube (id) | status proposto por linha (FR-014) |
| `pesquisa.md` (cada seção `##`), `ideias-gravacao.md` | **Anotação** de observação no perfil | impressão digital do trecho | lidas pelos agentes pelo MCP |
| `assets/*.jpg`, `assets/avatar-poses/`, `assets/stickers/` | **Asset** (007) e logo do perfil (003) | SHA-256 da imagem | `logo.jpg` → logo; `avatar-*` → poses do avatar; `sticker-*` → `sticker`; `foto-perfil` → `imagem` |
| `*nao-usar-ainda*` | fora | — | o próprio nome diz para não usar |
| `shop/persona.md` + `shop/persona/*.jpg` | **Asset avatar** (descrição → prompt, voz → tom de voz, regras → regras de imagem, imagens → referências com o look) e 2 **assets cenário** (prompt) | SHA-256 e nome | no perfil que o dono escolher (FR-024) |
| `registro-clipes.md` + `../media/clipes/` | **Conteúdo** de vídeo próprio (014), sem destino | SHA-256 do vídeo | FR-026; linha e vídeo casam pelo ID |
| `candidatos/`, `semana/`, `dia/`, `clipes/`, `revisoes/` | fora | — | arquivo operacional da rodada de teste, sem entidade |
| `_modelo/`, `modelos/`, `agencia.md`, `aprendizados.md`, `custos.md` | fora | — | moldes e manual dos agentes |
| `shop/nicho.md`, `shop/fontes-dados.md`, `shop/README.md` | fora | — | ficam para a 012 (produtos) |
| `shop/avatares*.md`, `shop/vozes-pt.md` | fora | — | HeyGen pausado |
| `shop/produtos/`, `roteiros/`, `pacotes/` | fora | — | não existem; serão das specs 011 e 012 |

## Clarifications

### Session 2026-10-06

- Q: O status `autorizado` do `fontes.md` vira qual dos 4 status do SociMan? → A: A pré-visualização
  propõe `sem_acordo`, e o dono pode trocar para `parceiro` linha a linha; um canal que já existe nunca
  muda de status sem a escolha explícita do dono naquele item (FR-014, FR-015).
- Q: O que fazer com o `registro-clipes.md` e os 70 clipes prontos de `../media/clipes/`? → A: Cada clipe
  com linha no registro vira um conteúdo de vídeo próprio da 014, sem destino, com deduplicação pelo
  SHA-256 do vídeo; os ≈900 MB vão para o HD, com o marcador e o piso de espaço livre (FR-026).
- Q: Depois da importação, quem é a fonte da verdade? → A: O SociMan. O markdown fica como arquivo (o
  SociMan nunca escreve nele), os agentes leem pelo MCP, e a reimportação é manual e só traz o que é novo
  (FR-027).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pré-visualizar a importação sem gravar nada (Priority: P1)

O dono abre "Importar da agência" e pede a leitura da pasta `shared/`. O SociMan lê os arquivos do
mapeamento e mostra um **relatório de pré-visualização**, agrupado por perfil e por tipo de item. Cada
item aparece numa destas situações:
- **novo:** vai ser criado;
- **igual:** já existe com o mesmo conteúdo, e nada muda;
- **diverge:** já existe, mas com valor diferente no SociMan (mostra os dois lados);
- **fora:** não entra, com o motivo (sem destino nesta spec, rascunho, sem canal identificável, arquivo
  de outra spec).

Cada item mostra o arquivo e o trecho (seção ou linha) de onde veio. Nada é gravado.

**Why this priority**: Já existe dado editado à mão no SociMan. Sem ver antes o que vai mudar, o dono
não confia na importação, e um erro pode estragar o que já está certo.

**Independent Test**: Com uma pasta de teste que tem 1 perfil novo, 1 perfil igual ao banco, 1 fonte
divergente e 1 arquivo fora do mapeamento, pedir a pré-visualização e conferir as 4 situações, as
contagens e a origem de cada item. Conferir também que nenhuma linha do banco mudou.

**Acceptance Scenarios**:

1. **Given** a pasta `shared/` atual e o banco de hoje, **When** o dono pede a pré-visualização,
   **Then** vê os 2 perfis e as 3 contas como "igual", 18 das 21 fontes já cadastradas como "igual",
   as 3 `pendente` que estão como `parceiro` como "diverge (direito)", as 8 restantes como "fora (sem canal do YouTube identificável)", as 16 imagens como
   "igual" e os 2 rascunhos `CHECKERBOARD` como "fora".
2. **Given** a pré-visualização aberta, **When** o dono não confirma em 30 minutos, **Then** ela expira e
   nada é gravado.
3. **Given** um membro, ou um cliente que não é humano (IA, agente, MCP), **When** tenta ler, confirmar
   ou desfazer, **Then** é recusado ("só o dono"), e a recusa a quem não é humano fica registrada.
4. **Given** um arquivo do mapeamento com formato inesperado (seção do molde faltando, tabela com colunas
   trocadas), **When** a pré-visualização abre, **Then** aquele arquivo aparece como "não reconhecido",
   com a seção ou a coluna que faltou, e os outros arquivos seguem normalmente.
5. **Given** a pasta inacessível ou vazia, **When** o dono pede a leitura, **Then** recebe uma mensagem
   clara ("a pasta da agência não está disponível") e nada acontece.

---

### User Story 2 - Confirmar e gravar, com histórico, sem duplicar (Priority: P1)

Na pré-visualização, o dono escolhe o que entra. Os itens **novos** vêm marcados. Nos itens que
**divergem**, a escolha padrão é "manter o SociMan", e ele pode trocar, item a item, para "usar o
markdown". Ao confirmar, tudo é gravado de uma vez. Cada mudança vai para o histórico da entidade, com o
dono como autor e a marca "importado de `<arquivo>` §`<trecho>`". A importação fica registrada: quem,
quando, quais arquivos (com a impressão digital de cada um) e o resultado por item.

Rodar a importação de novo, sobre os mesmos arquivos, não cria nada: tudo aparece como "igual".

**Why this priority**: É a parte que grava. A idempotência e o histórico são o que torna seguro rodar a
importação mais de uma vez (os agentes continuam gravando markdown até migrarem).

**Independent Test**: Importar a pasta de teste e conferir as entidades criadas, o histórico de cada uma
(autor, origem) e o registro da importação. Rodar de novo e conferir 0 itens novos e nenhuma versão nova
em nenhuma entidade.

**Acceptance Scenarios**:

1. **Given** a pré-visualização com 3 itens novos e 1 divergente em "manter o SociMan", **When** o dono
   confirma, **Then** os 3 são criados, o divergente fica igual, e o registro da importação lista os 4
   com o resultado.
2. **Given** um item divergente trocado para "usar o markdown", **When** o dono confirma, **Then** a
   entidade ganha uma versão nova, com o valor anterior no histórico e a origem da importação, e o dono
   pode reverter essa versão pelo histórico, como qualquer outra.
3. **Given** uma importação já confirmada, **When** o dono roda a importação de novo sem mudar os
   arquivos, **Then** a pré-visualização mostra 0 novos, e confirmar não grava nada.
4. **Given** um agente que acrescentou uma linha nova em `fontes.md` depois da última importação, **When**
   o dono importa de novo, **Then** só essa linha aparece como nova.
5. **Given** dois cliques em confirmar, ou uma segunda aba, **When** as duas confirmações chegam,
   **Then** só a primeira grava, e a outra recebe "esta pré-visualização já foi usada ou expirou".
6. **Given** que o dono editou no SociMan um item que estava na pré-visualização entre a leitura e a
   confirmação, **When** ele confirma, **Then** aquele item não é gravado e aparece como "mudou desde a
   leitura; leia de novo", e o resto segue.

---

### User Story 3 - Fontes e status de direito (Priority: P1)

Cada linha de `fontes.md` vira (ou é conciliada com) um canal-fonte ligado ao perfil. O SociMan
identifica o canal do YouTube pelo link ou pelo @ (usando a cota do YouTube, como no cadastro manual da
006). O status de direito é **proposto** a partir do status do markdown, e o dono confere cada linha
antes de confirmar. A evidência, as regras do programa, quem confirmou e a data vão para a evidência do
canal (link e nota). Linhas sem canal do YouTube identificável ficam **fora**, numa lista de "fontes para
o dono cadastrar à mão", com o motivo.

**Why this priority**: O direito é um princípio inegociável (II). O status vem de decisões do dono
registradas no markdown, e a importação não pode mudá-las sem ele ver. Os 3 `pendente` que viraram
`parceiro` à mão mostram que esse mapeamento precisa ficar explícito.

**Independent Test**: Com um `fontes.md` de teste que tem uma linha de cada status (`autorizado`,
`programa-de-cortes`, `pendente`, `negado`, `desconhecido`), uma de canal próprio, uma sem link e uma já
cadastrada com outro status, conferir o status proposto, a lista "fora" e que o canal já cadastrado
mantém o status dele.

**Acceptance Scenarios**:

1. **Given** uma linha `programa-de-cortes` de canal novo, **When** a pré-visualização abre, **Then** o
   canal aparece como novo, com o status `programa_de_cortes` e a evidência e as regras na nota.
2. **Given** uma linha de canal já cadastrado cujo status no SociMan difere do mapeado, **When** a
   pré-visualização abre, **Then** aparece como "diverge (direito)", com os dois status. A troca exige a
   escolha explícita do dono naquele item e fica no histórico do canal com o autor (princípio II).
3. **Given** uma linha com "handle não confirmado", site, Twitch ou TikTok, **When** a pré-visualização
   abre, **Then** a linha fica "fora: sem canal do YouTube identificável", com o texto original para o
   dono cadastrar depois.
4. **Given** a cota do YouTube esgotada, **When** a pré-visualização tenta identificar canais novos,
   **Then** essas linhas aparecem como "aguardando cota" (não "fora"), e o resto da pré-visualização
   funciona.
5. **Given** um canal já cadastrado e ligado a outro perfil, **When** o `fontes.md` de um perfil o cita,
   **Then** a importação só acrescenta o vínculo com o perfil, sem duplicar o canal nem mudar o direito.

---

### User Story 4 - Imagens na biblioteca de assets (Priority: P2)

As imagens do perfil e da persona vão para a biblioteca de assets (007), no armazenamento de arquivos no
HD. Uma imagem que já existe no perfil (mesmo SHA-256) não é enviada de novo: aparece como "igual". As
poses do avatar ficam no mesmo asset avatar; os stickers viram assets `sticker` quando têm transparência
e `imagem` quando não têm (o mesmo critério do cadastro manual). O logo vira o logo do perfil se o
perfil ainda não tem um.

**Why this priority**: Hoje todas as imagens utilizáveis já estão no SociMan. O valor está nos próximos
perfis e em provar que reimportar não duplica arquivo no HD.

**Independent Test**: Com uma pasta de teste que tem 1 imagem já no banco e 2 novas (uma com
transparência, outra sem), importar e conferir 0 arquivos novos para a primeira e o tipo certo das
outras duas. Reimportar e conferir 0 arquivos novos no armazenamento.

**Acceptance Scenarios**:

1. **Given** as 16 imagens atuais, já no SociMan, **When** a pré-visualização abre, **Then** todas
   aparecem como "igual" e nenhuma é enviada.
2. **Given** um arquivo com `nao-usar-ainda` no nome, **When** a pré-visualização abre, **Then** ele fica
   "fora" com esse motivo.
3. **Given** uma imagem inválida (corrompida, formato não aceito, acima do limite de 20 MB da 007),
   **When** a pré-visualização abre, **Then** só ela fica "fora" com o motivo da validação.
4. **Given** o HD desmontado (sem o marcador) ou abaixo do piso de espaço livre, **When** o dono
   confirma uma importação com imagens novas, **Then** a importação inteira é recusada antes de gravar,
   com o motivo, como nos outros envios.

---

### User Story 5 - Guia de comunicação e notas do perfil (Priority: P2)

Do `perfil.md`, o tom, as expressões da casa e os temas proibidos preenchem o **guia de comunicação do
perfil** (017) quando ele está vazio. Público, monetização, metas, decisões, pesquisa e pautas viram
**anotações** de observação no perfil (009), cada uma com o arquivo e a seção de origem, para o dono e
para os agentes (pelo MCP) lerem no SociMan, em vez de no markdown.

**Why this priority**: É o que ainda não está no SociMan e o que os agentes mais leem (tom, proibidos,
decisões). O guia vazio hoje faz o assistente de IA (008) gerar sem a voz do perfil.

**Independent Test**: Com um perfil de teste com guia vazio, importar e conferir o tom, o vocabulário e
o "não faça" do guia (versão 1, com histórico), e as anotações com a origem. Com o guia já editado,
conferir "diverge" e nenhuma mudança.

**Acceptance Scenarios**:

1. **Given** o guia do perfil vazio, **When** o dono importa, **Then** o guia ganha a versão 1: tom (do
   campo "Tom"), vocabulário (das "Expressões da casa", uma por termo) e "não faça" (de "Proibido").
2. **Given** o guia do perfil já editado no SociMan, **When** a pré-visualização abre, **Then** o guia
   aparece como "diverge", mostrando os dois lados, e só é trocado se o dono escolher "usar o markdown".
3. **Given** a tabela "Decisões e histórico" com 13 linhas, **When** o dono importa, **Then** surgem 13
   anotações, cada uma com a data da decisão, o texto e o "por quê", e reimportar não as repete.
4. **Given** as "Expressões da casa" com termos que não estão nos bordões do kit, **When** a
   pré-visualização abre, **Then** esses termos aparecem como sugestão de bordão, sem mudar o kit.

---

### User Story 6 - Clipes prontos do lote de teste (Priority: P3)

Os clipes prontos do lote de 25/09 (70 vídeos em `../media/clipes/`, 68 com linha no
`registro-clipes.md`) entram na Central de conteúdos como vídeo próprio,
com título, fonte e trecho do registro, para o dono revisar e agendar como qualquer outro conteúdo.

**Why this priority**: Os clipes existem, têm a marca d'água aplicada e nunca foram postados, mas estão
fora do SociMan. É um ganho real, mas a migração dos dados de cadastro vem antes.

**Independent Test**: Com 2 linhas de registro e 2 vídeos de teste, importar e conferir 2 conteúdos com
o título e a origem certos. Reimportar e conferir 0 novos.

**Acceptance Scenarios**:

1. **Given** uma linha do registro com o vídeo correspondente na pasta de clipes, **When** o dono
   importa, **Then** surge um conteúdo de vídeo próprio do perfil, com o título, e uma anotação no
   conteúdo com a URL e o trecho da fonte, ainda sem destino.
2. **Given** uma linha sem o vídeo, ou um vídeo sem linha, **When** a pré-visualização abre, **Then** o
   item fica "fora" com o motivo.

---

### User Story 7 - Ver e desfazer uma importação (Priority: P3)

O dono e os membros veem a lista de importações (quem, quando, arquivos, contagens por situação) e o
detalhe de cada item. O dono pode **desfazer** uma importação: o que ela criou e não foi alterado depois
é arquivado; o que ela trocou volta ao valor anterior pelo histórico, se ninguém mexeu depois. O que foi
alterado depois fica listado como "não desfeito", com o motivo.

**Why this priority**: É a saída para um engano (pasta errada, mapeamento proposto aceito sem querer). Com
a pré-visualização da US1, deve ser raro.

**Independent Test**: Importar, editar um dos itens criados, desfazer, e conferir que os outros itens
foram arquivados ou revertidos, que o editado ficou com o motivo, e que nada foi apagado.

**Acceptance Scenarios**:

1. **Given** uma importação que criou 3 anotações e trocou o guia, **When** o dono desfaz, **Then** as 3
   anotações são arquivadas, o guia volta à versão anterior, e a importação fica "desfeita por <dono> em
   <data>".
2. **Given** um canal criado pela importação e já usado num envio para corte, **When** o dono desfaz,
   **Then** o canal não é arquivado e fica listado como "não desfeito: já usado".

---

### Edge Cases

- **Markdown escrito por agente com variações** (negrito, crases, travessões, notas antes da tabela,
  colunas a mais): o leitor tolera formatação e ignora parágrafos fora das tabelas e seções do molde.
  Mudou a seção ou a coluna obrigatória: o arquivo é "não reconhecido", nunca lido pela metade em
  silêncio.
- **Célula com várias informações** (ex.: "youtube.com/@JovemNerd · tiktok.com/@jovemnerd"): vale o
  primeiro link do YouTube; os outros vão para a nota.
- **Duas linhas de `fontes.md` para o mesmo canal** (no mesmo perfil ou em perfis diferentes): um canal
  só, com os vínculos. Se os status mapeados forem diferentes, o item é "diverge" e o dono escolhe.
- **Canal-fonte arquivado no SociMan:** aparece como "diverge (arquivado)". A importação não restaura;
  restaurar é ação do dono no canal.
- **Perfil com slug que existe arquivado:** "diverge (arquivado)", sem restaurar.
- **Slug do markdown fora do padrão do SociMan** (maiúsculas, `_`): normalizado (minúsculas,
  kebab-case), e a pré-visualização mostra o slug final. Slug que colide com outro perfil: "fora".
- **Campo maior que o limite do SociMan** (nicho acima de 200 caracteres, texto de anotação grande):
  o nicho é cortado no limite com aviso, e o texto completo vai para uma anotação. Nada se perde em
  silêncio.
- **Texto do markdown que parece instrução** ("ignore as regras…"): é tratado como dado e gravado como
  texto. Nenhuma IA lê o markdown nesta importação.
- **Pasta alterada durante a leitura** (agente gravando): a impressão digital de cada arquivo é tirada
  na leitura. Se mudar antes da confirmação, aquele arquivo vira "mudou desde a leitura; leia de novo".
- **Imagem referenciada no `perfil.md` que não existe** (ex.: `watermark.png` ainda não gerado):
  "fora: arquivo citado não encontrado".
- **Fuso e datas:** datas do markdown (`YYYY-MM-DD`, com ou sem hora e `-03`) são gravadas como estão,
  em America/Sao_Paulo; datas inválidas deixam o item como "não reconhecido".
- **Perfil sem `perfil.md`** (só a pasta): fica "fora: sem perfil.md".

## Requirements *(mandatory)*

### Functional Requirements

**Quem e onde**

- **FR-001**: Só um **dono humano** DEVE poder ler (gerar a pré-visualização), confirmar e desfazer
  importações. Os outros atores DEVEM ser recusados como nas ações exclusivas de dono da 015: o membro
  recebe "só o dono", e a recusa a quem não é humano (IA, agente, cliente MCP) DEVE ficar registrada como
  evento de segurança. Membros DEVEM poder ver a lista de importações e o detalhe.
- **FR-002**: A importação DEVE ficar numa tela própria ("Importar da agência", nas configurações), e não
  DEVE existir como tool de escrita do MCP. A leitura do registro de importações pode ser exposta como
  tool de leitura, pelo mapa explícito da 009.
- **FR-003**: A importação só lê arquivos: não chama rede social, não publica e não altera conexão
  (princípio I). A única chamada externa é a identificação de canais do YouTube (FR-013), dentro da cota
  da 006. Não DEVE haver segredo novo.

**Leitura**

- **FR-004**: O SociMan DEVE ler a pasta da agência **só para leitura**, num caminho configurado
  (padrão: a pasta `shared/` do projeto da agência), e a pasta de clipes prontos (padrão: `media/clipes/`
  do mesmo projeto), também só para leitura. Ele **nunca** DEVE criar, alterar, mover ou apagar
  arquivos nela.
- **FR-005**: A leitura DEVE seguir o **mapeamento explícito** desta spec (tabela do Contexto): cada
  arquivo ou padrão de caminho tem um destino ou um motivo de ficar fora. Arquivo que não casa com o
  mapeamento DEVE aparecer como "fora: fora do mapeamento", só com o nome.
- **FR-006**: A leitura DEVE recusar link simbólico que aponte para fora da pasta, arquivo acima de um
  tamanho máximo (padrão: 2 MB para markdown e 20 MB para imagem) e mais arquivos que um limite fixo
  (padrão: 2.000). O conteúdo de arquivo fora do mapeamento nunca é lido nem guardado.
- **FR-007**: O markdown DEVE ser lido de forma **determinística** (sem IA), pelas seções do molde
  `_modelo/perfil.md` e pelas colunas das tabelas de `fontes.md`, comparadas sem acento, sem caixa e sem
  formatação (negrito, crases). Arquivo com seção ou coluna obrigatória faltando é "não reconhecido", com
  o que faltou.

**Pré-visualização (US1)**

- **FR-008**: Antes de gravar, o SociMan DEVE mostrar, por perfil e por tipo (perfil, conta, guia,
  anotação, canal-fonte, imagem, clipe):
  - cada item na situação **novo**, **igual**, **diverge** ou **fora** (e **aguardando cota** para canal
    não identificado por falta de cota), com o arquivo e o trecho de origem;
  - nos itens "diverge", o valor no SociMan e o valor no markdown, lado a lado;
  - os motivos de "fora";
  - as contagens por situação e os arquivos "não reconhecidos".
- **FR-009**: A pré-visualização DEVE expirar (padrão: 30 minutos) e ser de uso único. Ela guarda só o
  resultado da leitura (itens, impressões digitais e decisões), em estado efêmero. Nada é gravado no
  domínio nem no armazenamento de arquivos antes da confirmação.

**Confirmação, idempotência e histórico (US2)**

- **FR-010**: Na pré-visualização, o dono DEVE poder marcar e desmarcar cada item novo (padrão:
  marcado) e escolher, em cada item que diverge, "manter o SociMan" (padrão) ou "usar o markdown".
- **FR-011**: A confirmação DEVE gravar os itens marcados **de uma vez** (tudo ou nada), exceto os que
  mudaram desde a leitura (US2, cenário 6), que ficam de fora com o motivo. Com vídeos, a gravação pode
  levar alguns minutos: a tela mostra o andamento e o resultado, e uma falha no meio não deixa nada
  gravado no domínio. Cada mutação DEVE passar pelo
  histórico da entidade (princípio VII), com o **dono que confirmou como autor** e a origem
  `importacao` (id da importação, arquivo e trecho) nos detalhes da versão. Arquivos novos no
  armazenamento DEVEM ser gravados antes da transação e, se ela falhar, ficam sem referência (o
  armazenamento não tem delete; igual aos outros envios).
- **FR-012**: Cada tipo de item DEVE ter uma **chave de conciliação** (tabela do Contexto): slug para
  perfil; plataforma e @ normalizado para conta; id do canal do YouTube para canal-fonte; SHA-256 para
  imagem e vídeo; perfil e impressão digital do texto de origem para anotação; perfil para o guia.
  Reimportar o mesmo conteúdo DEVE dar "igual" e não gravar nada, nem versão nova.
- **FR-012a**: A importação DEVE ficar registrada: autor, data, caminho lido, impressão digital de cada
  arquivo, contagens por situação e, por item, a decisão do dono e o resultado (criado, atualizado,
  mantido, fora, não gravado). O registro é só de inserção, exceto o estado da importação e as marcas do desfazer em cada item.

**Fontes e direito (US3, princípio II)**

- **FR-013**: Cada linha de `fontes.md` DEVE ter o canal do YouTube identificado pelo link (`/channel/`,
  `/@handle`, `/c/`, `/user/`) ou pelo @, usando a mesma resolução e a mesma cota do cadastro manual de
  canal da 006. Uma linha sem link do YouTube, com "não confirmado" ou "a confirmar" no lugar do link, ou
  que não resolve, DEVE ficar "fora: sem canal do YouTube identificável", com o texto original.
- **FR-014**: O status de direito de canal **novo** DEVE ser **proposto** a partir do status do
  markdown: `programa-de-cortes` → `programa_de_cortes`; linha de canal do próprio dono (marcada como
  "canal próprio" ou "conteúdo próprio" na linha) → `proprio`; `autorizado` → **proposto `sem_acordo`**, e o dono
  pode trocar para `parceiro` linha a linha na pré-visualização (Clarifications, Q1); `pendente`, `negado` e `desconhecido` → `sem_acordo`.
  O dono DEVE poder trocar o status proposto de cada linha antes de confirmar.
- **FR-015**: A importação **nunca** DEVE mudar o direito de um canal que já existe sem a escolha
  explícita do dono naquele item. A troca vai para o histórico do canal com o autor, como a mudança
  manual de direito.
- **FR-015a**: Para um canal que já existe, o direito é **igual** quando o status do SociMan é um dos
  aceitos para o status do markdown: `programa-de-cortes` → `programa_de_cortes`; canal próprio →
  `proprio`; `autorizado` → `sem_acordo` ou `parceiro`; `pendente`, `negado` e `desconhecido` → só
  `sem_acordo`. Fora disso, o item é "diverge (direito)", e a escolha padrão é manter o status do SociMan.
- **FR-016**: A evidência do markdown DEVE ir para o canal: o primeiro link da coluna "Evidência" vira o
  link de evidência, e a nota recebe o status original do markdown, a evidência, as regras do programa,
  quem confirmou e a data, com a origem ("fontes.md de `<slug>`, linha N").
- **FR-017**: Uma linha `negado` DEVE ser importada com `sem_acordo` e a nota "negado no markdown em
  `<data>`", para o aviso aparecer em qualquer envio daquele canal.
- **FR-018**: Canal citado por um perfil e já cadastrado em outro DEVE só ganhar o vínculo com o perfil
  (006), sem duplicar nem mudar o direito.

**Guia, kit e anotações (US5)**

- **FR-019**: O guia de comunicação do perfil DEVE ser preenchido só quando estiver vazio (sem versão),
  a partir do `perfil.md` §4: "Tom" → tom; "Expressões da casa" → vocabulário (separadas por "·", "/" ou
  aspas); "Proibido" → "não faça". As palavras proibidas do guia (busca por palavra inteira da 017) não
  são preenchidas, porque o markdown lista temas e não palavras. Guia já editado DEVE aparecer como
  "diverge".
- **FR-020**: As expressões da casa que não estão nos bordões do kit DEVEM aparecer como sugestão na
  pré-visualização, sem mudar o kit. O restante do estilo visual (§5) fica fora (princípio III).
- **FR-021**: Viram **anotações de observação** no perfil, com o título "`<arquivo>` §`<seção>`" e a data
  original, quando houver: §3 (público), §6 (monetização) e §7 (metas) do `perfil.md`, uma por seção;
  cada linha de §8 (decisões); cada seção `##` da `pesquisa.md`; e cada pauta da `ideias-gravacao.md`.
  Seções vazias ou só com o texto do molde não viram anotação.
- **FR-022**: Nicho (§2) maior que o limite do perfil DEVE ser cortado no limite, com aviso, e o texto
  completo vai para uma anotação. Nicho já preenchido no SociMan DEVE ser "diverge" quando diferente.
  A bio do perfil não tem origem no markdown e nunca é tocada.

**Imagens (US4)**

- **FR-023**: Imagens DEVEM passar pela mesma validação de conteúdo e de limite da biblioteca (007) e ir
  para o armazenamento de arquivos no HD, com as conferências do marcador e do espaço livre. Imagem com
  o mesmo SHA-256 de uma imagem do perfil DEVE ser "igual" e não ser enviada de novo.
- **FR-024**: A persona da fábrica (`shop/persona.md` e `shop/persona/`) DEVE ir para o perfil que o dono
  escolher na pré-visualização (padrão: o perfil onde as imagens dela já estão, pelo SHA-256; senão,
  nenhum, e o item fica "fora: escolha o perfil"). A descrição para prompts vira o prompt do avatar; a
  voz, o tom de voz; as regras de imagem, as regras de imagem; cada imagem, uma referência com o look
  (cozinha, diner); e cada cenário, um asset cenário com o prompt.
- **FR-025**: O logo do perfil DEVE ser preenchido só se o perfil não tiver logo. Arquivo com
  `nao-usar-ainda` no nome DEVE ficar "fora".

**Clipes (US6)**

- **FR-026**: Cada vídeo de `../media/clipes/<slug>/<data>/` que tem linha no `registro-clipes.md` do
  perfil (pelo ID da linha = nome do arquivo sem extensão) DEVE virar um **conteúdo de vídeo próprio**
  (014) do perfil, com o título do registro (até 100 caracteres) e, numa anotação de observação no
  conteúdo (009), a origem (ID e data da linha, URL e trecho da fonte, produto/CTA e observação), sem
  destino (Clarifications, Q2). A chave de conciliação é o SHA-256 do vídeo:
  vídeo já guardado como conteúdo do perfil é "igual". O vídeo passa pelas mesmas conferências do envio
  de vídeo próprio da 014 (formato, tamanho, leitura da duração) e vai para o HD, com o marcador e o piso
  de espaço livre conferidos **para o total da importação** antes de gravar (≈900 MB hoje). Linha sem
  vídeo, vídeo sem linha ou vídeo inválido ficam "fora", com o motivo. As métricas do registro ("sem dado") e o
  status `aprovado` do markdown não são importados; aprovar e agendar continuam sendo atos do dono na 014.

**Depois da importação**

- **FR-027**: Depois da importação, o **SociMan é a fonte da verdade** dos itens importados
  (Clarifications, Q3): os agentes passam a ler pelo MCP (009); o markdown fica como arquivo, e o SociMan
  nunca escreve nele (FR-004). Reimportar é sempre manual (pelo dono) e só traz o que é novo; o que
  diverge continua com "manter o SociMan" como padrão. A troca dos AGENTS.md para ler do MCP é trabalho do
  lado da agência, fora desta spec.
- **FR-028**: A tela de importação DEVE mostrar, para cada perfil importado, a data da última importação
  e se os arquivos mudaram desde então (pela impressão digital), sem importar nada sozinha.

**Desfazer (US7)**

- **FR-029**: Desfazer DEVE: arquivar o que a importação criou e não foi alterado nem usado depois;
  reverter, pelo histórico, o que ela atualizou e ninguém mudou depois; e listar o resto como "não
  desfeito", com o motivo. Nada é apagado. O registro passa a `desfeita` (autor e data) e o ato vai para
  o histórico. Imagens no armazenamento ficam (sem delete), só sem referência.

**Escopo**

- **FR-030**: Ficam **fora desta spec**, com o motivo na pré-visualização:
  - **cenas** reutilizáveis além dos 2 cenários da persona (spec 010);
  - **roteiros e pacotes** da fábrica (`shop/roteiros/`, `shop/pacotes/`) e pautas como roteiros
    (spec 011; aqui as pautas viram só anotações);
  - **produtos**, nicho e fontes de dados da fábrica (`shop/produtos/`, `shop/nicho.md`,
    `shop/fontes-dados.md`) (spec 012);
  - planos, caçadas, pacotes de clipes e retros (`semana/`, `dia/`, `candidatos/`, `clipes/`,
    `revisoes/`), o manual e os moldes da agência, custos, aprendizados e o material do HeyGen.

### Key Entities

- **Importação:** uma confirmação do dono sobre uma leitura da pasta da agência. Guarda autor, data,
  caminho, impressão digital de cada arquivo lido, contagens por situação, estado (`processando`,
  `concluida`, `falhou` ou `desfeita`, com autor e data) e os itens.
- **Item da importação:** um pedaço de arquivo (seção, linha de tabela ou imagem) ligado a uma entidade
  de destino. Tem a origem (arquivo e trecho), a chave de conciliação, a situação na leitura (novo,
  igual, diverge, fora e o motivo), a decisão do dono, o resultado e a entidade criada ou alterada.
- **Pré-visualização:** resultado temporário e de uso único da leitura, com prazo. Não é domínio.
- **Entidades de destino (já existentes):** perfil e conta (003), bordões do kit (004, só comparação),
  canal-fonte e vínculo com o perfil (006), asset e arquivo de asset (007), anotação (009), conteúdo de
  vídeo próprio (014) e guia de comunicação (017). Esta spec não cria entidade de domínio
  nova além da importação e dos itens.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Sobre a pasta `shared/` atual e o banco atual, a pré-visualização sai em menos de 1 minuto
  (sem contar a cota do YouTube) e dá a **100% dos 71 arquivos e dos 70 vídeos** um destino ou um motivo de ficar fora.
- **SC-002**: Rodar a importação duas vezes seguidas sobre os mesmos arquivos grava 0 entidades, 0
  versões e 0 arquivos novos na segunda vez (verificado por teste).
- **SC-003**: 0 valores editados no SociMan são trocados sem a escolha "usar o markdown" do dono naquele
  item, e 0 status de direito de canal existente mudam sem essa escolha (verificado por teste).
- **SC-004**: 100% das mutações de uma importação aparecem no histórico da entidade com o dono como autor
  e a origem (arquivo e trecho).
- **SC-005**: 0 ações de importação aceitas de membro, IA, agente ou MCP (verificado por teste), e 0
  arquivos criados, alterados ou apagados na pasta da agência.
- **SC-006**: Depois de importar os 2 perfis, o dono e um agente pelo MCP encontram no SociMan o tom, as
  expressões, os proibidos, as decisões e a pesquisa de cada perfil, sem abrir o markdown.
- **SC-007**: Desfazer uma importação sem edições posteriores deixa o banco, entidade por entidade, como
  estava antes dela (só com registros arquivados e versões novas, nada apagado).

## Assumptions

- **Como as pastas chegam ao SociMan:** a API lê `../shared` e `../media/clipes` por montagens **só
  leitura** no container, em caminhos configuráveis. É a opção mais simples para um dono só e
  uma máquina só. Alternativa descartada: enviar um ZIP da pasta pela tela (duplica arquivos e
  complica a conciliação de imagens). As montagens são a única peça de infraestrutura nova e vão ao
  Complexity Tracking do plano.
- **Autor:** o autor de cada versão é o **dono que confirmou** (foi ele quem decidiu), e a origem
  `importacao` fica nos detalhes, para filtrar no histórico. Um autor `system:importacao` não é usado,
  porque nada é gravado sem um humano confirmar. As anotações (009), que exigem autor usuário ou cliente
  MCP, também ficam com o dono.
- **Os agentes continuam gravando markdown** até a migração deles para o MCP (fora desta spec, do lado da
  agência). Por isso a importação é reexecutável e mostra o que mudou desde a última.
- **Molde estável:** os agentes escrevem `perfil.md` e `fontes.md` pelos moldes de `_modelo/`. Mudou o
  molde, muda o leitor (uma tabela de seções e colunas), e o arquivo diferente aparece como "não
  reconhecido", nunca lido errado.
- **Sem IA:** nenhuma chamada de modelo. O texto do markdown é dado e não instrução (regra 6 da
  agência).
- **Cota do YouTube:** identificar um canal usa a mesma chamada do cadastro manual da 006. Hoje sobram 8
  fontes sem canal identificável, então o custo esperado é pequeno.
- **Achado no banco de dev (2026-10-06): 3 fontes `pendente` estão como `parceiro`** (Fofocalizando,
  Vênus Podcast e De Frente com Blogueirinha, todas de `queridinhos`), cadastradas à mão antes desta spec.
  A conciliação DEVE mostrá-las como "diverge (direito)", com os dois status, para o dono decidir (FR-015a).
  As 15 fontes `autorizado` que estão como `parceiro` não são divergência, porque `parceiro` é uma das
  escolhas aceitas para `autorizado` (Q1).
- **Material original próprio** (pasta `media/originais/`) não é canal-fonte: o envio avulso da 006 já
  cobre esse caso. A linha fica "fora", com essa explicação.
- **Limites** (prazo de 30 min, tamanhos, número de arquivos) são constantes no código, e os que o dono
  vê aparecem na tela.
- **Dependências:** perfis e contas (003), kit (004), canais-fonte, cota e envio avulso (006), biblioteca
  de assets e validação de imagem (007), anotações e mapa de tools (009), central de conteúdos (014), ações só de dono humano e registro de recusa (015), guia de comunicação (017),
  histórico (princípio VII) e armazenamento no HD com marcador.
