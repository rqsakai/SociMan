# Research: Histórico do TikTok Studio (020)

Decisões técnicas da 020. Cada item traz **Decisão / Por quê / Alternativas**. A evidência do formato está
em [notas-pesquisa.md](notas-pesquisa.md) (arquivo real de @atavernanerd, 2026-10-02). Os volumes são do
banco de dev em 2026-10-02:
- 2 séries: @atavernanerd (1ª coleta em 30/09 14:58 −03, 43 vídeos) e @meusqueridinhos10 (1ª coleta em
  01/10 18:11 −03, 89 vídeos desde 05/2025);
- um arquivo do Studio tem de 7 a 60 linhas (talvez 365).

## R1. Leitor de CSV: biblioteca padrão, cabeçalho por sinônimos

- **Decisão:** usar `csv` da biblioteca padrão, com o texto decodificado como **`utf-8-sig`** (tira o BOM).
  Se a decodificação falhar, recusa com `studio_formato`, sem tentar outra codificação.
  - **Seção:** é identificada **pelo cabeçalho**, e não pelo nome do arquivo. Cada cabeçalho passa por
    `ia.guia.normalizar` (NFKD, sem acento, `casefold`) e é procurado em `SINONIMOS` (`studio/formato.py`),
    uma tabela `campo → {aliases}`:

    | campo | inglês (confirmado) | pt-BR (provisório, R15) |
    |---|---|---|
    | `dia` | Date | Data |
    | `views` | Video Views | Visualizações de vídeo, Visualizações do vídeo |
    | `visitas_perfil` | Profile Views | Visualizações do perfil, Visitas ao perfil |
    | `likes` | Likes | Curtidas |
    | `comments` | Comments | Comentários |
    | `shares` | Shares | Compartilhamentos |
    | `seguidores` | Followers | Seguidores |
    | `seguidores_dif` | Difference in followers from previous day | Diferença de seguidores em relação ao dia anterior |

    `dia` + `views` = **visão geral**; `dia` + `seguidores` = **seguidores**. Um cabeçalho com `Hour`,
    `Gender`, `Top territories` ou um conjunto sem as obrigatórias dá `studio_secao_nao_importada`, com o
    nome da seção quando reconhecida (Conteúdo: `Video title`/`Post time`, Atividade, Gênero,
    Territórios).
  - **Números:** os inteiros são lidos depois de tirar espaços. O separador de milhar é aceito só no
    padrão `^\d{1,3}([.,]\d{3})+$`. Ficam de fora decimais, `K`/`M`, vazio em coluna obrigatória e
    negativo (exceto `seguidores_dif`). Um vazio em coluna opcional vira `NULL`.
  - **Linha:** linha totalmente vazia é ignorada. Linha com número de campos diferente do cabeçalho é
    erro.
- **Por quê:** o arquivo real é CSV simples, e a biblioteca padrão basta (princípio VIII). Identificar
  pelo cabeçalho funciona também com CSV solto ou renomeado. A tabela de sinônimos é o único lugar a mexer
  quando o dono exportar em pt-BR.
- **Alternativas:**
  - pandas: dependência grande para 60 linhas;
  - detectar a seção pelo nome do arquivo: o navegador renomeia ("(1)"), e o CSV solto perde o contexto;
  - aceitar XLSX via openpyxl: dependência nova sem caso real (Clarifications, ajustes).

## R2. ZIP lido em memória, com limites

