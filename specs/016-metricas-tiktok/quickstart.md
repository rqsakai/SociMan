# Quickstart: 016-metricas-tiktok

Este é o roteiro de verificação depois do `/speckit-implement`. Siga **um passo por vez**:
mostre o comando, explique em uma linha, rode, leia a saída e só então siga.
- os §1 e §2 são automáticos e usam a TikTok **falsa**;
- os §3 a §5 são com o dono e usam a TikTok **real** (app no sandbox, as 2 contas reais).

Nenhum agente chama a TikTok real por conta própria.

**Regra de segredos:** nunca rode `cat .env` nem imprima valores. Para conferir se uma variável
existe, use só o nome: `grep -oE '^(TIKTOK_SCOPES|METRICAS_COLETA_HABILITADA|AGENDADOR_METRICAS_S)=' .env`.
O `TIKTOK_SCOPES` não é segredo, e o §0.3 lê o conteúdo dele.

## §0. Antes de tudo
1. **Backup do banco** (a 0011 cria tabelas e mexe em `notificacao_tipo`), no HD, como na 015:
   `mkdir -p /media/sakai/BACKUP/tiktok/sociman/backups && docker compose exec -T postgres pg_dump -U sociman -Fc sociman > /media/sakai/BACKUP/tiktok/sociman/backups/pre-0011.dump`
   (fora do repositório; sem o sentinela `.sociman-volume` no HD, use o scratchpad da sessão).
   **Verificar:** tamanho > 0 e `docker compose exec -T postgres pg_restore -l < /media/sakai/BACKUP/tiktok/sociman/backups/pre-0011.dump | grep -c "TABLE DATA"` > 0.
2. **Portal da TikTok** (developers.tiktok.com, app do dono, **Sandbox**; passo do **dono**):
   confira que `user.info.stats` e `video.list` estão ligados (a spec diz que já estão).
   **Registrar:** os dois escopos aparecem no sandbox? `sim / não`.
3. **Escopos pedidos no login.** Um `TIKTOK_SCOPES` no `.env` sobrescreve o padrão novo:
   `grep -E '^TIKTOK_SCOPES=' .env || echo "sem TIKTOK_SCOPES no .env (vale o padrão)"`.
   Se a linha existir sem `user.info.stats,video.list`, acrescente os dois na mesma linha (só o
   dono edita o `.env`).
   **Verificar:** a linha não existe, ou contém os dois escopos.
4. Suba a stack: `docker compose up -d --build api agendador edge`.
   **Verificar:**
   - `curl -s http://localhost:8180/api/health` → `{"status":"ok",...}`;
   - `docker compose logs agendador | grep -i "trilha metricas"` → "trilha metricas ativa",
     ou ociosa com um motivo que você reconhece;
   - `docker compose exec api uv run alembic current` → `0011_metricas_tiktok (head)`.

## §1. Testes automáticos
1. `npm run test:api` → tudo verde, inclusive:
   - `test_migration_0011` e `test_coleta_metricas`;
   - `test_vinculo` e `test_anonimizacao`;
   - `test_guardas_016` e `unit/test_constitution_guards.py`.
2. `docker compose exec api uv run ruff check .` → sem erros.
3. `npm run gen:contract && npm run check:web` → contrato igual, typecheck, build, bundle, CSP
   e segredos ok.
4. `npm run test:e2e -- e2e/metricas.spec.ts` e depois `npm run test:e2e` (a 015 continua
   verde).

## §2. Guardas do princípio I (leitura, com o fake)
1. `npm run test:api -- -k "guardas_016 or constitution_guards"` → verde.
2. **Registrar:** o teste `test_coleta_so_le_com_interruptor_desligado` passou (a coleta com
   `PUBLICACAO_HABILITADA=false` e o botão desligado só chamou `token`, `user_info`,
   `video_list`, `video_query` e `status`).

