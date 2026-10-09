#!/bin/sh
# Roda o pytest da API numa stack EFÊMERA (docker-compose.test.yml): Postgres, Redis e
# MinIO novos a cada execução, com nome de projeto único, destruídos com `down -v`
# ao terminar (sucesso, falha ou Ctrl+C). A stack de dev não é tocada.
#
#   ./scripts/test-api.sh                  # suíte inteira
#   ./scripts/test-api.sh -q tests/unit    # argumentos vão direto para o pytest
#
# Config por variável (defaults só de teste): TEST_PG_USER, TEST_PG_PASSWORD, TEST_PG_DB,
# TEST_S3_ACCESS_KEY, TEST_S3_SECRET_KEY, TEST_S3_BUCKET, TEST_JWT_SECRET.
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PROJECT="sociman-test-$(date +%Y%m%d%H%M%S)-$$"
COMPOSE="docker compose -p $PROJECT -f $ROOT/docker-compose.test.yml --project-directory $ROOT"

cleanup() {
  trap - EXIT INT TERM
  echo "==> Destruindo a stack de teste $PROJECT (down -v)..." >&2
  $COMPOSE down -v --remove-orphans >/dev/null 2>&1 \
    || echo "AVISO: falha ao destruir $PROJECT; confira: docker ps -a --filter name=$PROJECT" >&2
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "==> Construindo a imagem de teste da API..." >&2
$COMPOSE build -q pytest || { echo "ERRO: falha no build da imagem" >&2; exit 1; }

echo "==> Subindo Postgres, Redis e MinIO efêmeros ($PROJECT)..." >&2
$COMPOSE up -d --wait --quiet-pull postgres redis minio >/dev/null 2>&1 \
  || { echo "ERRO: a infra de teste não ficou saudável" >&2; $COMPOSE logs --no-color >&2; exit 1; }

# Sem terminal (CI, `&`, pipe): sem TTY.
TTY_FLAG=
[ -t 0 ] && [ -t 1 ] || TTY_FLAG=-T

echo "==> Rodando pytest..." >&2
$COMPOSE run --rm --quiet-pull $TTY_FLAG pytest uv run pytest "$@"
code=$?
echo "==> pytest terminou com código $code" >&2
exit $code
