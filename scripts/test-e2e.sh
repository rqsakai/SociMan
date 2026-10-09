#!/bin/sh
# Roda os e2e (Playwright) numa stack EFÊMERA (docker-compose.e2e.yml, projeto sociman-e2e):
# Postgres, Redis, MinIO, Mailpit, API, worker, SPA e edge novos a cada execução, destruídos
# com `down -v` ao terminar (sucesso, falha ou Ctrl+C). A stack de dev (projeto sociman,
# :8180) não é tocada: o banco de dev e o usuário do dono ficam intactos.
#
#   ./scripts/test-e2e.sh                        # e2e/ contra o Vite dev (EDGE_MODE=dev)
#   ./scripts/test-e2e.sh --pwa                  # e2e-pwa/ contra o build de produção
#   ./scripts/test-e2e.sh e2e/marca.spec.ts -g x # demais argumentos vão para o Playwright
#
# Portas no host (só 127.0.0.1): edge 8280 (http) e 8643 (https), Mailpit 8127.
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PROJECT=sociman-e2e
COMPOSE="docker compose -p $PROJECT -f $ROOT/docker-compose.e2e.yml --project-directory $ROOT"

MODE=dev
if [ "${1:-}" = "--pwa" ]; then
  MODE=pwa
  shift
fi

export E2E_EDGE_PORT=8280 E2E_EDGE_TLS_PORT=8643 E2E_MAILPIT_PORT=8127
export E2E_BASE_URL="http://localhost:$E2E_EDGE_PORT"
export E2E_HTTPS_URL="https://localhost:$E2E_EDGE_TLS_PORT"
export E2E_MAILPIT_URL="http://127.0.0.1:$E2E_MAILPIT_PORT"
export E2E_COMPOSE="-p $PROJECT -f $ROOT/docker-compose.e2e.yml --project-directory $ROOT"
export E2E_WEB_DIST="$ROOT/.e2e/pwa-dist"
if [ "$MODE" = pwa ]; then
  export E2E_EDGE_MODE=prod
  PW_CONFIG=playwright.pwa.config.ts
else
  export E2E_EDGE_MODE=dev
  PW_CONFIG=playwright.config.ts
fi

cleanup() {
  trap - EXIT INT TERM
  echo "==> Destruindo a stack e2e $PROJECT (down -v)..." >&2
  $COMPOSE --profile dev --profile pwa down -v --remove-orphans >/dev/null 2>&1 \
    || echo "AVISO: falha ao destruir $PROJECT; confira: docker ps -a --filter name=$PROJECT" >&2
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Sobra de uma execução interrompida à força (kill -9): começa do zero.
$COMPOSE --profile dev --profile pwa down -v --remove-orphans >/dev/null 2>&1

if [ "$MODE" = pwa ]; then
  # Build próprio do e2e (o update.spec o reconstrói): o apps/web/dist do modo casa fica intacto.
  echo "==> Build de produção do SPA em $E2E_WEB_DIST..." >&2
  mkdir -p "$E2E_WEB_DIST"
  (cd "$ROOT" && npm run build -w @sociman/web -- --outDir "$E2E_WEB_DIST" --emptyOutDir) >&2 \
    || { echo "ERRO: falha no build do SPA" >&2; exit 1; }
fi

echo "==> Subindo a stack e2e ($PROJECT, perfil $MODE)..." >&2
$COMPOSE --profile "$MODE" up -d --build --wait --quiet-pull >/dev/null 2>&1 \
  || { echo "ERRO: a stack e2e não ficou saudável" >&2; $COMPOSE --profile "$MODE" logs --no-color --tail 80 >&2; exit 1; }

echo "==> Rodando Playwright ($PW_CONFIG) contra $E2E_BASE_URL..." >&2
(cd "$ROOT" && npx playwright test -c "$PW_CONFIG" "$@")
code=$?
echo "==> Playwright terminou com código $code" >&2
exit $code
