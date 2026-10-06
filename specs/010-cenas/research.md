# Research: Cenas para o Flow/Veo (010)

Decisões técnicas da 010. Cada item traz **Decisão / Por quê / Alternativas**. Fontes do domínio:
`../shared/shop/README.md`, `persona.md`, `config/agents/shop-roteirista/AGENTS.md` e
`config/agents/shop-diretor/AGENTS.md` (formato do pacote para o Flow), e o código da 007, 008, 009, 014 e
017. As pastas `../shared/shop/roteiros/` e `pacotes/` estão vazias em 2026-10-06: o exemplo de referência
do SC-003 é sintético, montado a partir do formato descrito pelo shop-diretor.

## R1. Pacote e entidades

- **Decisão:** pacote novo `sociman_api/cenas/` com 4 tabelas:
  - `cenas`: a cena;
  - `cena_tomadas`: os vídeos gerados;
  - `cena_usos`: o vínculo cena × conteúdo;
  - `cena_padroes`: estilo e negative padrão por perfil, uma linha por perfil.

  `entity_type`: `cena`, `cena_tomada` e `cena_padroes`. A cena pertence a um perfil e
  referencia os assets por id, sem copiar arquivos.
- **Por quê:** domínio novo com ciclo de vida próprio (status, tomadas). Assets continuam donos das
  imagens. A 011 vai referenciar `cenas.id`.
- **Alternativas:** cena como tipo de asset da 007. Rejeitada: o asset é imagem com arquivo obrigatório, e
  a cena tem status, prompt e vídeos.

## R2. Montagem do prompt: função pura, ordem fixa

- **Decisão:** `cenas/prompt.py` expõe `montar(entrada) -> PromptMontado`, sem acesso ao banco. A
  `entrada` tem a cena, o avatar, o arquivo de look/pose, o cenário e os padrões do perfil. A saída tem
  `texto`, `negative`, `partes` (lista ordenada de `{parte, texto}` para a tela destacar),
  `avatar_version` e `cenario_version`. Ordem fixa, separada por espaço e com ponto final em cada parte:
  1. `avatar.prompt` **sem nenhuma alteração** (guardado sem trim, FR-009 da 007), se houver avatar;
  2. `avatar.image_rules`, se houver (ver R12 sobre idioma). O cenário da 007 não tem regras de imagem
     próprias: a "regra visual" do cenário é o próprio prompt do ambiente (parte 4);
  3. ação. Se houver foto de produto: `"<produto> exactly as in the reference image"` na frase da ação,
     pela regra do shop-diretor, só acrescentada quando a ação ainda não traz "reference image";
  4. `cenario.prompt` sem alteração, se houver cenário;
  5. câmera, com plano e movimento traduzidos por tabela fixa (`close` → "close-up shot", `medio` →
     "medium shot", `parada` → "static camera", `aproximacao` → "slow push-in"…) mais o detalhe livre;
  6. iluminação e estilo (o da cena ou, vazio, o padrão do perfil);
  7. áudio e fala. Com fala: `She looks at the camera and says: "<fala>"`. O pronome vem do avatar e
     é "The person" quando não há avatar. O áudio ambiente vem depois.

  No modo `quadros`, o prompt traz antes `Start frame: …` e `End frame: …`. O texto na tela **não**
  entra no prompt (R12).
- **Por quê:** é o formato que o shop-diretor já usa. Uma função pura dá o SC-002 por teste unitário
  (descrição idêntica, ordem) e é a mesma usada ao vivo, ao congelar e ao remontar.
- **Alternativas:** template editável pelo dono. Fica para depois (YAGNI). As regras da IA já cobrem o
  ajuste fino.

## R3. Ingredientes

- **Decisão:** `ingredientes.py` devolve até 3 itens, nesta ordem e prioridade:
  1. arquivo do avatar escolhido (look `referencia` ou `pose`; padrão: a imagem principal do avatar);
  2. foto do produto (asset tipo `imagem`, arquivo principal);
  3. imagem do cenário (a escolhida ou a principal).

  Cada item tem `papel`, `assetId`, `arquivoId`, nome, dimensões e `downloadUrl` (link de mídia
  `MidiaKind imagem`, sem validade, da 007). Como a cena tem no máximo um arquivo de avatar, uma foto e
  uma imagem de cenário, o limite de 3 do Flow é garantido pela estrutura, sem aviso.
