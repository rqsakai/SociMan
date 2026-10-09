# Research: Aprender com o desempenho (023)

Decisões técnicas da 023. Cada item tem **Decisão / Por quê / Alternativas**. Os volumes são do banco de
dev em 2026-10-06: 2 contas, cerca de 40 posts medidos, a maioria com 0 a 2 views, e 42 mil vídeos-fonte.

## R1. Medida, fatores e efeito encolhido

- **Decisão:**
  - **Medida:** para cada post medido (`PostAnalisado.medido` da 019, marco escolhido, padrão `h24`), y =
    ln(1 + views). Os posts "aguardando" ficam fora.
  - **Estagnado:** a regra da 019 (`analytics.alertas.desempenho`, R9 da 019): ≥ 6 h e < 10% da mediana da
    conta na mesma idade, ou ≤ 1 view sem 5 referências.
  - **Peso:** w = 0,5^(idade_dias / 30), com janela máxima de 180 dias (`MEIA_VIDA_DIAS`, `JANELA_DIAS`).
  - **Parte A, entrega:**
    - e = 1 se o post saiu da estagnação, senão 0;
    - base da conta: p_c = Σw·e / Σw dos posts da conta;
    - efeito do grupo: Δ = Σw·(e − p_c) / (Σw + K), com K = 5 (`K_ENCOLHIMENTO`);
    - exibido em pontos percentuais ("+35 p.p. de chance de sair do zero").
  - **Parte B, rendimento:** só entre os entregues.
    - resíduo r = y − m_c, em que m_c é a média ponderada de y dos entregues da mesma conta;
    - efeito encolhido: θ = Σw·r / (Σw + K);
    - exibido como fator ≈ e^θ ("≈ 2,4× o típico da conta").
  - **Fatores** (`fatores.py`): tema principal (os secundários entram só na matriz), estilo do gancho,
    tamanho do gancho (≤ 40, 41–80, > 80 caracteres), duração (≤ 30 s, 31–60 s, > 60 s, as faixas da 019),
    faixa de 3 h de publicação, dia da semana, canal-fonte, hashtag (o bloco do R3) e modo de envio. Posts
    sem vínculo entram só nos fatores que não dependem do corte, como na 019.
- **Por quê:**
  - log(1+v) não explode com mediana 0 (atenção estatística 1 da spec) e não deixa um viral dominar a
    média.
  - O resíduo por conta tira o tamanho da conta da comparação (FR-011).
  - O encolhimento com K = 5 equivale a misturar 5 posts "típicos" no grupo: com 3 posts, o efeito cai a
    3/8 do bruto (FR-020).
  - Separar entrega de rendimento evita que os posts que a rede não mostrou contem como "assunto fraco"
    (atenção estatística 3).
- **Alternativas:**
  - lift da 019 (razão de medianas): infinito com mediana 0;
  - regressão múltipla: com 40 posts e dezenas de fatores, é instável e ilegível para o dono;
  - média sem log: um viral de 2.000 views vira o tema inteiro.

## R2. Intervalo, confiança, concentração e esquecimento

- **Decisão:**
  - **Intervalo:** reamostragem dos posts do grupo (com reposição), B = 400, semente fixa derivada do
    `perfil_id` e do fator. É reprodutível: a mesma entrada dá o mesmo intervalo. Usa o percentil 10–90
    (intervalo de 80%) do efeito encolhido.
  - **Confiança** (regra fixa em `estatistica.confianca`):
    - **forte:** n ≥ 10, o intervalo não cruza 0 e |efeito| ≥ ln 1,5 (ou ≥ 15 p.p. na entrega);
    - **moderada:** n ≥ 5 e o intervalo não cruza 0;
    - **fraca:** o intervalo cruza 0, mas |efeito| ≥ ln 1,3 (ou ≥ 8 p.p.);
    - **indício:** o resto.
  - **Amostra mínima:** n ≥ 5 posts distintos (`MIN_GRUPO`, o mesmo da 019) em ≥ 2 dias distintos
    (`MIN_DIAS`); a conta precisa de ≥ 15 posts medidos (`MIN_CONTA`). Abaixo disso, a linha mostra só a
    contagem e a mediana bruta, com "faltam N posts".
  - **Concentração:** quando o post com mais views responde por mais de 50% das views do grupo
    (`CONCENTRACAO`), a linha leva o aviso "puxado por 1 post" e o efeito recalculado sem ele. A
    recomendação só nasce se o efeito sem ele também passar a regra.
  - **Em alta / em queda:** o efeito dos últimos 30 dias (sem peso) é comparado com o do resto da janela.
    A marca aparece quando a faixa de confiança muda e o sinal se mantém (alta) ou se inverte (queda).
