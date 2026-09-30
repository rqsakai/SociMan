# Pesquisa (Phase 0): 016-metricas-tiktok

Base:
- [spec.md](spec.md) e a constitution 4.0.0 (princípios I e VII);
- `docs/pesquisa/metricas-tiktok.md`, chamada aqui de **pesquisa**;
- o plano e o código da 015 (`specs/015-tiktok-rascunho/`, `apps/api/src/sociman_api/publicacao/`),
  chamados de **015**.

Nenhuma API da TikTok foi chamada. O que depende da TikTok real está marcado **[testar]** e
entra no [quickstart](quickstart.md).

Nomes usados aqui:
- **série**: as métricas de uma conta do SociMan enquanto ela está conectada (tabela
  `metricas_series`); anonimizar encerra a série, e reconectar começa outra;
- **vídeo**: um post público da conta na TikTok (`metricas_videos`);
- **foto**: um registro dos contadores num momento (`metricas_video_fotos`,
  `metricas_conta_fotos`), só de inserção;
- **vínculo**: a ligação vídeo ↔ destino do SociMan;
- **leitor**: o código da rede que só lê (`publicacao/tiktok/leitor.py`).

---

## R1. Escopos no login e conexão sem escopos (FR-001, US1)

- **Decisão:**
  - o padrão de `TIKTOK_SCOPES` passa a `user.info.basic,user.info.profile,video.upload,
    video.publish,user.info.stats,video.list`;
  - os escopos de métricas são **opcionais** para a conexão: `ESCOPO_OBRIGATORIO` continua
    `video.upload`. Uma conexão sem eles publica normalmente e só não coleta;
  - `metricas_liberadas(conexao) = {"user.info.stats", "video.list"} ⊆ conexao.escopos`, uma
    função só, usada pela coleta, pelo `EstadoColeta` e pelo `iniciar`.
- **Reconectar para ampliar (mudança na 015):**
  - `iniciar` hoje responde 409 `ja_conectada` para qualquer conexão `conectada`. Passa a
    aceitar quando faltam os escopos de métricas. Continua 409 quando já estão todos, e passa a
    responder 409 `envio_em_andamento` se a conta tem um destino `enviando`;
  - no retorno, `_validar_e_gravar` aceita a conexão `conectada` com o **mesmo `open_id`**.
    Reusa a linha (como já faz com `precisa_reconectar`), grava `escopos` novos e troca a
    credencial sob `FOR UPDATE`. A versão leva `details.acao = "ampliada"`. `open_id` diferente
    continua `conta_diferente`;
  - se o dono desmarcar os escopos de métricas na tela da TikTok, a conexão fica como estava
    (com os escopos que vieram) e o `EstadoColeta` mostra "Faltam permissões:
    `user.info.stats`".
- **Detecção em tempo de uso:** `scope_not_authorized` (ou `access_token_invalid` só num
  endpoint de leitura) numa chamada da coleta **não** muda a conexão, porque a publicação pode
  continuar funcionando. Grava `sem_permissao_desde` na série, e a tela mostra "Reconectar para
  liberar métricas". A coleta daquela conta para até uma reconexão.
- **Por quê:** a pesquisa (§1.4) confirma que o token só carrega os escopos aprovados e que
  ampliar exige nova autorização. Mudar a conexão para `precisa_reconectar` por falta de escopo
  de métricas pararia os envios sem necessidade.
- **Alternativas:**
  - escopos de métricas obrigatórios: rejeitada, porque derrubaria as conexões atuais e
    misturaria publicação com métricas;
  - desconectar e conectar de novo: rejeitada, porque desconectar **anonimiza** (R13) e apaga a
    credencial;
  - segundo OAuth só para métricas: rejeitada, porque é o mesmo app e a mesma conta.
- **[testar]** se a TikTok aceita ampliar escopos numa autorização já concedida ou se refaz tudo
  (pesquisa §1.4: "não confirmado"). Os dois casos funcionam com este desenho.

## R2. Cliente de leitura e guardas do princípio I (FR-010, SC-006)

- **Decisão:**
  - no `cliente.py`, `LEITURA_016 = frozenset({("POST", "/v2/video/list/"), ("POST",
    "/v2/video/query/")})` e `ALLOWED = R21 | LEITURA_016`. O `GET /v2/user/info/` já estava; os
    campos de stats entram só no `fields`;
  - novo `publicacao/tiktok/leitor.py` com `LeitorTikTok` (o `LeitorRede` de
    `publicacao/executor.py`) e 4 métodos:
    | Método | Pedido | Devolve |
    |---|---|---|
    | `stats_conta(ctx)` | `GET /v2/user/info/?fields=open_id,follower_count,following_count,likes_count,video_count` | `StatsConta` |
    | `listar(ctx, cursor, max_count=20)` | `POST /v2/video/list/?fields=…` | `(list[VideoLido], cursor, has_more)` |
    | `consultar(ctx, ids)` (até 20) | `POST /v2/video/query/?fields=…` | `list[VideoLido]` (os que vieram) |
    | `post_publicado(ctx, publish_id)` | `POST /v2/post/publish/status/fetch/` | `PostId(id) \| Pendente(status) \| Falhou(codigo)` |
  - campos pedidos do vídeo: `id,create_time,share_url,video_description,title,duration,
    width,height,view_count,like_count,comment_count,share_count`. **Não** se pede
    `cover_image_url` (expira em 6 h) nem `embed_html`;
  - `VideoLido.id` é sempre `str`, porque o id da TikTok pode passar do inteiro seguro do JSON;
  - `registro.leitor_para(platform)` devolve o leitor ou None, e o `TikTokExecutor` ganha o
    atributo `leitor`.
- **Guardas** (plan, "Guardas" 1 a 3 e 6):
  - lista fechada;
  - imports de `metricas/`;
  - AST sem chamadas de envio no leitor nem em `metricas/`;
  - ciclo de integração com os dois níveis do interruptor desligados, em que o fake registra só
    `token`, `user_info`, `video_list`, `video_query` e `status`.
- **Por quê:** a exceção do guarda R16.1 é **por pasta**, e o cliente com `ALLOWED` é o ponto
  único de saída. Um cliente de leitura separado dividiria a lista fechada em duas e abriria uma
  segunda porta. O `status/fetch` é leitura, e já estava na lista.
- **Alternativas:**
  - pacote `metricas/tiktok/`: rejeitada, porque exigiria uma segunda exceção de pasta para
    `open.tiktokapis.com`;
  - `metricas/` chamando o cliente direto: rejeitada, porque quebra o guarda R16.2 (só o
    `registro` importa a rede).

## R3. Trilha `metricas` no agendador (FR-004)

- **Decisão:** `Trilha("metricas", AGENDADOR_METRICAS_S = 60, metricas.coleta.rodar,
  _metricas_ociosa)`.
- **Quando fica ociosa:**
  - `METRICAS_COLETA_HABILITADA=false` (padrão `true`);
  - o app da TikTok não configurado;
  - a chave dos tokens ausente.
- **Quando não fica ociosa:** **não** depende de `PUBLICACAO_HABILITADA` nem do botão "Envios
  automáticos", porque não envia nada. Também não depende do HD: grava só no Postgres.
