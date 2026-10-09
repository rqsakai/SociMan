# Pesquisa (Fase 0): 003-contas-sociais

## R1. Histórico genérico com reversão (princípio VII)
- **Decisão:** uma tabela única e imutável, `entity_versions`, reaproveitável pelas próximas specs,
  e um serviço `sociman_api/history.py`:
  - `record(db, actor, entity_type, entity_id, action, before, after)`. Ele calcula
    `changed_fields`, grava a versão `n` e incrementa `version` na entidade, **na mesma transação**
    da mutação.
  - `snapshot(entity)`: um dict só com os campos versionados. Ficam de fora `version`, os
    timestamps de auditoria e qualquer segredo.
  - `revert(db, actor, entity, to_version)`: aplica o `after` daquela versão, respeitando campos
    imutáveis (slug) e a unicidade. Grava uma versão nova com `action="reverted"` e
    `details.from_version`.
- **Por quê:** um mecanismo só para todo o domínio. A tela de histórico e a reversão genéricas
  saem de graça para as specs 004 a 010, e o MCP (009) usa o mesmo `actor`.
- **Alternativas:**
  - Tabela `_history` por entidade (triggers ou SQLAlchemy-Continuum): mais tabelas, e o autor
    fica difícil de pôr em trigger.
  - Event sourcing puro: complexo demais (princípio VIII).

## R2. Concorrência (FR-015)
- **Decisão:** controle otimista pela coluna `version`, que já existe por causa do histórico.
  O PATCH manda `version`; se ela for diferente da atual, a resposta é 409 `version_conflict`
  com a mensagem "Este perfil foi alterado por outra pessoa; recarregue". O UPDATE usa
  `WHERE id = :id AND version = :v`.

## R3. Arquivar em vez de apagar (FR-014)
- **Decisão:** `archived_at` e `archived_by` (null = ativo). Não existe rota DELETE. Arquivar e
  restaurar geram versões (`archived`/`restored`). A lista padrão filtra
  `archived_at IS NULL`.

## R4. Armazenamento de imagens
- **Decisão:** o cliente **`minio`** (minio-py), usado de forma síncrona como o resto da API,
  com o bucket `sociman` já criado pelo `minio-init`.
  - Chave dos objetos: `perfis/{perfil_id}/{uuid4}.{ext}`. É impossível de adivinhar
    (FR-009a).
  - Objetos nunca são apagados (FR-010).
  - Tabela `images`: `id`, `kind` (`logo`|`banner`), `object_key`, `content_type`, `bytes`,
    `width`, `height`, `sha256`, `uploaded_by`, `created_at`.
  - O perfil guarda `logo_image_id` e `banner_image_id`.
  - O bucket continua **privado** no MinIO. Só o imgproxy o lê (o `IMGPROXY_ALLOWED_SOURCES`
    já está restrito a `s3://sociman/`), e o MinIO não tem porta S3 no host.
- **Alternativas:**
  - `boto3`: dependência mais pesada, para o mesmo uso.
  - Guardar no Postgres (bytea): incha o banco e perde o imgproxy.

## R5. Validação de imagem (FR-008)
- **Decisão:** **Pillow**.
  - O `Image.open` + `verify()` identifica o formato real pelo conteúdo e recusa o que não for
    PNG, JPEG ou WebP.
  - O limite de 5 MB é checado lendo em streaming, e o upload é recusado assim que passar do
    limite.
  - Limite de pixels contra decompression bomb: `Image.MAX_IMAGE_PIXELS = 40_000_000`.
  - Dimensões mínimas: logo 200×200 e banner 1000×250.
  - O arquivo original é guardado como veio (o imgproxy faz os derivados). Os metadados EXIF não
    são exibidos, porque o imgproxy remove os metadados por padrão.
- Upload por `multipart/form-data`, que exige a dependência `python-multipart`.

