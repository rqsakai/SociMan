# Feature Specification: Perfis e contas sociais (003-contas-sociais)

**Feature Branch**: `003-contas-sociais`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "003-contas-sociais: cadastro de Perfis da agência (ex.: Queridinhos, A Taverna Nerd) e das contas de cada perfil por plataforma (TikTok, YouTube, Instagram…: @handle, link, status). O Perfil tem nome, slug, nicho, descrição/bio, idioma, logo e banner (upload para o MinIO, exibidos via imgproxy em /img) e status. Decisão do dono: um Perfil agrupa várias contas por plataforma (espelha ../shared/perfis/). Primeira spec de domínio: deve cumprir o princípio VII da constitution (autor e data em toda mutação, estado anterior guardado, nada apagado de fato, histórico visível e reversão pelo dono). O SociMan nunca publica em rede social (princípio I)."

## Clarifications

### Session 2026-09-29

- Q: O que é uma "conta" no SociMan? → A: Um **Perfil** (marca da agência, ex.: Queridinhos) agrupa várias **contas por plataforma** (@ no TikTok, no YouTube…). Nicho, bio, logo, banner e, nas próximas specs, kit de marca e padrões de corte ficam no Perfil.
- Q: O slug pode mudar depois de criado? → A: Não. O slug é definido na criação e fica fixo; o nome pode mudar à vontade.
- Q: Logos e banners são privados ou públicos? → A: Públicos na rede de casa (quem tem o endereço da imagem a vê sem login); o endereço não é adivinhável e não expõe o armazenamento.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cadastrar e ver os perfis da agência (Priority: P1)

Um usuário da casa cadastra um perfil da agência: nome, identificador curto (slug), nicho,
descrição/bio e idioma. Depois vê a lista de perfis com nome, nicho, status e as plataformas em
que cada um está, e abre um perfil para ver os detalhes.

**Why this priority**: é o centro do SociMan. Kit de marca, avatares, cortes e produtos das
próximas specs se penduram num perfil.

**Independent Test**: cadastrar "Queridinhos" (nicho "Achadinhos de beleza + casa", pt-BR),
vê-lo na lista, abrir, editar a bio e ver a alteração salva.

**Acceptance Scenarios**:

1. **Given** um usuário logado, **When** ele cadastra um perfil com nome, nicho e idioma,
   **Then** o perfil aparece na lista com status "Em preparação" e um slug derivado do nome
   (ex.: "A Taverna Nerd" → `a-taverna-nerd`), que ele pode ajustar **antes de salvar**; depois
   de criado, o slug não muda.
2. **Given** um slug já usado por outro perfil, **When** alguém tenta repeti-lo, **Then** o sistema
   recusa com "Já existe um perfil com esse identificador".
3. **Given** a lista de perfis, **When** o usuário filtra por status ou busca por nome, **Then** vê
   só os perfis que atendem ao filtro.
4. **Given** um perfil, **When** o usuário muda o status (Em preparação → Ativo → Pausado),
   **Then** a lista reflete o novo status.

---

### User Story 2 - Contas do perfil em cada plataforma (Priority: P1)

Dentro de um perfil, o usuário registra as contas em cada plataforma: plataforma, @ (handle),
link e status da conta. Um perfil pode estar só no TikTok hoje e ganhar YouTube depois.

**Why this priority**: sem as contas por plataforma não se sabe onde cada perfil existe; as specs
de cortes e publicação manual dependem disso.

**Independent Test**: em "Queridinhos", adicionar a conta TikTok `@meusqueridinhos10` com o link;
ver a conta no perfil e na lista (ícone TikTok); marcar a conta YouTube como "Planejada".

**Acceptance Scenarios**:

1. **Given** um perfil, **When** o usuário adiciona uma conta com plataforma e @, **Then** a conta
   aparece no perfil; o link é preenchido automaticamente a partir do @ quando a plataforma tem
   formato conhecido, e pode ser editado.
