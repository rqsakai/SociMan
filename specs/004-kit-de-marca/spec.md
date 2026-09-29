# Feature Specification: Kit de marca por perfil e aplicação nos cortes (004-kit-de-marca)

**Feature Branch**: `004-kit-de-marca`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "004-kit-de-marca: identidade visual por perfil em tokens que o produtor consiga aplicar: paleta, fontes, estilo de legenda, estilo do cartão de gancho, marca d'água/logo, stickers, card final/CTA, bordões e nomes de séries (docs/visao.md). Princípio III: marca em tokens, não em texto livre."

## Clarifications

### Session 2026-09-29

- Q: O kit só fica guardado ou já é aplicado nos cortes? → A: Guardado **e aplicado**: o SociMan aplica marca d'água, cartão de gancho e card final num corte (pós-processamento de vídeo). O estilo de legenda continua sendo aplicado pelo produtor de cortes, com os tokens exportados.
- Q: Como ficam as fontes? → A: O perfil pode enviar fontes próprias (TTF/OTF), além das fontes padrão.
- Q: De onde vem o corte que recebe a marca? → A: Upload do vídeo pelo SociMan (interface ou API), com o resultado guardado para baixar.
- Q: Onde ficam os vídeos, se nada pode ser apagado e o NVMe tem ~100 GB livres? → A: Tudo o que é pesado ou cresce sem parar fica no HD de 4 TB (`/media/sakai/BACKUP/tiktok`, ext4, 2,1 TB livres). O armazenamento de arquivos único do SociMan (imagens, fontes e vídeos) passa para o HD, assim como os temporários de upload e de processamento; no NVMe ficam só a aplicação, o banco e o cache de sessões. Os arquivos que já existem (logos e banners da 003) são migrados. Sem cota por soma de bytes. Proteções obrigatórias: um arquivo sentinela na pasta (sem ele, nada é gravado, para não encher o NVMe se o HD não estiver montado) e recusa de gravações com menos de 20 GB livres (configurável), com uso e espaço livre na tela.
- Q: O card final entra por cima do fim do corte ou depois dele? → A: Por cima dos últimos N segundos; a duração do corte não muda.
- Q: Quem queima o gancho, se o OpenShorts já queima um automático? → A: Só o SociMan. A exportação manda `openshorts.hook.enabled = false` (o preset mais próximo fica só como referência), e o produtor gera os cortes sem o gancho automático do OpenShorts.
- Q: Qual a validade dos links de fonte e marca d'água na exportação? → A: Links assinados sem validade; valem enquanto o arquivo existir.
- Q (dono, 2026-09-29, depois da POC): o gancho e o card final podem ter imagem de fundo? → A: Sim. Os dois ganham tipo de fundo "cor" ou "imagem"; com imagem, ela preenche a área (recorte sem distorção) e a cor do kit vira uma camada por cima com opacidade ajustável.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Definir o kit de marca do perfil (Priority: P1)

Na aba "Marca" de um perfil, o usuário define a identidade visual em campos objetivos: paleta,
fontes, estilo da legenda, estilo do cartão de gancho, marca d'água, card final (CTA), bordões e
nomes de séries. Cada escolha tem prévia visual e só aceita valores que o produtor consegue
aplicar.

**Why this priority**: resolve o problema de "resultado cru" (visao.md). Sem kit não há marca a
aplicar nem a exportar.

**Independent Test**: para "Queridinhos", definir legenda branca com contorno preto, embaixo,
estilo karaokê com destaque rosa; gancho com fundo rosa e texto branco; marca d'água
"@meusqueridinhos10" no canto inferior direito; salvar e ver a prévia de cada item.

**Acceptance Scenarios**:

1. **Given** um perfil sem kit, **When** o usuário abre a aba Marca, **Then** vê um kit inicial
   com valores padrão válidos (as cores do padrão atual dos cortes) e pode editá-lo.