## R6. Exibição (FR-009, FR-009a)
- **Decisão:** a API monta URLs do imgproxy, como o adapter do volans:
  `/img/{assinatura}/rs:fit:{w}:{h}/f:webp/{base64url("s3://sociman/{key}")}`.
  - Tamanhos: `thumb` 96×96 (lista), `logo` 256×256 e `banner` 1200×300.
  - Com `IMGPROXY_KEY`/`IMGPROXY_SALT` definidos, a URL é assinada (HMAC-SHA256). Sem eles, é
    `unsafe`, **aceitável só em dev**, porque o imgproxy já é restrito ao bucket.
  - O schema de saída do Perfil traz `logoUrls {thumb, medium}` e `bannerUrl`.
  - As imagens são públicas por decisão do dono (FR-009a). A URL não expira, e a assinatura só
    impede que terceiros peçam transformações arbitrárias.
- A CSP `img-src 'self' data:` já cobre `/img` (mesma origem).

## R7. Limite de upload no edge
- **Decisão:** hoje o `default.conf.template` não define `client_max_body_size`, e o padrão do
  nginx é **1 MB**, o que barraria logos de até 5 MB. Por isso:
  - `location /api/` recebe `client_max_body_size 8m`. Com 6m, um arquivo pouco acima de 6 MiB mais o overhead do multipart levava 413 do nginx, sem a mensagem clara da API;
  - o SPA confere o tamanho antes de enviar e trata um eventual 413 com a mesma mensagem;
  - a API também valida o limite de 5 MB (R5), então o app é seguro sozinho.

## R8. Normalização de @ e links (FR-006)
- **Decisão:** tabela de plataformas no código (`platforms.py`), com nome, template de link e
  regex de extração:
  - TikTok: `https://www.tiktok.com/@{h}`;
  - YouTube: `https://www.youtube.com/@{h}`;
  - Instagram: `https://www.instagram.com/{h}`;
  - Kwai: `https://www.kwai.com/@{h}`;
  - Facebook: `https://www.facebook.com/{h}`;
  - X: `https://x.com/{h}`.

  O handle é normalizado com strip, sem `@`, em minúsculas, sem espaços, e com os caracteres
  `[a-z0-9._-]`. "Outra" exige `platform_name` e `url`.
- **Unicidade (FR-005):**
  - índice único em `(platform, platform_name, handle)`, incluindo arquivadas;
  - índice único parcial em `(perfil_id, platform, platform_name) WHERE status='ativa' AND archived_at IS NULL`.

## R9. Slug (FR-002, FR-002a)
- **Decisão:** a sugestão remove acentos (unicodedata NFKD), passa para minúsculas e troca o que
  não for alfanumérico por hífen, entre 2 e 60 caracteres.
  - Índice único.
  - O campo não entra no `UpdatePerfilIn`, e a reversão o ignora (o slug fica fora do snapshot
    revertível; ele é imutável).
  - Um slug em conflito na criação recebe 409 `slug_in_use`.

## R10. Permissões
- **Decisão:** a leitura, a criação, a edição, o arquivamento e a restauração usam `RequireUser`
  (dono ou membro). A reversão usa `RequireOwner` (FR-013). Tudo passa pelo `Actor` da 001,
  preparado para o `mcp_client` da 009.

## R11. Testes
- **pytest:**
  - CRUD e regras de unicidade;
  - normalização de handle e link;
  - concorrência (409);
  - arquivar e restaurar;
  - histórico: toda rota de mutação gera versão com antes e depois (SC-004);
  - reversão pelo dono, 403 para membro e conflito de @ na reversão;
  - imagens: PNG, JPG e WebP válidos (gerados com Pillow nos testes), arquivo falso com extensão
    `.png`, maior que 5 MB, menor que o mínimo, e decompression bomb;
  - o MinIO **real** do compose, num bucket de teste `sociman-test` criado pela fixture;
  - nenhuma rota DELETE no OpenAPI (SC-006).
- **e2e (dev):** criar um perfil com conta e logo, ver a miniatura na lista, editar, abrir o
  histórico, reverter como dono e arquivar e restaurar.
