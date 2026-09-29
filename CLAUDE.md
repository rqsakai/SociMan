# CLAUDE.md: SociMan

Gestão de contas de mídia social da agência: contas, kit de marca, avatares e poses, cenas, scripts, canais-fonte, vídeos e padrões de corte. A IA acessa tudo por MCP. Docs em pt-BR.

## Como trabalhar (o dono)
- **Um passo por vez:** mostre o comando, explique em uma linha, rode, leia a saída e só então siga.
- **Spec Driven Development com o GitHub Spec Kit:** `/speckit-constitution`, depois `/speckit-specify`, `/speckit-clarify`, `/speckit-plan`, `/speckit-tasks` e `/speckit-implement`. **Nada de código de feature sem spec aprovada.** As specs ficam em `specs/NNN-nome/`.
- A visão e o backlog de specs estão em `docs/visao.md`. A constitution está em `.specify/memory/constitution.md`.
- Commit e push só quando o dono pedir. Mensagens em pt-BR, no imperativo.

## Stack
```
apps/web            SPA React 19 + Vite + Tailwind 4 (copiado do volans; auth UI pronta)
packages/contract   Zod + client tipado (herdado do volans; será gerado do OpenAPI do FastAPI)
apps/api            FastAPI (Python 3.12, uv), SQLAlchemy 2 + Alembic, PostgreSQL
redis / mailpit     sessões e limites de tentativa (Redis, AOF) / e-mail de dev (Mailpit)
docker/nginx        edge: /api → api:3001, /img → imgproxy, / → SPA; headers e CSP
reference/volans-api  API TypeScript original do volans (SÓ referência para portar a auth; não roda)
docs/reference/volans arquitetura, ADRs e produto do volans (referência)
.specify/ .claude/skills  Spec Kit
```

## Comandos
```bash
docker compose up -d                        # stack: http://localhost:8180  https://localhost:8543
curl http://localhost:8180/api/health       # {"status":"ok","db":"ok","redis":"ok"}
npm run test:api [-- args do pytest]      # API em stack EFÊMERA (docker-compose.test.yml): sobe Postgres/Redis/MinIO, roda o pytest e faz down -v sempre; pode rodar em paralelo
docker compose exec api uv run pytest       # alternativa rápida no dev (banco sociman_test + Redis DB 15; NUNCA duas ao mesmo tempo)
docker compose exec api uv run ruff check .
npm run check:web                           # check:contract + typecheck + build + check:bundle/csp/secrets
npm run gen:contract                        # OpenAPI do FastAPI → packages/contract (roda no host, sem Docker)
npm run test:e2e [-- args do playwright]  # Playwright em stack EFÊMERA (docker-compose.e2e.yml, projeto sociman-e2e, edge :8280/:8643, Mailpit :8127): sobe tudo, roda e faz down -v sempre; NUNCA toca o dev
docker compose exec api uv run sociman create-owner --email E --name N [--force]   # primeiro dono
docker compose exec api uv run sociman set-password --email E                      # senha de emergência
docker compose exec api uv run sociman reset-db --yes                              # zera banco+Redis (não roda em produção)
./scripts/certs-casa.sh [IP]                # CA da casa + certificado do edge (IP padrão 192.168.86.47); guia: docs/guia-certificado-casa.md
npm run casa:up                             # MODO CASA: build de produção + EDGE_MODE=prod + perfil prod (PWA instalável)
npm run test:e2e:pwa                        # e2e do PWA na stack efêmera (perfil pwa: build em .e2e/pwa-dist + EDGE_MODE=prod); não precisa do modo casa
docker compose --profile prod stop web-prod && docker compose up -d edge   # volta ao modo dev
./scripts/data-setup.sh check|init|count|migrate|compare|verify   # HD de dados (MinIO + work) — ver spec 004 quickstart §0
docker compose logs -f worker               # worker de vídeo (`sociman worker`): fila de cortes, ffmpeg
```
**Modo casa:** use `https://192.168.86.47:8543` nos aparelhos (com a CA da casa instalada). `http://192.168.86.47:8180` redireciona para lá; a CA pública fica em `http://192.168.86.47:8180/sociman-ca.cer`.
Portas: edge 8180/8543, console do MinIO 9101 (minioadmin/minioadmin, **só dev**), Mailpit (e-mails de dev) em **127.0.0.1:8126**. Postgres, API, Redis, SMTP e imgproxy ficam só na rede interna. **Não use** 8000/5175 (OpenShorts), 18789 (OpenClaw) nem 6379/1025/8025 (arka-manager, já ocupadas no host).

