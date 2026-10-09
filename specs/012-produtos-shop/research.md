# Research: 012-produtos-shop

Decisões técnicas do plano. Cada item: **Decisão**, **Por quê**, **Alternativas rejeitadas**. Fonte do
padrão: `../comfyui-docker/pipeline/produtos.py` (testado com `shorts_canelado`) e a 021-geracao-local
(`specs/021-geracao-local/data-model.md`), da qual esta spec usa os nomes exatos.

## R1. Pacote `produtos/` como alvo da 021

**Decisão:** pacote novo `apps/api/src/sociman_api/produtos/` com `models.py`, `schemas.py`,
`service.py` (CRUD, ficha, variantes, aprovar, arquivar), `fluxo.py` (orquestração dos passos), `ficha.py`
(saída estruturada e prompt do Claude, puro), `flat.py` (instrução do flat, pura), `estados.py`
(transições, puras), `usos.py`, `router.py` (`/api/produtos/{id}…`) e `router_perfil.py`
(`/api/perfis/{id}/produtos…`). O produto entra na 021 pelo **registro de passos e aplicadores**
(`geracao/passos.py` e o protocolo `Aplicador` de `geracao/aplicadores.py`, research R15 da 021): um
aplicador por passo (`produto.ficha`, `produto.recorte`, `produto.flat`) com `validar_alvo`,
`montar_params`, `aplicar` e `ao_mudar_estado`, registrados por `produtos/aplicadores.py`. Nenhuma lógica
de fila, GPU, RAM (`dockerctl`, decisão D1 da 021), rede (`gpu-local`, D2), espera ou limpeza é reescrita
aqui.

**Pedidos:** as gerações `produto.*` são criadas **pelo fluxo do produto** (R8), que chama o serviço de
pedido da 021 (o mesmo do `POST /api/perfis/{id}/geracoes`) com o ator humano da ação que disparou o
passo (criar, enviar variante, salvar ficha, refazer flat): `created_by` = quem pediu. O
`POST /api/perfis/{id}/geracoes` genérico com `alvoTipo = produto` responde 409 `alvo_incompativel`
("use as ações do produto"), porque a instrução do flat sai da ficha e não do pedido. Escolher,
cancelar, tentar de novo e gerar outras usam as rotas da 021 sem mudança.

**Referências das imagens do produto:** a rota genérica da 021 aceita como `referencias` só imagens "em
arquivo ativo de asset ativo". As fotos, recortes e flats do produto não estão em `asset_files`; por isso
a validação das referências dos passos `produto.*` é do `montar_params` do aplicador (imagem do mesmo
perfil, ligada a uma variante ativa do produto). O gate da implementação (T001) confere que o serviço de
pedido da 021 delega essa validação ao aplicador.

**Por quê:** a 021 é a dona do ciclo "pedir → gerar → escolher"; a 012 só define passos `produto.*`, o que
cada um faz no alvo e quando o produto muda de estado. Mesmo formato dos pacotes `assets/` e `cenas/`.

**Alternativas rejeitadas:** jobs próprios de produto (duplicaria a trilha `geracao` e a regra da GPU);
gravar o produto como um tipo de asset da 007 (a ficha e as variantes não cabem em `assets`/`asset_files`
sem colunas opcionais demais, e o insumo pede tabelas próprias).

## R2. Tipos dos campos da ficha (divergência insumo × pipeline)

**Decisão:**
- `detalhes_visiveis` vira **`text[]`** (lista, como o `List[str]` do pipeline), não `text`;
- `cuidados` continua `text[]` (insumo e pipeline concordam);
- `formato_corte` e `detalhes_visiveis` são **em inglês** (vão para a instrução do flat e para os
  prompts); `categoria` é pt-BR livre, com o exemplo do insumo ("roupa > shorts") no prompt;
- os campos em inglês (`material_en`, `formato_corte`, `detalhes_visiveis`, `tamanho_relativo`,
  `descricao_prompt`, `cor_en`) são guardados **exatamente** como enviados (sem trim), como o `prompt` do
  avatar na 007, porque vão literais para os prompts; a UI os marca "vai literal para os prompts".

