#!/bin/sh
# HD de dados do SociMan (spec 004, research R5 e R12; constitution 2.1.0, armazenamento).
# Um subcomando por vez, conferindo a saída de cada um:
#
#   ./scripts/data-setup.sh check              # HD montado (fora do /), dono 1000, sentinela, espaço
#   ./scripts/data-setup.sh init               # cria minio/, work/tmp, work/cortes e o sentinela
#   ./scripts/data-setup.sh count volume       # objetos e bytes por bucket no volume antigo (offline)
#   ./scripts/data-setup.sh count hd           # idem em $SOCIMAN_DATA_DIR/minio
#   ./scripts/data-setup.sh count s3           # idem pelo MinIO no ar (mc du)
#   ./scripts/data-setup.sh migrate            # com o minio PARADO: copia o volume para o HD
#   ./scripts/data-setup.sh verify             # compara volume × MinIO novo, buckets, sentinela, /img
#
# Nunca apaga o volume antigo nem grava fora de $SOCIMAN_DATA_DIR. Sem sudo.
# Variáveis: SOCIMAN_DATA_DIR (padrão /media/sakai/BACKUP/tiktok/sociman), DATA_MIN_FREE_GB (20),
# SOCIMAN_MINIO_VOLUME (sociman_minio-data), EDGE_PORT (8180), MINIO_ROOT_USER/PASSWORD (só dev).
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DIR=${SOCIMAN_DATA_DIR:-/media/sakai/BACKUP/tiktok/sociman}
MIN_FREE_GB=${DATA_MIN_FREE_GB:-20}
VOLUME=${SOCIMAN_MINIO_VOLUME:-sociman_minio-data}
EDGE=http://localhost:${EDGE_PORT:-8180}
SENTINEL="$DIR/.sociman-volume"
ALPINE=alpine:latest
MC=minio/mc:latest
NETWORK=sociman_default
COMPOSE="docker compose --project-directory $ROOT"

die() { echo "ERRO: $*" >&2; exit 1; }
ok() { echo "ok: $*"; }

# Ponto de montagem do caminho (ou do ancestral mais próximo que existe).
mount_of() {
  p=$1
  while [ ! -e "$p" ]; do p=$(dirname -- "$p"); done
  findmnt -no TARGET,SOURCE,FSTYPE -T "$p"
}

check_mount() {
  info=$(mount_of "$DIR")
  target=${info%% *}
  [ "$target" != "/" ] || die "$DIR cai na raiz (/), não no HD: o HD não está montado? ($info)"
  ok "$DIR fica em $info"
}

cmd_check() {
  fail=0
  check_mount
  if [ -d "$DIR" ]; then
    owner=$(stat -c %u:%g "$DIR")
    [ "$owner" = "1000:1000" ] && ok "dono de $DIR é 1000:1000" \
      || { echo "FALHA: dono de $DIR é $owner (esperado 1000:1000)"; fail=1; }
  else
    echo "FALHA: $DIR não existe (rode init)"; fail=1
  fi
  [ -f "$SENTINEL" ] && ok "sentinela $SENTINEL" \
    || { echo "FALHA: sentinela $SENTINEL não existe (rode init)"; fail=1; }
  for d in minio work/tmp work/cortes; do
    [ -d "$DIR/$d" ] && ok "pasta $d/" || { echo "FALHA: pasta $DIR/$d não existe"; fail=1; }
  done
  if [ -d "$DIR" ]; then
    free_kb=$(df -Pk "$DIR" | awk 'NR==2 {print $4}')
    free_gb=$((free_kb / 1024 / 1024))
    awk -v f="$free_gb" -v m="$MIN_FREE_GB" 'BEGIN { exit !(f >= m) }' \
      && ok "livre: ${free_gb} GB (piso ${MIN_FREE_GB} GB)" \
      || { echo "FALHA: livre ${free_gb} GB, abaixo do piso de ${MIN_FREE_GB} GB"; fail=1; }
  fi
  [ "$fail" = 0 ] || die "o HD de dados não está pronto"
  ok "HD de dados pronto"
}

