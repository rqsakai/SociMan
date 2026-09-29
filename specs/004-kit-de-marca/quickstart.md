# Quickstart de validação: 004-kit-de-marca

O contrato está em [contracts/http-api.md](contracts/http-api.md) e o modelo de dados em
[data-model.md](data-model.md).

## Pré-requisitos
- Seção 0 feita (MinIO no HD, sentinela e verificação da migração).
- Stack em modo dev (`docker compose up -d --build`, porque a imagem da API passa a ter `ffmpeg`),
  com `api`, **`worker`**, `minio` (dados no HD) e `imgproxy` no ar.
- `docker compose exec api ffmpeg -version` e `docker compose logs worker --tail 5` (mostra
  "worker pronto, aguardando cortes").
- Migration `0003_kit_de_marca` aplicada (o `start.sh` faz `alembic upgrade head`; o worker só
  começa depois da API saudável).
- Os perfis "Queridinhos" (conta TikTok `@meusqueridinhos10`, com logo) e "A Taverna Nerd" da 003.
- Vídeos de teste gerados na hora, no HD (nada de mídia no git nem no NVMe):
  ```bash
  W=/media/sakai/BACKUP/tiktok/sociman/work/quickstart && mkdir -p $W
  ffmpeg -f lavfi -i testsrc2=size=1080x1920:rate=30:duration=30 -f lavfi -i sine=d=30 \
    -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest $W/corte30.mp4
  ffmpeg -f lavfi -i testsrc2=size=1080x1920:rate=30:duration=60 -f lavfi -i sine=d=60 \
    -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest $W/corte60.mp4
  ```

## 0. Infra: MinIO no HD (R12, FR-018, SC-008), antes de tudo
Um passo por vez, conferindo cada saída:
```bash
findmnt -no SOURCE,FSTYPE -T /media/sakai/BACKUP     # /dev/sda1 ext4 (se mostrar a raiz, PARE)
./scripts/hd-setup.sh check                          # HD montado, dono 1000:1000, espaço livre
./scripts/hd-setup.sh init                           # cria minio/, work/tmp, work/cortes e .sociman-volume
./scripts/hd-setup.sh count                          # objetos e bytes do bucket sociman (volume antigo)
./scripts/hd-setup.sh migrate                        # para edge/imgproxy/api/minio, copia minio-data → HD, chown 1000
docker compose up -d                                 # compose novo: minio no bind do HD
./scripts/hd-setup.sh verify                         # compara a contagem, confere os 3 buckets e o sentinela
```
Verificar:
- a contagem e os bytes do bucket `sociman` são iguais antes e depois (SC-008);
- `docker volume ls | grep minio-data` ainda mostra o volume antigo (não é apagado);
- o logo de "Queridinhos" abre: pegue a URL `/img/...` em `GET /api/perfis` e rode
  `curl -sI http://localhost:8180<url>` (200); a lista de perfis mostra as miniaturas;
- `du -sh /media/sakai/BACKUP/tiktok/sociman/minio` tem o tamanho do volume antigo, e
  `docker compose exec api sh -c 'echo $TMPDIR'` mostra `/hd/work/tmp`;
- `npm run test:api` e `npm run test:e2e` verdes.

Remover o volume `minio-data` fica para depois, à mão, pelo dono.

## 1. Kit (US1)
Em "Queridinhos", aba Marca:
- sem kit salvo, aparece o padrão (legenda Anton branca, contorno preto, karaokê amarelo, embaixo;
  gancho branco com texto preto no topo) e a prévia já mostra os quatro itens;
- na paleta, adicione "Rosa Queridinhos" `#FF5FA2`: ela aparece nos seletores de cor;
- legenda: destaque = Rosa Queridinhos; gancho: fundo Rosa, texto branco; marca d'água: texto,
  conta `@meusqueridinhos10`, canto inferior direito. A prévia muda a cada campo;
- salve: vira a v1. Tamanho de legenda 300, cor `#GG0000` ou uma cor da paleta removida sendo
  usada são recusados, indicando o campo;
- aba Histórico do kit: a v2 mostra "legenda" e "gancho" como seções alteradas, com antes e
  depois. Como dono, reverter para a v1 volta o kit; como membro, o botão não aparece e a API
  responde 403;
- editar o kit em duas abas: a segunda recebe "Este kit foi alterado por outra pessoa;
  recarregue".

## 2. Fontes (US2)
Em "A Taverna Nerd", aba Fontes:
- envie um TTF (ex.: `apps/api/src/sociman_api/marca/fonts/Anton-Regular.ttf` renomeado para
  "Pergaminho"): aparece com a amostra "Os achadinhos que você queria" na própria fonte;
- um `.ttf` que é texto e um arquivo de 11 MB são recusados com a razão;
- escolha "Pergaminho" no gancho e salve: a prévia usa a fonte. Arquivar "Pergaminho" agora é
  recusado ("Esta fonte é usada no gancho; troque antes de arquivar"). Troque a fonte do gancho,
  salve e arquive: funciona, e a fonte some dos seletores;
- `ls /media/sakai/BACKUP/tiktok/sociman/minio/sociman-fonts/perfis/<id>/` (ou o console 9101):
  o arquivo continua lá.

## 3. Exportação (US3)
- "Exportar JSON" em "Queridinhos" baixa `kit-queridinhos-v<N>.json`.
- `openshorts.subtitle` tem só campos e valores do `SubtitleRequest`. `openshorts.hook.enabled` é
  `false` (só o SociMan queima o gancho), e `openshorts.hook.style` é `red`, como referência, com a
  nota de aproximação do fundo rosa.