**Por quê:** o pipeline já valida a saída do Claude como lista e a instrução do flat junta os detalhes
com "; ". Uma lista é dado estruturado (princípio III) e a tela edita item a item; um `text` obrigaria a
reparsear. O idioma segue o uso: o que entra no prompt é inglês, o que o dono lê é pt-BR.

**Alternativas rejeitadas:** `text` com "; " (perde estrutura, e um detalhe com ";" quebraria); traduzir
`formato_corte` (o modelo de imagem recebe inglês, e a tradução seria um campo a mais que o insumo não tem).

Limites (validação no service, 400 `invalid_produto` com `field`): `name` 1..80; `nome_comercial`
1..120; `categoria` 1..120; `material_en` 2 a 5 palavras e ≤ 60 caracteres; `material_pt` ≤ 60;
`formato_corte` ≤ 300; `detalhes_visiveis` ≤ 12 itens de ≤ 200; `tamanho_relativo` ≤ 300;
`descricao_prompt` ≤ 500 e uma frase só (um ponto final no fim; aviso, não erro, se houver mais);
`cuidados` ≤ 12 itens de ≤ 200; `descricao_venda` ≤ 600; `obs` ≤ 2.000; `cor_en`/`cor_pt` ≤ 40;
`url_loja` ≤ 500, `https://` (FR-029, informativo).

## R3. Seed do flat: `flat_geracao_id`, não `flat_seed`

**Decisão:** a variante guarda só `flat_geracao_id` (FK `geracoes`). A seed e a instrução usadas são
lidas da geração: `geracoes.params` (instrução, referências) e `geracao_candidatos.seed` da opção
escolhida (`geracoes.escolhido_id`). Nada de `flat_seed` em `produto_variantes`.

**Por quê:** a 021 já guarda seed por opção e a entrada resolvida por geração; repetir na variante seria
uma segunda fonte que pode divergir. O pipeline guardava `flat_seed` porque não tinha a geração.

**Alternativas rejeitadas:** coluna `flat_seed` (redundante); só `flat_image_id` (perde a rastreabilidade
que o FR-011 pede).

## R4. Estado anterior ao arquivar

**Decisão:** o arquivamento usa **só** `archived_at`/`archived_by` (o `_Versioned` da 003, como assets e
cenas). O enum `produto_status` tem `rascunho`, `gerando`, `revisao` e `aprovado`, **sem** `arquivado`.
O estado `arquivado` que a tela e a API mostram é **efetivo** (`archived_at IS NOT NULL`), calculado na
leitura. Arquivar não mexe em `status`; restaurar só limpa `archived_at`, e o produto volta ao estado em
que estava.

**Por quê:** resolve "restaurar volta ao estado anterior" sem coluna extra (`status_antes_arquivar`) e
sem duas fontes de verdade (`status = arquivado` e `archived_at` ao mesmo tempo, como o insumo listava).
É o padrão do projeto (estado efetivo calculado, como em `conteudos/consulta.py`).

**Alternativas rejeitadas:** `arquivado` no enum mais coluna do estado anterior (dois campos para um
fato); ler o estado anterior do histórico (frágil e caro).

Gerações em andamento de um produto arquivado continuam (a 021 não sabe de arquivamento); o resultado
entra no produto arquivado, e restaurar o mostra. Arquivar oferece "Cancelar gerações em andamento".

## R5. Ficha técnica: passo `produto.ficha` (motor `claude`) e registro da 008

**Decisão:**
- `fluxo.pedir_ficha` cria a geração `produto.ficha` (motor `claude`, `n_opcoes` como a 021 define para
  passo só de texto) com `params` = `{referencias: [originais em ordem], instrucao: obs (ou ""), extras: {nome}}`;
- o adaptador `claude` da 021 chama o modelo com `ficha.SYSTEM` (o texto do pipeline, adaptado), as fotos
  numeradas ("PRODUCT PHOTO N") e saída estruturada validada por um schema `FichaSaida` (pydantic) que
  espelha o `Ficha` do pipeline, com `detalhes_visiveis: list[str]` e `cores: [{foto, en, pt}]`;
- o resultado vai **direto** para o produto (FR-010 da 021): a ficha, as cores de cada variante (pela
  `position` = `foto - 1`) e `ficha_por = ia`, numa versão do produto com `details.geracao_id`;
