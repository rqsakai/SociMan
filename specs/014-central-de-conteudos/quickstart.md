# Quickstart de validação: 014-central-de-conteudos

O contrato está em [contracts/http-api.md](contracts/http-api.md) e o modelo de dados em
[data-model.md](data-model.md). Faça um passo por vez, conferindo cada saída antes do próximo.

## Pré-requisitos
- Specs 004, 006 e 008 validadas: MinIO no HD com sentinela, `worker` e `agendador` no ar, chave
  da Anthropic configurada.
- Dados reais do dev: 43 cortes (36 em `revisao`, 7 `pronto`) em "A Taverna Nerd" e "Queridinhos",
  com as contas TikTok `@atavernanerd` e `@meusqueridinhos10`.
- Dois usuários: um **dono** e um **membro** (criado em `/app/usuarios`).

## 0. Backup e migração
```bash
# 1) backup do banco antes da migração (no HD, fora do git e fora do MinIO)
mkdir -p /media/sakai/BACKUP/tiktok/sociman/backups
docker compose exec -T postgres pg_dump -U sociman -Fc sociman > /media/sakai/BACKUP/tiktok/sociman/backups/pre-0009.dump
ls -lh /media/sakai/BACKUP/tiktok/sociman/backups/pre-0009.dump      # tamanho > 0
docker compose exec -T postgres pg_restore -l < /media/sakai/BACKUP/tiktok/sociman/backups/pre-0009.dump | grep -c "TABLE DATA"   # > 0 (dump legível)

# 2) contagem antes (anote os números)
docker compose exec -T postgres psql -U sociman sociman -c \
  "select estado, count(*) from postagens group by 1 order by 1;"
docker compose exec -T postgres psql -U sociman sociman -c "select count(*) from cortes;"

# 3) aplicar (o start.sh da API faz alembic upgrade head)
docker compose up -d --build api worker agendador
docker compose exec api uv run alembic current                       # 0009_central_conteudos (head)
```
Conferir depois:
```bash
docker compose exec -T postgres psql -U sociman sociman -c \
  "select count(*) from conteudos where origem='corte';"            # = total de cortes
docker compose exec -T postgres psql -U sociman sociman -c \
  "select count(*) from cortes c left join conteudos k on k.id=c.id where k.id is null;"   # 0
docker compose exec -T postgres psql -U sociman sociman -c \
  "select estado, modo, count(*), count(aprovado_em) from postagens group by 1,2 order by 1;"
```
- `rascunho` virou `pendente` (sem `aprovado_em`); `agendado` e `postado` mantiveram o número, com
  `aprovado_em` preenchido; todos com `modo = lembrete`.
- `select intervalo_min_minutos, count(*) from contas group by 1;` → todas com 30.
- `curl -s http://localhost:8180/api/health` → `{"status":"ok","db":"ok","redis":"ok"}`.
- Só depois de validar os passos 1 a 7 abaixo, apague o backup:
  `rm /media/sakai/BACKUP/tiktok/sociman/backups/pre-0009.dump` (se algo der errado antes, restaure
  com `docker compose exec -T postgres pg_restore --clean --if-exists -U sociman -d sociman <
  /media/sakai/BACKUP/tiktok/sociman/backups/pre-0009.dump`).

## 1. Central de conteúdos (US1, SC-001, SC-006)
Em `/app/conteudos`:
- a lista mostra os 43 conteúdos, dos mais recentes aos mais antigos, com miniatura, título,
  perfil, origem "Corte", duração e os chips por conta; os 36 em revisão aparecem como
  "Em revisão", e os sem destino como "Sem conta";
- filtre "A Taverna Nerd" + atalho **"Prontos sem agendamento"**: aparecem exatamente os prontos
  da Taverna sem destino agendado ou postado (compare com o calendário, coluna "Sem data");
- a URL tem os filtros (`?perfilId=…&atalho=prontos_sem_agendamento`). Copie, abra em outra aba:
  mesma lista. Volte no navegador: filtros anteriores;
- busque um trecho de título; combine com estado e período;
- "Carregar mais" traz a próxima página sem repetir linhas (DevTools → Network: `cursor=`);
- clique numa linha: detalhe com player, abas por conta e histórico.

## 2. Aprovação (US2)
Com o **membro**:
- num corte pronto da Taverna, adicione a conta TikTok e clique **"Pedir aprovação"** (nota
  opcional). Faça o mesmo para mais 2 cortes pela seleção em lote ("Pedir aprovação");