cmd_init() {
  [ "$(id -u)" = 1000 ] || die "rode como o usuário 1000 (sem sudo)"
  check_mount
  parent=$(dirname -- "$DIR")
  [ -d "$parent" ] || die "$parent não existe; crie-a à mão no HD antes"
  mkdir -p "$DIR/minio" "$DIR/work/tmp" "$DIR/work/cortes"
  if [ -f "$SENTINEL" ]; then
    ok "sentinela já existe: $SENTINEL"
  else
    { echo "SociMan: HD de dados. Não apague este arquivo (sem ele o MinIO não sobe)."
      echo "criado em $(date -Iseconds)"
      findmnt -T "$DIR"; } > "$SENTINEL"
    ok "sentinela criado: $SENTINEL"
  fi
  ls -la "$DIR"
}

# Conta objetos (um xl.meta por objeto) e bytes em disco por bucket de um diretório de dados do
# MinIO, montado só leitura num alpine descartável. $1 = argumento de --mount.
count_dir() {
  docker run --rm --mount "$1,target=/d,readonly" "$ALPINE" sh -c '
    cd /d
    for b in */; do
      b=${b%/}
      [ -d "$b" ] || continue
      n=$(find "$b" -name xl.meta | wc -l)
      s=$(du -sb "$b" | cut -f1)
      echo "$b objetos=$n bytes_disco=$s"
    done'
}

mc_sh() {
  docker run --rm --network "$NETWORK" --entrypoint sh \
    -e U="${MINIO_ROOT_USER:-minioadmin}" -e P="${MINIO_ROOT_PASSWORD:-minioadmin}" "$MC" -c \
    "mc alias set l http://minio:9000 \"\$U\" \"\$P\" >/dev/null && $1"
}

# A imagem do mc não tem sed nem awk: ela só lista em JSON, e o parse é feito aqui.
count_s3() {
  buckets=$(mc_sh 'mc ls --json l' | sed -n 's/.*"key":"\([^"]*\)\/".*/\1/p' | tr '\n' ' ')
  [ -n "$buckets" ] || die "nenhum bucket no MinIO (está no ar?)"
  mc_sh "for b in $buckets; do mc du --json \"l/\$b\"; done" |
    sed -n 's/.*"prefix":"\([^"]*\)","size":\([0-9]*\),"objects":\([0-9]*\).*/\1 objetos=\3 bytes=\2/p'
}

cmd_count() {
  case ${1:-} in
    volume)
      docker volume inspect "$VOLUME" >/dev/null 2>&1 || die "volume $VOLUME não existe"
      count_dir "type=volume,source=$VOLUME" ;;
    hd)
      [ -d "$DIR/minio" ] || die "$DIR/minio não existe"
      count_dir "type=bind,source=$DIR/minio" ;;
    s3) count_s3 ;;
    *) die "use: count volume | count hd | count s3" ;;
  esac
}

minio_running() {
  [ -n "$($COMPOSE ps -q --status running minio 2>/dev/null)" ]
}

cmd_migrate() {
  check_mount
  [ -f "$SENTINEL" ] || die "sem o sentinela; rode init antes"
  docker volume inspect "$VOLUME" >/dev/null 2>&1 || die "volume $VOLUME não existe"
  ! minio_running || die "o minio está no ar; pare antes: docker compose stop edge imgproxy api minio"
  [ -z "$(ls -A "$DIR/minio")" ] || die "$DIR/minio não está vazia (migração já feita?); nada copiado"
  echo "==> Copiando $VOLUME → $DIR/minio (o volume é montado só leitura e fica intacto)..."
  docker run --rm --mount "type=volume,source=$VOLUME,target=/from,readonly" \
    --mount "type=bind,source=$DIR/minio,target=/to" "$ALPINE" \
    sh -c 'cp -a /from/. /to/ && chown -R 1000:1000 /to'
  cmd_compare
  echo "Próximo passo: docker compose up -d && ./scripts/data-setup.sh verify"
}