- a chamada entra em `ia_chamadas` (008) pelo motor `claude` da 021 (`geracao/motor_claude.py`, R14 da
  021), com `tipo_campo = "produto.ficha"`, `entity_type = "produto"`, `entity_id = produto.id`, a coluna
  `geracao_id`, custo aproximado e desfecho (`aplicada` no sucesso; `erro` com o código). Como a 021
  manda, o tipo `produto.ficha` entra em `ia/tipos.py` (`TipoCampoId`) **por esta spec**, com o schema de
  saída `FichaSaida` e a regra padrão (o `SYSTEM` do pipeline); `listar_regras` **não** o mostra (não há
  regra editável nem botão "Gerar" de campo para a ficha), e ele aparece no Registro e no Resumo do mês;
- o resultado de texto fica também em `geracao_candidatos.metricas` (a ficha, como o data-model da 021
  prevê para `produto.ficha`), e o aplicador copia para o produto;
- **imagens para o Claude:** cada original é reduzida em memória para no máximo 1568 px no lado maior e
  enviada em JPEG (qualidade 90), sem gravar nada; o original no MinIO continua intocado. Isso respeita o
  limite de tamanho por imagem da API e evita pagar tokens de imagem por pixels que o modelo não usa;
- o modelo é o mesmo do assistente (`IaClient` da 008); `PROMPT_VERSION` próprio `produto/1` em
  `details`, para rastrear mudanças no texto do pedido.

**Por quê:** é exatamente o fluxo testado no pipeline (1 chamada, fotos originais, saída validada), com o
registro de custo que o dono já usa. Gravar antes da GPU (FR-004) sai de graça: a geração `produto.ficha`
termina e aplica antes de o fluxo enfileirar o recorte.

**Alternativas rejeitadas:** uma chamada por foto (mais caro e perde a comparação entre variantes, que é
o que gera "identical in size and cut"); o Qwen-VL local (`Shop 0 - Analisar produto`) — errou o
material nos testes, e a ficha é o passo que corrige erro de material.

**Erros:** sem chave → `claude_unconfigured` (503 da 008); recusa, saída inválida ou fora do schema →
`entrada_invalida`/`internal` com mensagem em pt-BR; nada vai para a ficha. O produto fica `gerando` com
"Tentar de novo" e "Preencher à mão" (R9).

## R6. Recorte: passo `produto.recorte` (bloco `cutout`)

**Decisão:** uma geração `produto.recorte` por variante (motor `comfyui`, bloco `cutout` — `V2 - Cutout
(BiRefNet, fundo branco)`), `n_opcoes = 1`, `params = {referencias: [original], extras: {varianteId}, bloco: "cutout"}`. O candidato
único vai **direto** para `produto_variantes.recorte_image_id` (FR-031 da 021: `sem_escolha = True`, o
gerador chama `aplicar` e a geração vai de `rodando` a `escolhido`; a versão do produto leva
`details.geracao_id` e `details.automatico = true`, autor = quem pediu). Sem seed.

**Por quê:** resultado determinístico, como no pipeline; a revisão humana é a folha (FR-009 da 012).

## R7. Flat: passo `produto.flat` (bloco `keyframe`)

**Decisão:** quando `precisa_flat`, uma geração `produto.flat` por variante (motor `comfyui`, bloco
`keyframe` — `V2 - Keyframe (Qwen Edit)`, como o `rs.flat_lay` do pipeline), `n_opcoes = 2`, com
`params = {instrucao, referencias: [recorte da variante], extras: {varianteId}, bloco: "keyframe"}` e as
seeds da regra da 021 (R7: base sorteada, opção *i* = base + *i* − 1; "Gerar outras" continua depois da
maior já usada naquele alvo e passo, por isso nunca repete). A instrução vem de `flat.instrucao(ficha, variante)`, função pura que reproduz o
`flat_instrucao` do pipeline:

```text
Turn this product photo into a realistic flat-lay photo: the same item lying completely flat and relaxed
on a plain white surface, seen from directly above, with soft natural fabric folds and no volume at all,
as if simply laid down on a table; nobody is wearing it, no invisible body or mannequin shape. Keep
exactly the same item: {cor_en} {material_en}, {formato_corte}; {"; ".join(detalhes_visiveis)}. Same
color, texture, cut and logo. Plain white background, soft even light.
```

