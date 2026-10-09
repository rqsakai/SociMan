# Quickstart de validação: 007-assets-do-perfil

O contrato está em [contracts/http-api.md](contracts/http-api.md) e o modelo de dados em
[data-model.md](data-model.md). Um passo por vez, conferindo cada saída.

## Pré-requisitos
- Stack em modo dev (`docker compose up -d`), com `api`, `edge`, `minio` (dados no HD) e
  `imgproxy` no ar; `curl -s http://localhost:8180/api/health` com `storage: ok`.
- Os perfis "Queridinhos" e "A Taverna Nerd", com o kit da 004 salvo e pelo menos uma imagem de
  fundo e uma de marca d'água já enviadas (a Taverna usa `watermark.png`).
- As imagens reais da persona: `../shared/shop/persona/achadinhos-cozinha.jpg` (2048×2048) e
  `achadinhos-diner.jpg` (1080×1080).
- Mudou `docker/nginx/*` ou o `imgproxy`: `docker compose restart edge` e
  `docker compose up -d imgproxy` (armadilha 13).

## 0. Migração das imagens da 004 (R2, SC-003), antes de tudo
Antes de subir a API nova, anote as contagens no dev:
```bash
docker compose exec postgres psql -U sociman -d sociman -c \
  "SELECT kind, count(*) FROM images WHERE kind IN ('watermark','fundo') GROUP BY kind;"
```
Anote também, na aba Marca de cada perfil (ou em `GET /api/perfis/{id}/kit`), o
`watermark.imagem_id` e os `fundo_imagem_id` do gancho e do card final.
Suba a API nova (o `start.sh` roda `alembic upgrade head`) e confira:
```bash
docker compose up -d --build api
docker compose exec postgres psql -U sociman -d sociman -c \
  "SELECT i.kind, count(*) FROM images i JOIN asset_files f ON f.image_id = i.id
    WHERE i.kind IN ('watermark','fundo') GROUP BY i.kind;"          # igual à contagem de antes
docker compose exec postgres psql -U sociman -d sociman -c \
  "SELECT count(*) FROM images i LEFT JOIN asset_files f ON f.image_id = i.id
    WHERE i.kind IN ('watermark','fundo') AND f.id IS NULL;"         # 0
docker compose exec postgres psql -U sociman -d sociman -c \
  "SELECT count(*) FROM entity_versions WHERE entity_type='asset' AND actor_kind='system:migration';"
```
Verificar:
- as contagens batem (100% das imagens na biblioteca, SC-003);
- o kit de cada perfil é o mesmo (`imagem_id` e `fundo_imagem_id` iguais aos anotados), a
  prévia da aba Marca mostra as mesmas imagens e o "Exportar JSON" traz os mesmos links;
- na aba Assets, as imagens aparecem como "Fundo N" e "Marca d'água N", com o selo "Em uso" nas
  que o kit usa (US2-3, US3-3);
- `alembic upgrade head` de novo não cria nada (backfill idempotente).

## 1. Avatar "Achadinhos" (US1, SC-001, SC-005)
Cronometre do "Novo asset" até a última pose (meta: menos de 5 min). Em "Queridinhos", aba
Assets, "Novo asset" → Avatar:
- nome "Achadinhos"; **descrição para prompts**: cole o texto exato de
  `../shared/shop/persona.md` ("A cheerful 1950s pin-up style woman…");
- **tom de voz**: "Animado, próximo, 'amiga que achou uma pechincha'. Português do Brasil.
  Narração em off gerada à parte para manter a mesma voz.";
- **regras de imagem**: "Evitar textos em inglês no fundo (cartazes). Mãos longe do rosto nas
  cenas com fala.";
- tags: `persona`, `tiktok-shop`;
- **Looks**: envie `achadinhos-cozinha.jpg` com look "Cozinha, corpo inteiro", uso "cenas de
  cozinha", nota "HeyGen look 012eb0ab…"; e `achadinhos-diner.jpg` com look "Diner, busto", uso
  "cenas de fala em close", nota "HeyGen look 167089ca…". Marque a cozinha como principal: a
  miniatura do card muda (US1-2);
