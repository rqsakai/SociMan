# Quickstart de validação: 001-auth

Roteiro para provar que a feature funciona de ponta a ponta. Os contratos estão em
[contracts/http-api.md](contracts/http-api.md) e os dados em [data-model.md](data-model.md).

## Pré-requisitos
- Stack no ar: `docker compose up -d --build`. Os serviços novos são `redis` e `mailpit`.
- `docker compose ps` mostra `api`, `postgres` e `redis` saudáveis.
- Portas do host: edge 8180/8543 e Mailpit UI em **127.0.0.1:8126** (só dev). Redis e SMTP do
  Mailpit NÃO são publicados. As portas 6379, 1025 e 8025 do host pertencem ao arka-manager e não
  devem ser usadas.
- `JWT_SECRET` definido em `apps/api/.env` para rodar fora do Docker (em dev, a falta dele gera um
  segredo efêmero, e todas as sessões caem a cada restart da API).

## 1. Saúde
```bash
curl -s http://localhost:8180/api/health        # {"status":"ok","db":"ok","redis":"ok"}
```

## 2. Primeiro dono (FR-011)
```bash
docker compose exec api uv run sociman create-owner --email dono@casa.local --name "Dono"
```
Esperado: o comando pede a senha duas vezes e cria o usuário. Rodar de novo é recusado ("já existe
um dono ativo").

## 3. Login, sessão e logout (User Story 1)
1. Abra `http://localhost:8180/login` e entre como dono. A tela `/app` aparece.
2. Recarregue a página: continua logado (renovação pelo cookie `sociman_rt`).
3. Senha errada e e-mail inexistente mostram a mesma mensagem, "E-mail ou senha incorretos".
4. Clique em "Sair": `/app` volta a exigir login.

## 4. Usuários da casa (User Story 2)
1. Como dono, em `/app/usuarios`, crie `membro@casa.local` com uma senha provisória.
2. Em `http://127.0.0.1:8126`, o e-mail "Confirme seu e-mail" chegou em menos de 1 minuto (SC-008).
3. Antes de clicar no link, o login do membro é recusado com a opção de reenviar a verificação.
4. Clique no link, entre com a senha provisória e confirme que o app força `/trocar-senha`. Troque a
   senha e depois use o app normalmente.
5. Como membro, abrir `/app/usuarios` ou `/app/seguranca` responde "sem permissão" (403 na API).
6. Tentar desativar ou rebaixar o único dono é recusado (`last_owner`).

## 5. Recuperação (User Story 4)
Em "Esqueci a senha", peça a recuperação para o membro. O link chega no Mailpit, a nova senha
funciona e a antiga não; reabrir o link mostra "inválido ou expirado".

## 6. Eventos de segurança (User Story 3)
Em `/app/seguranca`, filtre pelo membro: aparecem `user_created`, `email_verified`,
`password_changed`, `login_*` e `password_reset_*`, cada um com autor, data e IP.

## 7. Testes automatizados (princípio VI)
```bash
docker compose exec api uv run pytest            # unit + integração (Postgres sociman_test + Redis DB 15)
docker compose exec api uv run ruff check .
npm run check:web                                # inclui check:contract (OpenAPI → cliente sem diff)
npm run test:e2e                                 # Playwright contra http://localhost:8180
```
Os testes cobrem obrigatoriamente:
- reuso do token de renovação revoga a família;
- duas renovações simultâneas não derrubam a sessão;
- limites de tentativas (SC-007);
- `membro` recebe 403 em todas as rotas só-dono (SC-003);
- `updated_by` preenchido em toda mutação (SC-004);
- respostas públicas idênticas para e-mail existente e inexistente (SC-006);
- desativação derruba a sessão na próxima requisição;
- o último dono não pode ser rebaixado nem desativado.

## Resultado da verificação (2026-09-29)
- `pytest`: 193 passed · `ruff`: limpo · `npm run check:web`: verde (contrato, typecheck, build, bundle, CSP, segredos).
- e2e: 7/7 em 3 rodadas seguidas durante a implementação e 7/7 na rodada final (13,4 s), autorizada pelo dono.
- SC-001 (login < 15 s): API responde o login em 0,14 s; o login pela tela no e2e leva menos de 1 s.
- SC-005 (recuperação < 3 min): o fluxo completo automatizado (pedir → e-mail → nova senha → login) roda em poucos segundos no e2e.
- SC-008 (e-mail de verificação < 1 min): no e2e o e-mail chega ao Mailpit em menos de 1 s após criar o usuário.
- SC-009 (achar um evento < 30 s): a consulta filtrada por usuário responde em 0,02 s; na tela são 2 cliques (Usuário → Filtrar).
- Validação manual do dono: US1, US2, US3 e US4 aprovadas.