Escolher ("Usar opção N", pela rota de escolha da 021) aplica no alvo: `flat_image_id` e
`flat_geracao_id` da variante, numa versão do produto com `details.geracao_id`. "Refazer flat":
com a última `produto.flat` da variante em `revisao`, é o "Gerar outras" da 021 (a antiga fica
`descartada`); depois de escolhida (geração final), a rota do produto `refazer-flat` cria uma geração nova
para a variante (seeds depois da maior já usada), e o flat vigente só muda com a nova escolha.

**Por quê:** é o bloco e a instrução testados; a instrução pura facilita o teste e o aviso do R10.

## R8. Orquestração e estados do produto

**Decisão:** `fluxo.reavaliar(db, actor, produto)` roda **na mesma transação** de cada evento que pode
mudar o produto: as ações do produto (criar com fotos, salvar ficha, variante nova, ligar/desligar
`precisa_flat`, aprovar, reverter) e o gancho **`ao_mudar_estado`** dos aplicadores `produto.*` (chamado
pela 021 em toda transição da geração, de job ou humana). Decide de forma pura (`estados.proximo`):

1. sem variante ativa → `rascunho`;
2. sem ficha (nenhum resultado aplicado e `ficha_por` nulo) → `gerando` e, se não há geração
   `produto.ficha` não final, cria uma;
3. ficha ok e variante ativa sem recorte → `gerando`; cria `produto.recorte` para as que não têm
   geração não final;
4. `precisa_flat` e variante ativa sem flat → `gerando`; cria `produto.flat` para as que não têm geração
   não final **e** cujo recorte já existe;
5. tudo pronto → `revisao` (se estava `aprovado` e o evento é uma edição, também `revisao`, FR-019).

Gerações que falharam ou foram canceladas **não** são recriadas sozinhas: o passo fica pendente, com
"Tentar de novo" (021) na tela. `aprovado` só vem da ação Aprovar (R11).

**Gancho sem rede e sem laço:** o `ao_mudar_estado` só lê e grava no banco (regra da 021: sem chamada de
rede nem de motor). Criar a próxima geração dentro do gancho é só INSERT (a 021 chama o gancho da nova com
`de = None`, e o `reavaliar` é idempotente porque olha `fila.abertas_do_alvo` antes de criar). Quando o
gancho roda no gerador (ex.: a ficha aplicada), o ator das gerações seguintes é o `created_by` da geração
que terminou (o humano que pediu). Uma exceção no gancho desfaz a transição (021) e vira `internal`.

**Por quê:** um ponto único de decisão evita estado preso (ex.: recorte pronto mas status ainda
`gerando`). As regras são puras e testáveis sem banco; os efeitos (criar gerações) ficam no `fluxo`.

**Alternativas rejeitadas:** máquina de estados no worker (a 021 não conhece produto); gatilhos no banco
(a lógica fica escondida e difícil de testar).

## R9. Ficha à mão (`ficha_por = humano`) e edição

**Decisão:** `PUT /api/produtos/{id}/ficha` com `version`. Regras de origem:
`null → humano` (ficha preenchida sem IA, por exemplo com o Claude fora), `ia → ia_editada`,
`ia_editada → ia_editada`, `humano → humano`. Preencher à mão com uma `produto.ficha` não final cancela
essa geração. Salvar ficha num produto `aprovado` volta a `revisao`. A ficha "completa" (para aprovar e
para liberar o flat) exige todos os campos de texto e listas não vazios, `precisa_flat` definido e
`cor_en`/`cor_pt` em toda variante ativa.

## R10. Aviso "flat feito com a ficha anterior"

**Decisão:** na leitura, para cada variante com flat, comparar `flat.instrucao(ficha_atual, variante)`
com a instrução gravada em `geracoes.params` da `flat_geracao_id`. Diferente → aviso
`flat_desatualizado` na variante, com "Refazer flat". Não refaz sozinho. O aviso não bloqueia aprovar.

