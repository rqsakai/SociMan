# Pesquisa (Fase 0): 007-assets-do-perfil

Fontes consultadas: a spec, a constitution 3.0.0, o `CLAUDE.md` (Frontend, Kit de marca,
armadilhas 13 a 18), o código da 003 e da 004 (`history.py`, `storage.py`, `datadir.py`,
`imaging.py`, `midia.py`, `router_midia.py`, `perfis/models.py`, `perfis/service_imagens.py`,
`marca/tokens.py`, `marca/service_kit.py`, `marca/fontes.py`, `marca/router_marca_dagua.py`,
`marca/router_fundos.py`, `cortes/service.py`), a migration `0004_fundo_imagem`, o edge
(`docker/nginx/default.conf.template`), o `docker-compose.yml` (imgproxy), os seletores do SPA
(`components/marca/{ProfileImagePicker,FundoImagePicker,WatermarkImagePicker}.tsx`) e o modelo
real `../shared/shop/persona.md` (+ `persona/achadinhos-cozinha.jpg` 2048×2048 e
`persona/achadinhos-diner.jpg` 1080×1080).

## R1. Modelo: `assets` + `asset_files` sobre a tabela `images` (FR-001, FR-002, FR-003)
- **Decisão:** duas tabelas novas, e a `images` da 003 continua sendo o **registro de arquivos**:
  - `assets`: o item da biblioteca (tipo, nome, descrição, tags, campos de avatar e cenário,
    arquivo principal, versão e arquivamento);
  - `asset_files`: liga um asset a uma linha de `images` (`image_id` UNIQUE) e guarda o papel do
    arquivo no asset (`referencia`, `pose` ou `arquivo`), o look e o uso, o rótulo e o "quando
    usar" da pose, uma nota, a ordem e o arquivamento;
  - `images` continua imutável (FR-010 da 003): o upload do asset valida, grava o objeto no bucket
    `sociman` (HD) e cria a linha em `images` exatamente como hoje, só com o `kind` do tipo do
    asset (R3). O imgproxy continua lendo só `s3://sociman/`.
- **Por quê:**
  - o kit (`watermark.imagem_id`, `hook/endCard.fundo_imagem_id`) e os cortes (`kit_tokens` com
    `object_key`) já apontam para `images.id` e `images.object_key`. Com os arquivos continuando em
    `images`, **nenhuma referência muda**: a migração não reescreve JSONB do kit nem dos cortes
    (R2, SC-003);
  - validação, gravação no HD, URLs do imgproxy e links de mídia já existem para `images`;
  - pose e referência de look têm metadados editáveis e ordem, o que a `images` (imutável) não
    pode ter; separar arquivo (imutável) de papel no asset (editável) mantém o FR-010 da 003;
  - avatar e cenário são o mesmo agregado com campos opcionais: uma tabela só, com os campos
    específicos em colunas anuláveis validadas por tipo, é mais simples de buscar e migrar que
    uma tabela por tipo.
- **Alternativas:**
  - **evoluir a `images`** (tipo, nome, tags, rótulo e ordem na própria imagem): quebra a
    imutabilidade da 003, mistura arquivo com metadado, e o avatar (um item com N imagens) não
    cabe numa linha de imagem;
  - **arquivos em JSONB dentro de `assets`**: sem FK para `images`, sem índice único para o
    rótulo da pose (edge case "duas poses com o mesmo rótulo") e sem consulta de "onde é usado"
    por `image_id`;
  - **tabelas `avatars`, `cenarios`, `stickers`…**: seis tabelas e seis rotas para o que a grade
    lista, filtra e busca junto.