2. **Given** a paleta, **When** o usuário cadastra cores com nome (ex.: "Rosa Queridinhos"
   `#FF5FA2`), **Then** essas cores ficam disponíveis nos seletores de cor dos outros itens.
3. **Given** um valor fora do permitido (cor inválida, tamanho de fonte fora da faixa, posição
   inexistente), **When** o usuário salva, **Then** o sistema recusa indicando o campo.
4. **Given** qualquer item do kit, **When** o usuário edita, **Then** a prévia mostra o resultado
   aproximado sobre um quadro vertical de exemplo (ou sobre o último corte enviado do perfil).
5. **Given** uma alteração no kit, **When** ela é salva, **Then** entra no histórico do kit com
   autor, data e antes/depois, e o dono pode reverter (princípio VII, como na spec 003).

---

### User Story 2 - Fontes próprias (Priority: P1)

O usuário envia arquivos de fonte (TTF ou OTF) para o perfil, dá um nome e passa a escolhê-las
na legenda, no gancho e no card final, junto com as fontes padrão.

**Why this priority**: identidade visual depende de tipografia (ex.: a Taverna Nerd com fonte de
pergaminho/madeira).

**Independent Test**: enviar uma fonte TTF para "A Taverna Nerd", vê-la na lista com amostra de
texto, escolhê-la no cartão de gancho e ver a prévia com a fonte.

**Acceptance Scenarios**:

1. **Given** um perfil, **When** o usuário envia um arquivo TTF/OTF válido de até 10 MB, **Then** a
   fonte aparece na lista do perfil com nome e amostra "Os achadinhos que você queria".
2. **Given** um arquivo que não é fonte (mesmo com extensão .ttf) ou maior que 10 MB, **When** o
   usuário envia, **Then** é recusado com a razão.
3. **Given** uma fonte em uso no kit, **When** o usuário tenta arquivá-la, **Then** o sistema avisa
   onde ela é usada e não deixa arquivar até trocar.
4. **Given** o kit, **When** o usuário escolhe a fonte, **Then** as opções são as fontes padrão
   mais as fontes ativas do próprio perfil.

---

### User Story 3 - Exportar o kit para o produtor de cortes (Priority: P1)

O produtor de cortes (agentes da agência e, depois, o MCP) obtém o kit do perfil num formato
estruturado e já traduzido para o que o gerador de cortes aceita hoje: parâmetros do estilo de
legenda, o estilo de gancho pré-definido mais próximo e links para fontes e marca d'água.

**Why this priority**: a legenda continua sendo aplicada pelo gerador de cortes; sem exportar, o
kit não chega a ela.

**Independent Test**: baixar o kit de "Queridinhos" em JSON; conferir que os parâmetros de
legenda estão dentro dos valores aceitos pelo gerador e que os links de fonte e marca d'água
abrem.

**Acceptance Scenarios**:

1. **Given** um kit salvo, **When** alguém pede a exportação, **Then** recebe um documento com a
   versão do kit, os tokens completos e uma seção "gerador de cortes" com os parâmetros de legenda
   e o estilo de gancho pré-definido mais próximo.
2. **Given** tokens que o gerador não suporta (ex.: cor do gancho personalizada), **When** a
   exportação é gerada, **Then** a seção do gerador indica a aproximação usada, e o kit completo
   segue disponível para o passo de marca do SociMan (US4).
3. **Given** a exportação, **When** ela é baixada pela interface, **Then** vem como arquivo
   `kit-<slug>-v<versão>.json`.

---

### User Story 4 - Aplicar a marca num corte (Priority: P2)

O usuário envia um corte (vídeo vertical já com legenda), escolhe o perfil e o texto do gancho, e
pede "Aplicar marca". O SociMan processa em segundo plano e entrega um novo vídeo com o cartão de
gancho no início, a marca d'água durante o vídeo e o card final no fim, conforme o kit. O dono
baixa o resultado e posta manualmente.

**Why this priority**: fecha o ciclo "marca aplicada no corte", mas depende do kit (US1–US2) e é
a parte mais pesada.