- **Decisão:** cada arquivo do envio é lido do `UploadFile` com teto. A requisição tem no máximo
  **5 MB** no total (`read(limite + 1)`; passou, 413 `arquivo_grande`). Um ZIP (assinatura `PK\x03\x04`,
  não pela extensão) é aberto com `zipfile.ZipFile(BytesIO(...))`, **sem `extract`**. Ele é recusado
  com 400 `studio_zip_inseguro` se:
  - tem mais de **20 entradas**;
  - a soma de `file_size` passa de **20 MB**, ou uma entrada tem razão de compressão acima de 100:1;
  - tem nome com `/` inicial, `\`, `..`, letra de unidade, pasta, link simbólico (`external_attr`
    S_IFLNK), entrada `.zip` ou cifrada (`flag_bits & 0x1`);
  - usa método diferente de *stored* ou *deflate*.

  Só são abertas as entradas cujo nome-base é `Overview.csv` ou `FollowerHistory.csv`, lidas com
  `open().read(teto + 1)` para não confiar no cabeçalho do ZIP. As outras são listadas como "ignoradas"
  e **nunca abertas** (o `Content.csv` traz títulos e links). Um ZIP sem nenhuma das duas dá
  `studio_secao_nao_importada`.
- **Por quê:** é a defesa contra *zip bomb*, *zip slip* e conteúdo indesejado sem tocar no disco. Assim,
  nada vai para o HD e a regra do marcador `.sociman-volume` não se aplica (R4). O ZIP real tem 5
  entradas na raiz, sem compressão e com ~1 KB.
- **Alternativas:** extrair para o `work/` do HD (desnecessário e cria arquivo identificável para
  apagar); confiar só na extensão (um `.csv` renomeado de ZIP passaria).

## R3. Ano das datas e conferência do @

- **Decisão:** em `studio/datas.py` (funções puras):
  - **Nome do ZIP:** `^Overview_(\d{4}-\d{2}-\d{2})_(\d{9,11})_([A-Za-z0-9._]{2,24})(?: \(\d+\))?\.zip$`
    e `^Followers_([A-Za-z0-9._]{2,24})(?: \(\d+\))?\.zip$`, sem caixa. O sufixo " (1)" do navegador é
    aceito. O handle vai para `normalizar_handle` (sem `@`, `casefold`), igual ao `contas.handle`.
  - **Datas aceitas:**
    - "September 25" e "Sep 25", com os meses em inglês;
    - "25 de setembro", "setembro 25" e "25 set", com os meses em pt-BR (provisório);
    - `AAAA-MM-DD` e `DD/MM/AAAA` (com ano, sem dedução).
  - **Ano pelo nome do ZIP da Visão geral:** o `início` do nome é o 1º dia (dia e mês têm de bater com a
    1ª linha). Os seguintes avançam o ano quando o mês volta (dez → jan). O fim é
    `date(fromtimestamp(epoch, APP_TZ))`, e o último dia do arquivo tem de ser **igual** a ele. Se
    divergir, o envio é recusado com `studio_datas` ("o nome do ZIP não bate com as datas do arquivo").
  - **Seguidores no mesmo envio:** se as datas sem ano coincidem com as da visão geral (a mesma sequência
    de dia e mês), usam o mesmo mapa de anos. Se não coincidem, vale a dedução abaixo, e a
    pré-visualização marca "ano deduzido".
  - **Dedução:** o último dia é a ocorrência mais recente daquele dia e mês com data ≤ hoje
    (`APP_TZ`). Os anteriores recuam e diminuem o ano quando o mês sobe. Precisam estar em ordem
    estritamente crescente, sem salto de 366 dias ou mais. Se não, recusa com `studio_datas`.
  - **Hoje:** uma linha com dia = hoje é ignorada (aviso `dia_incompleto`). Dia > hoje é erro.
  - **@:** o handle de cada ZIP tem de ser igual ao da conta (403 seria enganoso, então é 400
    `studio_conta_diferente`). Dois ZIPs com handles diferentes também dão esse erro. Num envio sem ZIP,
    `exigeConfirmacaoConta = true`, e confirmar sem `confirmoConta: true` dá 400 `confirmar_conta`.
- **Por quê:** o arquivo real não tem ano nem @ no conteúdo, e o nome do ZIP é a única âncora confiável.
  A dedução cobre o CSV solto. Como a pré-visualização mostra o período com o ano, o dono confere.
- **Alternativas:** pedir o ano ao dono (atrito, e erra na virada de ano); usar a data de modificação
  do arquivo (o navegador não a envia de forma confiável).

## R4. Pré-visualização efêmera no Redis, de uso único

- **Decisão:** `POST …/studio/previa` lê os arquivos, valida tudo e grava o resultado da leitura (as
  linhas normalizadas, os hashes e as contagens, poucos KB) no Redis:
  - chave `studio:previa:<uuid>` em JSON, com **TTL de 30 min**;
  - junto vão `user_id`, `conta_id`, `serie_id` e a **base**, a impressão do estado da série no momento:
    `ids` das importações ativas, a versão de cada uma e o dia da 1ª coleta.

  O confirmar faz `GETDEL` (atômico; o 2º clique não acha nada e recebe 410 `previa_indisponivel`).
  Depois, confere o dono e a conta e recalcula a base sob `pg_advisory_xact_lock(hashtext('studio:' ||
  serie_id))`. Se a base mudou, responde 409 `previa_desatualizada`. Cancelar é só não confirmar: o
  SPA descarta, e o TTL limpa. **Nenhum arquivo é gravado em disco ou no MinIO.**
- **Por quê:**
  - a pré-visualização é estado efêmero, que é o papel do Redis na constitution. Há precedente: o `state`
    do OAuth da 015 (`publicacao/conexoes.py`, `SET` com TTL + `GETDEL`). Se o Redis se perder, o dono só
    reenvia;
  - evita tabela de rascunho no PG e arquivo no HD;
  - o `GETDEL` mais o lock por série resolvem os dois cliques e as duas abas sem coluna nova.
- **Alternativas:**
  - arquivo temporário no `work/` do HD: exige limpeza, marcador e piso, e grava o @;
  - tabela `studio_previas` no PG: um domínio que não é domínio;
  - confirmar reenviando o arquivo (sem estado): o dono teria de escolher os arquivos duas vezes.

## R5. Modelo: importação versionada e dias só de inserção

- **Decisão:** duas tabelas novas no PostgreSQL, na migration `0013_historico_studio` (data-model.md):
  - **`metricas_studio_importacoes`:** tem `version` e histórico (`entity_type =
    "studio_importacao"`). O estado vai de `ativa` para `desfeita`. Os hashes SHA-256 por seção são de
    **cada CSV** (os bytes da entrada, não do ZIP: re-zipar não muda nada). `nomes_arquivos` é texto
    fora dos campos versionados.
  - **`metricas_studio_dias`:** uma linha por (importação, dia), com as colunas das duas seções, nulas
    quando a seção não veio. É só de inserção e reaproveita a função `metricas_recusa_mudanca()` com um
    trigger novo.

  Uma importação grava **todos** os dias válidos do envio, inclusive os sobrepostos. Quem decide o que
  vale é a leitura (R6). Por isso desfazer uma importação mais antiga faz a próxima valer (US4.3) sem
  regravar nada.
- **Idempotência:** sob o lock da série, uma seção cujo hash é igual ao de uma importação **ativa** da
  mesma série e seção é descartada do envio. Se todas as seções forem descartadas, o confirmar responde
  **200** com a importação existente e `gravados = 0`, sem criar linha nem versão (FR-014).
- **Por quê:**
  - mantém o padrão da 016 (observações só de inserção, e o histórico fica na entidade que as
    agrupa);
  - não mexe nas fotos da API;
  - uma tabela de dias com as duas seções fica mais simples que uma por seção. Uma importação só da
    visão geral deixa as colunas de seguidores nulas.
- **Alternativas:**
  - gravar como `metricas_conta_fotos` com `fonte = 'studio'`: a semântica é outra (total no instante ×
    valor do dia), e o `uq (serie_id, janela_em)` misturaria as fontes;
  - não gravar os dias sobrepostos: quebraria o US4.3;
  - versionar cada dia: centenas de versões sem valor.

## R6. Valor efetivo e cobertura

- **Decisão:** `studio/efetivo.py` (só leitura) expõe duas funções:
  - **`primeiro_dia_coberto(db, serie_ids) → {serie: date | None}`:** `min(coletado_em)` das fotos de
    conta e de vídeo da série, convertido para o dia em `APP_TZ`, **mais 1 dia**. Sem coleta, é `None`
    (nenhum dia está coberto).
  - **`dias(db, serie_ids, de, ate) → {serie: {dia: DiaStudio}}`:** o valor efetivo por seção é o da
    importação **ativa mais antiga** (`criada_em`, depois `id`) que tem a seção naquele dia. Na prática,
    um `DISTINCT ON (serie_id, dia)` por seção, em `ORDER BY i.criada_em, i.id`, com `estado = 'ativa'`.

  Regra do dia (FR-013), por série:
  - **usa o Studio** se `dia < primeiro_dia_coberto` (ou não há coleta) **e** existe dado efetivo da
    seção;
  - senão, usa a API, como na 019 hoje. Sem Studio, nada muda (regressão zero).

  **Cobertura** (`GET …/studio/cobertura`): por seção, as faixas contínuas dos dias efetivos, a faixa da
  coleta (`primeiro_dia_coberto − 1` até hoje), a sobreposição e os buracos (dias sem nenhuma das duas
  fontes entre o 1º dia importado e hoje).
- **Por quê:** é a resposta 2 do dono mais o ajuste do "dia sem coleta" (Clarifications). O dia da 1ª
  coleta de @meusqueridinhos10 hoje mostra as views da vida inteira de 89 vídeos. Com o Studio, mostra o
  dia real.
- **Alternativas:** cortar no instante exato da 1ª coleta (o dia do Studio não tem hora); preferir o
  Studio sempre (contra a resposta 2).

## R7. Integração no analytics da 019

- **Decisão:** a soma por dia passa a ser a base dos totais da conta. Mudanças em `analytics/`:
  1. **`base.ganhos_por_dia`** passa a devolver os **4 contadores** (views, likes, comments, shares)
     por vídeo e por dia, com a mesma regra de delta. Hoje devolve só views. O `base.ganhos` por vídeo
     continua para os "principais" e as análises por vídeo (FR-020).
  2. Função nova **`base.totais_diarios(db, filtro, periodo) → {serie: {dia: TotalDia}}`**, com
     `TotalDia(views, likes, comments, shares, seguidores_dif, visitas_perfil, fonte, comparacao)`:
     - agrega os ganhos diários da API por série;
     - calcula o ganho diário de seguidores pela API (a última `FotoConta` antes do fim do dia menos a
       última antes do início);
     - em cada (série, dia), aplica a regra da R6 e guarda o valor da outra fonte em `comparacao`.

     As séries do escopo vêm do filtro (conta, perfil, rede), e não só dos vídeos. Assim, uma conta com
     Studio e sem vídeo coletado aparece.
  3. **`visao_geral.valores`** passa a receber os totais (Σ dos `TotalDia` do período) em vez do dicionário
     por vídeo:
     - views, likes e engajamento saem da soma;
     - seguidores = Σ `seguidores_dif` efetivo;
     - posts e mediana por post não mudam (por vídeo).

     O mesmo vale para o período anterior e para a tabela por conta e perfil e o eixo `crescimento`
     do radar (`contas.py`). Tudo usa `totais_diarios`, filtrado por série.
  4. **Schemas:**
     - `Indicador.dias_studio: int`;
     - `ViewsConta` ganha `fonte` (`coletado` ou `studio`), `comparacao: int | None` e
       `visitas_perfil: int | None`;
     - `DiaCalendario` ganha `fonte` (`coletado`, `studio` ou `misto`) e `contas_studio`;
     - `Contexto` ganha `studio: {dias, series}`, para a nota "Como ler".
  5. **Abas por vídeo ou hora** (Quando postar/audiência, O que funciona, Curvas, Alertas): sem
     mudança de cálculo. Quando o período tem `contexto.studio.dias > 0` e nenhum post coletado, a SPA
     mostra a nota de FR-020.

  `analytics/` **importa** `metricas.studio.efetivo` (só leitura), nunca o contrário. O guarda de "sem
  escrita" da 019 continua valendo.
- **Por quê:** os deltas diários se cancelam em sequência (Σ dos diários = delta do período). Assim, somar
  por dia dá o mesmo número de hoje sem Studio e permite trocar só os dias do Studio. Um único caminho
  serve aos indicadores, à série, ao calendário e às contas, e o SC-002 da 019 continua valendo.
- **Alternativas:** corrigir o total do período subtraindo os dias do Studio (dois caminhos de cálculo
  para manter); uma visão materializada (desnecessária no volume atual).

## R8. Desfazer, histórico e reversão (princípio VII)

- **Decisão:**
  - **Confirmar** grava `history.record(..., "studio_importacao", imp, "created", None, snap)`.
  - **Desfazer** (`POST /api/studio/importacoes/{id}/desfazer` com `version`) faz `check_version` e
    muda `estado`, `desfeita_em` e `desfeita_por`. Grava `"updated"` com `details = {acao: "desfeita"}`.
  - **Snapshot:** `estado`, `secoes`, `periodo_de`, `periodo_ate`, `contagens`, `sha_visao_geral`,
    `sha_seguidores`, `desfeita_em` e `desfeita_por`. **Sem nomes de arquivo nem handle** (FR-017).
  - **Sem rota genérica de revert:** desfazer **é** a reversão da importação, e a reversão do desfazer
    é importar de novo (FR-015). Os dias não têm `version` (observações).
- **Por quê:** o padrão é o mesmo da 016 (vínculo e anonimização historiados na entidade que agrupa) e da
  exceção aprovada para envio e corte na 006. A reversão continua possível, pelo caminho que preserva os
  dados.
- **Alternativas:** "refazer" que reativa a importação desfeita (mais um estado e mais um caso de
  conflito, sem ganho sobre reimportar).

## R9. Anonimização (016)

- **Decisão:** `metricas/anonimizar.serie` ganha um passo: `UPDATE metricas_studio_importacoes SET
  nomes_arquivos = NULL WHERE serie_id = :s`. Os dias não mudam (só números e dia). O `details` da
  anonimização ganha `importacoes: N`. A exportação mostra a série como "Conta anônima N", como as fotos.
- **Por quê:** o nome do ZIP é o único dado identificador da importação, e o histórico já nasce sem ele
  (R8).
- **Alternativa:** guardar os nomes em hash (inútil para o dono, que quer ler o nome).

## R10. Exportação do dataset (016)

- **Decisão:** o ZIP de `metricas/export.py` ganha `studio_dias.csv` (ou `.jsonl` no JSON), com uma
  linha por dia importado de importação **ativa**. Colunas:
  - identificação: `serie_ref`, `conta` (rótulo ou "Conta anônima N"), `dia`, `importacao_id` e
    `importada_em`;
  - visão geral: `views`, `visitas_perfil`, `likes`, `comments` e `shares`;
  - seguidores: `seguidores` e `seguidores_dif`;
  - `efetivo_visao_geral` e `efetivo_seguidores` (bool: se aquele valor vale pela R6).

  O dicionário (`metricas/dicionario.py`) ganha as entradas, e `DICIONARIO_VERSAO` vai de 1 para 2.
- **Por quê:** o dataset de ML recebe o histórico com a proveniência explícita (FR-023).
- **Alternativa:** misturar no `fotos_conta.csv` (semânticas diferentes).

## R11. Rotas, permissões e edge

- **Decisão:**
  - `POST /api/contas/{conta_id}/studio/previa` (multipart `arquivos`, de 1 a 2): **RequireHumanOwner**;
  - `POST /api/contas/{conta_id}/studio/importacoes` (JSON `previaId`, `confirmoConta`):
    **RequireHumanOwner**;
  - `POST /api/studio/importacoes/{id}/desfazer`: **RequireHumanOwner**;
  - `GET /api/contas/{conta_id}/studio/importacoes` e `GET /api/contas/{conta_id}/studio/cobertura`:
    **RequireUser**.

  Os `operationId` são `studio_*`. Não há "tiktok" em rota nem em `operationId` (guarda do princípio I).
  A recusa a um não humano grava o evento `publicacao_recusada` pelo `require_human_owner` da 015.
  O nome do evento fica igual porque é o mesmo guarda; o `details.rota` diz qual foi.
  O edge não muda: `/api/` aceita 8 MB, e a API corta em 5 MB.
- **Por quê:** é o mesmo dispositivo das ações só de dono humano. Desfazer fica fora da rota da conta
  porque a importação tem id próprio.
- **Alternativas:** evento novo `studio_recusado` (mais um tipo de evento para o mesmo guarda); `location`
  própria no nginx (desnecessária para 5 MB).

## R12. SPA

- **Decisão:**
  - **Página nova** `/app/contas/:id/studio` (`pages/perfis/ContaStudio.tsx`, fora da rota lazy do
    analytics, **sem ECharts**). A cobertura usa barras em CSS e tabela. A página tem:
    1. **Cobertura**, para todos;
    2. **Importar**, só para o dono: `<input type="file" multiple accept=".zip,.csv">`, um texto curto
       "No TikTok Studio → Analytics → Visão geral e Seguidores → Baixar dados (ZIP)" e o botão
       "Ler arquivos";
    3. **Pré-visualização:** período com o ano e a origem, contagens por seção, totais, colunas,
       avisos, amostra (tabela), caixa "confirmo que é de @conta" quando necessária,
       "Confirmar importação" e "Cancelar";
    4. **Importações**, uma tabela com "Desfazer" (AlertDialog, só dono).
  - **Links:** no cartão da conta TikTok (aba Contas do perfil, ao lado de "Guia") e na aba Contas do
    analytics ("Histórico do Studio"). Na Visão geral, um período antes da 1ª coleta mostra ao dono o
    atalho "Importar histórico do Studio".
  - **Analytics (ECharts):**
    - na série diária, cada conta vira **duas séries** ("@conta — coletado" e "@conta — Studio"), com
      `null` nos dias da outra fonte, a mesma cor de entidade e traço tracejado mais opacidade 0,6 no
      Studio;
    - o tooltip mostra a fonte e a `comparacao`, escapado (ADR 0002);
    - o calendário marca os dias `studio` e `misto` com contorno tracejado;
    - o `Indicador` mostra "inclui N dias importados do Studio";
    - tabela alternativa e CSV com a coluna `fonte`.
- **Por quê:** a importação é uma ação de conta, e não de análise. Ficar fora do chunk de gráficos mantém
  o SC-004 da 019.
- **Alternativas:** uma aba "Studio" dentro do analytics (misturaria escrita numa área só de leitura,
  FR-009 da 019).

## R13. Testes e fixtures sintéticas

- **Decisão:**
  - **Nada do arquivo real entra no repositório.**
    - `tests/integration/studio_helpers.py` monta, em memória, os ZIPs e CSVs **sintéticos** no formato
      real: BOM, aspas, sem `\n` final, datas "September 25", nome
      `Overview_2026-09-25_<epoch>_contateste.zip`, e as entradas extras FollowerActivity, Gender,
      Territories e um `Content.csv` com título falso, para provar que ele não é aberto.
    - Os números seguem o padrão do real (picos, zeros), mas são inventados.
    - O `.gitignore` ganha `Overview_*.zip`, `Followers_*.zip`, `Content_*.zip` e `Viewers_*.zip`.
  - **Unitários:**
    - `test_studio_formato.py`: sinônimos en e pt-BR, números, seções;
    - `test_studio_datas.py`: ano pelo ZIP, dedução, virada de ano, fora de ordem, hoje, futuro;
    - `test_studio_zip.py`: bomb, slip, link, cifrado, aninhado, entradas demais, Content não aberto.
  - **Integração:**
    - `test_studio_previa.py`: contagens, conflitos, base, @, confirmação de conta;
    - `test_studio_importacao.py`: tudo ou nada, idempotência, 2 cliques, base mudou, desfazer,
      histórico, trigger só de inserção, fotos da API intactas (SC-004);
    - `test_studio_permissoes.py`: membro, `system:*` e token de agente → 403, mais o evento;
    - `test_studio_analytics.py`: R6/R7 com referência (SC-005, SC-006) e regressão sem Studio igual
      à 019;
    - `test_studio_anonimizar.py` e `test_studio_export.py`;
    - `test_migration_0013`.
  - **Guardas** (`test_constitution_guards.py`): `metricas/studio/` não importa `publicacao`, `httpx` nem
    `minio`; as rotas de escrita usam `RequireHumanOwner`; nenhum `ZipFile.extract*` no pacote.
  - **e2e** (`e2e/studio.spec.ts`): o dono envia os ZIPs sintéticos (gerados pelo teste) → vê a
    pré-visualização → confirma → a série diária do analytics mostra os dias "Studio" → desfaz → os dias
    somem. O membro vê a cobertura sem o botão de importar.
- **Por quê:** princípio VI, com o dado real do dono fora do git (privacidade e anonimização).

## R14. Fuso e "hoje"

- **Decisão:**
  - "Hoje" é `date.today()` em `APP_TZ` (America/Sao_Paulo), e as datas do Studio são gravadas como
    `date`.
  - A divisão "dia coberto" usa o início do dia em `APP_TZ` (R6).
  - A nota de leitura diz: "os dias do Studio seguem o calendário da TikTok, que pode não ser o de
    Brasília".
- **Por quê:** o arquivo não diz o fuso (notas, seção 0). Num dado diário, a diferença possível é de
  poucas horas na borda.

## R15. Cabeçalhos em pt-BR provisórios

- **Decisão:** a tabela da R1 já traz os sinônimos em pt-BR **prováveis**, marcados como `provisorio=True`
  no código, com um teste que lista quais são. Quando o dono exportar com a interface em português, os
  sinônimos são conferidos e o marcador sai (uma tarefa de verificação manual no quickstart §6).
  Um cabeçalho desconhecido nunca é "adivinhado": dá `studio_formato`, com as colunas encontradas.
- **Por quê:** a resposta 1 pede pt-BR e inglês, mas só o inglês foi visto. O risco de um sinônimo errado
  é só a recusa, nunca uma leitura errada.
