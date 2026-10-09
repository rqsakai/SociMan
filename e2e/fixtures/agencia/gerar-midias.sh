#!/usr/bin/env bash
# Regera as mídias sintéticas da pasta do e2e da 013 (imagens e 2 MP4 de 2 s). Só ffmpeg.
set -euo pipefail
cd "$(dirname "$0")"
ff() { ffmpeg -hide_banner -nostdin -y -loglevel error "$@"; }
T=shared/perfis/taverna-teste/assets
# Logo opaco (256 px, mínimo do logo é 200) e sticker com transparência.
ff -f lavfi -i "testsrc=s=256x256:d=1" -frames:v 1 "$T/logo.png"
ff -f lavfi -i "color=c=red@0.0:s=256x256,format=rgba,drawbox=x=64:y=64:w=128:h=128:color=yellow@1:t=fill" \
   -frames:v 1 "$T/stickers/sticker-dado.png"
ff -f lavfi -i "color=c=gray:s=256x256" -frames:v 1 "$T/marca-nao-usar-ainda.png"
ff -f lavfi -i "color=c=orange:s=512x512" -frames:v 1 -q:v 5 shared/shop/persona/achadinha-cozinha.jpg
C=clipes/taverna-teste/2026-10-01
for i in 1 2; do
  ff -f lavfi -i "testsrc=s=360x640:d=2:r=24" -f lavfi -i "sine=frequency=$((300 + 100 * i)):duration=2" \
     -c:v libx264 -preset veryfast -crf 35 -pix_fmt yuv420p -c:a aac -b:a 32k -shortest \
     -metadata comment="e2e-013-$i" "$C/taverna-teste-20261001-$i.mp4"
done