## R2. Migração das imagens da 004 (FR-006, US2-3, US3-3, SC-003)
- **Decisão:** a migration `0005_assets` cria as tabelas e faz um **backfill** das imagens da 004:
  - para cada `images` com `kind` em (`watermark`, `fundo`) **sem** `asset_files`, cria um asset
    (`tipo` `marca_dagua` ou `fundo`) com um arquivo (`role = arquivo`, principal), com
    `created_at`/`created_by` da imagem, nome "Marca d'água 1", "Fundo 1"… na ordem de envio, e
    a versão 1 no `entity_versions` (`action = created`, `actor_kind = system:migration`,
    `details = {"migracao": "0005_assets", "image_id": …}`);
  - os ids das imagens **não mudam**: o kit e os cortes continuam válidos sem tocar em JSONB;
  - o backfill fica numa função idempotente (`assets/backfill.py`, SQL puro sobre a conexão), que
    a migration chama com `op.get_bind()` e o teste chama direto (R10);
  - logos e banners da 003 **não** entram na biblioteca (são do perfil, não do kit; a spec só
    pede fundos e marca d'água). Imagens com `kind` `logo`/`banner` continuam fora dos seletores.
- **Verificação (SC-003):** o `quickstart.md` §0 roda antes e depois, no dev:
  ```sql
  SELECT kind, count(*) FROM images WHERE kind IN ('watermark','fundo') GROUP BY kind;
  SELECT i.kind, count(*) FROM images i JOIN asset_files f ON f.image_id = i.id
   WHERE i.kind IN ('watermark','fundo') GROUP BY i.kind;               -- tem de ser igual
  SELECT count(*) FROM images i LEFT JOIN asset_files f ON f.image_id = i.id
   WHERE i.kind IN ('watermark','fundo') AND f.id IS NULL;              -- tem de ser 0
  ```
  e confere que `GET /api/perfis/{id}/kit` e a prévia do kit continuam iguais (mesmo
  `fundo_imagem_id`/`imagem_id`), e que um corte enviado depois da migração sai com o fundo.
- **Rotas antigas da 004:** `POST/GET /api/perfis/{id}/marca-dagua` e `…/fundos` **continuam**
  (os testes e o e2e da 004 seguem valendo), mas o `upload_image` passa a criar também o asset
  (mesma transação), para que nenhuma imagem nova de kit fique fora da biblioteca. O SPA deixa de
  usá-las (R6); elas ficam marcadas `deprecated` no OpenAPI e saem numa spec futura.
- **Alternativas:**
  - **copiar os objetos para chaves novas** (`perfis/{id}/assets/…`): duplica arquivo no HD e
    obriga a reescrever o JSONB do kit e dos cortes; nada ganha;
  - **backfill preguiçoso** (criar o asset na primeira abertura da biblioteca): a SC-003 não
    teria momento de verificação, e o `GET` passaria a gravar;
  - **script separado** (`sociman assets migrar`): um passo manual a mais que alguém esquece; o
    `start.sh` já roda `alembic upgrade head`.

## R3. Tipos, validação e limite de 20 MB (FR-004, edge cases)
- **Decisão:**
  - `asset_tipo`: `avatar`, `cenario`, `fundo`, `sticker`, `marca_dagua`, `imagem`. O tipo é
    imutável (trocar o tipo é criar outro asset);
  - o `image_kind` é a **classe técnica** da imagem (validação e onde ela pode entrar no kit e
    no corte), e o tipo do asset é a classificação do usuário. O `image_kind` ganha só `avatar` e
    `imagem`; os demais tipos reaproveitam as classes da 004, que já têm exatamente a regra
    certa:

    | Tipo do asset | `image_kind` | Formatos | Transparência | Mínimo | Arquivos |
    |---|---|---|---|---|---|
    | `avatar` | `avatar` (novo) | PNG, JPG, WebP | não exige | 256×256 | vários: `referencia` (com look) e `pose` |
    | `cenario` | `fundo` | PNG, JPG, WebP | não exige | 540×540 | vários: `referencia` |
    | `fundo` | `fundo` | PNG, JPG, WebP | não exige | 540×540 | um (`arquivo`) |
    | `sticker` | `watermark` | PNG, WebP | **exige** ("O sticker precisa ter fundo transparente") | 64×64 | um |
    | `marca_dagua` | `watermark` | PNG, WebP | **exige** ("A imagem precisa ter fundo transparente", como na 004) | 64×64 | um |
    | `imagem` | `imagem` (novo) | PNG, JPG, WebP | não exige | 64×64 | um |

    Assim, uma imagem de cenário é, para o kit, o corte e os links de mídia, uma imagem de
    fundo, e um sticker é uma imagem com transparência como a marca d'água: o
    `cortes/service.resolve_corte_tokens` (que exige `kind = fundo`), o `router_midia.resolve`
    (`marca_dagua` → `watermark`, `fundo` → `fundo`) e a exportação **não mudam**. A mensagem de
    transparência do sticker vem de um parâmetro novo, `transparency_message`, do
    `validate_image`;
  - **tamanho:** `validate_image` ganha o parâmetro `max_bytes` (padrão 5 MB, como hoje, para logo,
    banner e as rotas antigas); as rotas da biblioteca usam **20 MB**, com a mensagem "Arquivo
    maior que 20 MB". O `read_limited` também recebe o limite (hoje lê até 5 MB + 1);
  - **pixels:** o `Image.MAX_IMAGE_PIXELS = 40_000_000` continua (um JPG de 20 MB passa de 40 MP
    raramente). Acima disso, a mensagem passa a ser "Imagem grande demais (máximo 40 megapixels)"
    em vez de "Formato não aceito" (a razão aparece, como pede o edge case);
  - **imgproxy:** fixar `IMGPROXY_MAX_SRC_RESOLUTION=40` no compose, para o imgproxy aceitar tudo o
    que a API aceita (o padrão depende da versão da imagem `latest`; verificar com
    `docker compose exec imgproxy imgproxy version` na implementação). O `IMGPROXY_MAX_SRC_FILE_SIZE`
    padrão (0, sem limite) já serve;
  - **edge:** o `location /api/` aceita 8 MB. As duas rotas de upload da biblioteca ganham uma
    `location` própria, como fontes e cortes:
    ```nginx
    location ~ ^/api/(perfis/[^/]+/assets/arquivo|assets/[^/]+/arquivos)$ {
      client_max_body_size 21m;   # a API recusa > 20 MB com invalid_image; folga para o multipart
      …
    }
    ```
    Com buffering normal (21 MB não precisa de streaming). Mudou o template → `docker compose
    restart edge` (armadilha 13). O spool do upload já vai para `work/tmp` no HD (`TMPDIR`);
  - HD fora: `datadir.ensure_writable()` **antes** de ler o corpo (503/507), como na 004.
- **Por quê:** reaproveita a validação pelo conteúdo que já tem teste; a transparência "real" é o
  `_has_transparency` da marca d'água (canal alfa com pelo menos um pixel não opaco), que é o que
  a spec pede para sticker.
- **Alternativas:** subir o `/api/` inteiro para 21 MB (aumenta a superfície de todas as rotas,
  rejeitado na 004 pelo mesmo motivo); validar transparência só pelo modo (`RGBA` com tudo opaco
  passaria).

## R4. Histórico e reversão: o asset é o agregado (FR-007, US1-5, princípio VII)
- **Decisão:** `entity_type = "asset"` no `entity_versions`, e **os arquivos fazem parte do
  snapshot do asset**:
  - `__versioned_fields__` = `tipo` (imutável, só exibição), `name`, `description`, `tags`,
    `prompt`, `voice_tone`, `image_rules`, `primary_file_id`, `archived` e `files`, uma
    propriedade que devolve a lista ordenada dos arquivos com `id`, `image_id`, `role`, `look`,
    `uso`, `label`, `quando_usar`, `notes`, `position` e `archived`;
  - toda mutação (dados, enviar arquivo, editar pose, reordenar, arquivar arquivo, principal,
    arquivar/restaurar o asset) é **uma** versão do asset, com `history.record` na mesma transação
    e o `changed_fields` dizendo o que mudou (`files`, `tags`…). A tela de histórico genérica da
    003 funciona sem mudança;
  - controle otimista: todas as mutações recebem `version` (409 `version_conflict`, "Este asset
    foi alterado por outra pessoa; recarregue"), **menos o envio de arquivo**, que só acrescenta
    (não há atualização perdida) e permite enviar várias poses em sequência;
  - **reversão (só dono, `RequireOwner`):** restaura os campos e, nos arquivos, o metadado, a
    ordem e o arquivamento da versão escolhida. Arquivo que não existia na versão alvo é
    **arquivado** (nunca apagado). Se a reversão arquivar o asset ou um arquivo em uso no kit,
    409 `revert_conflict` com os usos (R5). A reversão é uma nova versão (`reverted`);
  - nada é apagado: não há rota DELETE, e `storage.py` continua sem delete.
- **Por quê:** o usuário pensa no avatar como uma coisa só ("desfaz o que o agente fez no
  avatar"); histórico por arquivo obrigaria a reverter N entidades em ordem. O snapshot fica
  pequeno (dezenas de arquivos por avatar, só metadado).
- **Alternativas:** `entity_type` separado para `asset_file` (duas timelines e reversão em
  duas etapas); snapshot sem os arquivos (reordenar poses ficaria sem histórico, contra o
  princípio VII).

## R5. "Onde é usado" e arquivar com uso (FR-005, FR-007, US4-1, SC-004)
- **Decisão:** um módulo `assets/usos.py` com um **registro de provedores**, no molde do
  `fields_using_font` da 004:
  - cada provedor recebe `(db, perfil_id)` e devolve `{image_id: [Uso, …]}`; o asset está em uso
    se algum arquivo dele está em uso;
  - `Uso = {origem, rotulo, campo, fileId, bloqueia, href}`, ex.:
    `{origem: "kit", rotulo: "Card final (kit v3)", campo: "endCard.fundo_imagem_id",
    bloqueia: true, href: "/app/perfis/…?aba=marca"}`;
  - **provedor do kit (bloqueia):** lê os tokens vigentes (`service_kit.current_tokens`) e marca
    `watermark.imagem_id`, `hook.fundo_imagem_id` e `endCard.fundo_imagem_id` **não nulos**,
    mesmo com a seção desligada ou o `fundo_tipo = cor`, porque o `check_refs` valida esses ids
    sempre (arquivar quebraria o próximo salvamento do kit). Uma função pura nova em
    `marca/tokens.py`, `fields_using_image(kit, image_id)`, ao lado da `fields_using_font`;
  - **provedor de cortes (só informa):** conta os cortes do perfil cujo `kit_tokens` tem a chave
    do objeto (`imagem_key`, `fundo_imagem_key`) e lista os 5 mais recentes. Não bloqueia: o
    corte guardou os tokens resolvidos e o arquivo nunca é apagado, então arquivar o asset não
    muda nenhum corte (ver `open-questions.md`, Q1). A 006, ao importar clipes como cortes, entra
    pelo mesmo provedor sem mudança aqui;
  - **futuro (roteiros, cenas, stickers nos cortes):** a spec que criar a referência registra o
    próprio provedor (`usos.register("roteiro", fn)`); nada muda na 007;
  - **arquivar** o asset (ou um arquivo) com uso que bloqueia → 409 `asset_in_use`, "Em uso em:
    Card final (kit v3)", com `details.usos`. O SPA mostra a lista com link para o kit;
  - a grade recebe `inUse: bool` por item (uma consulta ao kit por página, barata: um kit por
    perfil) e o detalhe recebe a lista completa.
- **Por quê:** o padrão já existe para fontes (409 `font_in_use` com os campos); um registro
  deixa a 006 e as specs de roteiros e cenas acrescentarem usos sem editar os módulos da 007.
- **Alternativas:** tabela `asset_usages` mantida por gatilho ou pelo service do kit (estado
  duplicado que diverge; o kit guarda os ids em JSONB); consulta JSONB fixa só do kit (não
  estende).

## R6. Seletores do kit escolhem da biblioteca (FR-006, US2-2, US3)
- **Decisão:**
  - **API:** `GET /api/perfis/{id}/assets/imagens?tipo=…&q=…` devolve as imagens escolhíveis
    (arquivos ativos de assets ativos), com o nome do asset, o rótulo e o `ImageRef`, mais
    recentes primeiro. O seletor de **fundo** pede `tipo=fundo&tipo=cenario`; o de **marca
    d'água** pede `tipo=marca_dagua&tipo=sticker` (os dois exigem transparência; ver Q2);
  - **enviar direto no seletor:** `POST /api/perfis/{id}/assets/arquivo` (multipart `file`,
    `tipo`, `name?`) cria um asset de um arquivo e devolve o asset e a imagem. O seletor escolhe
    a imagem no rascunho do kit, como hoje: enviar não altera o kit;
  - **validação do kit (`service_kit.ref_context`):** `watermark_image_ids` passa a ser o conjunto
    das imagens de arquivos **ativos** de assets **ativos** do perfil com `images.kind =
    watermark` (tipos `marca_dagua` e `sticker`); `fundo_image_ids`, com `images.kind = fundo`
    (tipos `fundo` e `cenario`). É a única mudança de regra no kit. Salvar o kit com imagem arquivada dá `invalid_kit` ("imagem arquivada; restaure-a na
    biblioteca"); **reverter** o kit para uma versão que usa imagem arquivada dá 409
    `revert_conflict`, como já acontece com fonte arquivada;
  - **links de mídia, exportação e cortes:** não mudam. Como cenário é `kind = fundo` e sticker é
    `kind = watermark` (R3), o `router_midia.resolve`, a exportação e o
    `cortes/service.resolve_corte_tokens` aceitam as imagens da biblioteca sem nenhuma linha
    nova;
  - **SPA:** o `ProfileImagePicker` passa a listar da biblioteca (as 12 mais recentes do tipo) e
    ganha "Abrir biblioteca", um `Dialog` com busca e filtro de tipo, e o envio com limite de
    20 MB. `FundoImagePicker` e `WatermarkImagePicker` só trocam `list`/`upload` e os textos.
- **Por quê:** o kit continua guardando `images.id`, então a troca é só de origem da lista e da
  regra de pertinência; exportação, render e prévia não sabem que a biblioteca existe.
- **Alternativas:** o kit guardar `asset_id` (migração do JSONB do kit e dos cortes, e o avatar
  tem várias imagens: qual delas?); seletor abrindo a aba Assets em outra página (perde o
  rascunho do kit).

## R7. Baixar o original e copiar link (FR-008, US4-2)
- **Decisão:** o `midia.py` ganha o `MidiaKind` **`imagem`** (id = `images.id`, qualquer `kind`),
  que pode sair **sem validade** (como fonte, marca d'água e fundo: não é vídeo). O detalhe do
  asset traz, por arquivo, `link` (abre no navegador, `Content-Type` da tabela) e `downloadUrl`
  (`?download=1`, `Content-Disposition` com `<slug>-<nome-do-asset>-<n>.<ext>`):
  - o token sem `exp` é determinístico (mesmo payload, mesma assinatura), então o link é
    **estável** entre aberturas; é impossível de adivinhar (HMAC com o `JWT_SECRET`) e não pede
    login, como os links da exportação da 004;
  - o link continua valendo com o asset arquivado (o arquivo não some); a revogação de todos os
    links é trocar o `JWT_SECRET`, o mesmo risco já aceito na 004;
  - o arquivo servido é o **original** do MinIO (não a versão do imgproxy), com `Range`.
- **Por quê:** o dono cola o link no Flow/Veo ou manda para os agentes (US4); o imgproxy
  converteria para WebP e redimensionaria.
- **Alternativas:** URL pré-assinada do MinIO (expor o MinIO no edge); link de 1 h (quebra o
  "copiar link" para uso posterior, que é o caso de uso).

## R8. Busca, filtros e paginação (FR-005, SC-002, edge case "centenas")
- **Decisão:** filtro e busca no servidor, sem dependência nova:
  - `GET /api/perfis/{id}/assets?tipo=…&tag=…&q=…&archived=false&limit=48&cursor=…`;
  - `q`: `lower(name) LIKE '%q%'` ou tag igual a `lower(q)`; `tag`: `tags @> ARRAY[tag]`;
    `tipo`: vários valores (OR); ordenação por `updated_at desc, id` com cursor opaco
    (`updated_at|id` em base64url);
  - `tags` é `text[]` com índice GIN; tags normalizadas (minúsculas, sem espaço nas pontas,
    1..30 caracteres, até 20 por asset, sem repetição); a resposta traz `tags` (todas as tags
    usadas no perfil, com contagem) para o filtro em chips;
  - o SPA pagina com "Carregar mais" (`useInfiniteQuery`) e faz a busca com debounce de 250 ms.
- **Por quê:** 200 itens por perfil (SC-002) respondem em milissegundos com índice comum; uma
  busca no servidor mantém o MCP (spec 009) com o mesmo filtro.
- **Alternativas:** `pg_trgm` ou full-text (extensão e índice novos sem necessidade na escala de
  hoje); filtrar tudo no cliente (quebra com "centenas" e com o MCP).

## R9. Interface: aba "Assets", avatar e poses (US1–US4, princípio VIII)
- **Decisão:**
  - **aba "Assets"** no detalhe do perfil (`?aba=assets`, o parâmetro que o `PerfilDetalhe` já usa), com `AssetsTab`: filtros (chips de
    tipo, chips de tag, busca, "Mostrar arquivados"), grade responsiva de cards (miniatura
    `medium` do imgproxy sobre xadrez para tipos com transparência, nome, tipo, selo "Em uso",
    selo "Arquivado"), botão "Novo asset" (menu por tipo) e envio múltiplo para stickers e
    imagens (um asset por arquivo);
  - **detalhe do asset** em `/app/assets/:id` (página própria, como `/app/cortes/:id`): dados,
    tags, "onde é usado", arquivos com "Baixar original" e "Copiar link", histórico e
    arquivar/restaurar. Para **avatar**: descrição para prompts (textarea com contador de
    2.000) e **"Copiar descrição para prompt"**, tom de voz, regras de imagem, **looks**
    (referências agrupadas por `look`, com o uso, "Marcar como principal") e **poses** (grade
    com rótulo e "quando usar"). Para **cenário**: prompt do ambiente com "Copiar prompt" e
    referências;
  - **reordenar poses (e referências) sem dependência nova:** botões "Mover para a esquerda/
    direita" em cada card (funcionam no toque e no teclado, e o e2e usa) e, no desktop, arrastar
    com a API nativa do HTML5 (`draggable`, `onDragOver`, `onDrop`) como atalho. Uma chamada
    `PUT /api/assets/{id}/ordem` com a lista inteira, uma versão por reordenação. `@dnd-kit` fica
    rejeitado pelo princípio VIII (ver Q3);
  - **copiar para a área de transferência:** `navigator.clipboard.writeText` (o SPA roda em
    contexto seguro: `https://…:8543` no modo casa e `http://localhost` no dev); se falhar,
    seleciona o texto numa `Textarea` somente leitura e mostra "Copie com Ctrl+C". O texto
    copiado é o `prompt` exato do banco, sem trim nem formatação;
  - **avatar sem imagem:** o componente `Avatar` do shadcn com as iniciais e cor neutra;
  - componentes do shadcn já presentes: `Card`, `Badge`, `Dialog`, `Sheet`, `DropdownMenu`,
    `AlertDialog`, `Tabs`, `Tooltip`, `Field`/`NativeSelect`, `Textarea`, `Avatar`. Nenhum
    componente novo obrigatório (se preciso, `npx shadcn@latest add toggle-group` para os chips
    de tipo; é código gerado no repo, não dependência de runtime nova além do Radix já usado).
- **Por quê:** segue a estrutura da 005 (abas no perfil, páginas de detalhe próprias) e o
  padrão de `FontesTab`/`CortesTab`.
- **Alternativas:** detalhe em `Sheet` lateral (o avatar tem looks e poses demais para um
  painel); `@dnd-kit` (dependência nova para uma lista de ~10 poses).

## R10. Testes (princípio VI)
- **pytest (stack efêmera, `npm run test:api`):**
  - `unit/test_assets_schemas.py`: validação por tipo (campos de avatar só no avatar, limites de
    tamanho, normalização de tags);
  - `unit/test_imaging_assets.py`: novos `kind`, 20 MB, sticker sem transparência recusado com a
    mensagem da spec, mensagem de megapixels; a imagem de 20 MB + 1 byte é gerada no teste
    (ruído com `os.urandom`, sem fixture no git);
  - `unit/test_kit_tokens.py` (acréscimo): `fields_using_image`;
  - `integration/test_assets.py`: criar, enviar arquivos, looks, poses (rótulo repetido → 409
    `pose_label_in_use`), reordenar, principal, tags, busca e filtros, paginação, arquivar e
    restaurar, histórico com autor em toda mutação, reversão só dono (403 para membro) e
    reversão que arquiva arquivo novo, 409 em edição concorrente, 503/507 com o HD fora;
  - `integration/test_assets_usos.py`: arquivar asset usado no kit → 409 com a lista; trocar no
    kit e arquivar; uso por cortes só informa; `ref_context` recusa imagem arquivada;
    reversão do kit para versão com imagem arquivada → 409 `revert_conflict`;
  - `integration/test_assets_backfill.py`: imagens `watermark`/`fundo` criadas sem asset (como a
    004 deixava) → `backfill` → um asset por imagem, ids iguais, kit inalterado, histórico
    `system:migration`; rodar de novo não duplica (SC-003);
  - `integration/test_assets_midia.py`: link `imagem` sem validade, estável, download com nome,
    `Range`; link `marca_dagua` para imagem de sticker;
  - os testes da 004 (`test_fundos.py`, `test_marca_dagua.py`, `test_kit.py`, `test_export.py`,
    `test_cortes.py`) continuam verdes sem mudança de asserção, e o teste-guarda de "nenhuma rota
    DELETE" cobre as rotas novas.
- **e2e (stack e2e isolada, `npm run test:e2e`):** `e2e/assets.spec.ts`:
  - avatar "Achadinhos" com descrição, 2 looks (as imagens são geradas no teste, 1080×1080) e 3
    poses; reordenar com os botões; "Copiar descrição para prompt" (permissão
    `clipboard-read`/`clipboard-write` no contexto do Chromium e leitura com
    `navigator.clipboard.readText`);
  - cenário com imagem, escolhido como fundo do card final pelo seletor da aba Marca;
  - 3 stickers com tags, filtro por "promo"; sticker sem transparência recusado;
  - arquivar a imagem usada no kit → "Em uso em: Card final (kit v…)"; trocar e arquivar;
    "Mostrar arquivados" e restaurar;
  - `e2e/fundo.spec.ts` e `e2e/marca.spec.ts` da 004 são ajustados só no seletor (o texto do
    botão de envio e a lista vêm da biblioteca).
- **Medições:** SC-001 (avatar com 2 looks e 3 poses em < 5 min, pela interface) e SC-002
  (busca numa biblioteca de 200 itens; o quickstart cria os 200 por um script de seed na stack
  efêmera) ficam no `quickstart.md`.

## R11. Trabalho em paralelo com a 006 (sem colisão)
- **Decisão:** a 007 fica em **módulos novos** e toca arquivos existentes só em pontos pequenos e
  listados no `plan.md` ("Arquivos existentes tocados"). Pontos de atenção:
  - **migration:** duas cabeças quebram o `alembic upgrade head` do `start.sh`. Encadeamento
    combinado com a 006 (ver `specs/006-cortes-openshorts/plan.md`): a 007 usa
    `revision = "0005_assets"` com `down_revision = "0004_fundo_imagem"`, e a 006 usa
    `0006_cortes_openshorts` com `down_revision = "0005_assets"`. Se a 006 for mergeada antes,
    **quem fizer o merge por último troca o `down_revision` da própria migration para a cabeça da
    outra** (uma linha) e renomeia o arquivo para o número seguinte. Nada de `alembic merge`;
  - **`cortes/`:** a 007 **não toca** (R3: cenário e sticker usam as classes `fundo` e
    `watermark` que o corte já aceita). O provedor de usos lê a tabela `cortes` só para consulta;
  - **`router_midia.py` / `midia.py`:** a 006 pode mexer em vídeo; a 007 só acrescenta o kind
    `imagem` (um valor no `MidiaKind` e um ramo no `resolve`);
  - **`main.py`** (um `include_router`), **`App.tsx`** (uma rota), **`PerfilDetalhe.tsx`** (uma
    aba), **`default.conf.template`** (uma `location`), **`docker-compose.yml`** (uma variável no
    `imgproxy`) e **`perfis/models.py`** (valores do `ImageKind`): conflitos de merge triviais,
    em trechos distintos;
  - **contrato gerado** (`packages/contract`): as duas specs regeneram. Em conflito, não se
    resolve à mão: rebase e `npm run gen:contract` de novo (armadilha 6);
  - **e2e:** as duas specs usam o mesmo projeto `sociman-e2e`; não rodar dois `test:e2e` ao mesmo
    tempo (armadilha 18). O `test:api` pode rodar em paralelo.