## Frontend (desde a spec 005)
- UI com **shadcn/ui** (Radix) + Tailwind 4 + TanStack Query + **TanStack Table v9** (API nova: use `dataTableColumns<T>()` de `components/data-table`, não exemplos da v8).
- Componentes do shadcn em `apps/web/src/components/ui/` (adicione com `npx shadcn@latest add <nome>` dentro de `apps/web`); painel em `components/shell/` (AppShell, Sidebar, Topbar, AuthShell, MetricCard, HeaderCard, `usePageMeta`); tabelas com `components/data-table/DataTable`.
- Formulários: `components/ui/field.tsx` (`Field` + `NativeSelect`: `<select>` nativo, e os e2e dependem dele). Confirmações em AlertDialog (`role="alertdialog"`).
- Referência visual: `docs/design/layout-referencia.md` (Material Dashboard React, só inspiração). CSP: `style-src 'unsafe-inline'` aceito, `script-src` estrito (ADR 0001).
- Vitrine de componentes só em dev: `/app/_showcase`.

## Kit de marca e cortes (desde a spec 004)
- **MinIO no HD:** `${SOCIMAN_DATA_DIR}` (padrão `/media/sakai/BACKUP/tiktok/sociman`) tem `minio/`, `work/` e o sentinela `.sociman-volume`. Buckets: `sociman` (imagens), `sociman-fonts` e `sociman-videos`. O volume antigo `sociman_minio-data` ficou como cópia de segurança, sem uso.
- **Código:** `datadir.py` (sentinela, espaço livre, 503/507), `storage.py` (`bucket="imagens"|"fontes"|"videos"`, sem delete), `midia.py` + `router_midia.py` (links HMAC `/api/midia/{token}` com Range; vídeo com validade, fonte e marca d'água sem validade), `marca/` (tokens, kit, exportação para o OpenShorts, fontes, marca d'água) e `cortes/` (probe, render com Pillow, compose com ffmpeg, fila com SKIP LOCKED, worker).
- **Edge:** as rotas de upload grande têm `location` própria no `default.conf.template`: cortes com 520m e sem buffering, fontes com 11m. `/api/midia/` sem buffering.
- **Gancho:** quem queima é o SociMan. Ao gerar cortes no OpenShorts, **não** use `auto_hook` (a exportação traz `openshorts.hook.enabled=false`).