- **Produtor:** gerar os cortes no OpenShorts **sem o gancho automático**; senão, o corte sai com
  dois ganchos depois da marca do SociMan.
- Cada URL de `assets` tem `expiresAt: null` e abre com `curl -sI http://localhost:8180<url>`
  (200), também depois de dias; a mesma URL com um caractere trocado dá 403.
- Opcional, com o OpenShorts no ar: mandar `openshorts.subtitle` num `POST /api/subtitle` de um
  job de teste e ver a legenda rosa.

## 4. Aplicar a marca (US4)
Em "Queridinhos", aba Cortes:
1. Envie `$W/corte30.mp4` com o gancho "3 achadinhos que salvaram minha cozinha": a barra de
   upload chega a 100%, e o corte aparece como "Na fila" e depois "Processando 37%".
2. Envie `$W/corte60.mp4` logo em seguida: fica "Na fila, posição 1" até o primeiro terminar.
3. O primeiro fica "Pronto". Abra: o player toca no navegador e dá para pular para o meio (Range).
   O gancho rosa aparece nos primeiros 5 s, o @ fica no canto o vídeo todo, e o card final (se
   ligado) cobre os últimos segundos; a duração é a mesma do original (`ffprobe`). O áudio está lá. "Baixar" salva o MP4, e "Baixar original"
   salva o arquivo enviado, igual ao original (`sha256sum`).
4. **SC-003:** o `processingMs` do corte de 60 s é menor que 120000.
5. Recusas sem entrar na fila: um `.mp4` que é texto, um vídeo de 181 s, um gancho de 4 linhas.
6. **Reinício:** com um corte em "Processando", `docker compose restart worker`. Em até 2 min ele
   volta para "Na fila" e termina "Pronto".
7. **Falha:** envie um MP4 truncado (`head -c 200000 $W/corte30.mp4 > $W/quebrado.mp4`). Se o
   ffprobe aceitar, o worker marca "Falhou: o vídeo está corrompido ou não pôde ser lido", e
   "Tentar de novo" o põe na fila outra vez.
8. Kit alterado com um corte na fila: o corte sai com a versão do kit do envio (a lista mostra
   "kit v2").
9. Nada foi publicado: não existe rota, credencial nem job de rede social (teste-guarda).

## 5. HD de dados (FR-018, SC-007)
1. `curl -s http://localhost:8180/api/health`: `storage: ok`. A aba Cortes mostra o uso dos
   cortes e o espaço livre do HD (~2,1 TB).
2. Sem o sentinela: `mv .sociman-volume .sociman-volume.off` na pasta do HD. Um envio de corte,
   de fonte ou de logo recebe 503 "O HD de dados não está disponível", o health mostra
   `storage: unavailable`, e a aba Cortes avisa e desabilita o envio. `docker compose restart
   minio`: o `minio` sai com a mensagem do sentinela no log. Nada foi gravado no NVMe (`df` da
   raiz antes e depois). Volte o sentinela e suba o `minio` de novo.
3. Pasta ausente (simula o HD desmontado): com `SOCIMAN_HD_DIR=/nao-existe docker compose up -d
   minio`, o container não sobe (o Docker não cria a pasta: `create_host_path: false`). Volte ao
   `.env` normal.
4. Pouco espaço: com `HD_MIN_FREE_GB=999999` no `.env` e `docker compose up -d api worker`, um
   envio recebe 507 "Pouco espaço no HD de dados". Volte o valor para 20.
5. Temporários no HD: durante um processamento, `ls /media/sakai/BACKUP/tiktok/sociman/work/cortes/`
   mostra a pasta do corte; depois de "Pronto", ela sumiu. `docker compose exec worker du -sh /tmp`
   continua pequeno.

## 6. Testes automatizados
```bash
npm run test:api                           # stack efêmera; inclui ffmpeg real e amostragem de quadros
docker compose exec api uv run ruff check .
npm run check:web                          # contrato regenerado, typecheck, build, CSP (inalterada)
npm run test:e2e                           # inclui e2e/marca.spec.ts (precisa do worker)
```
Obrigatórios:
- SC-002: `openshorts.subtitle` dentro das faixas e enums do gerador, para kits gerados;
- SC-004: gancho, marca d'água e card nos tempos e posições, por amostragem de quadros;
- toda mutação de kit, fonte e corte gera versão com autor (princípio VII);
- nenhuma rota DELETE no OpenAPI (SC-005); `storage.py` sem delete;
- 403 para membro na reversão do kit; 409 em edição concorrente;
- a fila sobrevive a um worker morto (heartbeat);
- SC-007: sem o sentinela, envio recusado e nenhum objeto gravado; abaixo do mínimo, 507;
- SC-008: migração com contagem igual e imagens da 003 abrindo (seção 0);
- a exportação traz `openshorts.hook.enabled = false` e links de fonte sem validade.

## 7. Medir
SC-001 (kit a partir do padrão em menos de 5 min, pela interface), SC-003 (60 s em menos de
2 min) e SC-006 (os dois perfis reais expressos no kit, pela seção "Estilo visual" de
`../shared/perfis/*/perfil.md`):
- **Queridinhos:** legenda bold branca com contorno preto, embaixo, efeito pop; marca d'água
  texto `@meusqueridinhos10`; CTA "Segue pra mais achadinhos"; bordão "Olha esse achadinho...".
- **A Taverna Nerd:** paleta nogueira/âmbar/pergaminho/cinza-ferro; legenda com fundo pergaminho
  (`opacidade_fundo > 0`); marca d'água texto `@atavernanerd`, depois imagem `watermark.png` com
  transparência; CTA "Segue a taverna".
