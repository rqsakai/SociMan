# Quickstart: validar as Cenas (010)

Este é o roteiro de validação de ponta a ponta. A forma das rotas está em
[contracts/http-api.md](contracts/http-api.md) e as regras em [data-model.md](data-model.md).

## 0. Pré-requisitos

- A stack de dev está no ar: `docker compose up -d`, e `curl http://localhost:8180/api/health` devolve
  `ok`.
- A migration está aplicada: rode `docker compose exec api uv run alembic upgrade head`. A cabeça deve ser
  a `0015_cenas`.
- O HD de dados está montado: `./scripts/data-setup.sh check` responde ok, porque as tomadas vão para o
  MinIO no HD.
- O perfil de teste tem, na aba Assets (007):
  - o avatar **Achadinhos**, com a descrição de `../shared/shop/persona.md` e os looks "Cozinha, corpo
    inteiro" e "Diner, busto";
  - o cenário **Cozinha retrô**, com o prompt do ambiente;
  - uma imagem de produto.
- O guia do perfil (017) tem pelo menos uma palavra proibida, para o passo 3.
- Você está logado como dono. Para o passo 6, também como membro.

## 1. Testes automatizados

```bash
npm run test:api -- tests/ -k "cenas or anotacoes or mcp or ia_tipos or constitution or migration_0015" -q
docker compose exec -T api uv run ruff check .
npm run gen:contract && npm run check:web
flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/cenas.spec.ts e2e/propostas.spec.ts e2e/mcp.spec.ts
```

## 2. Montar a cena e copiar o prompt (US1, SC-001, SC-002)

1. Abra Perfil › **Cenas** › "Nova cena".
2. Preencha a cena:
   - avatar Achadinhos, look "Cozinha, corpo inteiro";
   - cenário Cozinha retrô;
   - plano médio, câmera parada;
   - ação `lifts the lid and steam comes out`;
   - fala `Gente, olha essa panela!`;
   - 8 s, modo Ingredientes;
   - produto "Panela" com a foto.
3. Salve e confira o prompt:
   - ele começa com a descrição do avatar, **idêntica** à da aba Assets (compare com "Copiar descrição
     para prompt" da 007);
   - a ordem é avatar → regras → ação (com "exactly as in the reference image") → cenário → câmera →
     estilo → fala em pt-BR entre aspas.
4. Confira os ingredientes: são 3 (look, foto do produto, cenário) e cada um tem "Baixar".
5. Clique em "Copiar prompt" e "Copiar negative prompt" e cole num editor. O texto deve ser exato.
6. Cronometre: o tempo do passo 1 ao 5 deve ficar abaixo de 2 min com os assets já prontos.

## 3. Avisos, status e congelamento (US2, Q3)

1. Troque a fala por uma de 20 palavras. Aparece "fala longa para 8 s", e o salvar continua permitido.
2. Ponha uma palavra proibida na fala. Aparece o aviso "proibida" com a palavra.
3. Clique em "Marcar como pronta". O status vira `pronta` e o prompt mostra "congelado".
4. Na aba Assets, edite a descrição do avatar (acrescente uma palavra) e volte à cena:
   - aparece o aviso "o avatar mudou", com a diferença;
   - o prompt continua o antigo;
   - "Remontar prompt" aplica a mudança e o status continua `pronta`.
5. Edite a ação. A cena volta a `rascunho`, e o histórico mostra a mudança de status.
6. Clique em "Duplicar". Nasce "(cópia)" em rascunho, sem tomadas.
7. Arquive a cópia, restaure e reverta uma versão (como dono).

## 4. Tomada e vínculo (US3, Q2)

1. Marque a cena como pronta e gere uma tomada de verdade no **Google Flow** com o prompt e os
   ingredientes. Esta parte é manual, com o dono.
2. Envie o MP4 em "Tomadas". Ele aparece com o player, a duração e o "prompt usado". Envie uma segunda
   tomada e marque-a como escolhida: a miniatura da cena muda.
3. Envie um vídeo de 40 s. Ele é recusado ("de 1 a 30 s").
4. Em Conteúdos, envie um vídeo próprio (014) e, no bloco "Cenas", escolha esta cena:
   - a cena vira `usada`, com "Usada em";
   - o conteúdo mostra a cena;
   - editar a ação dá a mensagem "duplique para variar".
5. Tire a cena do conteúdo. Ela volta a `pronta`.

## 5. IA e MCP (US4, US5, SC-004)

1. Na ação, use "Melhorar com IA". A proposta vem com explicação. Aplique: o histórico mostra o selo "com
   ajuda da IA".
2. Use "Ajustar cena com IA" com a instrução "mais close no produto". Só ação, câmera, estilo e áudio
   mudam, e a descrição do avatar continua idêntica no prompt.
3. Com um cliente MCP "leitura e propostas" (009), use a tool de anotação para gravar uma
   `proposta_cena` no perfil.
4. Abra "Propostas dos agentes" › Aceitar. O formulário abre preenchido. Salve: a cena nasce em rascunho
   com você como autor, e a proposta fica `aplicada`.
5. Com o mesmo cliente, tente `cenas_create`, `cenas_update` e `cenas_tomadas_upload` pelo nome. As três
   são recusadas, e o registro do MCP mostra a recusa.

## 6. Permissões

Como **membro**:
- o membro cria, edita, marca pronta, envia tomada e liga ao conteúdo;
- não vê "Reverter";
- `POST /api/cenas/{id}/revert` devolve 403 `somente_dono`.

## 7. Resultado

Registre a data, quem validou e o resultado de cada passo no fim deste arquivo. O passo 4.1 (Flow real) e o
passo 5.3 (OpenClaw real) dependem do dono.