- **Por quê:** avatar e produto são o que o Veo precisa manter fiel (a regra "produto igual ao real" do
  README). O cenário pode vir só do texto.
- **Alternativas:** ZIP com os ingredientes. Rejeitada: o download por item basta e não cria temporário
  no HD.

## R4. Avisos (não bloqueiam)

- **Decisão:** `avisos.py` puro devolve uma lista `{codigo, mensagem, campo}`:
  - `fala_longa`: palavras da fala > `ceil(15 × duração / 8)`;
  - `duracao_modo`: modo `ingredientes` com duração ≠ 8;
  - `produto_sem_foto`: produto com nome e sem foto;
  - `proibida`: `ia.guia.achar_proibidas` sobre fala, ação e texto na tela, com as proibidas efetivas do
    perfil;
  - `assets_mudaram`: congelado com versão do avatar/cenário diferente da atual, com `antes`/`depois` do
    texto da parte;
  - `asset_arquivado`: avatar, cenário ou foto arquivados.
- **Por quê:** os limites do Flow mudam sem aviso (Assumptions). O guia da 017 já define a comparação de
  proibidas (palavra inteira, sem acento e sem caixa).

## R5. Status e congelamento

- **Decisão:**
  - `status` é um enum gravado: `rascunho`, `pronta` ou `usada`.
  - **Marcar pronta** (`POST /api/cenas/{id}/pronta`) valida os requisitos do FR-006 (ação, duração,
    modo, quadros no modo `quadros`, assets não arquivados). Em seguida grava `prompt_congelado`,
    `negative_congelado`, `avatar_version_congelada` e `cenario_version_congelada` e registra o
    histórico. Falta algum requisito: 422 `cena_incompleta` com a lista.
  - **Editar** uma cena `pronta` com campo de prompt (lista fixa `CAMPOS_PROMPT`): volta a
    `rascunho`, limpa o congelado e registra a mudança. Editar só nome, tags ou notas mantém o status.
  - **Editar** uma cena `usada` com campo de prompt: 409 `cena_usada` ("duplique para variar").
  - **Reverter** (só dono) é recusado em `usada` (409 `cena_usada`). Nas demais, a versão volta com o
    status e o congelado do snapshot (sempre coerentes, pelo CHECK `ck_cenas_congelado`). Um snapshot
    `usada` sem vínculo ativo volta como `pronta`.
  - **Voltar a rascunho** é explícito (`POST …/rascunho`) e só vale para `pronta`.
  - **Remontar** (`POST …/remontar`) vale em `pronta` e `usada`: recalcula com os assets atuais e
    regrava o congelado (histórico `updated` com `details.acao = "remontar"`), sem mudar o status.
- **Por quê:** é a Q3 = A. O congelado é dado versionado da cena, então o revert do dono volta também o
  prompt.
- **Alternativas:** tabela de "versões do prompt". Rejeitada: o histórico genérico já guarda antes e
  depois.

## R6. Tomadas: recebimento e armazenamento

- **Decisão:** `POST /api/cenas/{id}/tomadas` (multipart, streaming) reaproveita
  `cortes.service.precheck`/`receive`:
  - prefixo `tomada-`;
  - `MAX_BYTES = 200 MB`;
  - HD com sentinela e piso.

  Depois do recebimento:
  1. ffprobe valida o arquivo: MP4/MOV/WebM, de 1 a 30 s, com aviso `naoVertical` fora de 9:16.
  2. O vídeo vai para o bucket de vídeos em `cenas/<cena_id>/tomadas/<tomada_id>.<ext>`.
  3. A miniatura é gerada como no vídeo próprio.
  4. A linha `cena_tomadas` é criada com `prompt_usado` = o prompt congelado da cena no momento.

  A primeira tomada vira a escolhida (`cenas.tomada_escolhida_id`). Só cenas `pronta`/`usada` recebem
  tomadas: 409 `cena_nao_pronta`. O edge ganha uma `location` própria
  (`^/api/cenas/[^/]+/tomadas$`, `client_max_body_size 210m`, sem buffering), como a do vídeo próprio.
  Assistir usa o link `MidiaKind video` com validade e Range (004).
