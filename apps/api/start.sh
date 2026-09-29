#!/bin/sh
# Migrations antes de subir (mesmo padrão do volans: api-start.sh).
set -e
alembic upgrade head
if [ "${SOCIMAN_RELOAD:-0}" = "1" ]; then
  exec uvicorn sociman_api.main:app --host 0.0.0.0 --port 3001 --reload --proxy-headers --forwarded-allow-ips='*'
fi
exec uvicorn sociman_api.main:app --host 0.0.0.0 --port 3001 --proxy-headers --forwarded-allow-ips='*'
