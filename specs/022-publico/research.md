# Research: Público (022)

Decisões técnicas da 022. Cada item traz **Decisão / Por quê / Alternativas**. A evidência do formato vem
dos arquivos reais de @atavernanerd (exportados em 02/10/2026, interface em inglês; ver o Contexto da
spec), lidos só de cópias temporárias e **nunca** copiados para o repositório. A 022 só **acrescenta** ao
pacote `metricas/studio/` da 020 (research R1–R15 da 020).

## R1. Seções novas no `formato.py`: cabeçalhos, números e "sem dado"

- **Decisão:**
  - **`SINONIMOS`** ganha os campos novos (inglês confirmado; pt-BR provisório, com `provisorio=True`):

    | campo | inglês (confirmado) | pt-BR (provisório) |
    |---|---|---|
    | `genero` | Gender | Gênero |
    | `territorio` | Top territories | Principais territórios, Territórios |
    | `distribuicao` | Distribution | Distribuição |
    | `hora` | Hour | Hora |
    | `ativos` | Active followers | Seguidores ativos |
    | `espectadores` | Total Viewers | Total de espectadores, Espectadores |
    | `espectadores_novos` | New Viewers | Novos espectadores |
    | `espectadores_recorrentes` | Returning Viewers | Espectadores recorrentes |

  - **Seções pelo cabeçalho**, sempre com `dia` quando a seção é diária:
    - `genero` + `distribuicao` → `genero`;
    - `territorio` + `distribuicao` → `territorios`;
    - `dia` + `hora` + `ativos` → `atividade`;
    - `dia` + `espectadores` → `espectadores`.

    Elas **saem** de `OUTRAS_SECOES`; só o Conteúdo fica lá. `ORIENTACAO` passa a citar os 3 ZIPs
    aceitos (Visão geral, Seguidores e Espectadores).
  - **`ler_linhas(arquivo, cabecalho, linhas)`** é extraída do `ler` atual. O `ler` (CSV) continua com a
    mesma assinatura e chama a nova; a planilha (R2) também a usa. A identificação da posição passa a
    aceitar a célula (`Problema.celula`, opcional, ex.: "B4"), sem mudar os campos que já existem.
  - **"Sem dado"** só nas seções de público: `undefined` (sem caixa) e a célula vazia viram `None` nas
    colunas numéricas. Para elas, a "coluna obrigatória vazia" **não** é erro (o `undefined` real cai na
    coluna obrigatória `Total Viewers`). Nas colunas de chave (`dia`, `hora`, `genero`, `territorio`),
    vazio continua sendo erro. As seções da 020 não mudam: lá, `undefined` continua sendo "não é um número
    inteiro".
  - **Arquivo só com o cabeçalho:** nas 4 seções de público, `ler` devolve uma `Leitura` com
    `linhas = []` e `vazia = True` (campo novo), em vez do `studio_formato` "não tem nenhum dia" (que
    continua valendo para a Visão geral e os Seguidores).
- **Por quê:** os cabeçalhos reais confirmam as seções, e a tabela única continua sendo o único lugar a
  mexer quando chegar um arquivo em pt-BR. O `undefined` é um valor real do Studio (o 1º dia do
  `Viewers.xlsx`), e não um defeito do arquivo.
- **Alternativas:**
  - um leitor separado por seção: duplicaria as regras de linha, campo e número da 020;
  - tratar `undefined` como 0: mentiria no dado (FR-007);
  - recusar `undefined`: recusaria o arquivo real.

## R2. XLSX com a biblioteca padrão (`planilha.py`)

