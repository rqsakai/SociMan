# SociMan

Gestão das contas de mídia social da agência: contas, kit de marca, avatares, cenas, scripts, canais-fonte e padrões de corte. SPA (PWA) + API Python, com MCP para as IAs.

- Visão e backlog: [`docs/visao.md`](docs/visao.md)
- Guia para o Claude Code: [`CLAUDE.md`](CLAUDE.md)
- Base: o SPA, o edge nginx e as travas de segurança vieram do boilerplate **volans** (`../../theitnerd/volans`, commit `4d4058f`). A API foi reescrita em FastAPI.

## Subir

Requisitos: Docker, Node ≥ 22 e [uv](https://docs.astral.sh/uv/).

```bash
npm install                 # deps do SPA (o container web usa o node_modules do host)
docker compose up -d
```

- App: http://localhost:8180 (https://localhost:8543, com cert local autoassinado)
- API: http://localhost:8180/api/health · docs em `/api/docs`
- MinIO: http://localhost:9101

## Desenvolvimento orientado a spec

```text
/speckit-constitution → /speckit-specify → /speckit-clarify → /speckit-plan → /speckit-tasks → /speckit-implement
```

## Checagens

```bash
cd apps/api && uv run pytest && uv run ruff check .
npm run check:web
```