- **Por quê:** é a Q2 = A. O código de recebimento e de probe já existe, e o tamanho de uma tomada de
  30 s em 1080p fica bem abaixo de 200 MB.
- **Origem extensível:** toda tomada tem `origem` (enum `tomada_origem`), que nesta spec é sempre
  `flow_manual`, gravada pelo envio. O serviço de tomadas separa "receber o arquivo e validar"
  (`registrar_tomada(cena, arquivo, origem)`) do transporte HTTP. Assim, a 021 (jobs de geração local com
  candidatos, `docs/insumos/021-geracao-local.md`) poderá criar tomadas com `origem = geracao_local` e
  um `geracao_id` próprio, reaproveitando a validação, o `prompt_usado` e a escolha, sem migrar dados nem
  mudar rotas. A 010 não cria nada da 021: sem fila, worker, GPU, `geracoes` ou candidatos.
- **Alternativas:** limite de 2 GB, como o vídeo próprio. Rejeitado: uma tomada é curta, e um limite
  apertado protege o HD.

## R7. Vínculo cena × conteúdo e status `usada`

- **Decisão:**
  - Tabela `cena_usos (cena_id, conteudo_id, criado_em, criado_por, desfeito_em, desfeito_por)`, com
    um uso ativo único por par.
  - `PUT /api/conteudos/{id}/cenas { cenaIds, version }` define o conjunto do conteúdo e confere a
    `version` do conteúdo. O conteúdo deve ser de origem `video_proprio`, as cenas do mesmo perfil, não
    arquivadas e não `rascunho`; senão 409/422.
  - O serviço cria e desfaz usos e recalcula o status das cenas afetadas: com uso ativo → `usada`; sem
    nenhum → `pronta`.
  - Histórico: `cena` recebe `updated` com `details.uso = {conteudoId, acao}`. `conteudo` recebe
    `updated` com `details.cenas = {antes, depois}`, sem novo campo versionado no conteúdo.
  - O revert do conteúdo não mexe nos usos; para desfazer, edite o conjunto.
- **Por quê:** não altera o modelo `conteudos` da 014. O histórico registra quem ligou e quando, nos dois
  lados (FR-012).
- **Alternativas:** array `cena_ids` versionado no conteúdo. Rejeitada: o revert do conteúdo mudaria o
  status das cenas em cascata.

## R8. "Onde é usado" dos assets

- **Decisão:** registrar o provedor `cena` em `assets.usos.register` (`cenas/usos_assets.py`), com
  `bloqueia = False` e rótulo "N cenas". Ele aponta para a aba Cenas filtrada pelo asset e cobre o
  avatar (qualquer arquivo dele), o cenário e a foto do produto.
- **Por quê:** a 007 deixou esse gancho para "roteiros e cenas", e a spec pede que nada seja bloqueado
  (FR-009).

## R9. Proposta de cena pelo MCP (anotação da 009)

- **Decisão:**
  - **Migration:** `ALTER TYPE anotacao_alvo ADD VALUE 'cena'` e `ALTER TYPE anotacao_tipo ADD VALUE
    'proposta_cena'`, dentro de `op.get_context().autocommit_block()`, porque o valor novo não pode ser
    usado na mesma transação. Depois, troca do CHECK `ck_anotacoes_proposta_em_destino` por
    `ck_anotacoes_proposta_alvo`: `tipo = 'observacao' OR (tipo = 'proposta_texto' AND alvo_tipo =
    'destino') OR (tipo = 'proposta_cena' AND alvo_tipo IN ('perfil','cena'))`.
  - **Downgrade:** recria o CHECK antigo, só se não houver linhas com os valores novos. O valor de enum
    fica, porque o PG não remove valores.
  - **Campos:** `CamposCena` (Pydantic, `extra="forbid"`) com os campos editáveis da cena. Os ids de
    avatar, cenário e foto são validados no perfil (não arquivados), senão 422 `proposta_invalida`.
    Os `campos` das anotações viram união discriminada pelo `tipo`.
  - **Aceitar:** a SPA abre o formulário de nova cena (alvo perfil) ou da cena (alvo cena) preenchido.
    O "Salvar" humano manda `propostaId`, e `anotacoes.service.aplicar_cena` marca `aplicada` na mesma
    transação, com o autor humano e a referência no histórico da cena (como o `aplicar` do destino).
    Descartar usa a rota existente.
  - **Alvo cena arquivada ou `usada`:** criar a proposta é recusado (409 `alvo_arquivado`/`cena_usada`).