- **Uma volta** (`rodar(db, client=None, agora=None)`), com uma sessão curta por conta e commit
  por passo:
  1. séries: cria a série das contas TikTok com conexão `conectada` e escopos (R1), sem série
     viva;
  2. para cada série ativa, sem `adiar_ate` no futuro e sem `sem_permissao_desde`:
     1. **descoberta** (R5), se `lista_proxima_em ≤ agora`;
     2. **fila de vídeos** (R4), para os vídeos com `proxima_coleta_em ≤ agora`, em lotes de 20;
     3. **foto da conta** (R6), se `conta_proxima_em ≤ agora`;
  3. **buscas de post** vencidas (R9) e a varredura dos lembretes marcados como postados nas
     últimas 25 h (R10, Q3 = A);
  4. `ultima_coleta_em` e o erro por série.
- **Erros por série**, isolados: uma conta com erro não atrasa a outra:
  | Erro | Efeito na série | Mensagem na tela |
  |---|---|---|
  | `ConexaoIndisponivel`/`SemResposta` | `ultimo_erro` e `adiar_ate = agora + 5 min` | "A TikTok não respondeu; tentando de novo às HH:MM" |
  | `rate_limit_exceeded` ou taxa local | `adiar_ate = agora + 60 s` | nenhuma, se durar menos de 15 min |
  | `scope_not_authorized` | `sem_permissao_desde` | "Reconectar para liberar métricas" |
  | `ConexaoPerdida` | nenhum (a conexão já vai para `precisa_reconectar` pela 015) | "Reconecte a conta" |
  | outro `RecusaRede` | `ultimo_erro` com o código; tenta na próxima volta | "A TikTok recusou (código X)" |
- **Autor:** `Actor(kind="system:metricas")` no histórico dos destinos (vínculo automático).
- **Por quê:**
  - o agendador já tem o lock, o isolamento por thread e o log de motivo ocioso;
  - 60 s de intervalo basta para a tolerância de 15 min (SC-002) e custa quase nada: a volta
    vazia é 1 consulta indexada.
- **Alternativas:**
  - usar a trilha `publicacao`: rejeitada, porque ela fica ociosa com
    `PUBLICACAO_HABILITADA=false`, e a coleta tem de rodar mesmo sem publicação;
  - serviço novo: rejeitada pelo princípio VIII;
  - cron por conta: rejeitada, porque o agendador já existe.

## R4. Cadência e agenda por idade (FR-003, SC-002)

- **Decisão:** a agenda de cada vídeo é **ancorada na idade** (`publicado_em` = `create_time`).
  As idades-alvo são geradas por uma função pura, `agenda.alvos()`:
  | Faixa de idade | Passo | Alvos (idade) | Fotos |
  |---|---|---|---|
  | até 48 h | 1 h | 1 h, 2 h … 48 h | 48 |
  | 2 a 30 dias | 1 dia | 3 d, 4 d … 30 d | 28 |
  | 30 a 90 dias | 7 dias | 37 d, 44 d … 86 d, 90 d | 9 |
  | 90 a 365 dias | 30 dias | 120 d, 150 d … 360 d, 365 d | 10 |
  | depois de 365 d | não há mais | `proxima_coleta_em = NULL` | 0 |

  Somando a foto da descoberta, são **cerca de 96 fotos por vídeo** (arredondado para 95 nas
  estimativas).
- **Próxima coleta:** `proxima_coleta_em = publicado_em + menor alvo > idade da última foto`.
  A fila é o índice parcial `ix_metricas_videos_fila (proxima_coleta_em) WHERE
  proxima_coleta_em IS NOT NULL`.
- **Tolerância e atraso:**
  - uma foto vale para o alvo `A` se for tirada entre `A` e `A + min(15 min, passo/4)`;
  - se a volta chega depois disso (agendador parado, TikTok fora), a foto é tirada **só para o
    alvo mais recente já vencido**. Os alvos pulados ficam sem foto: nada é inventado nem
    interpolado na gravação;
  - a foto sempre guarda `idade_s` real e `alvo_idade_min`.
- **SC-002** é medido por `fotos no prazo ÷ alvos vencidos` (consulta do quickstart §5).
- **Por quê:**
  - ancorar na idade põe fotos exatamente em 1 h, 24 h, 7 d e 30 d, que são os marcos da tela
    e os rótulos do ML (R15). A interpolação vira quase exata;
  - com poucos vídeos por conta, o lote de 20 do `video/query` junta os vídeos da mesma volta
    mesmo sem alinhar os horários.
- **Alternativas:**
  - janelas de relógio (todo vídeo às :00 e à meia-noite): rejeitada, porque juntaria melhor os
    pedidos, mas os marcos cairiam entre fotos e a precisão iria para a interpolação. Como o
    custo de pedidos é irrelevante (R18), a precisão vale mais;
  - fila no Redis: rejeitada, porque a fila precisa sobreviver, e a constitution diz que o
    Redis não é banco de registro.
- A cadência fica em **constantes de `agenda.py`**, e não em variável de ambiente. Se a medição
  do `view_count` (R19) mostrar que a hora não muda nada, o ajuste é uma linha, com teste.

## R5. Descobrir vídeos: `video/list` paginado × `video/query` por ids (FR-002)

- **Decisão:** os dois endpoints, cada um no seu papel:
  - **`video/list`** descobre vídeos:
    - a **1ª página** (20 mais novos) roda **a cada hora** por conta (`lista_proxima_em`);
    - a **varredura completa** roda na primeira vez da série: segue o `cursor` enquanto
      `has_more`, até 10 páginas por volta, e guarda `varredura_cursor` para continuar na
      volta seguinte. Termina com `varredura_concluida_em`;
    - a 1ª página também atualiza o metadado dos 20 mais novos (legenda, link, disponível);
  - **`video/query`** tira as fotos agendadas: ids da fila, 20 por chamada.
- **Vídeo novo** (id nunca visto na série):
  - cria `metricas_videos` com o metadado;
  - grava a **foto de descoberta** com os números que vieram na própria lista, com
    `alvo_idade_min = floor(idade_min)`, ou o alvo da agenda cuja tolerância contém essa idade
    (R4), para não gastar uma foto a mais na mesma janela. Não gasta outra chamada;
  - agenda o próximo alvo;
  - roda o casamento (R10).
- **Vídeo com mais de 1 ano na varredura:** entra com a foto de descoberta e
  `proxima_coleta_em = NULL`. É a única foto dele (open-questions Q2 = A, decisão do dono).
- **Vídeo que não volta no `video/query`:**
  - marca `disponivel = false` e `indisponivel_desde`;
  - continua na fila na mesma cadência, porque pode voltar a ser público;
  - reaparecer limpa a marca;
  - as fotos antigas ficam (US2, cenário 4).
- **Por quê:**
  - a `video/list` é o único jeito de achar posts feitos fora do SociMan e os rascunhos
    finalizados no app;
  - a `video/query` é o jeito recomendado pela própria doc para renovar vídeos conhecidos
    (pesquisa §1.2) e não precisa paginar até vídeos antigos;
  - com 2 contas, a descoberta horária custa 48 pedidos por dia.