**Independent Test**: enviar um MP4 vertical de 30 s para "Queridinhos" com o gancho "3 achadinhos
que salvaram minha cozinha"; acompanhar o status até "Pronto"; baixar e ver o gancho nos primeiros
segundos, a marca d'água o tempo todo e o card final nos últimos segundos.

**Acceptance Scenarios**:

1. **Given** um perfil com kit, **When** o usuário envia um vídeo MP4/MOV/WebM de até 500 MB e até
   3 minutos, **Then** o processamento entra na fila e a tela mostra o status (Na fila,
   Processando com progresso, Pronto ou Falhou).
2. **Given** o processamento pronto, **When** o usuário abre o resultado, **Then** pode assistir no
   navegador e baixar o arquivo; o vídeo original continua guardado e inalterado.
3. **Given** o kit do perfil, **When** a marca é aplicada, **Then** o resultado tem: cartão de
   gancho com o texto informado na fonte/cores/posição do kit durante a duração do kit; marca
   d'água (logo ou @) na posição, escala e opacidade do kit durante todo o vídeo; card final com o
   CTA do kit por cima dos últimos segundos definidos (a duração do vídeo não muda); áudio
   preservado.
4. **Given** um vídeo inválido (não é vídeo, corrompido, mais longo que 3 min, maior que 500 MB),
   **When** é enviado, **Then** é recusado com a razão, sem entrar na fila.
5. **Given** um processamento que falha, **When** o usuário vê o status, **Then** vê "Falhou" com
   uma razão compreensível e pode tentar de novo.
6. **Given** o SociMan, **When** a marca é aplicada, **Then** nada é publicado em rede social
   (princípio I); o resultado só fica disponível para download.
7. **Given** a lista de cortes do perfil, **When** o usuário a abre, **Then** vê os envios com
   data, autor, gancho, versão do kit usada e status.

---

### Edge Cases

- Vídeo horizontal ou quadrado: é aceito; a marca é aplicada no quadro como ele é (sem cortar nem
  esticar), com posições relativas ao tamanho do vídeo.
- Vídeo sem áudio: processado normalmente.
- Texto de gancho longo: quebra em até 3 linhas; acima disso é recusado ("Gancho longo demais").
- Kit sem marca d'água ou sem card final (desligados): o passo correspondente é pulado.
- Kit alterado enquanto um corte está na fila: o corte usa a versão do kit vigente no momento do
  envio (registrada no corte).
- Vários envios ao mesmo tempo: processados um de cada vez, na ordem; a tela mostra a posição na
  fila.
- Servidor reiniciado durante o processamento: o corte volta para a fila e é reprocessado.
- Fonte do kit arquivada depois de usada em cortes antigos: os cortes antigos continuam
  reproduzíveis (o arquivo da fonte nunca é apagado).
- Envio interrompido: nada entra na fila; nenhum arquivo parcial é mostrado.
- HD de dados desmontado ou sem o sentinela: envios de corte, fonte e imagem são recusados ("O HD
  de dados não está disponível") e o processamento espera; nenhum arquivo vai para o disco do
  sistema. Imagens, fontes e vídeos já guardados ficam indisponíveis até o HD voltar; login e
  edição do kit continuam funcionando se a aplicação já estiver no ar.
- HD de dados com pouco espaço (abaixo do mínimo configurado): novas gravações são recusadas
  ("Pouco espaço no HD de dados"); nada é apagado para abrir espaço.
- Corte que já veio com o gancho do gerador: é responsabilidade do produtor gerar sem o gancho
  automático; o SociMan não detecta gancho já queimado.

## Requirements *(mandatory)*

### Functional Requirements

**Kit de marca (tokens)**
- **FR-001**: Cada perfil DEVE ter um kit de marca com: paleta (1 a 12 cores com nome e valor
  hexadecimal), estilo da legenda, cartão de gancho, marca d'água, card final, bordões (até 20
  textos curtos) e nomes de séries (até 20 nomes).