- **Por quê:** é a Q1 = A. Reaproveita a caixa "Propostas dos agentes", os limites, o registro e a regra
  "só o autor edita a própria".

## R10. IA: 5 tipos de campo da cena

- **Decisão:** `ia/tipos.py` ganha a entidade `cena` e 5 tipos:
  - `cena.acao` (texto, en);
  - `cena.camera` (texto, en, o detalhe livre);
  - `cena.estilo` (texto, en);
  - `cena.audio` (texto, en);
  - `cena.ajustar` (formato novo `campos_cena`, que propõe os quatro juntos).

  Todos usam `usa_guia = "so_proibidas"`. O contexto (`ia/contexto.py`) leva a descrição do avatar, as
  regras de imagem, o prompt do cenário, o produto, a duração, o modo e a fala, só como contexto. A
  saída de `cena.ajustar` só tem as 4 chaves, e qualquer outra é descartada pela validação de `saida.py`.
  A aplicação usa o `PATCH` da cena com `ia: [...]` (como asset e postagem). Regras padrão em
  `regras_padrao.py`, com as do shop-diretor: gestos simples, nada de texto legível, mãos fora do rosto
  na fala, produto "exactly as in the reference image".
- **Por quê:** FR-014/015. A descrição do avatar não é campo da cena, então a IA não tem como alterá-la.
- **Alternativas:** um só tipo que reescreve o prompt montado inteiro. Rejeitada: quebraria a montagem
  derivada e a garantia do SC-002.

## R11. MCP: classificação no mapa

- **Decisão:**
  - **`TOOLS`, escopo leitura:** `cenas_list`, `cenas_get` (com prompt montado ou congelado,
    ingredientes e avisos), `cenas_versions`, `cenas_tomadas_list`, `cenas_padroes_get` e
    `conteudos_cenas_get`. As leituras de tomada devolvem metadados, sem link de vídeo (`ocultar` do
    `downloadUrl`).
  - **Escrita do agente:** só `anotacoes_create` com `tipo = "proposta_cena"`, já em `TOOLS` com escopo
    `propostas`. A descrição em pt-BR ganha o formato dos campos.
  - **`FORA`** (o portão responde `escopo_mcp`): `cenas_create`, `cenas_update`, `cenas_duplicar`,
    `cenas_pronta`, `cenas_rascunho`, `cenas_remontar`, `cenas_archive`, `cenas_restore`,
    `cenas_tomadas_upload`, `cenas_tomadas_escolher`, `cenas_tomadas_update`, `cenas_tomadas_archive`,
    `cenas_tomadas_restore`, `conteudos_cenas_put` e `cenas_padroes_put`.
  - **`PROIBIDAS`:** `cenas_revert`, `cenas_tomadas_revert` e `cenas_padroes_revert` (rotas
    `RequireHumanOwner`).
- **Por quê:** FR-016 a FR-018 e FR-023 da 009. O `test_mcp_mapa.py` falha com operação sem
  classificação, então nenhuma rota nova vira tool sozinha.

## R12. Idioma e texto na tela

- **Decisão:**
  - O prompt e o negative ficam em inglês. A fala e o texto na tela ficam em pt-BR.
  - As regras de imagem do avatar entram **como estão**: hoje estão em pt-BR em `persona.md`, e o Veo
    entende, mas a tela sugere escrevê-las em inglês.
  - O SociMan não traduz nada (nenhuma chamada de IA implícita).
  - O texto na tela é guia de edição, mostrado no painel "Edição" da cena e fora do prompt, porque o
    negative bloqueia texto no vídeo.
- **Por quê:** é a convenção do shop-diretor e o princípio VIII.
