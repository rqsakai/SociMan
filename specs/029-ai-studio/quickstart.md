# Quickstart: 029 AI Studio

Roteiro de validação. Os detalhes de dados e de rotas estão em [data-model.md](data-model.md) e [contracts/http-api.md](contracts/http-api.md).

## §0 Antes
- Stack de dev de pé (`docker compose up -d`) e `curl http://localhost:8180/api/health` ok.
- Backup do banco antes da migration:
  ```bash
  docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > /media/sakai/BACKUP/tiktok/sociman/backups/pre-0024.dump
  ```
- `docker compose exec -T api uv run alembic upgrade head` → `0024_ai_studio (head)`. Depois, `docker compose restart api gerador agendador`.

## §1 Automático
```bash
npm run test:api -- -k "ai_studio or agencia_lista or perfil_base or migration_0024 or mcp_mapa or constitution"
npm run test:api                       # suíte inteira
docker compose exec api uv run ruff check .
npm run gen:contract && npm run check:web
flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/ai-studio.spec.ts
flock /tmp/sociman-e2e.lock npm run test:e2e   # inteiro
```

## §2 Manual no navegador (dono)
1. **Menu:** abra o grupo **AI Studio**. Devem estar lá Avatares, Cenários, Vozes, Produtos, Cenas, Assets e Movimentos. Movimentos abre a página "em breve".
2. **Listas:** em AI Studio › Avatares, os avatares de hoje aparecem com o perfil base. Filtre por um perfil, depois por "Sem perfil" (vazia), e recarregue a página: o filtro continua.
3. **Item sem perfil:** crie um cenário sem perfil base e peça "Gerar cena". O formulário avisa "Sem perfil base: só as regras do tipo, sem guia". Use uma opção.
4. **Perfil base na geração:** num cenário do perfil A, gere trocando o perfil base para B. Em Configurações › Assistente de IA › Registro (só para os passos com Claude, como a checagem do avatar ou a ficha do produto), confira que a chamada usou o perfil B, e que o cenário continua com o perfil base A.
5. **Cena cruzada e criação no lugar:** em AI Studio › Cenas › Nova cena, escolha perfil base B e um cenário do perfil A. Clique em "+ Novo avatar", crie um avatar e volte: ele está escolhido, e o resto da cena continua preenchido. Salve.
6. **Perfil:** abra a página do perfil A. Ela não tem mais as abas Assets, Cenas, Produtos e Vozes, e tem o card "Ver no AI Studio" com as contagens. Abra um link antigo `/app/perfis/<A>?aba=vozes` e `/app/estudio`: os dois chegam à lista certa.
7. **Kit de marca:** no kit do perfil A, o seletor de fundo lista a biblioteca da agência.

## §3 Esperado no fim
- Nenhum item sumiu: a contagem por tipo no AI Studio é igual à soma das abas antigas.
- As vozes repetidas entre perfis (se havia) aparecem com " (2)" e uma versão "nome_unico_029" no histórico.
- O registro do assistente mostra "Sem perfil" nas chamadas feitas sem perfil base.