- **FR-002**: Estilo da legenda DEVE conter exatamente os parâmetros que o gerador de cortes aceita:
  fonte, tamanho (10–200), cor do texto, cor e espessura do contorno (0–10), cor e opacidade do
  fundo (0–1), estilo (clássico ou karaokê), cor de destaque (karaokê), efeito (nenhum, brilho,
  pop, caixa), posição (topo, meio, base) e maiúsculas (sim/não).
- **FR-003**: Cartão de gancho DEVE conter: fonte, cor do texto, cor e opacidade do fundo, cor e
  espessura do contorno, posição (topo, centro, base), tamanho (P, M, G), duração (1–10 s) e
  ligado/desligado.
- **FR-004**: Marca d'água DEVE conter: tipo (logo do perfil, imagem própria com transparência ou
  texto com o @ da conta), posição (4 cantos, centro inferior, centro superior), escala (5–40% da
  largura), opacidade (10–100%), margem e ligado/desligado.
- **FR-005**: Card final DEVE conter: texto de CTA (até 80 caracteres), fonte, cor do texto, cor de
  fundo, mostrar logo (sim/não), duração (1–5 s) e ligado/desligado.
- **FR-005a**: O cartão de gancho e o card final DEVEM ter tipo de fundo "cor" ou "imagem". Com
  imagem: a imagem de fundo do perfil preenche a área (caixa do gancho ou quadro inteiro do card),
  recortada sem distorção, e a cor de fundo do kit é aplicada por cima como camada com opacidade
  (0–1). O padrão é "cor", e os kits já salvos continuam iguais.
- **FR-005b**: O perfil DEVE poder enviar imagens de fundo (PNG, JPG ou WebP, até 5 MB, mínimo
  540×540 px), listadas para escolha. Imagens nunca são apagadas.
- **FR-006**: Todo valor do kit DEVE ser validado (cores hexadecimais, faixas, opções fechadas);
  cores podem referenciar a paleta por nome. Texto livre só em bordões, séries e CTA.
- **FR-007**: O kit DEVE ter histórico, reversão pelo dono e controle de edição concorrente, como os
  registros da spec 003 (princípio VII).
- **FR-008**: A interface DEVE mostrar prévia de legenda, cartão de gancho, marca d'água e card
  final sobre um quadro vertical de exemplo.

**Fontes**
- **FR-009**: O perfil DEVE poder enviar fontes TTF/OTF de até 10 MB, com nome; o arquivo é validado
  pelo conteúdo; fontes nunca são apagadas, só arquivadas (e não podem ser arquivadas em uso).
- **FR-010**: As fontes disponíveis no kit são as padrão (Anton, Noto Serif Bold, Liberation Sans,
  Liberation Serif) mais as fontes ativas do perfil.

**Exportação**
- **FR-011**: DEVE haver uma exportação do kit em formato estruturado, versionada, com os tokens
  completos, links de fontes e marca d'água (assinados e sem validade, valendo enquanto o arquivo
  existir), e uma seção para o gerador de cortes com os parâmetros de legenda e o gancho
  **desligado** (`enabled = false`, porque só o SociMan queima o gancho), com o estilo
  pré-definido mais próximo só como referência (e a aproximação indicada).
- **FR-012**: A exportação DEVE ser acessível a usuários logados (interface e API); o acesso por
  agentes de IA vem na spec 009 (MCP).

**Aplicação da marca**
- **FR-013**: O usuário DEVE poder enviar um vídeo (MP4, MOV ou WebM; até 500 MB e 3 min) para um
  perfil, com texto do gancho (até 120 caracteres, até 3 linhas), e pedir a aplicação da marca.
- **FR-014**: O processamento DEVE rodar em segundo plano, um por vez, com status (na fila,
  processando com percentual, pronto, falhou com razão) e sobreviver a reinício do servidor.
- **FR-015**: O resultado DEVE ter cartão de gancho, marca d'água e card final conforme a versão do
  kit registrada no envio, com áudio, resolução e duração preservados (o card final fica por cima
  dos últimos segundos).