- **Poses**: três poses (use recortes das próprias imagens ou quaisquer PNG/JPG ≥ 256 px):
  "apontando para o produto" ("quando usar": "mostrar o item na mão"), "surpresa", "piscando".
  Tente uma quarta com o rótulo "Surpresa": recusada ("Já existe uma pose com esse rótulo neste
  avatar");
- reordene: mova "piscando" para a primeira posição com os botões (e, no desktop, arrastando).
  Recarregue: a ordem ficou (US1-3);
- "Copiar descrição para prompt" e cole num editor: o texto é idêntico ao do `persona.md`
  (US1-4, FR-009);
- histórico do avatar: uma versão por ação, com autor; como dono, reverta para a versão antes da
  reordenação: a ordem volta. Como membro, o botão "Reverter" não aparece e a API dá 403 (US1-5);
- **SC-005:** todo o conteúdo do `persona.md` (descrição, voz, regras, 2 looks com arquivo, uso e
  origem, 2 cenários da §2) coube sem campo faltando.

Avatar sem imagem: crie "Teste Estrela" sem enviar nada; o card mostra as iniciais "TE" em cor
neutra (primeira letra da primeira e da última palavra, como no perfil).

## 2. Cenários e fundo do kit (US2)
- Novo asset → Cenário "Cozinha retrô", prompt "1950s kitchen with mint-green countertops,
  wooden cabinets, copper pots hanging, pastel bowls on shelves, a stainless steel gas stove.",
  tag `cozinha`, uma referência (qualquer imagem ≥ 540×540). Crie também "Diner" (sem imagem).
  Os dois aparecem na grade com miniatura (ou o ícone do tipo) (US2-1).
- Aba Marca → Card final → fundo "Imagem": o seletor lista as imagens de fundos **e** cenários da
  biblioteca; "Abrir biblioteca", busque "cozinha", escolha a referência da "Cozinha retrô" e
  salve o kit. A prévia mostra a imagem (US2-2).
- No seletor, "Enviar imagem de fundo" com um JPG novo: ele entra na biblioteca como "Fundo" com o nome
  do arquivo e fica escolhido no rascunho.
- Envie um corte (aba Cortes, 004): o card final sai com a imagem do cenário (o corte aceita a
  classe `fundo`, R3).

## 3. Stickers e marca d'água (US3)
- Envio múltiplo em Sticker: 3 PNG com transparência, tags `reação` (2) e `promo` (1, e mais um
  com as duas). Filtre por tag `promo`: só os certos aparecem; busque pelo nome: idem (US3-2).
- Envie um JPG como sticker: "O sticker precisa ter fundo transparente" (US3-1). Um PNG todo
  opaco: a mesma mensagem.
- Aba Marca → Marca d'água → tipo Imagem: o seletor lista marcas d'água e stickers; escolha um
  sticker, salve. A exportação traz o link da imagem em `assets.watermarkImage` (US3).
- Limites: um arquivo de 21 MB → "Arquivo maior que 20 MB" (vindo da API, não um 413 do edge);
  um de 19 MB passa. Um `.txt` renomeado para `.png` → "Formato não aceito".

## 4. Onde é usado, arquivar e baixar (US4, SC-004)
- Abra a referência da "Cozinha retrô" (em uso no card final): "Onde é usado" mostra "Card final
  (kit vN)" e "N cortes". "Arquivar": recusado com "Em uso em: Card final (kit vN)" (US4-1). O
  uso por cortes aparece mas não bloqueia.
- Na aba Marca, escolha outra imagem para o fundo do card e salve; volte e arquive o cenário:
  agora passa. (Trocar o tipo de fundo para cor **não** libera: o kit guarda o
  `fundo_imagem_id` mesmo com fundo `cor`, e o uso continua bloqueando, R5.)
  Na aba Marca, o seletor não mostra mais a imagem; reverter o kit para a versão com a imagem →
  "Essa versão não vale mais…" (409 `revert_conflict`).
- "Mostrar arquivados": o cenário aparece com o selo; "Restaurar" o traz de volta (US4-3).
- "Baixar original": o arquivo baixado tem o mesmo `sha256` do enviado
  (`sha256sum` dos dois). "Copiar link": abra numa janela anônima (sem login): a imagem abre;
  copie de novo depois de recarregar: o link é o mesmo (US4-2, FR-008).
- Nenhuma rota DELETE: `curl -s http://localhost:8180/api/openapi.json | grep -c '"delete"'` → 0.

## 5. HD de dados (edge case)
Sem o sentinela (`mv .sociman-volume .sociman-volume.off` na pasta do HD): a aba Assets lista os
assets e os textos (as miniaturas podem falhar, porque o imgproxy lê do MinIO); "Novo asset" de
avatar sem arquivo funciona; enviar arquivo, "Baixar original" e "Copiar link" aberto respondem
"O HD de dados não está disponível". Nada foi gravado no NVMe. Volte o sentinela.

## 6. Testes automatizados
```bash
npm run test:api                           # stack efêmera; inclui backfill, usos, mídia e os testes da 004
docker compose exec api uv run ruff check .
npm run gen:contract && npm run check:web  # contrato regenerado, typecheck, build, CSP (inalterada)
npm run test:e2e                           # stack e2e isolada; e2e/assets.spec.ts + fundo/marca ajustados
```
Obrigatórios:
- toda mutação de asset e arquivo gera versão com autor (princípio VII); reversão só dono (403
  para membro); 409 em edição concorrente;
- nenhuma rota DELETE no OpenAPI (SC-004); arquivar com uso no kit → 409 `asset_in_use`;
- backfill: um asset por imagem de fundo e marca d'água, ids iguais, idempotente (SC-003);
- sticker sem transparência recusado com a mensagem da spec; 20 MB aceito até o limite;
- `ref_context` recusa imagem arquivada; o corte aceita fundo de cenário;
- link `imagem` sem validade, estável e com download do original.

## 7. Medir
- **SC-001:** tempo do §1 (meta: < 5 min).
- **SC-002:** na stack efêmera do e2e, um seed de 200 assets (script do teste, tipos e tags
  variados); cronometre da abertura da aba até achar um asset por tag e por nome (meta: < 10 s).
- **SC-003:** as contagens do §0.
- **SC-005:** a checagem do §1.

## Resultado
**2026-09-29, `sakai-desktop` (trilha C).**

**§0 / SC-003 no dev.** A linha de base de T001 não foi anotada antes do upgrade: a API do dev
já estava em `0006_cortes_openshorts` quando a trilha C começou. Como a `0005` não cria nem
apaga linhas em `images`, a contagem de `images` depois do upgrade é a mesma de antes:
- `images` com `kind IN ('watermark','fundo')`: `fundo = 1` (nenhuma `watermark`);
- as mesmas imagens com `asset_files`: `fundo = 1` (100%); sem asset: `0`;
- versões `asset` com `system:migration`: `1`; o asset é "Fundo 1" (`fundo`);
- o kit do perfil que usa a imagem ("Fundo E2E 6cf78dd4", v1) continua com
  `endCard.fundo_imagem_id = d9496097…`, o mesmo `image_id` do `asset_files`;
- `alembic upgrade head` de novo: nada muda (1 asset, 1 versão de migração).
O dev não tem os perfis "Queridinhos" e "A Taverna Nerd"; a prévia e o "Exportar JSON" à mão
(§0, T041) e os §1–§5 à mão (T042) ficam para o dono.

**Edge e imgproxy (T002, T003).** `imgproxy version` = 4.0.12, com
`IMGPROXY_MAX_SRC_RESOLUTION=40` (dev e e2e). `nginx -t` ok. POST de 15 MB sem login:
`/api/perfis/x/assets/arquivo` → 401 e `/api/assets/x/arquivos` → 401 (chegou à API);
`/api/perfis/x/imagens` → 413 (edge, 8m).

**SC-002 (e2e, stack efêmera, 200 assets):** por tag 499–1359 ms, por nome 706–736 ms
(meta: < 10 s).

**e2e** (`flock /tmp/sociman-e2e.lock npm run test:e2e`): `assets.spec.ts` (3 testes),
`assets-escala.spec.ts`, `fundo.spec.ts` e `marca.spec.ts` verdes em duas rodadas completas
seguidas (19/19; na segunda, o único vermelho era o `cortes-openshorts.spec.ts` da 006, ainda
em andamento). `npm run test:e2e:pwa`: 10/10. Capturas em `.playwright-mcp/sociman/007-*.png`.

**Achado do e2e (corrigido na trilha B):** o `checkImageFile` media a imagem com uma URL `blob:`,
que a CSP (`img-src 'self' data:`) bloqueia, e recusava toda imagem com "Formato não aceito".
Agora usa `createImageBitmap`.