- **Decisão:** a função `planilha.ler(arquivo, dados) -> (cabecalho, linhas, celulas)` trabalha em memória,
  com `zipfile.ZipFile(BytesIO)` e `xml.etree.ElementTree.fromstring`.
  1. **Contêiner:** usa os limites da 020 (`ZIP_ENTRADAS = 20`, `ZIP_EXPANDIDO = 20 MB`,
     `ZIP_RAZAO = 100`, sem cifrado, método *stored* ou *deflate*), com uma variante de
     `_conferir_entrada` que **aceita subpastas relativas** (o XLSX tem `xl/worksheets/…`) e mantém a
     recusa de caminho absoluto, `\`, `..`, unidade e link. Também é recusado:
     - entrada `.zip` ou `.xlsx` dentro (não há segundo nível);
     - `vbaProject.bin` ou content-type de macro (`macroEnabled`): **macro**;
     - `xl/externalLinks/` ou `xl/connections.xml`: **link externo**;
     - um `.xls` antigo ou um XLSX cifrado (contêiner OLE, pela assinatura): "planilha antiga ou cifrada".
  2. **Partes abertas**, cada uma com teto de leitura: `[Content_Types].xml`, `xl/workbook.xml`,
     `xl/_rels/workbook.xml.rels`, a aba escolhida e `xl/sharedStrings.xml` (se houver). Nenhuma outra
     parte é aberta (estilos, tema e metadados ficam fechados).
  3. **XML seguro:** antes do parser, se os bytes de uma parte contêm `<!DOCTYPE` ou `<!ENTITY`, a planilha
     é recusada. O `expat` da stdlib não busca entidades externas, e sem DTD não há expansão de
     entidades. Assim se evita o *billion laughs* e o XXE sem defusedxml.
  4. **Aba:** é a que se chama `Viewers` (sem caixa; pt-BR provisório: `Espectadores`). Se não houver, mas
     o arquivo tiver **uma aba só**, vale ela. Fora isso, recusa ("a planilha não tem a aba Viewers"). As
     outras abas nunca são abertas. Recusa também `<workbookProtection>` e `<sheetProtection>`
     ("planilha protegida").
  5. **Células:** os tipos `t="str"` (o real), `t="s"` (texto compartilhado), `t="inlineStr"`, `t="n"`
     ou sem `t` (número) e `t="b"`. Uma célula com `<f>` (fórmula) dá recusa ("fórmula"). A posição vem de
     `r="B4"`, e linhas e colunas faltando viram vazio. Na coluna `Date`, um número inteiro entre 1 e
     2.958.465 é lido como número de série do Excel (base 1899-12-30) e convertido para `AAAA-MM-DD` antes
     de ir para as datas. Um número com casas decimais numa coluna de contagem continua sendo "não é um
     número inteiro".
  6. **Saída:** a função devolve as linhas como texto, e quem segue é o `formato.ler_linhas` (R1), com os
     problemas citando a célula ("B4").
- **Por quê:** o arquivo real é mínimo (1 aba, 32 células, todas `t="str"`, sem `sharedStrings`). Um leitor
  para esse subconjunto cabe em poucas dezenas de linhas, sem dependência nova (princípio VIII). As recusas
  cobrem tudo o que poderia executar, buscar fora ou mentir no valor (fórmula, macro, link, DTD).
- **Alternativas:**
  - openpyxl: dependência nova e bem maior que a necessidade;
  - pedir ao dono que converta para CSV: o Studio só oferece XLSX nessa seção, e converter à mão abre
    espaço para erro;
  - aceitar fórmulas lendo o valor em cache: o valor pode não bater com a fórmula, então é recusado.

## R3. Arquivos e envio (`arquivos.py`)

- **Decisão:**
  - `ler_envio` aceita **de 1 a 3** arquivos (mensagem: "Envie de 1 a 3 arquivos: os ZIPs da Visão geral,
    de Seguidores e/ou de Espectadores"). O teto de 5 MB por envio não muda.
  - `ENTRADAS` ganha `FollowerGender.csv`, `FollowerTopTerritories.csv`, `FollowerActivity.csv` e
    `Viewers.xlsx`. O `Content.csv` continua **nunca aberto**.
  - **ZIP de Espectadores** (`Viewers_<handle>.zip`): `datas.nome_zip` passa a reconhecer `Viewers` como
    seção `espectadores` (sai de `_OUTRAS`; o `Content` fica). A entrada `Viewers.xlsx` é lida com
    `read(teto + 1)` e entregue à `planilha.ler`: é o único aninhado aceito, com um nível só. A checagem
    "ZIP dentro do ZIP" continua valendo para `.zip`.
  - **XLSX solto:** um arquivo cuja assinatura é ZIP e que tem `[Content_Types].xml` deixa de ser recusado.
    Ele vai para a `planilha.ler` e vira um `Csv` lógico (`entrada = "Viewers.xlsx"`, `sha` dos bytes do
    XLSX). O `.xls` (OLE) continua recusado, com orientação.
  - Um `Arquivo` pode ter até 4 entradas lidas (Seguidores). A regra "cada seção no máximo uma vez por
    envio" vale por seção (R1), não por arquivo.
- **Por quê:** é o mínimo para aceitar os dois ZIPs reais sem afrouxar as proteções da 020.
- **Alternativas:**
  - aceitar ZIP aninhado em geral: abriria a porta a *bombs* em cascata sem necessidade;
  - extrair o XLSX para disco: proibido (020, FR-011).

## R4. Datas da atividade e dos espectadores; data da foto

- **Decisão:**
  - **Espectadores:** um dia por linha, como a Visão geral. As regras de `datas` da 020 valem iguais
    (crescente, salto ≤ 60, hoje ignorado, futuro é erro).
  - **Atividade:** cada dia aparece até 24 vezes (uma por hora). Os **dias distintos, na ordem da 1ª
    aparição**, passam por `deduzir`/`pelo_nome`/`mesmo_mapa` como uma lista de dias. Assim, a ordem das
    linhas pode ser por dia ou por hora. Um mesmo par (dia, hora) repetido com o mesmo número conta uma
    vez; com números diferentes, é erro. A hora é um inteiro de 0 a 23; também são aceitos `"5"`,
    `"05"`, `"5:00"` e `"05:00"`, e o resto é erro.
  - **Âncora do ano** (ordem): Visão geral (nome do ZIP) → Seguidores (`mesmo_mapa` com a Visão geral, ou
    `deduzir`) → Espectadores → Atividade (as duas por `mesmo_mapa` com a 1ª seção já resolvida que contém
    todos os dias e meses, ou `deduzir`). O `anoOrigem` de cada seção segue a regra da 020 (`nome_zip` ou
    `deduzido`; `misto` na importação).
  - **Data da foto** (FR-012, resposta A): se o **mesmo ZIP** trouxe o `FollowerHistory.csv` com dias, a
    data é `min(último dia do FollowerHistory + 1, hoje)`, com origem `historico`. Isso vale mesmo quando o
    `FollowerHistory.csv` já foi importado antes (idempotente): ele é lido do mesmo jeito. Senão, a data é
    `hoje` (no `APP_TZ`), com origem `importacao` e o aviso `data_foto_importacao`.
- **Por quê:** a atividade é a única seção com chave composta. Deduzir o ano pelos dias distintos reaproveita
  a regra testada da 020. A data da foto pelo `FollowerHistory.csv` é determinística e caiu no dia certo no
  arquivo real (01/10 + 1 = 02/10, o dia do download).
- **Alternativas:**
  - exigir a atividade ordenada por dia: frágil, porque o formato com dados ainda não foi visto;
  - data da foto = dia da importação sempre: rejeitada pelo dono (resposta A).

## R5. Seções vazias

- **Decisão:**
  - Uma seção de público com `Leitura.vazia` aparece na prévia em `publico[]` com `vazia = true` e a
    mensagem de FR-006. Ela não entra nas linhas do Redis.
  - Na confirmação, as seções vazias do envio vão para `secoes_vazias` da importação criada. Se a
    importação não é criada (tudo idempotente), nada é anotado.
  - Se **todas** as seções do envio vierem vazias, a prévia recusa com **400 `studio_sem_dados`**: "Os
    arquivos vieram sem dados de público: a TikTok libera esses dados quando a conta tem mais seguidores
    (cerca de 100). Reimporte quando a conta crescer." O `details` traz a lista de seções.
  - **Estado "veio vazia"** (FR-026, FR-028): por série e seção, a importação ativa mais recente que tem
    a seção em `secoes_vazias`, desde que ela seja **mais nova** que a última importação ativa que trouxe
    dado daquela seção.
- **Por quê:** o caso real comum (ZIP de Seguidores com o histórico preenchido e o resto vazio) fica
  registrado sem gravar observações falsas, e o estado vazio da aba tem o motivo certo.
- **Alternativas:**
  - gravar uma importação só de vazias: criaria importação sem dado nenhum, e confundiria a lista e o
    desfazer;
  - não anotar nada: a aba não saberia dizer "veio vazia" e diria só "nenhuma importação".

## R6. Modelo: ampliar a importação e 3 tabelas só de inserção

- **Decisão:**
  - **`metricas_studio_importacoes`** (aditiva):
    - `sha_genero`, `sha_territorios`, `sha_atividade` e `sha_espectadores`;
    - `data_foto` e `data_foto_origem`;
    - `secoes_vazias text[]`.

    Os CHECKs `ck_studio_imp_secoes` (1 a 6 seções no conjunto ampliado) e um `ck_studio_imp_sha_publico`
    novo são trocados ou criados. Há índices parciais de SHA por seção nova, como os da 020.
  - **3 tabelas novas**, todas com trigger `metricas_*_so_insercao` (a função `metricas_recusa_mudanca`
    da 0011):
    - `metricas_studio_distribuicoes`: (importação, série, tipo, data da foto, rótulo, %);
    - `metricas_studio_atividade`: (importação, série, dia, hora, ativos);
    - `metricas_studio_espectadores`: (importação, série, dia, total, novos, recorrentes).
  - **`metricas_studio_dias` não muda** (nem colunas nem CHECKs).
- **Por quê:**
  - cada seção tem uma chave diferente (foto, dia e hora, dia), e tabelas separadas deixam os CHECKs
    simples;
  - a tabela da 020 e o `studio_dias.csv` do dataset ficam intactos;
  - uma importação só mantém um desfazer e uma lista.
- **Alternativas:**
  - colunas novas em `metricas_studio_dias`: quebraria o CHECK `tem_X = (X IS NOT NULL)` com o "sem
    dado", e mudaria o arquivo exportado da 020;
  - uma tabela genérica chave-valor: perderia os CHECKs por tipo e complicaria as consultas;
  - uma entidade de importação separada para o público: dois desfazer para o mesmo envio.

## R7. Valor efetivo e leitura derivada (`efetivo.py`)

- **Decisão:** funções novas, só de leitura, no mesmo padrão `DISTINCT ON … ORDER BY criada_em, id` da
  020 (a importação **ativa** mais antiga vale):
  - `fotos(db, serie_ids, tipo, ate=None)`: por (série, tipo, data da foto), os rótulos da foto efetiva;
  - `foto_valida(fotos, fim)`: a de maior data ≤ `fim`, com `anterior_ao_periodo = data < inicio`;
    `comparacao = foto_valida(fotos, inicio − 1 dia)` quando é **outra** data (FR-016, resposta A);
  - `atividade(db, serie_ids, de, ate)`: por (série, dia, hora);
  - `espectadores(db, serie_ids, de, ate)`: por (série, dia);
  - `ultimo_dia_atividade(db, serie_ids)`: para o atalho de FR-017;
  - `vazias(db, serie_id)`: R5.
- **Por quê:** é a mesma regra de precedência da 020, e o analytics continua importando daqui (nunca o
  contrário).
- **Alternativas:**
  - materializar os efetivos: o volume é pequeno, e o cálculo na hora fica sempre certo depois de um
    desfazer.

## R8. Prévia e confirmação

- **Decisão:**
  - **Prévia:** `PreviaStudio` ganha `publico: SecaoPublicoPrevia[]` (aditivo; `secoes` continua só com
    as da 020). Cada item traz:
    - `secao`, `vazia`, `jaImportada`, as contagens, a amostra e os avisos;
    - nas fotos, `dataFoto`, `dataFotoOrigem`, a distribuição e a `situacao` (`novo`, `igual` ou
      `divergente` contra a foto efetiva da mesma data);
    - na atividade, o `pico` (dia, hora e ativos) e as faixas de dias.

    O `periodo` passa a cobrir também os dias e as datas de foto das seções de público. O `podeConfirmar`
    fica verdadeiro se há qualquer seção (da 020 ou de público) nova e com linhas.
  - **Avisos novos:**
    - `data_foto_importacao`;
    - `espectadores_soma` (FR-010: dias em que o total é diferente de novos + recorrentes);
    - `sem_dado` (contagem de `undefined` por seção);
    - `secao_vazia`.

    Os avisos que já existem (`dia_incompleto`, `dias_faltando`, `ano_deduzido`, `cabecalho_provisorio`)
    passam a valer também para atividade e espectadores. O `diverge_da_coleta` **não** se aplica (a API não
    tem esses dados).
  - **Redis:** o estado da 020 ganha `publico: {genero|territorios: {sha, dataFoto, dataFotoOrigem,
    itens}, atividade: {sha, anoOrigem, linhas}, espectadores: {sha, anoOrigem, linhas}}` e `vazias: [...]`.
    A `base` não muda (ela já pega qualquer importação ou desfazer na série).
  - **Confirmar:**
    - as seções com o mesmo SHA de uma ativa saem, como na 020, agora pelo dicionário
      `SHA = {secao: coluna}` ampliado;
    - a importação recebe as `secoes` novas, os SHAs, `data_foto`/`data_foto_origem` (quando há foto) e
      `secoes_vazias`;
    - `periodo_de`/`periodo_ate` = mínimo e máximo de todos os dias e datas de foto gravados;
    - `ano_origem`: das seções diárias gravadas (regra da 020). Com só fotos gravadas, vale o `anoOrigem`
      do `FollowerHistory.csv` usado na data (origem `historico`), ou `deduzido` (origem `importacao`);
    - `gravados` = total de **linhas** inseridas em todas as tabelas;
    - o `history.record("created")` ganha `details.publico` com as seções e as contagens, sem rótulos,
      nomes ou handle.
- **Por quê:** é só acréscimo na prévia e no confirmar da 020, então o SPA atual continua funcionando
  enquanto a parte nova é feita.
- **Alternativas:**
  - misturar as seções de público em `secoes[]`: obrigaria a mudar o `totais` (união) e a `LinhaAmostra`
    da 020, quebrando o componente atual.

## R9. Analytics: rota `analytics_publico` e 3º mapa

- **Decisão:**
  - **`GET /api/analytics/publico`** (`operation_id="analytics_publico"`, `RequireUser`, o `FiltroDep` da
    019). A resposta `PublicoOut` traz o `contexto` (019) e `contas[]`, uma por conta do filtro, na ordem
    de `ordem_contas`, com o rótulo de conta anônima da 019. Cada conta tem:
    - `genero` e `territorios`: a foto válida, a data, `anteriorAoPeriodo`, a comparação em p.p., a
      `importacaoId` e os seguidores na data da foto (o `seguidores` efetivo da 020 no dia anterior à foto,
      quando houver). Nos territórios, `outrosPct = 100 − Σ`;
    - `atividade`: 168 células `{dia, hora, valor = média, n, amostraPequena}`, com `diasComDado` e
      `ultimoDiaComDado`;
    - `espectadores`: a série diária e os 3 indicadores. O `novos` é a soma; `mediaTotal` e
      `mediaRecorrentes` são médias sobre os dias com valor. Cada um traz o anterior, a `variacaoPct` e o
      `n` (dias). A comparação é com o período anterior da 019;
    - `motivos`: por card, `sem_importacao`, `veio_vazia` ou `sem_dado_no_periodo`.
  - **Constantes:** `MIN_DIAS_CELULA = 2` (FR-025) em `analytics/publico.py`. A `TOLERANCIA_GENERO = 2.0`
    p.p. é da leitura e fica em `metricas/studio/publico.py` (R1, R14). Os dois módulos `publico.py` são de
    pacotes diferentes: o de `studio/` lê arquivos, e o de `analytics/` monta a aba.
  - **Dia da semana** da atividade: é o dia de calendário do arquivo (0 = segunda, como o `CelulaMapa` da
    019); a hora é a do arquivo (R13).
  - **"Quando postar":** `QuandoPostarOut` ganha `atividadeSeguidores: AtividadeQuandoPostar` (aditivo),
    com o mesmo cálculo das contas do filtro. Com várias contas, vem a lista por conta, e o SPA usa um
    seletor local, na ordem de contas.
  - **MCP:** `analytics_publico` entra em `mcp/mapa.py` como tool de **leitura** ("Analytics: público"), como
    as outras rotas do analytics. Não há rota nova de escrita.
- **Por quê:** é uma rota por aba, como na 019. O mapa reaproveita a forma da célula da 019, então o
  `MapaSemana` do SPA serve sem mudança de componente.
- **Alternativas:**
  - campos de público na `visao_geral`: misturaria abas e pesaria a rota mais usada;
  - somar a atividade de contas diferentes: o mesmo seguidor pode estar nas duas, e a soma confunde
    (FR-022).

## R10. Cobertura e exportação

- **Decisão:**
  - **Cobertura:** `Cobertura` ganha `publico: CoberturaPublico` (aditivo), com:
    - `fotos[] {tipo, dataFoto, importacaoId}`;
    - `atividade {faixas, buracos}` e `espectadores {faixas, buracos}`, em dias, calculados como as faixas
      da 020;
    - `vazias[] {secao, em}` (R5).
  - **Exportação:** `metricas/export.py` ganha `studio_distribuicoes.csv`, `studio_atividade.csv` e
    `studio_espectadores.csv`, só das importações ativas, com `importacao_id` e `efetivo` (a linha é a que
    vale). O `dicionario.py` passa a `DICIONARIO_VERSAO = 3`, com as colunas novas no fim do dicionário
    (regra de evolução já documentada). O filtro de período da exportação vale pelo `dia` e pela
    `data_foto`.
- **Por quê:** completa a US5 com o padrão da 020 (FR-022 e FR-023 de lá).
- **Alternativas:**
  - um CSV único de público: as colunas são diferentes por seção.

## R11. Anonimização

- **Decisão:** **nenhuma mudança de código**. As tabelas novas não têm identificador: só números, dia, hora,
  o rótulo de gênero normalizado e o rótulo de território como veio. O `nomes_arquivos` da importação já é
  anulado pela 020. Um teste novo garante que, depois de `anonimizar.serie`, os 3 conjuntos continuam lá e
  sem nenhum texto com o @, e que a aba Público mostra "Conta anônima N".
- **Por quê:** FR-019. Território e gênero não identificam a conta.
- **Alternativas:**
  - apagar o público ao desconectar: contradiz a 016 (anonimizar, não apagar).

## R12. SPA

- **Decisão:**
  - **Aba:** `ABAS_ANALYTICS` ganha `"publico"` logo depois de `"quando-postar"` (rótulo "Público").
    `abas/Publico.tsx` traz os 4 cards no `CardAnalytics` (título, como ler, tabela, CSV e amostra).
  - **Distribuições:** `components/analytics/Distribuicao.tsx`, com **barras horizontais de um tom só**
    (a cor de magnitude da paleta da 019), rótulo e % em texto ao lado da barra e a mudança em p.p. com
    ▲/▼ e texto. Não usamos uma cor por gênero (evita estereótipo e não depende de cor para ler). Com
    várias contas, aparecem em pequenos múltiplos, um por conta, com a cor fixa da conta só no título.
  - **Mapa:** o `MapaSemana` da 019 (sequencial de um tom, célula com amostra pequena marcada). A nota diz
    "horas conforme a TikTok" e "fonte: TikTok Studio".
  - **Espectadores:** linhas por conta (cores fixas) e barras empilhadas novos × recorrentes, com os
    indicadores no topo. O "sem dado" é um buraco na linha (`null`), nunca zero.
  - **Quando postar:** o 3º `MapaSemana`, "Seguidores on-line (TikTok Studio)", com estado vazio e atalho.
  - **Atalho de período** (FR-017): `estado.setPeriodo(ultimo − 6, ultimo)`.
  - **Histórico do Studio:**
    - `EnvioArquivos` passa a aceitar até 3 arquivos e `.xlsx`;
    - `PreviaStudio` mostra os blocos de público (as vazias com a explicação);
    - `CoberturaBarras` mostra as fotos (marcos) e as faixas de atividade e espectadores.
- **Por quê:** reaproveita os componentes da 019 e da 020, e segue as regras de acessibilidade e de
  paleta da 019 (FR-005 a FR-008).
- **Alternativas:**
  - pizza para o gênero: pior de ler e de comparar entre fotos e contas.

## R13. Fuso da atividade

- **Decisão:** gravar o **dia e a hora como vieram** e mostrar a nota "horas conforme a TikTok". A
  constante `FUSO_ATIVIDADE = None` (= "como veio") fica em `publico.py`. Se um arquivo real mostrar que as
  horas estão em UTC, ela vira `"UTC"` e a conversão para `APP_TZ` acontece **na leitura do analytics**,
  sem migrar dado.
- **Por quê:** o arquivo não traz fuso, e os 3 CSVs reais vieram vazios. Converter às cegas poderia
  deslocar o mapa inteiro.
- **Alternativas:**
  - assumir UTC agora: sem evidência; a única fonte que fala de UTC (notas da 020, [1]) é de terceiros e
    trata da Visão geral.

## R14. Provisórios e conferência com arquivo real

- **Decisão:** ficam marcados como provisórios, com um teste que os lista (como o `provisorios()` da 020):
  - os sinônimos pt-BR das seções novas;
  - os rótulos de gênero aceitos: `Male`/`Female`/`Other` e os sinônimos `Masculino`/`Feminino`/`Outro`
    e `Homem`/`Mulher`;
  - os formatos de %: `"52%"`, `"52"`, `"52.3"`, `"52,3"` e a fração `"0.52"`. O formato é decidido por
    arquivo: se algum valor tem `%`, todos são %; se não, com o máximo ≤ 1 e a soma ≤ 1 + tolerância, é
    fração; com o máximo entre 1 e 100, é %. Um arquivo que mistura `%` com valores sem `%` é recusado;
  - o formato da hora (R4).

  A pendência de conferir com um arquivo real fica no quickstart §6.
- **Por quê:** os arquivos reais de público vieram vazios. Uma recusa clara é melhor que uma leitura
  errada, e o ajuste é uma linha.
- **Alternativas:**
  - esperar uma conta passar de 100 seguidores para especificar: atrasaria os espectadores, que já têm
    dado real.