## Armadilhas
1. **Containers rodam como UID 1000.** Se uma pasta de bind mount não existir, o Docker a cria como root (foi o que aconteceu com `docker/certs`). Crie antes.
2. **CSP estrita em produção** (herdada do volans). `check:csp` compara `apps/web/vite.config.ts` com `docker/nginx/05-edge-mode.envsh`. Mudou um, mude o outro.
3. **A API confia em `X-Forwarded-*`** (`--forwarded-allow-ips='*'`) porque só o edge a alcança. Nunca publique a porta da API.
4. **Não mate processos por nome** (`pkill -f vite` mata processos dentro dos containers). Use porta ou PID.
5. **Segredos:** `.env` é gitignored, e `check:secrets` roda sobre os arquivos rastreados. Credenciais do compose são só de dev.
6. **O contrato é gerado** (constitution, princípio IV): não edite `packages/contract/openapi.json` nem `src/generated/` à mão. Mudou rota ou schema na API → `npm run gen:contract`. O `check:contract` acusa divergência.
7. **Sessão do banco com `DbSession` (scope="function")**: no escopo padrão o FastAPI commita depois de enviar a resposta e o SPA lê dado velho. Nunca declare `Depends(get_db)` direto (há teste de regressão).
8. **Negação que precisa ficar registrada** (ex.: `login_failed`) é commitada antes do erro (`_deny` em `auth/service.py`), porque o `get_db` faz rollback quando a rota levanta exceção. Revogação de sessões no Redis só **depois** do commit.
9. **E-mail que não pode revelar se a conta existe** (reenvio de verificação, esqueci a senha) sai em BackgroundTask, para o tempo de resposta ser igual.
10. **`JWT_SECRET`** fica em `apps/api/.env` (gitignored). Sem ele a API usa um segredo efêmero e toda sessão cai a cada reload.
11. **Service worker só no build de produção** (modo casa). Em dev (Vite) não há SW. O e2e do PWA usa o HTTP de localhost porque o Chromium de teste não tem a CA e recusa SW com certificado inválido.
12. **Chaves da CA** ficam em `docker/certs/ca/` (gitignored, 600). Nunca compartilhe `sociman-ca.key`; só `sociman-ca.crt/.cer` são públicos.
13. **Mudou `docker/nginx/*`?** Rode `docker compose restart edge`. O template é montado como arquivo, e `up -d` não recria o container.
14. **Specs de domínio usam `history.py`** (princípio VII): toda mutação chama `history.record` na mesma transação (autor, antes/depois), cada entidade tem `version` (controle otimista → 409 `version_conflict`) e `__versioned_fields__`/`__immutable_fields__`. **Não existe DELETE no domínio**: arquivar/restaurar; reversão só pelo dono.
15. **Imagens:** `storage.py` (MinIO, bucket privado, sem delete) + `imaging.py` (validação Pillow pelo conteúdo, URLs `/img` do imgproxy). `IMGPROXY_KEY`/`IMGPROXY_SALT` no `.env` da raiz assinam as URLs; sem eles é `unsafe` (só dev). O edge aceita até 8 MB em `/api/`; a API limita a 5 MB.
16. **FastAPI 0.141 envolve rotas incluídas em `_IncludedRouter`**: procurar rota em `app.routes` não funciona (use `app.openapi()`).

17. **Armazenamento NVMe × HD** (constitution 2.1.0): no NVMe ficam a aplicação, o PostgreSQL e o Redis (o que precisa ser rápido); o MinIO inteiro (imagens, fontes, vídeos), os temporários do ffmpeg, downloads e exportações vão para o HD em `/media/sakai/BACKUP/tiktok` (partição BACKUP, 2,1 TB). O uso do HD exige o arquivo marcador `.sociman-volume` (sem ele, recusa: HD desmontado encheria o NVMe) e um piso de espaço livre.
18. **e2e isolado do dev:** `npm run test:e2e` e `test:e2e:pwa` sobem o projeto compose `sociman-e2e` (outra rede, volumes em tmpfs, portas 8280/8643/8127 só em 127.0.0.1) e o derrubam com `down -v`; o banco de dev e o usuário do dono ficam intactos. **Nunca rode `npx playwright test` direto**: sem `E2E_BASE_URL`/`E2E_MAILPIT_URL`/`E2E_COMPOSE` ele falha de propósito, e o `compose()` dos helpers recusa qualquer projeto que não seja `sociman-e2e`. Os dois modos usam o mesmo nome de projeto: não rode dois e2e ao mesmo tempo.

## Regras de negócio herdadas da agência (não mudam)
- O SociMan **nunca publica** em rede social.
- Direito autoral é responsabilidade do dono (constitution 3.0.0, princípio II): o SociMan não bloqueia. O canal-fonte tem status informativo (`proprio`, `parceiro`, `programa_de_cortes`, `sem_acordo`) que só o dono muda; `sem_acordo` ou envio avulso mostra aviso, e todo envio para corte fica no histórico.