- **Alternativas:**
  - só `video/list`, paginando tudo a cada hora: rejeitada, porque o custo cresce com o
    histórico da conta, e um vídeo de 300 dias seria lido 24 vezes por dia sem uso;
  - só `video/query`: rejeitada, porque não descobre vídeos novos.

## R6. Fotografar a conta (FR-002, FR-003)

- **Decisão:**
  - `user/info` com `follower_count`, `following_count`, `likes_count` e `video_count`;
  - a janela da foto é **horária** quando a série tem algum vídeo com menos de 48 h (`janela_em
    = hora cheia`) e **diária** nos outros casos (`janela_em = 00:00 de America/Sao_Paulo`,
    tirada na 1ª volta depois da meia-noite);
  - `UNIQUE (serie_id, janela_em)` + `ON CONFLICT DO NOTHING`;
  - `conta_proxima_em` é a próxima janela;
  - a 1ª foto sai na 1ª volta da série nova (SC-001).
- **Por quê:**
  - a janela de relógio aqui é natural (a spec pede "uma vez por dia"), e a hora cheia deixa o
    gráfico regular;
  - o `video_count` só conta vídeos públicos (pesquisa §1.1), e isso vai no dicionário.
- **Alternativa:** ancorar a foto da conta na publicação de cada vídeo. Rejeitada, porque o
  seguidor-na-publicação do dataset sai por interpolação (R16).

## R7. Idempotência e só inserção (FR-002, SC-006)

- **Decisão:**
  - **uma foto por vídeo por janela:** `UNIQUE (video_id, alvo_idade_min)`, e a gravação é
    `INSERT … ON CONFLICT DO NOTHING`. Uma volta repetida (queda depois do pedido e antes do
    commit, duas instâncias por engano) não duplica nada;
  - a conta usa `UNIQUE (serie_id, janela_em)`;
  - **só inserção no banco:** o trigger `metricas_so_insercao` (`BEFORE UPDATE OR DELETE … FOR
    EACH ROW`) levanta erro nas duas tabelas de fotos. O `TRUNCATE` do `tests/conftest.py` e do
    `reset-db` não dispara trigger de linha, então os testes e o e2e continuam limpando;
  - a ordem da volta é **pedido → INSERT das fotos + UPDATE da agenda do vídeo → commit**. Se a
    volta cai antes do commit, a próxima refaz o pedido; a TikTok não muda com leituras.
- **Por quê:** SC-006 pede 0 fotos sobrescritas ou apagadas "verificado por teste". O trigger
  vale até para SQL escrito à mão, e o teste de migração o confere.
- **Alternativas:**
  - `REVOKE UPDATE, DELETE` para o papel da aplicação: rejeitada, porque a aplicação e as
    migrations usam o mesmo usuário do Postgres;
  - `UNIQUE (video_id, coletado_em)`: rejeitada, porque não impede duas fotos da mesma janela
    em segundos diferentes.

## R8. Modelo de série temporal no Postgres e volume

- **Decisão:** duas tabelas estreitas de fotos, com `bigint identity` e só os contadores. O
  metadado mora no vídeo e na série. Índices:
  - `metricas_video_fotos`: `UNIQUE (video_id, alvo_idade_min)` e `ix (video_id, idade_s)`
    (curvas e marcos por `LATERAL`), mais `ix (coletado_em)` (exportação por período);
  - `metricas_conta_fotos`: `UNIQUE (serie_id, janela_em)`.
- **Volume estimado** (linha de foto: ~60 B de dados + ~24 B de cabeçalho; com os 3 índices,
  ~200 B por foto no total):
  | Cenário | Vídeos/ano | Fotos de vídeo/ano | Fotos de conta/ano | Espaço/ano | Pedidos/dia |
  |---|---|---|---|---|---|
  | **2 contas**, ~2 posts/dia cada | ~1.460 | ~139 mil | ~17,5 mil (horária quase sempre) | **~30 MB** | ~200 (list 48 + query ~100 + user/info 48 + status) |
  | **20 contas**, ~2 posts/dia cada | ~14.600 | ~1,39 milhão | ~175 mil | **~300 MB** | ~2.000 |

  Para comparar: o limite é 600 por minuto, ou seja, 864 mil por dia e por endpoint. O pico de
  20 contas usa menos de 0,3%.
- **Sem particionamento:** abaixo de dezenas de milhões de linhas, uma tabela com índice B-tree
  é mais simples e rápida o bastante. A revisão fica marcada para cerca de **20 milhões de
  fotos**, cerca de 14 anos com 20 contas. As alternativas seriam particionar por ano
  (`coletado_em`) ou usar BRIN.
- **Por quê:**
  - o Postgres fica no NVMe, e 300 MB/ano não pesa;
  - trocar de banco ou acrescentar TimescaleDB é emenda da constitution (stack fixa).