- **Por quê:**
  - A reamostragem não supõe distribuição, cabe em cerca de 20 linhas e fica rápida com dezenas de
    posts (400 × 30 grupos ≈ 12 mil médias).
  - A semente fixa garante SC-003 (o teste compara com a referência).
- **Alternativas:**
  - intervalo t de Student (supõe normalidade, ruim com 0/1);
  - Bayes completo (dependência e explicação difícil);
  - intervalo de 95% (com n pequeno, nada passaria nunca).

## R3. Coocorrência, separabilidade e blocos

- **Decisão:**
  - **Blocos:** hashtags com o **mesmo conjunto exato de posts** na janela viram um bloco ("#a + #b +
    #c"), contado uma vez. Pares com Jaccard ≥ 0,8 aparecem como "quase sempre juntas", sem fundir.
  - **Matriz:** hashtag (ou bloco) × tema principal, com a contagem de posts. É um Heatmap na SPA.
  - **Separabilidade da hashtag:**
    - para cada tema t, o par vale quando há ≥ 3 posts de t com a hashtag e ≥ 3 sem ela
      (`MIN_SEPARAVEL`);
    - o efeito "dentro do tema" é a média, ponderada por n, das diferenças entre os resíduos encolhidos
      com e sem a hashtag em cada tema válido (estratificação simples);
    - sem nenhum tema válido, a hashtag sai como "não separável do tema X", sendo X o tema onde ela mais
      aparece.
  - **Fator × fator:** quando ≥ 80% dos posts de um grupo têm o mesmo valor de outro fator
    (`CONFUSAO`), e esse valor tem efeito próprio de confiança ≥ moderada, a linha leva "quase só com X =
    valor" e não gera recomendação. Vale para os pares tema × horário, tema × canal-fonte e
    hashtag × canal-fonte.
  - **Exploratório:** o cabeçalho mostra quantas comparações foram feitas ("32 comparações; espere 3 ou 4
    falsos achados fracos"), e só confiança ≥ moderada vira recomendação (FR-028).
- **Por quê:** é exatamente o padrão #multiversomarvel, #vingadoresdoomsday e #geek, que aparecem nos
  mesmos 3 ou 4 posts de Marvel (atenção estatística 2).
- **Alternativas:**
  - correção de Bonferroni: com n tão pequeno, zera tudo; o rótulo e a regra de recomendação são mais
    honestos;
  - regressão com interação: instável com poucos posts.

## R4. Distribuição travada

- **Decisão:** uma conta está **travada** quando mais de 60% dos posts medidos dela no período estão
  estagnados (`TRAVADA`). Nesse caso:
  - a parte B da conta (e a contribuição dela para o perfil) é rotulada "indício";
  - nenhuma recomendação nasce de evidência só dessa conta;
  - a tela aponta para o Diagnóstico.

  A parte A continua visível, porque é justamente o que muda quando a conta destrava.
- **Por quê:** FR-027. Hoje as duas contas estão travadas, e a spec pede que a tela diga isso em vez de
  "aprender" com ruído.
- **Alternativas:** excluir os estagnados e analisar o resto (sobram 5 ou 6 posts, e o dono não veria por
  que nada conclui).

## R5. Chamadas de IA: tipos, quadros e assincronia

- **Decisão:**
  - **Tipos:** 3 `TipoCampo` novos em `ia/tipos.py`, como `guia.montar`: `aprendizado.taxonomia`,
    `aprendizado.classificacao` e `aprendizado.analise`. Ganham regra padrão em `regras_padrao.py`
    (editável pelo dono na tela do assistente), schema de saída em `saida.py` e entrada no registro e no
    resumo. O modelo é o `textos_model` da 008 (sem preço novo em `custo.py`).
  - **Taxonomia:** chamada síncrona na rota (como `guia.montar`). A entrada são até 40 posts recentes do
    perfil: legenda, gancho, hashtags e os primeiros 600 caracteres da transcrição. A saída tem de 3 a 15
    temas, cada um com nome (≤ 40), descrição (≤ 200) e palavras-chave (≤ 20, cada uma ≤ 30). Nada é
    salvo.
  - **Classificação:**
    - 1 chamada por post, com taxonomia, legenda, hashtags, gancho e transcrição (≤ 4.000 caracteres,
      como a `cortes.transcript`);
    - saída: `temaId` (dos ids enviados, ou `null`), até 2 `secundarios`, `estiloGancho` (enum fixo),
      `justificativa` (≤ 160) e `sugestaoTema` opcional;
    - o servidor recusa um id fora da lista (FR-005) e guarda a sugestão.
  - **Análise:**
    - **pedido assíncrono** (`aprendizado_analises.estado = pendente`) executado pela trilha (R4 do plano);
    - entrada: os N melhores (padrão 8, máximo 15) pelo resíduo encolhido do post, e N comparáveis (piores
      entregues da mesma conta e do mesmo período, que não estão estagnados), mais o resumo dos efeitos
      com confiança ≥ fraca;
    - saída: até 6 hipóteses, cada uma com `texto` (≤ 240), `postsIds`, `contraste` (≤ 160), `n` e
      `grau = "a_conferir"`;
    - o servidor recusa id fora do conjunto enviado (FR-032).
  - **Quadros (Clarification 1):**
    - 4 por vídeo, em t = 0,3 s, 2 s, 50% e duração − 0,5 s;
    - `extract_frame` de `cortes/compose.py` sobre o arquivo do corte (`cortes.result_key`, no bucket
      `videos`) ou do vídeo próprio (014), baixado com `storage.get_to_file` para
      `work/tmp/aprendizado/<analise>/`;
    - cada quadro é reduzido com Pillow a 512 px de largura (JPEG q = 80) e vai como bloco `image`
      base64 no `user`;
    - o `IaClient._chamar` passa a aceitar `str | list[bloco]`;
    - a pasta é apagada no `finally`;
    - vídeo sem arquivo entra só com texto, e a análise grava quantos.
  - **Estimativa:** `custo.estimar(entrada_tokens, saida_max, model)`, com tokens de texto ≈ caracteres/4
    e imagem ≈ (512 × altura)/750 por quadro. Mostra com e sem quadros. Pedir sem `confirmoCusto: true` →
    409 `confirmar_custo`, com as duas estimativas no corpo.
  - **Segurança do prompt:** legendas, transcrições e hashtags vêm da rede e de terceiros. Vão dentro de
    `<post id="…">` com a base dizendo que são **dados**, nunca instruções. Sem `tools` (guarda
    `test_cliente_da_ia_nao_envia_tools`). A saída é validada pelo schema e pelos limites.
- **Por quê:** reaproveita o registro, o custo, as regras editáveis e os fakes da 008. A análise com
  quadros não cabe numa requisição (Complexity Tracking).
- **Alternativas:**
  - um tipo "aprendizado" só, com modo: perde a separação por finalidade no resumo (FR-052);
  - classificar em lote (10 posts por chamada): mais barato, mas uma resposta ruim estraga 10 e o
    registro fica menos claro (desfecho por post);
  - vídeo inteiro: a API não aceita vídeo, e quadros bastam para edição e match cut.

## R6. Recomendações: calculadas na leitura, decisões gravadas

- **Decisão:**
  - **Cálculo:** `recomendacoes.calcular(analise, preferencias, decisoes)` aplica as regras de FR-035 sobre
    os efeitos de R1–R4 e gera `Recomendacao(chave, tipo, alvo, escopo, motivo, evidencia, origem)`.
  - **Chave estável:** `"<tipo>:<escopo>:<alvo>"`, por exemplo `tema_ampliar:perfil:<temaId>`,
    `hashtag_fixar:conta:<contaId>:#matchcut` e `padrao_gancho:perfil:pergunta`.
  - **Decidir:** `POST …/recomendacoes/decidir {chave, decisao, motivo?}`.
    - O servidor **recalcula** a recomendação daquela chave. Se ela não existir mais, responde 409
      `recomendacao_mudou`.
    - Se existir, grava `aprendizado_decisoes` (chave, decisão, evidência no momento, `n`, `faixa`, autor),
      com `history`.
    - Aceitar aplica a preferência (R7).
  - **Filtro das decididas:**
    - uma recomendação com decisão `aceita` ainda vigente não aparece;
    - uma `rejeitada` só reaparece se n ≥ 2 × n_da_decisão ou a faixa de confiança mudou (FR-038), com o
      selo "já rejeitada em DD/MM".
  - **De hipótese:** "transformar em recomendação" grava uma linha em `aprendizado_decisoes` com
    `estado = aberta`, `origem = hipotese` e `analise_id`. Só o tipo `padrao_*` é aceito; o dono escolhe
    qual (gancho, duração ou horário) e o texto curto. Ela segue o mesmo decidir.
  - **Superada:** é calculada. Uma decisão de tema que foi juntado ou arquivado aparece como "superada"
    na lista de decididas.
- **Por quê:** GETs não escrevem, e não há tarefa para manter recomendações que ninguém viu
  (Complexity Tracking).
- **Alternativas:** gravar todas numa trilha (tabela que cresce, mais estados).

## R7. Preferências e "fixar hashtag" no guia

- **Decisão:**
  - **Tabela:** `aprendizado_preferencias`, com uma linha do perfil (`conta_id IS NULL`) e no máximo uma
    por conta, como `ia_guias`. Sem linha, a versão é 0.
  - **Campos:**
    - `temas` (jsonb `{temaId: "ampliar"|"cortar"}`; sem chave = neutro);
    - `hashtags_evitar` (text[], normalizadas);
    - `padroes` (jsonb, lista de `{tipo, texto, valor?}`, por exemplo `{tipo:"horario", valor:{dias:[1,2],
      de:18, ate:21}}`);
    - `classificacao_auto` e `usar_desempenho` (só na linha do perfil, padrão `true`);
    - `pedido_classificacao_em`;
    - `version`.
  - **Efetivas:** `preferencias.efetivas(perfil, conta)` junta perfil e conta. A conta vence no mesmo
    tema; as listas somam sem repetir.
  - **Fixar:** aceitar `hashtag_fixar` chama `ia.service_guia` para acrescentar a hashtag ao guia da conta
    (ou do perfil, se o escopo for perfil). Valem as mesmas regras da 017 (máximo de fixas e proibidas), e
    o `history` do guia leva `details.origem = "recomendacao_023"` e a chave.
    - No máximo: 409 `fixas_no_maximo` com a lista atual. O corpo pode trazer `substituir: "#x"`.
    - Proibida: 400 `ia_proibida`.
    - Reverter a decisão reverte só a decisão. A hashtag sai pelo revert do guia, e a tela avisa e leva
      até lá.
  - **Edição direta:** o dono pode voltar um tema a neutro, tirar uma hashtag evitada ou remover um padrão
    (`PATCH …/preferencias` com `version`) e reverter versões. Tudo com histórico.
- **Por quê:** FR-037 a FR-039. As fixas continuam num lugar só (o guia), sem dois donos para a mesma
  regra.
- **Alternativas:** guardar as fixas também nas preferências (duas fontes de verdade, que divergem).

## R8. Bloco `<desempenho>` e prompt `ia/3`

- **Decisão:**
  - **Prompt:** `PROMPT_VERSION = "ia/3"`. A ordem do `system` fica: base → regras do tipo →
    `<guia_perfil>` → `<guia_conta>` → **`<desempenho versao_perfil="N" versao_conta="M">`** →
    `<perfil>`. O `cache_control` continua no último bloco.
  - **Quem recebe:** só os tipos `postagem.*` e `guia.testar`, e só com `usar_desempenho = true`.
  - **Conteúdo:**
    - temas `ampliar` (nomes) e padrões aceitos (texto curto);
    - hashtags "evitar", com a frase "não use";
    - até 3 exemplos (`<exemplo post="id">`: legenda ≤ 300 e gancho ≤ 120), escolhidos por regra fixa:
      - maior resíduo encolhido entre os entregues da conta (ou do perfil, sem posts na conta) nos últimos
        90 dias;
      - conta não travada e não anonimizada;
      - sem proibida efetiva;
      - empate pelo mais recente.
  - **Base:** a base ganha uma linha: "<desempenho> mostra o que já rendeu; use como inspiração sem
    copiar, e nunca contra o guia ou as regras fixas".
  - **Registro:** a chamada grava `desempenho_perfil_version`, `desempenho_conta_version` (NULL = não
    enviado) e `desempenho_exemplos` (uuid[] de `metricas_videos`). O registro mostra "sem bloco de
    desempenho" quando nulo.
  - **Saída:** em `saida.py`, `_sem_evitadas` roda depois de `_com_fixas`. Uma fixa que também está em
    "evitar" não acontece, porque o aceite recusa. As evitadas removidas vão para `ajustes` ("removida
    #fyp: marcada para evitar").
- **Por quê:** FR-044 a FR-047, no mesmo molde das versões de guia da 017 (R8 dela). Regras fixas tornam o
  bloco reprodutível.
- **Alternativas:**
  - mandar os efeitos crus: o modelo "aprenderia" achados fracos sem o dono decidir;
  - exemplos escolhidos pela IA: não determinístico.

## R9. Afinidade no Descobrir e no Mercado

- **Decisão:**
  - **Preferências × amostra (FR-043):** `ampliar`/`cortar` aceitos valem sempre; o termo estatístico
    (θ_t) só entra com a amostra mínima do R2 (abaixo dela, θ_t = 0).
  - **Por tema:** `afinidade.valores(db, perfil)` (Python, uma vez por requisição) calcula, para cada tema
    ativo:
    - a_t = clamp(θ_t / ln 2, −1, 1) × peso da confiança (forte 1; moderada 0,7; fraca 0,3; indício 0);
    - preferência `ampliar` → max(a_t + 0,5, 0,5), limitado a 1;
    - `cortar` → −1 e oculto.
  - **Por canal-fonte:** a_c é o mesmo cálculo sobre o fator canal-fonte.
  - **Final:** a = clamp(0,7·a_tema + 0,3·a_canal, −1, 1). a_tema é o de maior |a_t| entre os temas que
    casam, e um `cortar` vence.
  - **Pontos:** 20·a (`PESO_AFINIDADE = 20`), somados ao score exibido de hoje (`score_exibido`, que já
    aplica "já cortado") e limitados a 0–100.
  - **Casamento em SQL:**
    - `translate(lower(title || ' ' || coalesce(description,'')), 'áàâãäåéèêëíìîïóòôõöúùûüçñ',
      'aaaaaaeeeeiiiiooooouuuucn') ~ '\m(kw1|kw2…)\M'`, por tema, num `CASE` que devolve a_t;
    - as palavras-chave são normalizadas por `ia.guia.normalizar` e escapadas para regex;
    - o teste de paridade (`tests/integration/test_aprendizado_afinidade_norm.py`, contra o PG) compara `translate` × `normalizar` em
      todas as letras acentuadas do pt-BR e do espanhol.
  - **Só com `perfilId`:** sem perfil, nada muda (FR-043).
  - **Cortados:** a cláusula `NOT cortado` é aplicada por padrão. `mostrarCortados=true` a retira, a
    resposta traz `ocultosPorTema` (um `count` com o mesmo filtro), e cada item traz `afinidade {pontos,
    temaId, temaNome, cortado, motivo}`.
  - **Motivo:** quando |20·a| ≥ 10 e é maior que a maior contribuição da 006, o motivo exibido vira "Tema
    Marvel/MCU: ≈ 2,4× o típico da conta". O `score_reason` gravado não muda.
  - **Mercado:** as oportunidades da 019 usam a mesma expressão (é só leitura, e `analytics/` importa
    `aprendizado.afinidade`).
  - **Direito:** nada aqui lê ou grava `direito` além de mostrá-lo. O `enviar` continua devolvendo 409
    `aviso_direito` (teste SC-008).
- **Plano B:** se o teste de 50 mil vídeos com 30 temas × 20 palavras passar de +300 ms, entra uma tabela
  `aprendizado_fonte_temas (perfil_id, video_fonte_id, tema_id)`, refeita pela trilha a cada versão de
  taxonomia e a cada sync. Fica registrado no Complexity Tracking, se acontecer.
- **Plano B aplicado (2026-10-06, aprovado pelo líder):** medido no dev, o regex em título + descrição
  levou 5,5 s sobre 42 mil vídeos-fonte (descrição média de 846 caracteres), e o `LIKE ANY` de 1,3 a 1,8 s. O
  teste de 50 mil vídeos falhava com +2,6 s. Por isso entrou a migration `0019_aprendizado_fonte_temas`:
  - `aprendizado_fonte_temas` é um **cache de casamento**, derivado e reconstruível, sem `version` nem
    `history`. Em cada volta, a trilha `aprendizado` (`fonte_temas.atualizar`, que roda mesmo sem
    `ANTHROPIC_API_KEY`) reconstrói o perfil quando `preferencias.fonte_temas_versao` difere de
    `taxonomia_versao`; senão, casa só os vídeos-fonte novos (`first_seen_at > fonte_temas_em`). A função
    `fonte_temas.reconstruir` é idempotente;
  - enquanto o perfil não está casado com a taxonomia atual, a afinidade fica **neutra** (nunca cai no
    regex na leitura);
  - arquivar ou juntar um tema apaga as linhas dele na hora;
  - a leitura é um `EXISTS` por tema na tabela. O teste de 50 mil voltou a passar, dentro de +300 ms. A
    reconstrução completa (50 mil × 30 temas) leva cerca de 40 s, na trilha, fora das requisições.
- **Por quê:** o cursor e a ordem do Descobrir estão no SQL (`_chave` em `service_videos.py`). Uma
  expressão evita cache e trilha extra.
- **Alternativas:**
  - extensão `unaccent` (mais uma peça no PG e no e2e, e o `translate` basta);
  - classificar os vídeos-fonte pela IA (42 mil chamadas).

## R10. Diagnóstico e conferências

- **Decisão:**
  - **Sinais** (`diagnostico.py`, na leitura), cada um com o número:
    - `conta_nova`: < 30 dias desde a 1ª coleta, ou < 15 posts;
    - `muitos_no_dia`: > 3 posts no mesmo dia local;
    - `intervalo_curto`: < `contas.intervalo_min_minutos` do post anterior;
    - `fora_da_audiencia`: a hora da publicação fora das 6 horas de maior ganho do mapa da audiência da
      019 na conta (com ≥ 500 views atribuídas; senão, o sinal não é avaliado);
    - `repostagem`: o mesmo `video_fonte_id` ou trecho já publicado em outra conta, canal `sem_acordo` ou
      envio avulso;
    - `curto`: < 10 s;
    - `legenda_vazia`;
    - `hashtags_demais`: > 8.

    A conta fica "travada" pela regra do R4.
  - **Checklist fixo** em código (`CHECKLIST`): `restrito`, `nao_elegivel_para_voce`, `nao_original`,
    `privacidade`, `musica`, `diretrizes`, cada um com o texto do que conferir no app.
  - **Conferências:** `PUT /api/aprendizado/posts/{videoId}/conferencias/{item}` com `{resultado: ok |
    problema | nao_sei, nota?, version?}`. A tabela é `aprendizado_conferencias`, versionada com
    `history`. Não cria tarefa nem mexe em destino.
- **Por quê:** FR-048 a FR-050. O mapa de atividade dos seguidores da 022, quando existir, é mais fiel que
  o da audiência. Ele entra depois, sem mudar a regra (fica anotado como evolução).
- **Alternativas:** gravar os sinais (ficariam velhos; a 019 já calcula alertas na leitura).

## R11. Anonimização (016) cobre a 023

- **Decisão:** `metricas/anonimizar.py` ganha um passo para os vídeos da série:
  - `aprendizado_classificacoes.justificativa` e `sugestao_tema` → NULL; o tema e o estilo ficam, porque
    são categóricos;
  - `aprendizado_conferencias.nota` → NULL;
  - as análises que usaram posts da série têm as `hipoteses[].texto` e `contraste` trocados por
    "[removido: conta anonimizada]", mantendo `n` e os ids;
  - as decisões guardam só números e chaves.

  As séries anônimas nunca entram como exemplos (R8) nem nos posts enviados à IA (R5).
- **Por quê:** os textos derivam da legenda e da transcrição, que a 016 apaga ao anonimizar.
- **Alternativas:** apagar as linhas (viola "nada é apagado" e perde a estatística).

## R12. SPA

- **Decisão:**
  - **Rota:** lazy `/app/perfis/:id/aprendizado`, com `?aba=analise|temas|recomendacoes|diagnostico|ia`, a
    conta, a medida e o período na URL. O link fica na página do perfil, na aba "O que funciona" do
    analytics (com o perfil do filtro) e no detalhe do vídeo.
  - **Gráficos:** o componente `Grafico` da 019.
    - efeitos: Bar empilhado transparente (o intervalo), com Scatter (o ponto), em linhas por fator;
    - matriz hashtag × tema: Heatmap.

    Nenhum chart novo é registrado. Cada card segue FR-005, FR-006 e FR-008 da 019 (tabela alternativa,
    CSV, leitura e paleta).
  - **Editores:** temas (lista com juntar e arquivar), classificação (tema principal, secundários e estilo,
    com `NativeSelect`), cartão de recomendação (aceitar/rejeitar com AlertDialog e motivo), pedido de
    análise (estimativa com e sem quadros, e "Confirmar custo"). Polling de 5 s enquanto
    `estado ∈ {pendente, processando}`.
  - **Descobrir:** selo "tema cortado", contador "N ocultos por tema cortado", interruptor "mostrar temas
    cortados" (na URL) e motivo com tema.
  - **Assistente:** o registro mostra "Desempenho: perfil vN, conta vM, 3 exemplos" ou "sem bloco", e o
    resumo mostra as 3 finalidades novas (só dono).
  - **Agendamento:** a dica "Janela preferida: ter–qua, 18 h–21 h" vem das preferências efetivas (só
    leitura).
- **Por quê:** a 019 já resolveu gráfico, CSP, PWA (o chunk fora do precache) e acessibilidade.

## R13. Permissões, MCP e guardas

- **Decisão:**
  - **Leituras:** `RequireUser`. O custo e a estimativa são `null` para membro, e o servidor nem calcula.
  - **Escritas:** `RequireHumanOwner` (temas, taxonomia, classificação, decidir, preferências, análises,
    classificar pendentes, conferências). Membro recebe 403 `somente_dono`. `system:*` e token MCP
    recebem 403 `somente_humano`, com o evento de recusa registrado.
  - **MCP:**
    - as leituras (`aprendizado_temas_list`, `aprendizado_classificacoes_list`, `aprendizado_analise`,
      `aprendizado_recomendacoes`, `aprendizado_diagnostico`) viram tools de escopo `leitura`;
    - as análises da IA ficam em `FORA` ("IA paga ou dado de dono");
    - todas as escritas vão para `PROIBIDAS`.
  - **Guardas novas** em `test_constitution_guards.py`:
    1. `aprendizado/` não importa `publicacao`, `httpx`, `postagem.service`, `conteudos.agendamento` nem
       `envios.service_envios`;
    2. nenhuma rota `aprendizado_*` é DELETE, e nenhuma tem "tiktok" ou "youtube";
    3. toda rota de escrita depende de `require_human_owner`;
    4. `afinidade.py` e `canais/` não atribuem `direito` (varredura de AST, como a do "postado");
    5. a lista de trilhas passa a incluir `aprendizado` (o guarda é atualizado, não removido);
    6. GETs de `aprendizado/` não chamam `db.add`, `history.record` nem `commit` (por varredura e por teste
       de integração com contagem de versões).

## R14. Desempenho

- **Decisão:** um teste com 10× o volume (400 posts, 4.000 fotos, 30 temas, 400 classificações) exige
  análise e recomendações < 2 s. Outro, com 50 mil vídeos-fonte e 30 temas × 20 palavras, exige o
  Descobrir com afinidade ≤ +300 ms sobre o mesmo pedido sem afinidade.
- **Plano B:** a reamostragem cai de 400 para 200 e a lista de efeitos é guardada por requisição (sem
  cache entre requisições). Na afinidade, entra a tabela do R9.

## R15. Testes e fakes

- **Decisão:**
  - **Fake do Claude** (`tests/fakes/anthropic_fake.py`): responde os 3 schemas novos de forma
    determinística:
    - a taxonomia vem de palavras frequentes;
    - a classificação escolhe o 1º tema cujo nome aparece no texto;
    - a análise cria 2 hipóteses citando os 2 primeiros posts;
    - a instrução "id inválido" devolve um id fora do conjunto, para testar a recusa;
    - registra se recebeu blocos `image`.
  - **e2e:** o `openshorts-fake` (`/v1/messages`) ganha os mesmos casos.
  - **Semeadura:** `aprendizado_helpers.py` reaproveita `metricas_helpers.semear` e gera posts com temas,
    ganchos, hashtags coocorrentes, um viral, uma conta travada e uma repostagem.
  - **Quadros:** o teste usa um MP4 sintético gerado com `ffmpeg -f lavfi` (testsrc, 6 s) no HD efêmero
    da stack de teste, e o caso "HD fora" (sem marcador) → `hd_indisponivel`.
- **Por quê:** nenhum teste chama serviço real (CLAUDE.md, 006 e 008).