**Por quê:** a instrução é exatamente o que dependia da ficha (cor, material, corte, detalhes); comparar
o texto evita guardar hash ou versão da ficha na variante.

## R11. Aprovar, refazer e variantes

**Decisão:**
- `POST /api/produtos/{id}/aprovar` (dono **e** membro, FR-021): exige `status = revisao`, ficha completa
  (R9), ≥ 1 variante ativa, recorte em todas e, com `precisa_flat`, flat em todas, e **nenhuma geração
  `produto.*` não final** do produto (ex.: um "Refazer flat" com opções esperando escolha). Faltando algo
  → 409 `produto_incompleto` com `pendencias: [{variante_id?, motivo}]`;
- variante nova (`POST /api/produtos/{id}/variantes`, multipart): ≤ 6 ativas (409 `limite_variantes`),
  cores vazias (o dono preenche); `reavaliar` cria recorte (e flat) e o produto volta a `gerando`;
- arquivar variante: recusa a última ativa (400 `invalid_produto`, "arquive o produto"); restaurar
  variante respeita o limite de 6;
- reordenar variantes: lista com exatamente as ativas (padrão dos `asset_files`);
- `precisa_flat` ligado à mão → `reavaliar` cria os flats que faltam; desligado → os flats ficam
  guardados e deixam de ser exigidos e expostos ao uso (R13).

## R12. Imagens: `images.kind = produto`, MinIO no HD

**Decisão:** `ImageKind.produto` (enum `image_kind`, `ALTER TYPE … ADD VALUE IF NOT EXISTS 'produto'`
fora da transação que o usa) e `imaging.MIN_SIZE["produto"] = (512, 512)`, formatos PNG/JPG/WebP,
**20 MB** pelas rotas de produto (`max_bytes` como na 007). Upload validado pelo conteúdo antes de criar
qualquer linha ou geração (FR-002). Chave `perfis/{perfil_id}/{uuid4}.{ext}` no bucket `sociman`
(`storage.py`, `bucket="imagens"`), com o `datadir` (sentinela `.sociman-volume` e piso de espaço, 503/507)
como todo upload. Recortes e flats são gravados pela 021 como `images` com `kind = produto` (o `Passo.image_kind` dos
três passos), validados por `imaging.validate_image` antes de virar imagem (o recorte sai do mesmo
tamanho da foto; o flat sai no tamanho do bloco `keyframe`, ≥ 512). Links: as opções da geração usam o
link **com validade** da 021 (podem ser apagadas aos 90 dias); a foto original, o recorte e o flat **da
variante** usam o `MidiaKind imagem` **sem validade** (nunca são apagados). Miniaturas pelo imgproxy.

**Proteção na limpeza:** `produtos/uso.py` registra um provedor no `midia_em_uso` da 021
(`geracao/uso.py`): toda imagem referenciada por `produto_variantes` (original, recorte, flat, inclusive
de variante ou produto arquivados) está em uso e nunca é apagada, mesmo que não tenha passado pelo
`escolhido_id`.

**Edge:** `location` nova `~ ^/api/(perfis/[^/]+/produtos|produtos/[^/]+/variantes)$` com
`client_max_body_size 130m` (até 6 fotos × 20 MB numa criação) e o mesmo bloco de proxy das rotas de
upload da 007, para a recusa vir da API. `docker compose restart edge` (armadilha 13).

## R13. Ponte com as cenas (010), só por acréscimo

**Decisão:**
- migration acrescenta em `cenas`: `produto_id uuid null FK → produtos.id` e
  `produto_variante_id uuid null FK → produto_variantes.id`; **não** remove `produto_nome` nem
  `produto_imagem_id`;
- CHECKs novos: `ck_cenas_produto_variante` (`produto_variante_id IS NULL OR produto_id IS NOT NULL`) e
  `ck_cenas_produto_modo` (`produto_id IS NULL OR (produto_nome IS NULL AND produto_imagem_id IS NULL)`):
  a cena usa **ou** a referência leve **ou** o catálogo. O `ck_cenas_produto` da 010 continua;
- validação no service da cena: produto do mesmo perfil, `aprovado` e não arquivado **ao ligar** (400
  `invalid_cena`, field `produtoId`); variante ativa daquele produto e com recorte;
