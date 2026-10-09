# Quickstart: 026-mercado-shop

Guia de validação. Os detalhes de rotas estão em `contracts/http-api.md`, o protocolo do coletor em
`contracts/coletor.md` e as tabelas em `data-model.md`. Tudo que toca a rede real é feito **com o dono**
(§2 em diante); §1 roda sem rede.

## §0. Pré-requisitos (uma vez)

- Constitution **4.4.0** aplicada (princípio IX). Conferir: `grep -n "^### IX" .specify/memory/constitution.md`.
- `.env` da raiz: `COLETA_HABILITADA=false` (padrão) e `MERCADO_HASH_PEPPER=<segredo gerado pelo dono, nunca
  impresso>`; `npm run check:secrets` passa.
- HD montado com o marcador (`./scripts/data-setup.sh check`); o bucket `sociman-mercado` é criado pela API na
  subida (como os outros).
- Migration aplicada: `docker compose exec api uv run alembic upgrade head` (conferir `0025_mercado_shop`).
- Depois de mudar o código da trilha: `docker compose restart agendador`.

## §1. Automático (sem rede real)

```bash
npm run test:api -- tests/unit/test_mercado_calculo.py tests/unit/test_mercado_cadencia.py \
  tests/unit/test_coleta_credenciais.py tests/integration/test_coleta_ingestao.py \
  tests/integration/test_mercado_fila.py tests/integration/test_mercado_leitura.py \
  tests/integration/test_migration_0025.py tests/unit/test_constitution_guards.py
cd apps/coletor && uv run pytest && cd ../..
npm run check:web && npm run test:e2e -- e2e/mercado.spec.ts
```

Esperado:
- o **coletor falso** (`tests/fakes/coletor_fake.py`) posta 10 dias de fotos de 3 produtos e a leitura devolve
  os cartões com vendas, GMV, crescimento e comissão por venda iguais aos do teste (SC-001); o reenvio do
  mesmo lote responde `repetido` (SC-004);
- `UPDATE`/`DELETE` nas tabelas só de inserção levantam erro; nenhuma tabela do lago tem `perfil_id`;
- ligar o interruptor sem aceite → 409 `risco_nao_aceito`; com `COLETA_HABILITADA=false` a fila vem vazia e
  `POST /api/coleta/coletas` → 503 `coleta_desligada` (SC-003);
- revezamento: 3 perfis com fila 3× o teto recebem cada um ao menos um terço (menos um) por nível (SC-010);
- no coletor: nenhuma ação fora de `CLIQUES_PERMITIDOS` (AST), poda de PII, ritmo dentro dos limites, log sem
  dado pessoal; o servidor HTML sintético faz `uma-vez --limite 3` devolver 3 resultados e a página de captcha
  sintética gera o evento e para (SC-002);
- e2e: cockpit, detalhe, aba Mercado do perfil e `/app/configuracoes/coleta` com o coletor falso do
  `openshorts-fake`.

## §2. Instalar o coletor e fazer a sonda (com o dono)

1. **Instalar** (host, fora do Docker):
   ```bash
   cd apps/coletor && uv sync && uv run sociman-coletor autoteste --sem-token
   ```
   O autoteste acha o Chrome (`google-chrome`, `google-chrome-stable` ou `chromium`; ou `chrome_bin` no
   config) e confere a sessão gráfica.
2. **Perfil do Chrome (X1):** `uv run sociman-coletor perfil-iniciar` abre o Chrome no perfil
   `~/.config/sociman-coletor/chrome-profile` (700). O dono faz o login na conta de afiliado e no Affiliate
   Center, fecha a janela. Nada é gravado pelo coletor.
3. **Aceite e token (X3, X4):** em `/app/configuracoes/coleta`, o dono lê o aviso, clica no aceite (grava
   `risco_aceito_em/por`), cria um cliente e copia o token **uma vez** para `~/.config/sociman-coletor/token`
   (`chmod 600`). `config.toml`: `api_url = "https://192.168.86.47:8543"`, `ca_cert =
   "<caminho da CA da casa>"` (ou `http://localhost:8180` sem CA, em dev).
4. **Sonda guiada (X6):** com `COLETA_HABILITADA=true` e o botão ligado, o dono cola **1 link de produto** na
   aba Mercado de um perfil e roda:
   ```bash
   uv run sociman-coletor uma-vez --limite 1
   ```
   Esperado: a tela mostra a rodada, 1 item `gravado`, a ficha, as imagens e a primeira foto; o bruto está
   no bucket `sociman-mercado`. O dono abre o bruto pela tela (link assinado) e **confere os nomes dos campos
   reais** do Affiliate Center brasileiro (comissão, criadores, vendas 7/30 d). Se algum campo não casou, o
   parser é ajustado e `uv run sociman-coletor reprocessar --desde <hoje>` preenche o que faltava sem recoletar.
5. Repetir com `--limite 3` incluindo 1 ranking de categoria (depois de escolher as categorias do perfil, X2).

**Depois da sonda, no servidor (X8, 2026-10-09):** o servidor não cita os endereços da rede em código
(guarda do princípio IX); as bases das URLs das tarefas que não são de produto (rankings, vitrine,
`categorias`, lojas sem URL própria, vídeos) vêm do `.env` da raiz: `MERCADO_URL_PUBLICA` e
`MERCADO_URL_AFFILIATE`, preenchidas com o que a sonda mostrou, seguidas de `docker compose up -d api
agendador`. Vazias, só as tarefas de produto (URL canônica do próprio lago) nascem na fila; a tela
"Coleta de mercado" continua funcionando. Os caminhos montados sobre essas bases
(`mercado/fontes/tiktok_shop.py`, `url_tarefa`) são o formato de referência: ajuste-os junto com os
parsers do coletor se a sonda mostrar outros.

## §3. Ligar de verdade (X5)

```bash
cp apps/coletor/systemd/sociman-coletor.service ~/.config/systemd/user/
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY
systemctl --user enable --now sociman-coletor
journalctl --user -u sociman-coletor -n 50 --no-pager
```

Conferir no 1º dia: `GET /api/coleta/estado` (ou a tela) mostra batimentos, páginas do dia subindo com
pausas de 5–40 s entre ações (cerca de 20–90 s por página), nenhuma rodada "abortada"; nos logs, só contagens e ids. No 2º dia, os cartões
saem de "coletando" e mostram vendas/dia; no 7º dia, "amostra pequena" some.

## §4. Parar, pausar e retomar

- Parar na hora: `touch ~/.config/sociman-coletor/PARAR` (ou `systemctl --user stop sociman-coletor`).
- Pausar N horas ou desligar: `/app/configuracoes/coleta`. Desligar no servidor: `COLETA_HABILITADA=false` +
  `docker compose up -d api agendador`.
- Captcha ou login perdido: o sino avisa; o dono resolve na janela do Chrome que ficou aberta e clica
  **"Continuar"** na tela; o coletor retoma 60 min depois. Sem clique em 2 h, a rodada é encerrada com o motivo "pausa vencida"
  e a próxima janela recomeça.

## §5. Ponte com a 012 (depois do merge da 012)

No detalhe de um produto de mercado com ficha e imagens, "Adotar no catálogo" → escolher o perfil → o produto
da 012 aparece com as imagens copiadas e o vínculo de origem; adotar de novo → aviso de duplicidade com o link
do existente (SC-009).