2. **Given** um perfil que já tem conta ativa no TikTok, **When** o usuário tenta outra conta
   TikTok ativa no mesmo perfil, **Then** o sistema recusa ("Este perfil já tem uma conta ativa
   no TikTok").
3. **Given** um @ já cadastrado na mesma plataforma em outro perfil, **When** alguém tenta repeti-lo,
   **Then** o sistema recusa com "Esse @ já pertence ao perfil X".
4. **Given** uma conta, **When** o usuário muda o status (Planejada, Ativa, Pausada, Encerrada),
   **Then** o novo status aparece no perfil.
5. **Given** o SociMan, **When** qualquer tela ou integração é usada, **Then** nada é publicado nas
   plataformas (o SociMan só registra; princípio I).

---

### User Story 3 - Logo e banner do perfil (Priority: P2)

O usuário envia o logo (quadrado) e o banner (retangular) do perfil. A lista e o perfil mostram
as imagens em tamanhos adequados, carregando rápido também no celular.

**Why this priority**: dá identidade visual à gestão e prepara o kit de marca (spec 004), mas o
cadastro funciona sem imagens.

**Independent Test**: enviar um PNG de logo e um JPG de banner para "Queridinhos"; ver a miniatura
na lista e o banner no perfil; trocar o logo e confirmar que o novo aparece.

**Acceptance Scenarios**:

1. **Given** um perfil, **When** o usuário envia uma imagem PNG, JPG ou WebP de até 5 MB como logo,
   **Then** o logo aparece no perfil e como miniatura na lista.
2. **Given** um arquivo que não é imagem, ou maior que 5 MB, ou menor que 200×200 px (logo) /
   1000×250 px (banner), **When** o usuário tenta enviar, **Then** o envio é recusado com a
   razão ("Formato não aceito", "Arquivo maior que 5 MB", "Imagem pequena demais").
3. **Given** um perfil com logo, **When** o usuário troca o logo, **Then** o novo aparece e o
   anterior continua disponível no histórico (US4).
4. **Given** um perfil sem logo, **When** ele aparece na lista, **Then** mostra as iniciais do nome
   sobre uma cor neutra.

---

### User Story 4 - Histórico, arquivamento e reversão (Priority: P1)

Toda alteração em perfil ou conta fica no histórico do registro (quem, quando, o que mudou, antes
e depois). Nada é apagado: perfis e contas são **arquivados** e podem ser restaurados. O dono
pode reverter um perfil ou uma conta para uma versão anterior.

**Why this priority**: exigência da constitution (princípio VII) para a primeira spec de domínio;
agentes de IA vão escrever nesses registros pelo MCP (spec 009) e o dono precisa desfazer erros.

**Independent Test**: editar a bio de um perfil duas vezes (usuários diferentes), ver as duas
alterações no histórico com autor e data, reverter para a primeira versão e confirmar a bio
antiga; arquivar o perfil, vê-lo sumir da lista padrão, restaurar e vê-lo de volta.

**Acceptance Scenarios**:

1. **Given** um perfil, **When** qualquer campo muda, **Then** o histórico mostra a alteração com
   autor, data/hora e os valores antes e depois de cada campo alterado.
2. **Given** o histórico, **When** o **dono** escolhe "Reverter para esta versão", **Then** o
   registro volta aos valores daquela versão, e a própria reversão entra no histórico como uma
   nova alteração (autor = dono), sem apagar as versões intermediárias.
3. **Given** um `membro`, **When** ele tenta reverter, **Then** é recusado com "Sem permissão".
4. **Given** um perfil, **When** um usuário o arquiva, **Then** ele sai da lista padrão e aparece
   no filtro "Arquivados"; suas contas continuam registradas; o dono ou o membro pode
   restaurá-lo.
5. **Given** uma reversão que traria de volta um @ que hoje pertence a outro registro,
   **When** o dono tenta reverter, **Then** o sistema recusa explicando o conflito.
6. **Given** a troca de logo ou banner, **When** se reverte para uma versão anterior, **Then** a
   imagem daquela versão volta a ser exibida.

---

### Edge Cases

- Nome com acentos e símbolos: o slug sugerido é só minúsculas, números e hífen ("Achadinhos da
  Lú!" → `achadinhos-da-lu`).
- @ digitado com ou sem "@", com espaços ou maiúsculas: é normalizado (sem "@", minúsculas, sem
  espaços) e mostrado sempre como `@handle`.
- Link colado em vez de @ (ex.: `https://www.tiktok.com/@meusqueridinhos10`): o @ é extraído do
  link quando a plataforma é conhecida.
- Plataforma não listada: opção "Outra" com nome livre da plataforma e link obrigatório.
- Envio de imagem interrompido: o perfil fica como estava; nenhuma imagem pela metade é exibida.
- Dois usuários editam o mesmo perfil ao mesmo tempo: quem salvar por último sobre uma versão
  desatualizada recebe "Este perfil foi alterado por outra pessoa; recarregue" em vez de
  sobrescrever em silêncio.
- Arquivar perfil com contas ativas: permitido, com aviso de que as contas continuam ativas nas
  plataformas (o SociMan não publica nem encerra nada fora dele).

## Requirements *(mandatory)*

### Functional Requirements

**Perfis**
- **FR-001**: Usuários logados DEVEM poder criar, ver, editar, arquivar e restaurar perfis.
- **FR-002**: Um perfil DEVE ter nome (1..80), slug único (minúsculas, números e hífen, 2..60,
  sugerido a partir do nome), nicho (texto até 200), descrição/bio (até 2000), idioma (padrão
  pt-BR), status (`em_preparacao`, `ativo`, `pausado`) e, opcionalmente, logo e banner.
- **FR-002a**: O slug é definido na criação e NÃO PODE ser alterado depois (referência estável
  para agentes, pastas de mídia e links); o nome pode ser alterado livremente. A reversão nunca
  altera o slug.
- **FR-003**: A lista de perfis DEVE mostrar logo (ou iniciais), nome, nicho, status e as
  plataformas das contas ativas, com busca por nome e filtro por status (incluindo "Arquivados").

**Contas por plataforma**
- **FR-004**: Um perfil DEVE poder ter várias contas, cada uma com plataforma (TikTok, YouTube,
  Instagram, Kwai, Facebook, X ou Outra com nome), @ normalizado, link, status (`planejada`,
  `ativa`, `pausada`, `encerrada`) e observação opcional.
- **FR-005**: O mesmo @ NÃO PODE existir duas vezes na mesma plataforma (entre todos os perfis,
  inclusive arquivados); um perfil NÃO PODE ter duas contas `ativa` na mesma plataforma.
- **FR-006**: Para plataformas conhecidas, o link DEVE ser sugerido a partir do @ e o @ extraído de
  um link colado.
- **FR-007**: O SociMan NÃO DEVE publicar, seguir, comentar ou alterar nada nas plataformas; contas
  são apenas registros (princípio I).

**Imagens**
- **FR-008**: Logo e banner DEVEM aceitar PNG, JPG e WebP de até 5 MB, com mínimo de 200×200 px
  (logo) e 1000×250 px (banner); o conteúdo real do arquivo é verificado (não só a extensão).
- **FR-009**: As imagens DEVEM ser exibidas redimensionadas para o tamanho de cada tela
  (miniatura na lista, tamanho médio no perfil).
- **FR-009a**: As imagens podem ser vistas sem login por quem tem o endereço delas (são públicas
  nas redes de qualquer forma), mas o endereço NÃO DEVE ser adivinhável nem permitir listar
  outras imagens, e o armazenamento das imagens NÃO DEVE ficar acessível diretamente.
- **FR-010**: Trocar uma imagem NÃO DEVE apagar a anterior; ela fica ligada à versão antiga do
  perfil no histórico.

**Histórico e reversão (princípio VII)**
- **FR-011**: Toda criação, alteração, arquivamento, restauração e reversão de perfil ou conta DEVE
  registrar autor, data/hora e o estado anterior e o novo.
- **FR-012**: Cada perfil e cada conta DEVE ter uma tela de histórico com as alterações, da mais
  recente para a mais antiga, mostrando campo a campo o antes e o depois.
- **FR-013**: O **dono** DEVE poder reverter um perfil ou uma conta para qualquer versão anterior;
  a reversão cria uma nova versão e respeita a regra de unicidade do @ (FR-005) e nunca muda o slug (FR-002a).
- **FR-014**: Perfis e contas NUNCA são apagados; "remover" é arquivar, e arquivados podem ser
  restaurados.
- **FR-015**: Edições concorrentes DEVEM ser detectadas: salvar sobre uma versão desatualizada é
  recusado com mensagem clara.

### Key Entities

- **Perfil**: marca da agência. Nome, slug único, nicho, bio, idioma, status, logo, banner,
  arquivado (sim/não), versão atual, autor e datas. Tem várias contas e várias versões.
- **Conta**: presença do perfil numa plataforma. Plataforma (ou nome livre), @ normalizado, link,
  status, observação, arquivada (sim/não), versão atual, autor e datas. Pertence a um perfil.
- **Imagem**: arquivo enviado (logo ou banner) com tipo, tamanho, dimensões e quem enviou;
  nunca apagada, referenciada pelas versões do perfil.
- **Versão (histórico)**: registro imutável de uma mudança num perfil ou conta: número da versão,
  autor (usuário ou, no futuro, cliente MCP), data/hora, tipo (criado, alterado, arquivado,
  restaurado, revertido) e o estado completo antes e depois.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Cadastrar um perfil com uma conta leva menos de 2 minutos.
- **SC-002**: Os 2 perfis atuais da agência (Queridinhos e A Taverna Nerd) podem ser cadastrados
  com todas as contas que existem hoje, sem campo faltando para os dados de identidade.
- **SC-003**: A lista de perfis abre em menos de 1 segundo na rede de casa, com as miniaturas.
- **SC-004**: 100% das alterações feitas nos testes aparecem no histórico com autor, data e
  antes/depois.
- **SC-005**: Reverter um perfil para uma versão anterior leva menos de 30 segundos e restaura
  100% dos campos daquela versão (inclusive logo e banner).
- **SC-006**: Nenhum teste consegue apagar de fato um perfil, conta ou imagem pela aplicação.

## Assumptions

- Todos os usuários logados (dono e membro) podem criar, editar, arquivar e restaurar; só a
  **reversão** para versões anteriores é reservada ao dono (princípio VII: "o dono pode reverter").
- A importação dos perfis de `../shared/perfis/` é a spec 011; aqui o cadastro é manual.
- Kit de marca (cores, fontes, legendas) é a spec 004; aqui o perfil só tem logo e banner.
- Métricas das plataformas (seguidores, views) e integração com APIs das redes ficam fora.
- O histórico genérico construído aqui (versões com antes/depois e reversão) será reutilizado
  pelas próximas specs de domínio.
- Arquivamento é por registro; arquivar um perfil não arquiva automaticamente suas contas.