# Volume antigo × cópia no HD (offline): objetos e bytes em disco por bucket.
cmd_compare() {
  before=$(cmd_count volume)
  after=$(cmd_count hd)
  echo "--- volume $VOLUME"; echo "$before"
  echo "--- HD $DIR/minio"; echo "$after"
  echo "$before" | while read -r line; do
    echo "$after" | grep -qxF "$line" || die "diferença no bucket: $line"
  done
  ok "a cópia no HD tem os mesmos objetos e bytes do volume (SC-008)"
}

cmd_verify() {
  cmd_check
  docker volume inspect "$VOLUME" >/dev/null 2>&1 && ok "volume antigo $VOLUME continua lá" \
    || die "o volume $VOLUME sumiu"
  minio_running || die "o minio não está no ar"
  [ "$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' \
      "$($COMPOSE ps -q minio)")" = "$DIR/minio" ] && ok "o minio usa $DIR/minio" \
    || die "o minio não usa $DIR/minio"
  vol=$(cmd_count volume)
  s3=$(count_s3)
  echo "--- volume antigo (xl.meta)"; echo "$vol"
  echo "--- MinIO no HD (mc du)"; echo "$s3"
  # Logo depois da migração, a contagem bate; com envios novos, todo objeto do volume precisa
  # continuar no MinIO novo (chave por chave).
  echo "$vol" | while read -r b n _; do
    if echo "$s3" | grep -q "^$b $n "; then
      ok "bucket $b: mesma contagem (${n#objetos=}) no MinIO novo (SC-008)"
    else
      old_keys=$(docker run --rm --mount "type=volume,source=$VOLUME,target=/d,readonly" "$ALPINE" \
        sh -c "cd /d/$b && find . -name xl.meta | sed 's|^\./||; s|/xl.meta\$||'" | sort)
      tmp=$(mktemp)
      mc_sh "mc ls -r --json l/$b" | sed -n 's/.*"key":"\([^"]*\)".*/\1/p' | sort > "$tmp"
      missing=$(printf '%s\n' "$old_keys" | comm -23 - "$tmp")
      rm -f "$tmp"
      [ -z "$missing" ] || die "bucket $b: objetos do volume que faltam no MinIO novo: $missing"
      ok "bucket $b: os ${n#objetos=} objetos do volume estão no MinIO novo (mais os enviados depois)"
    fi
  done
  for b in sociman sociman-fonts sociman-videos; do
    echo "$s3" | grep -q "^$b " && ok "bucket $b" || die "falta o bucket $b (o minio-init rodou?)"
  done
  key=$(mc_sh 'mc ls -r --json l/sociman' | sed -n 's/.*"key":"\([^"]*\)".*/\1/p' | head -1)
  if [ -z "$key" ]; then
    echo "aviso: bucket sociman vazio; /img não conferido"
  else
    url=$($COMPOSE exec -T api python -c \
      "from sociman_api.imaging import image_urls; print(image_urls('$key')['thumb'])")
    code=$(curl -s -o /dev/null -w '%{http_code}' "$EDGE$url")
    [ "$code" = 200 ] && ok "/img de $key: 200" || die "/img de $key: $code ($EDGE$url)"
  fi
  du -sh "$DIR/minio"
  ok "verificação concluída"
}

case ${1:-} in
  check) cmd_check ;;
  init) cmd_init ;;
  count) shift; cmd_count "$@" ;;
  migrate) cmd_migrate ;;
  compare) cmd_compare ;;
  verify) cmd_verify ;;
  *) echo "uso: $0 check | init | count volume|hd|s3 | migrate | compare | verify" >&2; exit 2 ;;
esac