- o botão "Aprovar" não aparece para o membro; forçar pela API responde 403:
  ```bash
  # com o cookie do membro (copiado do DevTools para a variável; não cole em chat)
  curl -sk -o /dev/null -w '%{http_code}\n' -X POST https://localhost:8543/api/destinos/<id>/aprovar \
    -H 'content-type: application/json' -H "cookie: $COOKIE_MEMBRO" -d '{"version":2}'   # 403
  ```
Com o **dono**:
- o sino mostra 3 "Aprovação pedida"; o atalho "Aguardando aprovação" mostra 3;
- aprove 2 (um individual, um pelo lote) e **recuse** 1 com motivo. Sem motivo, o botão fica
  desabilitado e a API responde 400;
- o membro recebe "Aprovação respondida" para os 3; o recusado volta a "Pronto" com o motivo
  visível na aba da conta;
- tente aprovar um conteúdo **em revisão**: "Aplique a marca antes de aprovar" (409
  `conteudo_nao_pronto`);
- o histórico do destino mostra quem pediu, quem aprovou e quem recusou, com data.

## 3. Agendar com o modo certo (US3, SC-002)
Com o **dono**, num corte pronto **sem destino** (direto no clipe, `/app/cortes/<id>`):
- **Agendar** → conta TikTok `@atavernanerd`, amanhã 19:00, "Gerar com IA" (008), modo
  **Lembrete manual** → "Aprovar e agendar". Cronometre: menos de 1 min;
- no seletor de modo, os outros três aparecem desabilitados com o motivo:
  - "Criar rascunho no horário" e "Publicar no horário": "Aguardando a spec de integração (015)";
  - "Rascunho antes, publicar no horário": "O TikTok não permite publicar um rascunho pela API";
- o item aparece em Conteúdos (chip "Agendado · amanhã 19:00") e no calendário (ícone de lembrete);
- o histórico do destino tem duas versões: `aprovado` e `agendado`;
- agende o mesmo conteúdo para uma segunda conta (se houver) com outro horário: cada conta tem o
  seu (US3-6);
- **intervalo mínimo (Q3):** agende outro conteúdo para a mesma conta amanhã às 19:10. O diálogo
  avisa "Há outro post em @atavernanerd às 19:00; o intervalo mínimo é 30 min", com "Manter mesmo
  assim" e "Escolher outro horário" (a API respondeu 409 `intervalo_conflito`). Mantenha: o
  agendamento é gravado, e a versão do destino tem `intervaloIgnorado: true`;
- tente um horário no passado: 400 `planned_in_past`. Como **membro**, "Agendar" num pronto não
  aprovado mostra "Pedir aprovação" (a API responde 403 `aprovacao_necessaria`);
- reagende pelo calendário (arrastar) e cancele pela aba da conta: o histórico mostra as duas
  mudanças e o calendário atualiza.

### "Hora de postar", "a postar" e "atrasado" (FR-007)
- agende um destino para daqui a 2 min. No horário, o dono e o autor recebem "Hora de postar" no
  sino, com link para `/app/conteudos/<id>?conta=<conta>`, e o chip vira **"A postar"**;
- "Postado" com um link: o chip vira "Postado" e o link aparece;
- para ver "atrasado" sem esperar 24 h (só no dev):
  ```bash
  docker compose exec -T postgres psql -U sociman sociman -c \
    "update postagens set planned_at = now() - interval '25 hours', lembrado_em = now() where id = '<id>';"
  ```
  O chip vira "Atrasado", e o atalho "Atrasados" conta 1. O estado gravado continua `agendado`
  (`select estado from postagens where id='<id>'`).

## 4. Sequência (US4, SC-003)
Com o dono, em Conteúdos, selecione 7 conteúdos aprovados (ou prontos) da Taverna →
**"Agendar em sequência"**: conta TikTok, a partir de amanhã, horários `19:00`, modo Lembrete,
"Gerar textos com IA para os que não têm":
- a **prévia** mostra o intervalo mínimo da conta (30 min) e 7 dias seguidos, um por dia. Se o
  passo 3 deixou um agendamento amanhã às 19:00 (ou às 19:10), o primeiro dia aparece como **pulado
  (conflito)** e a sequência termina um dia depois;
- **intervalo por conta:** como dono, em `/app/perfis/<Taverna>` → aba Contas, mude o intervalo da
  conta TikTok para 0 e peça a prévia de novo: o horário das 19:00 continua pulado (mesmo minuto),
  mas um agendamento às 19:10 não bloqueia mais. Volte para 30. O histórico da conta mostra as duas
  mudanças. Como **membro**, o campo aparece só para leitura, e o `PATCH` com
  `intervaloMinMinutos` responde 403;