- **FR-016**: Original e resultado DEVEM ficar guardados e disponíveis para assistir e baixar;
  nenhum vídeo é apagado pela aplicação; nada é publicado (princípio I). Vídeos, fontes e imagens ficam no
  HD de dados (FR-018).
- **FR-017**: Cada envio registra autor, data, perfil, texto do gancho, versão do kit, status e
  duração do processamento.
- **FR-018**: Todo arquivo de mídia (imagens, fontes, vídeos) e todo temporário grande (upload e
  processamento) DEVE ficar no HD de dados, num caminho configurável (padrão
  `/media/sakai/BACKUP/tiktok/sociman`) com um arquivo sentinela criado pelo script de setup. Sem o
  sentinela, o armazenamento, os envios e o processamento DEVEM recusar operar. Gravações DEVEM
  ser recusadas quando o espaço livre do HD ficar abaixo de um mínimo configurável (padrão 20 GB),
  e a interface DEVE mostrar o uso e o espaço livre. Os arquivos já existentes (spec 003) DEVEM ser
  migrados para o HD sem perda.

### Key Entities

- **Kit de marca**: um por perfil; tokens de paleta, legenda, gancho, marca d'água, card final,
  bordões e séries; versão e histórico.
- **Fonte**: arquivo de fonte de um perfil (nome, formato, tamanho, quem enviou); nunca apagada.
- **Imagem de marca d'água**: imagem própria (com transparência) usada como marca d'água, quando o
  kit não usa o logo do perfil.
- **Corte**: vídeo enviado para um perfil, com gancho, versão do kit, status do processamento,
  vídeo original e vídeo com marca.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Preencher o kit de um perfil a partir do padrão leva menos de 5 minutos.
- **SC-002**: 100% dos parâmetros de legenda exportados estão dentro dos valores aceitos pelo
  gerador de cortes (verificado automaticamente).
- **SC-003**: Um corte vertical de 60 s recebe a marca em menos de 2 minutos no servidor de casa
  (sem placa de vídeo).
- **SC-004**: Em 100% dos cortes processados nos testes, gancho, marca d'água e card final aparecem
  nos tempos e posições do kit (verificado por amostragem de quadros).
- **SC-005**: Nenhum vídeo, fonte ou imagem pode ser apagado pela aplicação.
- **SC-006**: Os dois perfis reais conseguem expressar no kit o estilo registrado hoje em
  `../shared/perfis/*/perfil.md` (seção Estilo visual) sem recorrer a texto livre.
- **SC-007**: Com o HD de dados ausente ou sem o sentinela, 0 bytes de mídia ou de temporário são
  gravados no disco do sistema, e 100% dos envios são recusados com a razão (verificado
  automaticamente).
- **SC-008**: Depois da migração, 100% dos logos e banners da spec 003 continuam abrindo, e a
  contagem de objetos antes e depois é igual.

## Assumptions

- A legenda com tempo por palavra continua sendo gerada e queimada pelo gerador de cortes
  (OpenShorts); o SociMan não reprocessa legendas, só exporta o estilo.
- O produtor gera os cortes no OpenShorts **sem o gancho automático**; o gancho é sempre queimado
  pelo SociMan (US4).
- O HD de dados não é backup: é o único lugar onde os arquivos de mídia ficam. Backup fica fora
  desta spec.
- O gerador de cortes hoje aceita só 6 estilos de gancho pré-definidos e uma marca d'água fixa;
  por isso gancho personalizado e marca d'água por perfil são aplicados pelo SociMan (US4).
- "Stickers" (visao.md) ficam fora desta spec: entram como imagens adicionais numa spec futura.
- O servidor de casa não tem placa de vídeo por enquanto; o processamento é por CPU, um corte por
  vez.
- Permissões como na 003: dono e membro editam o kit, enviam fontes e cortes; só o dono reverte
  versões do kit.
- Integração automática com o fluxo dos agentes (pegar cortes do OpenShorts sem upload) fica para
  specs futuras (008/009).
