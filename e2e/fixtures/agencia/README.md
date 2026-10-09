# Pasta sintética da agência (e2e da spec 013)

Montada **só leitura** na stack e2e (`/agencia/shared` e `/agencia/clipes`). Tudo aqui é inventado:
nada foi copiado da pasta real da agência. Os canais citados nos `fontes.md` são os do YouTube falso
(`e2e/fakes/server.py`: `@canalimportacao` e `@parceiroimportacao`, que nenhum outro e2e usa).

Regerar as mídias (imagens e os 2 MP4 de 2 s) com `./gerar-midias.sh` (precisa de `ffmpeg`).
Este README fica fora das duas raízes montadas.