- **Alternativas:**
  - JSONB com a série inteira por vídeo: rejeitada, porque exigiria UPDATE (quebra o "só
    inserção") e porque cada nova foto regravaria o documento todo;
  - particionamento já: rejeitada pelo princípio VIII, sem volume que peça.

## R9. Vínculo nível 1: `status/fetch` estendido (FR-005, SC-003)

- **Decisão:** a tabela `metricas_buscas_post`, com uma linha por destino.
  - **Quem entra:** destinos `criar_rascunho` cuja última tentativa terminou `entregue` e que
    ainda não têm vínculo. A trilha `metricas` cria a busca na 1ª volta em que vê o destino, com
    `entregue_em = tentativa.concluida_em`;
  - **Agenda de consultas** (depois de `entregue_em`):
    | Período desde a entrega | Intervalo | Consultas |
    |---|---|---|
    | até 2 h | 10 min | 12 |
    | 2 a 24 h | 30 min | 44 |
    | 1 a 3 dias | 3 h | 16 |
    | 3 a 14 dias | 12 h | 22 |

    São cerca de 94 consultas por destino no pior caso, e todas usam a taxa `status` da 015,
    compartilhada com a trilha de publicação.
  - **Resultados:**
    - `PUBLISH_COMPLETE` com `publicaly_available_post_id` (a grafia da TikTok): guarda
      `post_id`, faz `video/query [post_id]` e vincula com `metodo = envio` (R12). Se o
      `video/query` não traz o vídeo (privado, moderação), a busca continua e tenta só o
      `video/query` a cada 12 h até o fim do prazo;
    - `SEND_TO_USER_INBOX` ou em processamento: continua;
    - `FAILED`: encerra (`fim = falhou`);
    - fim de 14 dias: encerra (`fim = prazo`), e o destino mostra "Não achamos o post: cole o
      link".
  - **O modo `publicar` (post direto da 015)** já termina com `destino.rede_post_id`. A coleta
    cria o vínculo `envio` quando descobre o vídeo com esse id, sem busca.
  - **Não muda a tentativa:** ela é final na 015 e continua imutável. O `post_id` fica na busca,
    e a busca aponta para a tentativa (`tentativa_id`), sem copiar o `publish_id`.
- **Por quê:**
  - a 015 encerra o `status/fetch` 2 h depois do upload (`STATUS_PRAZO`), e o dono pode
    finalizar o rascunho dias depois (pesquisa §5.2);
  - consultar com mais frequência no começo pega o caso comum (finalizar logo) dentro de 24 h
    (SC-003).
- **Alternativas:**
  - reabrir a tentativa: rejeitada, porque quebra o "linhas em fase final não mudam" e
    misturaria leitura com a máquina de envio;
  - webhook: rejeitada, porque exige endereço público (pesquisa §5.5).
- **[testar]:**
  - se o `status/fetch` responde dias depois;
  - se o `publicaly_available_post_id` é o mesmo `id` do `video.list` (pesquisa §5.1: "muito
    provável").

  Se falhar, o nível 2 cobre.

## R10. Vínculo nível 2: casamento pela lista (FR-005)

- **Decisão:** roda quando um vídeo novo é descoberto (R5), quando uma busca encerra sem id e
  na volta seguinte a um "Marcar como postado" de lembrete (Q3 = A, abaixo).
  - **Âncora do destino** (a data de referência para o casamento; open-questions Q3 = A):
    | Destino | Âncora | Janela de `V.publicado_em` |
    |---|---|---|
    | `criar_rascunho` com a última tentativa `entregue`, em `rascunho_criado` ou `postado` (o dono marcou à mão) | `entregue_em` (a da busca, R9) | `entregue_em − 5 min` a `entregue_em + 14 d` |
    | `lembrete` em `postado` (o dono clicou em "Marcar como postado") | `posted_at` (a hora do clique) | `posted_at − 24 h` a `posted_at + 1 h` |
    | `lembrete` em `aprovado`/`agendado` (antes do clique) | nenhuma: **nunca liga sozinho** | só gera a lista de candidatos para o dono escolher (R11) |
    | outros (`publicar`, `falhou`, arquivado) | nenhuma | `publicar` liga pelo `rede_post_id` (R9); `falhou` incerto só pelo nível 3 |
  - **Candidatos de um vídeo `V`** (conta de `V`, sem vínculo, `V.vinculo_automatico`
    verdadeiro): destinos da mesma conta, com âncora, sem vínculo e sem bloqueio, que cumprem
    as duas condições:
    - `V.publicado_em` dentro da janela da âncora;
    - `|V.duracao_s − duração do vídeo do conteúdo em s| ≤ 1` (a TikTok arredonda para inteiro).
      A duração do conteúdo vem do `duration_ms` do corte ou do vídeo próprio.
  - **Bloqueio do destino:** o destino tem no histórico um `details.acao = "vinculo_desfeito"`
    (R11). Vale para os dois tipos de âncora, sem coluna nova.
  - **Varredura depois do clique:** a trilha procura, a cada volta, os destinos de lembrete em
    `postado` com `posted_at` nas últimas 25 h, sem vínculo e sem bloqueio, e roda o casamento
    contra os vídeos sem vínculo já descobertos. O `posted_url` digitado no `marcar_postado` não
    é lido pela trilha (para ligar por link, o dono usa "Ligar a um post", R11).
  - **Legenda compatível:** as duas legendas são normalizadas (minúsculas, sem acento, sem
    `#tags`, sem emoji, sem pontuação, sem espaço repetido). Compara-se
    `L(V) = legenda da TikTok` com `L(D) = publicacao.legenda.legenda_tiktok(destino)`
    (descrição + hashtags, a mesma regra do "Copiar textos" da 015), pela
    **similaridade de Jaccard dos tokens**:
    - **compatível**: Jaccard ≥ 0,5, ou uma legenda contém a outra;
    - **neutra**: `L(V)` com menos de 3 tokens (o dono não colou a legenda);
    - **incompatível**: o resto.
  - **Regra de decisão (unicidade nos dois sentidos):** o vínculo automático só sai se `V` tem
    **exatamente um** destino candidato **não incompatível** **e** esse destino tem exatamente
    um vídeo candidato não incompatível entre os vídeos sem vínculo da conta dentro da janela da
    sua âncora. Com a legenda **neutra**, vale só se a duração bater e houver um candidato só
    nos dois sentidos. Os destinos de rascunho e os de lembrete já postados disputam o mesmo
    vídeo: a unicidade é contada sobre todos eles.
  - **Ambíguo** (2 ou mais em qualquer sentido): nada é ligado; o destino fica "a confirmar"
    (derivado, sem tabela) e sai 1 aviso `vinculo_a_confirmar` por destino.
  - `metodo = casamento`, autor `system:metricas`. Num lembrete `postado`, o estado não muda
    (R12); só o vínculo é gravado, com o histórico.
- **Por quê:**
  - a spec pede data, duração e legenda, e "ambiguidade nunca resolvida sozinha";
  - a unicidade nos dois sentidos evita ligar o vídeo A ao destino X quando o vídeo B também
    serviria a X (dois cortes do mesmo canal com a mesma duração);
  - Jaccard é simples, explicável e testável.
- **Alternativas:**
  - distância de edição: rejeitada, porque é sensível à ordem e às hashtags que o dono mexe;
  - capa por hash perceptual: rejeitada, porque a capa expira e exigiria baixar da CDN (fora
    da lista fechada);
  - lembrete (open-questions Q3): **B** (nunca sozinho) deixaria trabalho manual em todo post
    de lembrete; **C** (âncora no horário agendado ±6 h) erra quando o dono posta fora do
    horário. Escolhida a **A**: âncora no clique "postado".

## R11. Vínculo nível 3, escolha de candidato e desfazer (FR-005, FR-006)

- **Decisão:** `POST /api/destinos/{id}/vinculo` (**H**) aceita duas formas.
  - **`{videoId}` (escolher):** um vídeo da mesma série, sem vínculo, vindo da lista de
    candidatos ou de "vídeos sem vínculo da conta"; `metodo = escolha`.
  - **Candidatos de um lembrete antes do clique** (Q3 = A): o `GET .../vinculo` de um destino
    `lembrete` em `aprovado`/`agendado` lista os vídeos sem vínculo da conta publicados nos
    últimos 14 dias, com a duração a ±1 s e a legenda não incompatível, ordenados pela distância
    ao `planned_at` (ou ao `aprovado_em`, sem data). Não há aviso nem vínculo automático: a lista
    é só para o dono escolher em 1 clique, e a escolha marca o destino como `postado` (R12).
  - **`{link}` (colar):**
    - aceita `https://www.tiktok.com/@<handle>/video/<id>` (com ou sem query);
    - recusa com o motivo:
      | Link | Motivo na tela |
      |---|---|
      | encurtado (`vm.tiktok.com`, `vt.tiktok.com`) | "Abra o link e copie o endereço completo" (resolver o encurtado seria um pedido fora da lista fechada) |
      | `@handle` ≠ `conta.handle` | "O link é de @x; este destino é de @y" (US3, cenário 3) |
      | `video/query [id]` com o token da conta não devolve o vídeo | "Não achamos este post em @y (é de outra conta, privado ou foi apagado)" **[testar]** se o `video/query` recusa ids de outra conta ou só não os devolve (os dois casos dão a mesma mensagem) |
    - aceito → cria ou atualiza `metricas_videos` e liga com `metodo = link`.
  - **O vídeo já está ligado a outro destino:** 409 `video_ja_vinculado`, com o destino atual.
    O dono desfaz lá antes; não há troca silenciosa.
- **Desfazer:** `POST /api/destinos/{id}/vinculo/desfazer` (**H**).
  - `metricas_videos.destino_id`, `vinculo_metodo`, `vinculado_por` e `vinculado_em` = `NULL`
    (o `ck_metricas_videos_vinculo` exige os dois primeiros juntos) e `vinculo_automatico =
    false` no vídeo, para ele não voltar sozinho;
  - a busca do destino (se houver) é encerrada com `fim = desfeito`, e o destino não se liga
    mais automaticamente, só pela ação do dono. O bloqueio vem do `vinculo_desfeito` no
    histórico do destino (R10), e por isso vale também para o lembrete, que não tem busca;
  - estado: `publicado → rascunho_criado` se foi o vínculo que o moveu (R12). Um lembrete
    continua `postado` (o `postado` é um fato humano e não é desfeito pelo vínculo);
  - refazer é o mesmo `POST .../vinculo`.
- **Histórico (princípio VII):** cada ligar e desfazer grava `history.record` na **postagem**
  (`entity_type = "postagem"`, `action = "updated"`), com `before` e `after` do estado e `details
  = {acao: "vinculo_feito" | "vinculo_desfeito", metodo, automatico: bool}`. Os ids e o link da
  TikTok **não** vão para o histórico, porque ele não é anonimizável (R13). Quem abre o destino
  vê o vídeo atual pelo vínculo vivo.
- **Controle otimista:** o corpo leva a `version` do destino, e uma mudança concorrente dá 409
  `version_conflict`.
- **Por quê:** a spec pede que o dono cole o link, escolha e desfaça, com histórico. Resolver
  encurtador pediria um GET para tiktok.com, fora da lista fechada do princípio I.

## R12. O que marca o destino como "publicado" (FR-005)

- **Decisão:**
  | Estado do destino ao ligar | Modo | Efeito |
  |---|---|---|
  | `rascunho_criado` | `criar_rascunho` | → **`publicado`** (sistema nos níveis 1 e 2; dono no nível 3) |
  | `publicado` (post direto da 015) | `publicar` | nenhum (já tem `rede_post_id`); só o vínculo |
  | `postado` (o dono marcou à mão) | qualquer | nenhum; só o vínculo. No `lembrete`, o nível 2 roda com a âncora no `posted_at` (R10, Q3 = A); no `criar_rascunho`, os níveis 1 e 2 seguem com a âncora da entrega |
  | `aprovado`/`agendado` | `lembrete` | só o dono: escolha de um candidato (R11) ou link → **`postado`** pelo `marcar_postado` humano de sempre (014), com `posted_url = link` (link colado) ou `null` (escolha); níveis 1 e 2 não se aplicam antes do clique (Q3 = A) |
  | `falhou` com `falha_incerta` | automático | só nível 3 (o rascunho pode ter chegado); → `publicado` |
  | outros | | 409 `destino_sem_post` ("Este destino ainda não pode ser ligado a um post") |
- **Uma função só:** `postagem/service.py::publicacao_pelo_vinculo(db, actor, destino,
  vinculado: bool)`:
  - aceita só `rascunho_criado → publicado` (ou `falhou → publicado` com a incerteza) ao ligar;
  - aceita só `publicado → rascunho_criado`/`falhou` ao desfazer, e **somente** se a última
    mudança de estado para `publicado` veio de `vinculo_feito` (conferido no histórico). Um
    `publicado` da 015 nunca volta;
  - entra em `ESTADOS_015_PERMITIDOS` do guarda de AST, que continua vivo.
- **O link na tela** sai do vínculo (`metricas_videos.share_url`), não de
  `postagens.posted_url`. A 016 não copia dados da TikTok para o destino nem para o histórico
  dele. Exceção: o `posted_url` digitado no caminho de lembrete, que é o `marcar_postado` da 014.
- **Por quê:**
  - a spec diz que o destino "passa a publicado com o link";
  - o estado gravado mantém o calendário, os filtros e os atalhos da 014 sem regra nova;
  - não é envio: o dono publicou no app, e o SociMan só registra o que observou (princípio I).
- **Alternativa:** estado derivado ("publicado" quando há vínculo). Rejeitada, porque espalharia
  exceções por `consulta.py` (estado efetivo, atalhos, calendário, contagens), e o estado gravado
  ficaria "rascunho_criado" para sempre.

## R13. Anonimização ao desconectar (FR-009)

- **Decisão:** ao desconectar (a rota **H** da 015), na mesma transação, depois de revogar e
  apagar a credencial:
  1. se a série viva tem ao menos 1 foto, o corpo precisa de `confirmoAnonimizar: true`. Sem
     isso, 409 `confirmar_anonimizacao`, com `{videos, fotos}` em `details`. A tela mostra: "As
     métricas de @x (N vídeos, M fotos) serão anonimizadas: os números ficam, mas sem a conta,
     os links, as legendas e o elo com os conteúdos. Isso não pode ser desfeito.";
  2. `anonimizar.serie(db, serie)`, só com **UPDATE**:
     | Tabela | Coluna | Vira |
     |---|---|---|
     | `metricas_series` | `conta_id` | `NULL` |
     | | `rotulo` | `"Conta anônima N"` (sequência global) |
     | | `anonimizada_em`, `anonimizada_por` | agora, dono |
     | | erro e cursor | `NULL` |
     | `metricas_videos` | `rede_video_id`, `share_url`, `legenda`, `titulo` | `NULL` |
     | | `destino_id`, `vinculo_metodo`, `vinculado_por`, `vinculado_em` | `NULL` (o método fica em `features.vinculo_metodo`; o `ck_metricas_videos_vinculo` exige `destino_id` e `vinculo_metodo` nulos juntos) |
     | | `publicado_em` | truncado para a hora |
     | | `features` | congeladas antes de cortar o elo (abaixo) |
     | | `proxima_coleta_em` | `NULL` |
     | `metricas_buscas_post` (destinos da conta) | `post_id` | `NULL` |
     | | busca aberta | encerrada com `fim = anonimizada` |
     | fotos de vídeo e de conta | nada | não têm identificador; o elo é o vídeo ou a série |
  3. **características congeladas** (`metricas_videos.features`, JSONB), só as **não
     identificadoras**:
     - `origem` (corte, vídeo próprio ou fora) e `modo_envio`;
     - `vinculo_metodo` e `score`;
     - `canal_status_direito` (o status, sem o canal);
     - `duracao_s`, `hora_local` e `dia_semana`;
     - `intervalo_post_anterior_h` e `seguidores_na_publicacao`;
     - `gancho_caracteres` e `hashtags_n`.

     Perfil, conta, canal, gancho, legenda e hashtags em texto **não** entram (open-questions
     Q1 = A, decisão do dono);
  4. uma versão da **conexão** (`history.record`, `details = {acao: "metricas_anonimizadas",
     videos, fotos}`), sem identificadores da série.

  Reconectar depois cria **outra série** (US2, edge case): a anônima continua sem conta.
- **Irreversível:** nenhum dado para desfazer é guardado. Não há rota de restaurar, e a
  reversão da conexão não toca a série.
- **Limite do que é anonimizado:** as tabelas `metricas_*` (o que a 016 obteve pela API).
  Ficam fora:
  - `conexoes` (`open_id` e `username`) e `postagens.rede_post_id` da 015, com o histórico
    deles: são o registro de execução do princípio I, e o histórico é só de inserção;
  - o `posted_url` digitado pelo dono (014).

  A 016 não copia nenhum dado da TikTok para o destino nem para o histórico (R11, R12), e é
  isso que torna a anonimização das métricas efetiva: a série anônima não tem caminho de volta
  para conta ou destino.
- **Por quê:**
  - é a decisão do dono (Clarifications: "anonimizadas, não apagadas");
  - os termos da TikTok pedem que dados obtidos pela API não fiquem ligados a quem revogou o
    acesso (pesquisa §6.3).

  UPDATE sem DELETE é a leitura mais próxima do princípio VII que cumpre isso (exceção
  justificada no plan).
- **Alternativas:**
  - DELETE: rejeitada pelo dono;
  - pseudônimo reversível (tabela de mapeamento): rejeitada, porque não é anonimização;
  - anonimizar também em `precisa_reconectar`: rejeitada, porque o dono pode só reconectar, e
    anonimizar é irreversível.

## R14. Telas e gráficos (FR-007, US4)

- **Decisão:**
  - **gráfico:** componente próprio `components/metricas/LinhaChart.tsx`, em SVG puro, com:
    - 1 a 4 séries e eixos com ticks "bonitos";
    - marcadores verticais (vídeos publicados no gráfico da conta; 1 h/24 h/7 d/30 d no do
      vídeo);
    - tooltip no ponto mais próximo por mouse e teclado (setas), com `role="img"` +
      `aria-label` e uma tabela escondida (`sr-only`) com os pontos, para leitor de tela;
    - cores dos tokens do tema, claro e escuro.
  - **Sem biblioteca:** o SPA não tem nenhuma hoje (`package.json`). A spec pede 3 gráficos de
    linha, e o componente fica perto de 200 linhas, sem dependência e sem `unsafe-eval`. A CSP
    não muda: SVG inline e atributos `style` já são aceitos pelo `style-src 'unsafe-inline'`
    (ADR 0001).
  - **Lugares:**
    - `/app/metricas` (item "Métricas" no menu), com 2 abas:
      - **Ranking:** `DataTable` (TanStack v9) filtrável por perfil, conta, origem e período,
        ordenável por views 24 h, views 7 d, engajamento e velocidade. O clique leva ao
        conteúdo, ou ao `/app/metricas/videos/:id` quando o vídeo é de fora;
      - **Contas:** seletor de conta, gráfico de seguidores e curtidas com os vídeos marcados
        e o estado da coleta;
    - **DestinoPanel** ganha a seção "Desempenho": curva, `MarcosCard` e `VinculoPanel`
      (estado, candidatos, colar link e desfazer, para o dono);
    - **ConexaoCard** ganha o `ColetaStatus` ("Coletando métricas · última coleta há 12 min",
      "Reconectar para liberar métricas" para o dono, ou o erro) e a confirmação da
      anonimização no desconectar;
    - o botão **Exportar** (dono) em `/app/metricas` abre o `ExportarDialog`.
  - **Miniatura:** a do conteúdo no SociMan (MinIO + imgproxy). Um vídeo de fora mostra o
    ícone da rede, sem imagem da CDN (a capa expira em 6 h e ficaria fora da CSP `img-src
    'self'`).
  - **Horário:** o eixo e os textos ficam em `America/Sao_Paulo` (`APP_TZ`); a API manda ISO com
    offset.
- **Alternativas:**
  - Recharts (o que o `chart` do shadcn usa): rejeitada, porque traz o d3 e várias centenas de
    kB para 3 gráficos de linha (princípio VIII);
  - uPlot: rejeitada, porque é leve mas desenha em canvas (acessibilidade pior) e ainda seria
    dependência nova;
  - capa da TikTok: rejeitada, porque expira e sai da CSP.

## R15. Marcos 1 h/24 h/7 d/30 d, ranking, engajamento e velocidade (FR-007)

- **Marco `T`** de uma métrica `m` num vídeo:
  1. se a idade atual do vídeo for menor que `T`: `null`, com `motivo = "ainda_nao"` ("ainda
     não");
  2. a foto logo antes (`idade_s ≤ T`) e a logo depois (`idade_s ≥ T`), por `LATERAL … ORDER BY
     idade_s LIMIT 1` sobre o índice `(video_id, idade_s)`. **Âncora `(0, 0)`**: na idade 0
     todo contador vale 0, e ela vale como a foto "antes" quando não há outra;
  3. interpolação linear em `idade_s`. Com foto exatamente em `T`, o valor é o dela;
  4. `estimado = true` quando o intervalo entre as duas fotos passa de 25% de `T` (por exemplo,
     vídeo de fora descoberto com 3 h, e o marco de 1 h sai de `(0,0)–(3h, v)`);
  5. sem foto depois de `T`, num vídeo mais velho que `T` (a coleta parou): usa a última foto
     se ela estiver a até 10% de `T`; senão `null`, com `motivo = "sem_dado"`.
- **Contagens que caem** (a TikTok corrige): a interpolação usa os valores como vieram, sem
  forçar monotonia.
- **Ranking** (`GET /api/metricas/videos`), uma consulta SQL com os filtros e 2 LATERAIS por
  marco pedido:
  - `views_24h` e `views_7d`: os marcos;
  - **engajamento** = `(likes + comments + shares) ÷ views` da **última foto** (0 quando views
    = 0);
  - **velocidade** = views ganhas nas **últimas 24 h de idade**, ou seja, `última foto −
    interpolado(idade_última − 24 h)`, dividido por 24, em views por hora. Para um vídeo com
    menos de 24 h, `views ÷ idade_h`;
  - paginação por cursor, 50 por página, e ordenação estável (métrica, `publicado_em`, `id`);
  - filtros: perfil, conta, origem (`corte`, `video_proprio`, `fora`, `anonima`) e período de
    publicação.
- **Por quê:**
  - interpolação linear na idade é o que a pesquisa §6.1 recomenda para os rótulos do ML, e com
    a agenda ancorada (R4) quase sempre há foto no próprio marco;
  - calcular na leitura evita tabela de cache e invalidação: com 1 ano de 2 contas são cerca de
    1.500 vídeos × 8 buscas por índice, em milissegundos (SC-004).
- **Alternativas:**
  - tabela de marcos materializada: rejeitada pelo princípio VIII, porque exige invalidação a
    cada foto;
  - spline: rejeitada, porque exagera entre fotos esparsas e é difícil de explicar na tela.

## R16. Exportação CSV/JSON e dicionário (FR-008, SC-005)

- **Decisão:** `GET /api/metricas/export?formato=csv|jsonl&de&ate&perfilId&contaId&
  incluirAnonimas` (dono) → `application/zip`, com o nome
  `sociman-metricas-<AAAAMMDD>-<AAAAMMDD>.zip`. O ZIP tem 5 arquivos:
  | Arquivo | Uma linha por | Colunas principais |
  |---|---|---|
  | `fotos_videos.<ext>` | foto de vídeo | `video_ref`, `coletado_em`, `idade_h`, `alvo_idade_h`, `views`, `likes`, `comments`, `shares` |
  | `videos.<ext>` | vídeo | `video_ref`, `serie`, `rede`, `conta`, `perfil`, `origem`, `vinculo_metodo`, `publicado_em`, `hora_local`, `dia_semana`, `duracao_s`, `legenda`, `hashtags`, `url`, `disponivel`; do SociMan: `conteudo_id`, `destino_id`, `modo_envio`, `canal_fonte`, `canal_status_direito`, `score`, `gancho`, `gancho_caracteres`, `hashtags_n`, `intervalo_post_anterior_h`, `seguidores_na_publicacao`; rótulos: `views_1h`, `views_24h`, `views_7d`, `views_30d`, `engajamento_7d` (+ `*_estimado`) |
  | `fotos_conta.<ext>` | foto da conta | `serie`, `conta`, `coletado_em`, `janela`, `seguidores`, `seguindo`, `curtidas`, `videos` |
  | `dicionario.csv` | coluna | `arquivo`, `coluna`, `tipo`, `unidade`, `significado`, `origem` (TikTok, SociMan ou calculado) |
  | `LEIAME.txt` | — | filtro usado, data, versão do dicionário e avisos (só vídeos públicos, contagens acumuladas, `video_count` conta só públicos) |
- **Cabeçalho estável:**
  - a ordem e os nomes vêm de `metricas/dicionario.py` (constante única), e um teste compara o
    cabeçalho do CSV com o dicionário;
  - uma coluna nova entra no fim e sobe a versão do dicionário (`DICIONARIO_VERSAO`);
  - CSV em UTF-8 **com BOM**, vírgula, ponto decimal e datas ISO 8601 com offset de SP, para
    abrir na planilha sem ajuste (SC-005);
  - JSON Lines: um objeto por linha, com as mesmas chaves.
- **Vídeos sem vínculo:** colunas do SociMan vazias e `origem = fora`.
- **Vídeos anonimizados** (só com `incluirAnonimas`):
  - `serie = "Conta anônima N"`;
  - `conta`, `perfil`, `legenda`, `url`, `gancho`, `canal_fonte`, `conteudo_id` e `destino_id`
    vazios;
  - as características saem de `features`.
- **`video_ref`:** o uuid do SociMan (`metricas_videos.id`), nunca o id da TikTok. O mesmo
  arquivo serve antes e depois da anonimização.
- **Montagem:**
  - streaming do banco (`yield_per(2000)`) para um `SpooledTemporaryFile(max_size=32 MB, dir=
    <HD>/work/exports)`, porque exportação grande vai para o HD pela constitution. Antes de
    montar, a rota estima o tamanho pela contagem de fotos (~120 B por linha); se passar de
    32 MB, exige o HD pelo `datadir` (sentinela e piso), com 503 `storage_unavailable` ou 507
    `storage_full`. Abaixo disso, o arquivo fica só na memória e o HD não é tocado;
  - 1 mês de 1 conta sai em menos de 2 s;
  - o download é por `fetch` com Bearer + `Blob`, sem link público.
- **Por quê:**
  - um ZIP resolve "CSV ou JSON" com os 3 conjuntos e o dicionário numa ação só;
  - as características entram por join na hora (pesquisa §6.1: "não copiar"), menos para as
    séries anônimas.
- **Alternativas:**
  - uma rota por arquivo: rejeitada, porque são 4 downloads para montar um dataset;
  - Parquet: rejeitada, porque exigiria dependência nova; o ML lê CSV sem problema.

## R17. TikTok falsa para as rotas de leitura (pytest e e2e)

- **pytest** (`tests/fakes/tiktok_fake.py`, a mesma classe da 015):
  - `user_info` com os campos de stats, quando pedidos (`seguidores(handle, n)`);
  - `video_list` com o cursor em ms, `max_count` ≤ 20, `has_more` e só os vídeos públicos, do
    mais novo para o mais antigo;
  - `video_query` com até 20 ids; só devolve os vídeos **da conta do token**; os privados e
    apagados não voltam;
  - controles:
    - `video(handle, id, criado_em, duracao, legenda, publico=True)`;
    - `contadores(id, views=…, likes=…)`, que também aceita cair;
    - `tornar_privado(id)`;
    - `publicar_rascunho(publish_id, post_id)`, que faz o próximo `status` devolver
      `PUBLISH_COMPLETE` com `publicaly_available_post_id`;
  - falhas pelo `falhar_proximo` de sempre, mais `scope_not_authorized`;
  - `requests` registra `("POST", "video_list")` e as outras chamadas, para o guarda 6;
  - o **relógio** é o parâmetro `agora` de `coleta.rodar` e de `agenda`, usado sem sleep e sem
    freezegun (sem dependência nova).
- **e2e** (`e2e/fakes/server.py`, `openshorts-fake`):
  - as mesmas rotas sob `/tiktok/v2/video/{list,query}/` e os stats no `user/info`;
  - controle por `POST /tiktok-e2e/videos` (criar, contadores, privado) e `POST
    /tiktok-e2e/publicar-rascunho`;
  - `AGENDADOR_METRICAS_S: "2"` no `docker-compose.e2e.yml`.

  Um histórico longo (ranking de uma semana) é semeado por **INSERT via `psql`**, pelo
  `compose()` dos helpers. O trigger aceita INSERT, e o projeto `sociman-e2e` é isolado.
- **Por quê:** é o mesmo padrão da 015. Nenhum teste chama a TikTok real, e a agenda é testável
  por injeção de tempo.

## R18. Limites de taxa

- **Decisão:**
  - `limites.TAXAS["leitura"] = 120` por minuto, por token e por endpoint (`user_info`,
    `video_list`, `video_query`); a TikTok permite 600;
  - o `status/fetch` usa a chave `"status"` da 015 (29 por minuto), compartilhada com a trilha
    de publicação;
  - a taxa estourada adia a série 60 s, sem erro visível;
  - o 429 `rate_limit_exceeded` da TikTok é tratado igual.
- **Orçamento real:** cerca de 3 pedidos por hora por conta (R8), cerca de 1.000 vezes abaixo do
  limite. A taxa local só protege contra laço acidental.

## R19. Latência do `view_count` e ajuste da cadência

- **Decisão:** não se muda a cadência antes de medir. O quickstart §3.4 mede com um vídeo novo:
  - as fotos de hora em hora nas primeiras 6 h;
  - se o `view_count` fica igual por mais de 2 fotos seguidas enquanto o app mostra
    visualizações novas, a TikTok atualiza com atraso.

  O resultado vai para a pesquisa (§1.4) e decide se a faixa de 48 h passa a 2 h ou 3 h (é uma
  constante em `agenda.py`).
- **Por quê:** a pesquisa não achou a latência documentada (§1.4, "não confirmado"), e a spec
  (Assumptions) pede a conferência nos primeiros dias.

## R20. Onde guardar: só Postgres × MongoDB × híbrido

O dono aceita um MongoDB se ele for melhor para ingerir e usar os dados em JSON (séries
temporais, respostas brutas da API, dataset de ML). A avaliação abaixo é honesta, sobre o volume
real.

- **Decisão:** **só PostgreSQL**, com as tabelas estreitas de fotos de R8. Não se adota
  TimescaleDB, nem MongoDB, nem arquivo de respostas brutas.
  - **Respostas brutas:** não são guardadas. Cada campo que a 016 pede à TikTok já vira coluna:
    os contadores vão para a foto, e o metadado vai para o vídeo e a série. Guardar o JSON cru
    repetiria esses dados, e ele contém legenda e link, que teriam de entrar na anonimização
    (R13).
  - **Etapa 2** (Business API: retenção por segundo, fontes, audiência, que são listas
    aninhadas): uma coluna `extras jsonb` na foto, com `fonte = 'business'` (já reservada no
    data-model). Esse campo só entra na migration da etapa 2.
- **Comparação:**
  | Critério | Só Postgres (recomendado) | MongoDB (time series collections) | Híbrido (Postgres + Mongo) |
  |---|---|---|---|
  | Volume real (140 mil a 1,4 milhão de fotos por ano, 30 a 300 MB) | folgado: B-tree e `LATERAL` em milissegundos (R8, R15) | folgado também; o Mongo só ganharia em outra ordem de grandeza | folgado |
  | Joins com as características (corte, canal, gancho, destino, perfil) | SQL direto, numa transação | não há join com o Postgres: seria preciso copiar as características para o Mongo ou juntar no Python | idem ao Mongo, para tudo que cruza os dois |
  | Vínculo e estado (transação com o destino, histórico, `version`) | mesma transação que `postagens` e `entity_versions` | impossível: o destino está no Postgres | vínculo no Postgres, série no Mongo, sem transação comum: consistência "no melhor esforço" |
  | Anonimização (R13) | um UPDATE na mesma transação do desconectar | segundo passo, em outro banco; uma falha no meio deixa dado identificável | idem |
  | Só inserção (SC-006) | trigger no banco (R7) | coleções time series recusam update em parte dos campos, mas não bloqueiam delete sem papel próprio | idem |
  | Exportação e ML | uma consulta com join → CSV/JSONL (R16); o ML lê CSV | JSON nativo, mas sem as características sem cópia | duas fontes para juntar |
  | Backup | o `pg_dump` que já existe (quickstart da 015 §0) | segundo backup (`mongodump`) e restauração coordenada com o Postgres | dois backups que precisam estar no mesmo ponto no tempo |
  | NVMe × HD (constitution 2.1.0) | no NVMe, com o banco, porque é pequeno e lido a cada tela | um banco novo no NVMe, ou no HD (mais lento e sujeito ao sentinela) | idem |
  | Testes efêmeros e e2e | nada muda | serviço novo no `docker-compose.test.yml` e no `docker-compose.e2e.yml`, com fixture de limpeza, driver (`pymongo`) e fake de conexão | idem |
  | Constitution | cabe na stack fixa | **emenda** (a stack é fixa: "Trocar ou adicionar um componente da stack é emenda"), MINOR, com Complexity Tracking | idem |
- **Por quê:**
  - o problema é pequeno e **relacional**: o valor para o ML está na junção das métricas com as
    características do SociMan, que moram no Postgres;
  - o vínculo, o estado "publicado" e a anonimização precisam de uma transação com o destino e
    com o histórico;
  - o princípio VIII pede a peça mínima. Um segundo banco traz serviço, backup, driver, testes
    e emenda, sem ganho mensurável em 30 a 300 MB por ano.
- **Alternativas rejeitadas:**
  - **TimescaleDB:** troca a imagem do Postgres (emenda da stack) para compressão e agregações
    contínuas que só compensam na casa de dezenas ou centenas de milhões de linhas. Continua
    sendo a primeira opção **se** o volume passar do ponto de revisão de R8 (cerca de 20
    milhões de fotos), porque é o mesmo banco e o mesmo SQL;
  - **MongoDB:**
    - é bom quando os documentos são heterogêneos, grandes e consultados sozinhos;
    - aqui os documentos são pequenos, uniformes e sempre consultados junto com dados
      relacionais.

    Se o dono quiser mesmo assim (open-questions Q4, opções B e C), o impacto está listado abaixo;
  - **Híbrido:** herda o custo do Mongo e ainda cria dois lugares de verdade para a mesma
    série.
- **Quando o MongoDB passaria a valer a pena** (qualquer um destes, e não o volume de hoje):
  1. guardar **respostas cruas grandes e heterogêneas** de várias redes e APIs (por exemplo,
     Business API + YouTube Analytics + Instagram Insights, com retenção por segundo e audiência)
     como fonte primária, consultadas documento a documento e sem junção com o SociMan;
  2. ingestão de **terceiros em escala**: milhares de contas ou vídeos que não são do dono
     (pesquisa de tendência), passando de centenas de milhões de pontos por ano, onde o
     esquema muda sem aviso;
  3. um consumidor externo (pipeline de ML ou ferramenta de BI) que exija a API do Mongo.

  Nos casos 1 e 2, a ordem seria: primeiro `jsonb` no próprio Postgres (e TimescaleDB, se o
  volume pedir), e só então um Mongo, via emenda, como **depósito de brutos no HD**, mantendo o
  Postgres como fonte da verdade dos vínculos e do estado.
- **Resposta bruta em `jsonb` no Postgres, agora:** também rejeitada por ora. Seriam cerca de 5 KB
  por resposta × ~200 por dia ≈ 365 MB/ano com 2 contas (3,6 GB com 20) no NVMe, quase tudo
  repetindo colunas que já existem, e com legenda e link a anonimizar. Se o dono quiser o bruto
  para reprocessar no futuro, a saída mínima é uma coluna `bruto jsonb` só no **vídeo** (a
  última resposta, sobrescrita), sem crescimento por foto.
- **Impacto se a escolha for MongoDB ou híbrido:**
  1. **Emenda da constitution** (MINOR): acrescentar o MongoDB às "Restrições técnicas", dizer
     o que ele guarda e o que continua no Postgres, e decidir NVMe ou HD. Aprovação do dono via
     `/speckit-constitution`;
  2. **compose:**
     - serviço `mongo`, só na rede interna e sem porta publicada (a 27017 está livre no host,
       mas a regra de portas vale), com usuário e senha de dev;
     - volume no NVMe, ou no HD com sentinela e piso de espaço, pela constitution;
     - variáveis `MONGO_URL` em `api` e `agendador`;
  3. **backup:** `mongodump` junto do `pg_dump`, no mesmo horário, e um roteiro de restauração
     dos dois no mesmo ponto;
  4. **testes efêmeros:** Mongo em `docker-compose.test.yml` e `docker-compose.e2e.yml` (com
     tmpfs), limpeza por teste e dependência `pymongo`;
  5. **código:**
     - o vínculo e o estado continuam no Postgres;
     - a coleta grava no Mongo, e a anonimização vira passo duplo com reconciliação;
     - a exportação junta as duas fontes no Python;
     - o guarda de só inserção passa a papel e usuário do Mongo;
  6. **Complexity Tracking** com essas linhas, e uma spec a mais de trabalho (estimativa: +30%
     na 016).