- em outra aba, agende outro item para um horário da prévia e só então confirme na primeira aba:
  a resposta é "A prévia mudou" com a prévia nova (409 `previa_desatualizada`);
- confirme a prévia nova: os 7 aparecem no calendário, um por dia; a barra de textos gera os
  títulos que faltavam (até 3 ao mesmo tempo). Cronometre os 10: menos de 2 min;
- selecione dois agendados → "Trocar horários": só os dois mudam.

## 5. Vídeo próprio (US5)
- Em Conteúdos → "Enviar vídeo próprio" → perfil "Queridinhos" → um MP4 vertical curto. Ao terminar,
  o item aparece com origem **"Vídeo próprio"**, situação "Pronto", miniatura e duração;
- confira no MinIO (console em `:9101`, só dev): `sociman-videos/conteudos/<id>/video.mp4`;
- edite o título, aprove para `@meusqueridinhos10` e agende em lembrete manual;
- filtre por origem "Vídeo próprio": só ele;
- um arquivo que não é vídeo (renomeie um `.txt` para `.mp4`) → 400 `invalid_video`; um vídeo
  horizontal é aceito com o aviso "não é vertical"; um vídeo com mais de 10 min → 400
  `invalid_video` com o motivo (os limites de 1 s e 2 GB são cobertos pelo teste automatizado).

## 6. Casos de borda
- **Arquivar** um conteúdo com agendamento: o diálogo avisa que os agendamentos serão cancelados;
  depois, o destino volta a "Aprovado" e o histórico tem `cancelado_por_arquivo`;
- **conta pausada** (mude o status da conta em `/app/perfis/<id>`): os agendamentos dela ficam
  "Atenção · Conta pausada", e nenhum "Hora de postar" sai para eles;
- **conflito de versão**: abra o mesmo destino em duas abas e reagende nas duas: a segunda recebe
  o aviso de sempre (409 `version_conflict`);
- **"o vídeo mudou desde a aprovação"**: só aparece se o vídeo final de um corte aprovado mudar
  (não há rota para refazer a marca de um corte pronto na 014; o teste automatizado cobre).

## 7. Guardas e verificação final (princípio I, VI, VII; SC-004, SC-005)
```bash
npm run test:api -- tests/unit/test_constitution_guards.py tests/integration/test_guardas_014.py -q
npm run test:api                                  # tudo verde
docker compose exec api uv run ruff check .       # sem erros
npm run gen:contract && npm run check:web         # contrato sem divergência, typecheck, build, csp, secrets
flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/conteudos.spec.ts e2e/cortes-openshorts.spec.ts e2e/assistente-ia.spec.ts
```
- os guardas provam: só `lembrete` disponível em toda rede e conta; modos automáticos recusados
  pela API e pelo banco; nenhum código atribui `rascunho_criado`, `publicado` ou `falhou`; o
  agendador só tem as quatro trilhas da 006; os lembretes não mudam estado;
- `test_escala_conteudos` mostra o p95 da lista com 500 conteúdos (< 200 ms);
- nenhum pedido sai do container para domínios de rede social (a 014 não tem cliente HTTP novo:
  `grep -rn "httpx" apps/api/src/sociman_api/conteudos apps/api/src/sociman_api/postagem` → nada).

## Resultado

### Migração no dev (T069, 2026-09-29)
- Backup antes: `/media/sakai/BACKUP/tiktok/sociman/backups/pre-0009.dump` (13,7 MB, 24 `TABLE DATA`).
- `docker compose restart api agendador worker`; `alembic current` = `0009_central_conteudos`.
- Antes → depois: cortes 64 → 64 (8 `revisao`, 56 `pronto`); conteúdos → 64, todos origem `corte`
  com `id = corte_id` (0 cortes sem conteúdo); postagens 0 → 0; contas 4 → 4, todas com
  `intervalo_min_minutos = 30`; `ia_chamadas` com `corte_id` 0 → 0.
- `entity_versions` 273 → 273, com o md5 dos ids (`eadc84b3…`) e o das linhas inteiras (`b2795708…`)
  idênticos antes e depois.
- `/api/health`: `{"status":"ok","db":"ok","redis":"ok","storage":"ok"}`; sem erros nos logs de
  api, worker e agendador.