- "Ligar ao catálogo" = `PATCH` da cena com `produtoId` (+ `produtoVarianteId`) e `produtoNome: null`,
  `produtoImagemId: null` numa mutação só (uma versão, com histórico); os dois novos entram em
  `__versioned_fields__` e nos campos que mudam o prompt (cena `pronta` volta a `rascunho`; cena `usada`
  recusa, como na 010);
- prompt (`cenas/prompt.py`): `Entrada` ganha `produto_prompt: str | None` (a `descricao_prompt`) e
  `produto_cor: str | None` (`cor_en` da variante). Com catálogo, a ação recebe
  `", with the product exactly as in the reference image"` e entra uma parte nova **`produto`** logo
  depois da ação: a `descricao_prompt` literal, seguida de `"Color: {cor_en}."` quando há variante. A
  referência leve continua montando como hoje (nada muda no prompt das cenas existentes);
- ingrediente (`cenas/ingredientes.py`): com catálogo, o ingrediente `produto` é o **recorte** da
  variante (sem variante: a primeira variante ativa), com `produtoId`/`produtoVarianteId` no schema
  `Ingrediente` (campos opcionais novos; `asset_id`/`arquivo_id` ficam opcionais);
- aviso novo em `cenas/avisos.py`: `produto_fora_de_aprovado` quando o produto da cena não está
  `aprovado` ou foi arquivado (só informa; a cena continua);
- uso: `produtos/usos.py` lista as cenas por `produto_id` (origem `cena`, `bloqueia = False`) para a
  seção "onde é usado" do produto; filtro de cenas por `produtoId` na lista da 010.

**Por quê:** é o pedido do dono (acréscimo, sem migração forçada) e mantém o prompt congelado das cenas
`pronta`/`usada` intacto (FR-006a da 010). A frase da ficha separada da ação evita reescrever a ação do
usuário.

**Alternativas rejeitadas:** migrar as cenas com `produto_nome` para produtos (não há como casar nome
livre com produto); a frase da ficha dentro da ação (quebraria a regra "ação como o usuário escreveu").

## R14. MCP (009) e anotações

**Decisão:** entradas novas no `mcp/mapa.py`, só leitura: "Listar produtos" (`GET
/api/perfis/{id}/produtos`, padrão `status=aprovado`) e "Ver produto" (`GET /api/produtos/{id}`, com a
ficha, as variantes e os links das imagens), mais `_versoes("um produto")`. O `anotacoes` ganha o alvo
`produto` (`AnotacaoAlvo.produto`) para a `observacao` (escopo "leitura e propostas"). Nenhuma rota de
escrita de produto entra no mapa (o teste-guarda do mapa confere a lista fechada).

## R15. Permissões

**Decisão:** `RequireHuman` (dono ou membro humano; outro ator → 403 `somente_humano`, como as rotas de
escrita da 021) para criar, editar, enviar fotos, salvar ficha, pedir ficha, refazer flat, aprovar,
arquivar e restaurar; escolher, cancelar, tentar de novo e gerar outras já são `RequireHuman` na 021;
`RequireOwner` para `revert`. `RequireUser` só nas leituras (o MCP lê pelo mapa).

## R16. Histórico (princípio VII, constitution 4.3.0)

**Decisão:** `entity_type = "produto"` no `history.py`. Snapshot versionado (`__versioned_fields__`) com
os campos da ficha, `obs`, `url_loja`, `status`, `ficha_por`, `archived` e **`variantes`** (propriedade:
lista ordenada por `position` com `id`, `cor_en`, `cor_pt`, `original_image_id`, `recorte_image_id`,
`flat_image_id`, `flat_geracao_id`, `archived`). `perfil_id` é imutável. Reverter (só dono) restaura a
ficha, as cores e as referências de imagem da versão alvo **sem gerar nada** (FR-023); uma imagem
referenciada pela versão alvo que a limpeza de 90 dias apagou não existe por construção, porque recortes
e flats em uso são candidatos **escolhidos** (nunca apagados). Depois de reverter, `reavaliar` recalcula
o status (nunca restaura `aprovado` sozinho: um produto revertido vai a `revisao`).

