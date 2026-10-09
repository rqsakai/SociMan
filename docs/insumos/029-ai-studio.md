# Insumo da 029: AI Studio (biblioteca da agência)

Pedido do dono em 2026-10-09. Este arquivo é insumo para o `/speckit-specify`, não é spec.

## Problema
- Avatares, cenários, vozes, produtos e cenas pertencem a um perfil (`perfil_id` obrigatório desde a 007, 010, 012 e 025). Para montar um vídeo, o dono entra no perfil e navega por abas.
- Na criação da cena (010), não dá para criar o cenário, o avatar ou o produto que falta. É preciso sair, criar em Assets e voltar.
- A página provisória `/app/estudio` (correção de 2026-10-09: seletor de perfil + as abas do perfil) só tapa o buraco. A 029 a substitui.

## Decisões do dono (2026-10-09)
1. **Os assets são da agência, com perfil opcional.** A biblioteca do AI Studio é uma só. Cada item (avatar, cenário, voz, produto, cena e os outros assets) pode ter um **perfil base**, que é só uma referência: na geração, o guia de comunicação e as proibidas desse perfil entram no prompt (a regra `usa_guia` da 017). O item pode ser usado em vídeo de **qualquer** perfil.
2. **Menu próprio, com os tipos separados.** O grupo **AI Studio** no menu principal tem os itens:
   - **Avatares:** kit padrão, looks e poses, consentimento (025);
   - **Cenários:** cena e variações (025);
   - **Vozes** (025);
   - **Produtos** (012);
   - **Cenas** (010);
   - **Assets:** os outros tipos da 007, ou seja, imagem, sticker, marca d'água e fundo;
   - **Movimentos:** "em breve", lugar guardado para a 030.
3. **Na hora de gerar, escolhe-se o perfil base.** Vale para gerar avatar, voz, produto, cena etc.: o formulário do passo traz "Perfil base" (opcional, e o padrão é o perfil base do item). Sem perfil, só valem as regras do tipo, sem guia.
4. **A clonagem de movimento é a 030**, não a 029. A 029 só guarda o item no menu.

## O que a spec precisa cobrir
- **Dados:**
  - `perfil_id` passa a ser opcional (é o "perfil base") em `assets`, `cenas`, `produtos` e `vozes`; os itens existentes mantêm o perfil atual como base;
  - mudar o perfil base é uma edição versionada (princípio VII);
  - a unicidade de nome, hoje por perfil (assets, vozes, rótulos), passa a ser por agência ou continua por perfil base? Decidir no clarify.
- **Usos cruzados:**
  - a cena (010) passa a aceitar avatar, cenário e produto de qualquer perfil (hoje recusa os de fora com 422);
  - o conteúdo e o destino (014) continuam do perfil e da conta da postagem;
  - o kit de marca (004/007: fundo, marca d'água) continua do perfil e escolhe da biblioteca da agência; "em uso no kit" continua bloqueando arquivar.
- **Criação no lugar:** na nova cena, "+ Novo avatar/cenário/produto" abre o cadastro num diálogo e volta já escolhido.
- **Página do perfil:**
  - as abas Assets, Cenas, Produtos e Vozes saem;
  - no lugar, entram atalhos "Ver no AI Studio" com o filtro do perfil base;
  - os links antigos (`?aba=assets` etc.) redirecionam, como foi feito com `?aba=cortes` na 024.
- **Listas do AI Studio:**
  - filtros de perfil base ("Sem perfil" incluso), tag, busca e arquivados, na URL;
  - a lista de avatares mostra a situação do kit;
  - a de vozes, o estado e a sincronização.
- **API:**
  - rotas de lista sem perfil (`/api/assets?perfilId=…`, `/api/cenas?…`, `/api/produtos?…`, `/api/vozes?…`), com as rotas por perfil mantidas como `deprecated`;
  - classificar no `mcp/mapa.py`;
  - o MCP continua só lendo.
- **Geração (021):** o pedido de passo aceita `perfilBaseId`; a chamada grava qual guia foi usado (como `guia_perfil_version` já faz).
- **LGPD (025):** nada muda. O consentimento e a revogação são do item, não do perfil.
- **Aprendizado e analytics:** filtram por perfil do **conteúdo**, não do asset. Conferir se algo lê `asset.perfil_id` como dono.
- **e2e:** menu e listas, criar um avatar sem perfil, usar um cenário do perfil A numa cena do perfil B, criação no lugar, redirecionamento dos links antigos.

## Fora da 029
- A clonagem de movimento (030).
- Permissões por perfil (multi-tenant futuro): por enquanto, dono e membro veem toda a biblioteca.