## §3. Reconectar as 2 contas e conferir a 1ª foto (com o dono, TikTok real)
1. Abra `https://192.168.86.47:8543/app/perfis` → perfil da Taverna → aba **Contas**.
   **Verificar:** a conta @atavernanerd mostra "Reconectar para liberar métricas", e nenhuma
   coleta foi tentada:
   `docker compose exec -T postgres psql -U sociman -d sociman -tAc "select count(*) from metricas_series"`
   → `0`.
2. Clique em **Reconectar para liberar métricas** e autorize na TikTok, marcando todas as
   permissões.
   **Verificar:**
   - a conta volta "Conectada", com "Coletando métricas";
   - os escopos incluem `user.info.stats` e `video.list`
     (`curl` autenticado não é preciso: a tela mostra a lista).

   **Registrar:** a TikTok pediu só os escopos novos ou todos de novo? Houve erro?
3. Espere até 2 min (uma volta) e confira a 1ª foto e a varredura, sem imprimir dados da conta
   além de contagens:
   ```bash
   docker compose exec -T postgres psql -U sociman -d sociman -c "
   select s.id, (select count(*) from metricas_conta_fotos f where f.serie_id=s.id) fotos_conta,
          (select count(*) from metricas_videos v where v.serie_id=s.id) videos,
          s.varredura_concluida_em is not null varredura_ok, s.ultimo_erro_codigo
   from metricas_series s where s.anonimizada_em is null;"
   ```
   **Verificar** (SC-001): `fotos_conta ≥ 1`, `videos` perto do número de vídeos públicos da
   conta no app, `varredura_ok = t` e sem erro.
4. **Latência do `view_count`** (research R19). Use um vídeo publicado nas últimas horas, ou
   publique um no §4 e volte aqui. Depois de 6 h:
   ```bash
   docker compose exec -T postgres psql -U sociman -d sociman -c "
   select round(f.idade_s/3600.0,1) idade_h, f.views, f.likes, f.coletado_em
   from metricas_video_fotos f join metricas_videos v on v.id=f.video_id
   where v.id = '<video_id da tela /app/metricas>' order by f.idade_s;"
   ```
   **Registrar:**
   - as views mudam de hora em hora?
   - quantas fotos seguidas repetiram o número enquanto o app mostrava mais?

   O resultado vai para `docs/pesquisa/metricas-tiktok.md` §1.4 e decide se a faixa de 48 h
   continua de hora em hora.
5. Repita os passos 1 a 3 com @meusqueridinhos10.
6. **Membro:** entre como membro e abra a mesma conta.
   **Verificar:** vê "Coletando métricas", sem os botões de reconectar e desconectar (US1,
   cenário 3).

## §4. Vínculo de um rascunho publicado (com o dono)
Pré-requisito: um destino em `criar_rascunho` que chegou como rascunho (spec 015, quickstart
§3), com a publicação ligada nos dois níveis.
1. Com o rascunho entregue, abra o destino.
   **Verificar:** a seção "Desempenho" mostra "Procurando o post" (estado `buscando`).
2. No app da TikTok, finalize o rascunho em **público**. Cole a legenda do "Copiar textos".
   **Registrar:** a hora em que publicou.
3. Espere até 30 min.
   **Verificar** (SC-003):
   - o destino virou **Publicado**, com o link do post e o método "pelo envio" (nível 1) ou
     "pela lista" (nível 2);
   - a curva começou a aparecer;
   - o histórico do destino mostra "vínculo feito".

   **Registrar:**
   - quanto tempo levou;
   - qual nível ligou;
   - se o `status/fetch` devolveu o id (R9, [testar]). Confira sem imprimir o id:
     ```bash
     docker compose exec -T postgres psql -U sociman -d sociman -c "
     select fim, consultas, post_id is not null tem_post_id from metricas_buscas_post
     order by entregue_em desc limit 3;"
     ```
4. **Link errado e desfazer:** num destino de lembrete ainda **não** marcado como postado (aprovado
   ou agendado), use "Ligar a um post" e cole o link de um vídeo da **outra** conta.
   **Verificar:** a recusa "O link é de @…; este destino é de @…".

   Depois cole o link certo.
   **Verificar:** ligou, e o destino virou **Postado**. Clique em **Desfazer vínculo**.
   **Verificar:**
   - o vídeo volta a "sem vínculo" e aparece como "fora do SociMan" no ranking;
   - o histórico registra a troca.