A emenda 4.3.0 (duas exceções de eliminação nomeadas e auditadas, aplicadas na 021) cobre a limpeza das
opções de flat não escolhidas; esta spec não cria exceção nova: produto e variante nunca são apagados.

## R17. Testes e fakes

**Decisão:**
- **pytest:** o **mesmo fake do ComfyUI da 021** (`tests/fakes/comfyui_fake.py`: `/upload/image`,
  `/prompt` validando os nós do contrato dos blocos `cutout` e `keyframe`, PNG sintético com a seed,
  falhas fora do ar, `OutOfMemoryError` e saída vazia; VRAM programável em `/system_stats`), o
  `dockerctl_fake.py` da 021 para conferir a RAM e o `anthropic_fake.py` estendido com a resposta estruturada da ficha (e os modos
  recusa e saída inválida). Puros: `estados.proximo`, `flat.instrucao`, validação da ficha, prompt da cena
  com catálogo. Integração: fluxo completo (criar → ficha → recortes → flats → escolher → aprovar), falha
  de GPU sem nova chamada ao Claude (SC-002, contando chamadas no fake), RAM de volta a 12 GB (pelo fake
  do Docker da 021), limites, arquivar/restaurar, reverter, ponte com cenas, mapa do MCP;
- **e2e:** o serviço `openshorts-fake` (que já responde `POST /v1/messages`) ganha a ficha quando o
  `system` é o da ficha; o ComfyUI falso do e2e é o da 021 (`/comfyui/*`, controle em `/geracao-e2e/*`,
  serviço `gerador` no `docker-compose.e2e.yml`). Fluxo do dono no navegador: criar com 2
  fotos, ver a ficha, escolher os flats, editar uma cor, aprovar, ligar a uma cena e conferir o prompt;
- nenhum teste chama serviço real.

## R18. SPA

**Decisão:** aba **Produtos** no perfil (`?aba=produtos`, `pages/perfis/tabs/ProdutosTab.tsx`, com
`DataTable`) e tela `/app/produtos/:id` (`pages/produtos/ProdutoPage.tsx`): cabeçalho com estado e
ações, **folha** (originais | recortes | flats por variante, uma coluna por variante no celular),
**ficha** editável (`Field`, listas editáveis item a item, selo "vai literal para os prompts" nos campos
em inglês, "Copiar descrição para prompts"), andamento dos passos com os componentes da 021
(`components/geracao/`: `AndamentoGeracao` com progresso e "Aguardando a GPU ficar livre",
`OpcoesGeracao` com opções lado a lado, "Usar opção N", "Gerar outras", "Cancelar" e "Tentar de novo"), "onde é usado" e histórico. Polling com TanStack Query (`refetchInterval` enquanto
houver geração não final). Na cena (010), seletor de produto (só aprovados) e de variante, e o botão
"Ligar ao catálogo" nas cenas com referência leve. Contrato por `npm run gen:contract`.

## R19. Migration e ordem

**Atualização (gate de 2026-10-08):** o head real é `0021_geracao_interrupcoes` (da 021) e a 025 ainda não
entrou; a 012 fica `0022_produtos_shop` com `down_revision = "0021_geracao_interrupcoes"`, e a 025 passa a ser a
`0023`.

**Decisão original:** `0022_produtos_shop`, com `down_revision = "0021_cadastro_padronizado"` **provisório**: a
cadeia depende da ordem real de merge da 021 (`0020_geracao_local`, também provisório) e da 025 (`0021_cadastro_padronizado`). Se a 025
atrasar, a 012 pode entrar logo depois da 021 e o `down_revision` muda para a revisão da 021 (o gate do
`/speckit-implement` confere com `alembic heads` antes de gerar o arquivo). Conteúdo: valor `produto` no
`image_kind`, tipos `produto_status` e `produto_ficha_por`, tabelas `produtos` e `produto_variantes`,
colunas e CHECKs novos em `cenas`, valor `produto` no alvo de anotação (`anotacao_alvo`). **Downgrade:** recusa se houver
produto ou cena com `produto_id`; senão remove o que criou (o valor de enum é recriado como na `0004`).
O valor `produto` de `geracao_alvo` já existe desde a 021.
