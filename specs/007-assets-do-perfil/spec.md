# Feature Specification: Biblioteca de assets do perfil (007-assets-do-perfil)

**Feature Branch**: `007-assets-do-perfil`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "Gestão do avatar da conta num nível mais global (não de cortes em si): uma área de assets do perfil, com avatares, cenários (fundos), stickers etc."

## Clarifications

### Session 2026-09-29

- Q: Onde fica a gestão de avatares, cenários e stickers? → A: Numa **biblioteca de assets do perfil** (aba própria no perfil), fora do fluxo de cortes. Os seletores de imagem do kit (fundo e marca d'água, spec 004) passam a escolher dessa biblioteca.
- Q: Ordem em relação à 006? → A: As duas em paralelo.
- Q: Um corte que usou a imagem impede arquivar o asset? → A: Não. Só o **kit de marca** bloqueia o arquivamento; o uso em cortes aparece em "Onde é usado" (ex.: "12 cortes") só como informação.
- Q: Quais tipos cada seletor do kit mostra? → A: Fundo do gancho e do card final: **fundos e cenários**. Marca d'água: **marcas d'água e stickers** (os dois exigem transparência).
- Q: Como reordenar poses e referências? → A: Botões "mover ←/→" em cada card (toque e teclado) e, no computador, arrastar com o recurso nativo do navegador (HTML5), sem dependência nova.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Avatares e poses (Priority: P1)

O usuário cria os avatares (personas) de um perfil, por exemplo "Achadinhos". Cada avatar tem:
- nome;
- uma descrição fixa para prompts, usada com as mesmas palavras em todas as gerações, para manter
  a consistência;
- tom de voz;
- regras de imagem;
- imagens de referência, organizadas por **look** (ex.: "Cozinha, corpo inteiro", "Diner, busto");
- **poses**: imagens do avatar em posições diferentes, cada uma com rótulo e um "quando usar".

**Why this priority**: o avatar é a identidade recorrente dos vídeos (TikTok Shop e cortes com
apresentadora). Hoje ele vive em markdown solto (`shared/shop/persona.md`).

**Independent Test**: criar o avatar "Achadinhos" no perfil Queridinhos, colar a descrição para
prompts, enviar as duas imagens de referência (cozinha e diner) como looks, acrescentar uma pose
"apontando para o produto" e ver tudo na aba Assets, com o botão "Copiar descrição para prompt".

**Acceptance Scenarios**:

1. **Given** um perfil, **When** o usuário cria um avatar com nome e descrição para prompts, **Then**
   o avatar aparece na biblioteca com a imagem principal (ou as iniciais).
2. **Given** um avatar, **When** o usuário envia imagens de referência com o nome do look e o uso,
   **Then** elas aparecem agrupadas por look, e uma delas pode ser marcada como principal.
3. **Given** um avatar, **When** o usuário acrescenta poses (imagem, rótulo e "quando usar"), **Then**
   as poses aparecem numa grade e podem ser reordenadas com os botões "mover ←/→" (e, no
   computador, arrastando).
4. **Given** um avatar, **When** o usuário clica em "Copiar descrição para prompt", **Then** o texto
   exato vai para a área de transferência.
5. **Given** qualquer alteração, **When** ela é salva, **Then** fica no histórico, com reversão pelo
   dono (princípio VII).

---

### User Story 2 - Cenários e fundos (Priority: P1)

O usuário cadastra cenários reutilizáveis: nome, prompt do ambiente (ex.: "1950s kitchen with
mint-green countertops…"), imagens de referência e tags. As **imagens de fundo** do kit (004)
passam a ser cenários ou imagens desta biblioteca.

**Why this priority**: cenários se repetem entre vídeos e hoje ficam espalhados.

**Independent Test**: criar o cenário "Cozinha retrô" com o prompt e uma imagem, e escolher essa
imagem como fundo do card final no kit (aba Marca), pelo seletor da biblioteca.

**Acceptance Scenarios**:

1. **Given** um perfil, **When** o usuário cria um cenário com nome, prompt e imagens, **Then** ele
   aparece na biblioteca com a miniatura.
2. **Given** o kit (aba Marca), **When** o usuário escolhe "Imagem" como fundo do gancho ou do card,
   **Then** o seletor mostra as imagens de cenários e fundos da biblioteca do perfil, com busca, e
   permite enviar uma nova (que entra na biblioteca).
3. **Given** as imagens de fundo já enviadas pela 004, **When** a biblioteca é aberta pela primeira
   vez, **Then** elas já aparecem como fundos, sem perda.

---

### User Story 3 - Stickers e imagens de marca (Priority: P2)

O usuário mantém stickers (PNG ou WebP com transparência) e as imagens de marca d'água e logos
alternativos na mesma biblioteca, com tags e busca. Os stickers ficam prontos para uso futuro nos
cortes. A marca d'água do kit escolhe desta biblioteca (marcas d'água e stickers).

**Why this priority**: completa a identidade visual; o uso nos cortes vem depois.

**Independent Test**: enviar 3 stickers com transparência e tags "reação" e "promo", filtrar por
"promo" e ver só os certos; escolher uma imagem da biblioteca como marca d'água no kit.

**Acceptance Scenarios**:

1. **Given** um sticker sem transparência, **When** o usuário envia, **Then** é recusado com "O
   sticker precisa ter fundo transparente".
2. **Given** a biblioteca, **When** o usuário filtra por tipo e tag ou busca por nome, **Then** vê só
   os assets correspondentes.
3. **Given** as imagens de marca d'água já enviadas pela 004, **When** a biblioteca é aberta,
   **Then** elas aparecem como tipo "marca d'água".

---

### User Story 4 - Onde é usado, arquivar e baixar (Priority: P2)

Cada asset mostra **onde é usado** (kit de marca, cortes e, no futuro, roteiros e cenas). Assets
nunca são apagados: são arquivados, e um asset em uso **no kit de marca** não pode ser arquivado
sem trocar antes; o uso em cortes aparece só como informação e não impede arquivar. O
usuário pode baixar o original e copiar um link (para usar no Flow/Veo ou mandar aos agentes).

**Independent Test**: tentar arquivar a imagem de fundo usada no kit e ver "Em uso em: Card final
(kit v3)"; trocar no kit e arquivar; baixar o original.

**Acceptance Scenarios**:

1. **Given** um asset usado no kit, **When** o usuário tenta arquivar, **Then** é recusado com a lista
   de usos.
2. **Given** um asset, **When** o usuário clica em "Baixar original" ou "Copiar link", **Then** recebe
   o arquivo original ou um link que abre sem login e não é adivinhável.
3. **Given** assets arquivados, **When** o usuário marca "Mostrar arquivados", **Then** eles aparecem
   e podem ser restaurados.
4. **Given** um asset usado só em cortes (e não no kit), **When** o usuário arquiva, **Then** o
   arquivamento passa, e "Onde é usado" continua mostrando os cortes (que não mudam).

---

### Edge Cases

- Imagem muito grande (> 20 MB) ou em formato não suportado: recusada com a razão.
- Avatar sem imagem: aparece com iniciais e cor neutra.
- Duas poses com o mesmo rótulo no mesmo avatar: recusado.
- HD indisponível: a biblioteca mostra os dados, mas envios e downloads respondem com a mensagem
  de armazenamento indisponível (spec 004).
- Muitos assets (centenas): a grade pagina ou carrega aos poucos, e a busca continua rápida.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Cada perfil DEVE ter uma biblioteca de assets (aba "Assets") com os tipos: **avatar**,
  **cenário**, **fundo**, **sticker**, **marca d'água** e **imagem** (genérica).
- **FR-002**: O **avatar** DEVE ter nome, descrição para prompts (texto fixo, até 2.000 caracteres),
  tom de voz, regras de imagem, imagens de referência agrupadas por look (nome do look e uso), uma
  imagem principal e poses (imagem, rótulo único no avatar, "quando usar", ordem).
- **FR-003**: O **cenário** DEVE ter nome, prompt do ambiente, imagens de referência e tags.
- **FR-004**: **Sticker** e **marca d'água** DEVEM exigir transparência real; **fundo** e **cenário**
  aceitam PNG, JPG ou WebP sem transparência; o limite é 20 MB por imagem.
- **FR-005**: Todo asset DEVE ter tags, busca por nome e tag, filtro por tipo, e mostrar **onde é
  usado**.
- **FR-006**: Os seletores de imagem do kit DEVEM escolher da biblioteca do perfil (com envio de
  novo arquivo direto no seletor): o fundo do gancho e do card final mostra **fundos e cenários**;
  a marca d'água mostra **marcas d'água e stickers**. As imagens já enviadas pela 004 DEVEM
  aparecer na biblioteca sem perda.
- **FR-007**: Assets NUNCA são apagados: arquivar e restaurar; um asset em uso **no kit de marca**
  não pode ser arquivado (erro com a lista de usos). O uso em cortes é só informativo e não
  bloqueia. Alterações ficam no histórico, com reversão pelo dono
  (princípio VII).
- **FR-008**: Todo asset DEVE permitir baixar o original e copiar um link estável, não
  adivinhável, que abre sem login.
- **FR-009**: O avatar DEVE ter "Copiar descrição para prompt", que copia o texto exato.

### Key Entities

- **Asset**: item da biblioteca de um perfil. Tipo, nome, descrição, tags, arquivos, arquivado,
  versão e histórico.
- **Arquivo do asset**: imagem (original no HD), com papel no asset (principal, referência de
  look, pose), metadados (dimensões, transparência) e ordem.
- **Avatar** (asset tipo avatar): descrição para prompts, tom de voz, regras de imagem, looks e
  poses.
- **Cenário** (asset tipo cenário): prompt do ambiente e imagens de referência.
- **Uso**: onde o asset é referenciado (kit e seção, cortes e, no futuro, roteiros e cenas).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Cadastrar o avatar "Achadinhos" com 2 looks e 3 poses leva menos de 5 minutos.
- **SC-002**: Encontrar um asset por tag ou nome numa biblioteca de 200 itens leva menos de 10
  segundos.
- **SC-003**: 100% das imagens de fundo e marca d'água enviadas na 004 aparecem na biblioteca depois
  da migração.
- **SC-004**: Nenhum asset pode ser apagado de fato pela aplicação, e nenhum asset em uso no kit de
  marca pode ser arquivado.
- **SC-005**: O conteúdo de `shared/shop/persona.md` (Achadinhos: descrição, 2 cenários, 2
  imagens) cabe na biblioteca sem campo faltando.

## Assumptions

- Assets são por perfil. Um avatar compartilhado entre perfis fica para depois (hoje cada perfil
  tem sua persona).
- Os arquivos ficam no MinIO no HD (constitution 2.1.0), como as imagens da 004.
- Vídeos de avatar (looks animados, clipes do HeyGen/Veo) e vozes (áudio) ficam fora; esta spec
  cuida de imagens e textos. Áudio e vídeo de referência podem entrar numa spec futura.
- Geração de imagens por IA a partir dos prompts fica fora: o SociMan guarda e organiza; a geração
  continua no Flow/Veo (decisão do dono de 2026-09-24).
- A importação automática de `../shared/shop/persona*` e `../shared/perfis/*/assets` é a spec de
  importação; aqui o cadastro é manual (a POC pode cadastrar a Achadinhos).