5. **Registrar** se a TikTok devolveu o vídeo de outra conta no `video/query` ou só não o
   devolveu (R11). A mensagem na tela é a mesma nos dois casos.
6. **Lembrete ligado sozinho** (Q3 = A). Escolha um destino de lembrete aprovado, poste à mão no
   app (público, com a legenda do "Copiar textos") e, **até 1 h depois**, clique em **Marcar como
   postado** sem colar o link.
   **Verificar:**
   - antes do clique, a seção "Desempenho" já lista o post como candidato (depois da próxima
     descoberta, até 1 h);
   - depois do clique, em até 1 h (a próxima 1ª página do `video/list`), o destino aparece
     ligado "pela lista", sem ação sua, e continua **Postado**.

   **Registrar:** quanto tempo levou e se houve mais de um candidato.

## §5. Depois de uma semana de coleta
1. `/app/metricas` → Ranking → perfil Taverna → ordenar por "views 7 dias".
   **Verificar** (SC-004): o top 5 aparece em menos de 30 s de uso; clicar no 1º abre a curva
   com os marcos 1 h/24 h/7 d preenchidos e 30 d como "ainda não".
2. **Cadência no horário** (SC-002), na faixa horária (48 alvos por vídeo), sobre os vídeos
   publicados nos últimos 7 dias que já passaram de 49 h. O denominador são os **alvos
   vencidos**, e não as fotos tiradas (um alvo pulado conta como falha):
   ```bash
   docker compose exec -T postgres psql -U sociman -d sociman -c "
   with v as (select id from metricas_videos where anonimizado_em is null
              and publicado_em between now() - interval '7 days' and now() - interval '49 hours')
   select count(*) filter (where f.idade_s <= f.alvo_idade_min*60 + 900)::float
          / nullif(48 * (select count(*) from v), 0) no_prazo
   from metricas_video_fotos f join v on v.id = f.video_id
   where f.alvo_idade_min between 60 and 2880 and f.alvo_idade_min % 60 = 0;"
   ```
   **Verificar:** `no_prazo ≥ 0.95`.
3. **Exportar** (dono): `/app/metricas` → Exportar → Taverna, último mês, CSV.
   **Verificar** (SC-005):
   - o download leva menos de 1 min;
   - o ZIP abre, e `fotos_videos.csv` abre na planilha com acentos certos e uma linha por foto;
   - `videos.csv` tem as colunas do SociMan preenchidas nos vídeos ligados e `origem = fora`
     nos outros;
   - `dicionario.csv` explica cada coluna.
4. **Só inserção** (SC-006), no banco de dev e em transação desfeita:
   ```bash
   docker compose exec -T postgres psql -U sociman -d sociman -c "
   begin; update metricas_video_fotos set views = 0 where id = (select min(id) from metricas_video_fotos); rollback;"
   ```
   **Verificar:** erro "metricas: fotos são só de inserção".

## §6. Anonimização (opcional; só se o dono quiser testar numa conta de teste)
Desconectar anonimiza as métricas, **sem volta**. Não faça isso com @atavernanerd nem com
@meusqueridinhos10 só para testar: o e2e cobre esse caminho. Se o dono decidir desconectar uma
conta de verdade, confira na tela:
- o aviso com o número de vídeos e fotos;
- a confirmação;
- depois, no ranking com "incluir anônimas", a série aparece como "Conta anônima N", sem links.

## §7. Encerramento
1. `CLAUDE.md`: seção "Métricas (desde a spec 016)", com trilha, `METRICAS_COLETA_HABILITADA`,
   só inserção, anonimização ao desconectar e o reconectar para ampliar escopos.
2. `docs/visao.md`: marcar a 016 e registrar o resultado dos §3.4, §4.3 e §4.5.
3. `docs/pesquisa/metricas-tiktok.md`: trocar os **[não confirmado]** medidos por
   **[confirmado em 2026-MM-DD]**.
