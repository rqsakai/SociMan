# Quickstart de validação: 003-contas-sociais

O contrato está em [contracts/http-api.md](contracts/http-api.md) e o modelo de dados em
[data-model.md](data-model.md).

## Pré-requisitos
- Stack em modo dev (`docker compose up -d`), com o `api` saudável, `minio` healthy e `imgproxy`
  no ar.
- Migration `0002_perfis` aplicada (o `start.sh` faz `alembic upgrade head`).
- Um dono criado (`sociman create-owner`) e um membro (gestão de usuários da 001).

## 1. Perfis (US1)
Em `/app/perfis`, clique em "Novo perfil", com Nome "A Taverna Nerd" e nicho "Geek, gadgets, games, toys, RPG/D&D":
- o slug sugerido é `a-taverna-nerd`;
- ao salvar, o perfil aparece na lista como "Em preparação";
- criar outro perfil com o mesmo slug é recusado;
- depois de criado, o slug não pode ser editado.

## 2. Contas (US2)
Em "Queridinhos", aba Contas, adicione TikTok, colando `https://www.tiktok.com/@meusqueridinhos10`:
- o @ vira `@meusqueridinhos10` e o link é mantido;
- uma segunda conta TikTok **ativa** no mesmo perfil é recusada;
- o mesmo @ em outro perfil é recusado com "Esse @ já pertence ao perfil Queridinhos";
- a conta YouTube com status "Planejada" é aceita.

## 3. Logo e banner (US3)
- Um PNG de 512×512 vira logo e aparece a miniatura na lista (a URL começa com `/img/`).
- Um JPG de 1500×500 vira banner.
- São recusados: um `.png` que na verdade é texto, um arquivo de 6 MB e um logo de 100×100, cada
  um com a mensagem correspondente.
- `curl -I http://localhost:8180/img/...` sem login responde 200 (imagem pública, FR-009a).
- A porta S3 do MinIO não está publicada no host.

## 4. Histórico e reversão (US4)
1. Edite a bio de "Queridinhos" duas vezes, como membro e depois como dono.
2. A aba Histórico mostra as duas edições, com autor, data e o antes e depois da bio.
3. Como dono, clique em "Reverter para esta versão" na v1: a bio antiga volta, e aparece uma
   versão nova do tipo "Revertido".
4. Como membro, o botão de reverter não aparece, e a API responde 403.
5. Troque o logo e reverta: o logo anterior volta.
6. Arquive o perfil: ele some da lista e aparece em "Arquivados". Restaure: ele volta.
7. Edite o mesmo perfil em duas abas. A segunda a salvar recebe "Este perfil foi alterado por
   outra pessoa; recarregue".

## 5. Testes automatizados
```bash
docker compose exec api uv run pytest     # inclui MinIO real (bucket sociman-test)
docker compose exec api uv run ruff check .
npm run check:web                          # contrato regenerado, typecheck, build, CSP
npm run test:e2e                           # inclui e2e/perfis.spec.ts (zera o banco de dev)
```
Obrigatórios:
- toda mutação gera versão com antes e depois (SC-004);
- nenhuma rota DELETE no OpenAPI (SC-006);
- a reversão restaura 100% dos campos, inclusive as imagens (SC-005);
- validação de imagem pelo conteúdo;
- 403 para membro na reversão;
- 409 em edição concorrente.

## 6. Medir
SC-001 (cadastro com conta em menos de 2 min), SC-003 (lista em menos de 1 s) e SC-005 (reversão
em menos de 30 s).

## Resultado da verificação (2026-09-29)
- `npm run test:api` (stack efêmera): 311 passed, em duas rodadas seguidas, sem teste pulado.
- `ruff`: limpo. `npm run check:web`: verde.
- `npm run test:e2e`: 8/8, em duas rodadas seguidas (inclui `perfis.spec.ts`).
- **SC-002:** os dois perfis reais foram cadastrados pela API no banco de dev, sem nenhum campo faltando: Queridinhos (TikTok `@meusqueridinhos10`) e A Taverna Nerd (YouTube e TikTok `@atavernanerd`). O mesmo @ em plataformas diferentes é aceito.
- **SC-003:** a lista responde em cerca de 5 ms na API.
- **SC-005:** a reversão responde em cerca de 11 ms e restaura os campos. O teste de imagem confirma que o logo antigo volta.
- **SC-001:** o cadastro pela interface ainda não foi medido; fica para a validação manual do dono.
- Ajustes feitos durante a verificação:
  - o edge passou para `client_max_body_size 8m`, porque com 6m um arquivo pouco acima de 6 MiB recebia 413 do nginx em vez da mensagem da API;
  - o input de arquivo oculto saiu da árvore de acessibilidade, porque aparecia com o mesmo nome do botão visível;
  - um `skipif` que nunca desligava foi removido, porque o FastAPI 0.141 esconde as rotas incluídas de `app.routes`.
