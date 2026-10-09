# Quickstart: validar a Importação da agência (013)

Roteiro de validação de ponta a ponta. A forma das rotas está em [contracts/http-api.md](contracts/http-api.md)
e as regras em [data-model.md](data-model.md).

> **Dados reais:** os testes automatizados usam só pastas **sintéticas** (`tests/integration/agencia_helpers.py`
> e `e2e/fixtures/agencia/`). O passo 5 lê a pasta real da agência (`../shared` e `../media/clipes`), à mão,
> com o dono, no banco de dev. **Antes do passo 5, faça um backup do banco** (o dev é o banco de uso).

## 0. Pré-requisitos

- Stack de dev no ar: `docker compose up -d` e `curl http://localhost:8180/api/health` → `ok`.
- Montagens: `docker compose exec api ls /agencia/shared/perfis /agencia/clipes` lista os perfis e as
  pastas de clipes; `docker compose exec api touch /agencia/shared/x` **falha** ("Read-only file system").
- Migration aplicada: `docker compose exec api uv run alembic upgrade head` (cabeça `0016_importacao`).
- HD montado com o marcador e espaço livre para ~1 GB além do piso (`./scripts/data-setup.sh check`).
- Logado como dono (e, para o passo 4, também como membro).

## 1. Testes automatizados

```bash
npm run test:api -- tests/ -k "agencia or constitution or migration_0016" -q
docker compose exec -T api uv run ruff check .
npm run gen:contract && npm run check:web
flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/importacao.spec.ts
```

**Esperado:** tudo verde, incluindo:
- a pasta sintética com as 4 situações e as contagens certas (US1);
- a 2ª importação com 0 entidades, 0 versões e 0 arquivos novos (SC-002);
- nenhum valor editado e nenhum direito existente trocado sem escolha (SC-003);
- histórico com o dono e a origem em toda mutação (SC-004);
- 0 ações aceitas de membro, IA ou MCP, e nenhuma escrita na pasta (SC-005);
- desfazer volta o banco ao estado anterior, com arquivados e versões novas (SC-007).

## 2. Pré-visualização sintética na tela

1. Aponte as raízes para a pasta do e2e (`AGENCIA_SHARED_HOST=./e2e/fixtures/agencia/shared`,
   `AGENCIA_CLIPES_HOST=./e2e/fixtures/agencia/clipes` no `.env`) e `docker compose up -d api`.
2. Abra `/app/configuracoes/importacao` → "Ler a pasta da agência".
3. **Confira:** cartões com as contagens; filtros por perfil, tipo e situação; um item `diverge` mostra os
   dois lados; canal novo com o direito proposto `sem_acordo` e a troca para `parceiro`; itens `fora` com
   o motivo.

## 3. Confirmar, reimportar e desfazer (sintético)

1. Troque um `diverge` para "Usar o markdown", desmarque um `novo` e confirme.
2. **Confira:** o andamento até "concluída"; no histórico da entidade trocada, o dono como autor e
   "importado de `<arquivo>` §`<trecho>`".
3. Leia a pasta de novo: 0 novos (o desmarcado continua `novo`), e confirmar não grava nada.
4. Desfaça: o criado é arquivado, o trocado volta; edite antes um item criado e confira "não desfeito:
   editado depois".
5. Volte as raízes para o padrão (remova as 2 linhas do `.env`) e `docker compose up -d api`.

## 4. Permissões

- Como **membro**: a página abre com o estado e a lista, sem "Ler", "Confirmar" nem "Desfazer"; a rota de
  prévia responde 403 `somente_dono`.
- Com um **token MCP** (009): as tools `agencia_importacoes_list` e `agencia_importacoes_get` respondem; a
  prévia, a confirmação e o desfazer não existem como tool, e uma chamada direta à rota responde 403
  `somente_humano`, com o evento registrado.

## 5. Pasta real da agência (com o dono)

1. Backup do banco. "Ler a pasta da agência".
2. **Confira com o dono** (números de 2026-10-06; mudam se os agentes gravaram depois):
   - 2 perfis e 3 contas `igual`;
   - 18 canais `igual`, 3 `diverge(direito)` (Fofocalizando, Vênus Podcast, De Frente com Blogueirinha:
     `pendente` × `parceiro`) e 8 `fora` (sem canal do YouTube identificável ou conteúdo próprio);
   - 16 imagens `igual` e 2 `fora` (`nao-usar-ainda`); persona em `queridinhos` (`igual`, ou `diverge` campo a campo se o texto do SociMan foi editado);
   - guia dos 2 perfis `novo`; anotações `novo` (público, monetização, metas, 11 + 13 decisões, seções da
     pesquisa, pautas);
   - 68 clipes `novo` (≈900 MB) e os vídeos sem linha no registro `fora` (70 vídeos para 68 linhas);
   - todos os outros arquivos `fora`, cada um com o motivo (SC-001: 100% com destino ou motivo).
3. O dono decide os 3 `diverge(direito)` e confirma. Acompanhe o andamento (alguns minutos).
4. **Confira:** os guias preenchidos (tela do guia), as anotações no perfil (e pelo MCP), os 68 conteúdos
   na Central de conteúdos, sem destino, cada um com a anotação da origem; `./scripts/data-setup.sh count`
   mostra os vídeos novos no HD.
5. Leia de novo: 0 novos (SC-002). Registre o resultado na tarefa final.
