# Feature Specification: Histórico do TikTok Studio (020-historico-tiktok-studio)

**Feature Branch**: `020-historico-tiktok-studio`

**Created**: 2026-10-02

**Status**: Draft

**Input**: User description: "A API pública da TikTok (Display API) só dá totais atuais, sem série histórica.
Preencher o banco com o histórico das 2 contas conectadas (@atavernanerd e @meusqueridinhos10) importando
o arquivo exportado do TikTok Studio (Analytics → baixar dados), que traz métricas diárias da conta (e
talvez por vídeo) dos últimos ~60 dias. Só o dono importa, com pré-visualização antes de confirmar; o
histórico importado é marcado com a fonte e nunca sobrescreve o coletado; reimportar é idempotente;
desfazer com histórico; o analytics (019) passa a usar a série diária importada, deixando claro o que é
importado e o que é coletado."

## Contexto

A 016 coleta as métricas pela API pública da TikTok desde a reconexão das contas (@atavernanerd em
30/09/2026; @meusqueridinhos10 em 01/10/2026). Essa API devolve só o total de agora (views acumuladas de
cada vídeo, seguidores da conta) e não tem nenhuma série do passado. Por isso o analytics da 019 começa
"do zero": a série diária, as comparações com o período anterior e os seguidores ganhos só existem a
partir da primeira coleta. Pior: no dia da primeira coleta, todas as views da vida de cada vídeo antigo
aparecem como "ganhas naquele dia".

O TikTok Studio, no desktop, deixa o dono **baixar os dados da conta**, uma seção por vez, cada uma num
ZIP. O formato foi conferido com um arquivo real de @atavernanerd exportado em 02/10/2026 (detalhes em
`notas-pesquisa.md`):
- **Visão geral** (`Overview_<início>_<fim>_<conta>.zip` → `Overview.csv`): uma linha por dia com views de
  vídeo, visitas ao perfil, curtidas, comentários e compartilhamentos **do dia**;
- **Seguidores** (`Followers_<conta>.zip` → `FollowerHistory.csv`): uma linha por dia com o **total** de
  seguidores e a diferença para o dia anterior. O mesmo ZIP traz demografia e atividade, que ficam fora;
- as datas vêm **sem ano** ("September 25") e o @ da conta só aparece no **nome do ZIP**.

Esta spec importa esses dois arquivos como uma **fonte separada** ("importado do Studio"), sem tocar no que
a API coletou, e faz o analytics usar esses dias onde não há coleta completa.

## Clarifications

### Session 2026-10-02

- Q: Que formato o importador aceita? → A: CSV e XLSX, com cabeçalho em pt-BR ou inglês reconhecido
  automaticamente; o formato é conferido com um arquivo real das contas antes do plano.
- Q: Num dia com dado do Studio e da coleta da API, qual vale? → A: vale a API; o Studio só preenche os
  dias sem coleta, e o valor importado aparece como comparação no tooltip.
- Q: O arquivo por vídeo (seção "Conteúdo") entra? → A: Não; fica fora desta spec.

### Ajustes depois do arquivo real (confirmado pelo dono em 2026-10-02)

- **Formato:** a exportação real vem em **ZIP por seção, com CSV dentro** (UTF-8 com BOM, tudo entre
  aspas). São aceitos o ZIP da Visão geral, o ZIP de Seguidores e os dois CSVs soltos, juntos ou
  separados. **XLSX não é aceito:** nenhuma das duas seções usadas vem em XLSX, e aceitá-lo exigiria uma
  dependência nova (princípio VIII). Um XLSX recebe a orientação de enviar o ZIP. Isso substitui o "CSV
  e XLSX" da primeira resposta.
- **Seguidores:** o total vem pronto no `FollowerHistory.csv`. Não há estimativa.
- **"Dia sem coleta"** (resposta 2): o Studio vale nos dias **anteriores à 1ª coleta e no próprio dia da
  1ª coleta** (o dia que a coleta não cobre inteiro). Nesse primeiro dia, a conta da API soma views da
  vida inteira dos vídeos antigos, e o Studio é o número certo.
- **Pré-visualização:** fica num estado efêmero por 30 minutos, é de uso único, e os arquivos
  enviados **nunca** são gravados em disco nem no armazenamento de arquivos.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Importar o histórico diário de uma conta (Priority: P1)

O dono baixa no TikTok Studio os ZIPs da Visão geral e de Seguidores, abre no SociMan a tela "Histórico do
Studio" da conta TikTok e envia os dois arquivos (ou só um). O SociMan lê e mostra uma
**pré-visualização** antes de gravar qualquer coisa:
- o período (com o ano deduzido);
- quantos dias serão gravados, quantos já existem e quantos coincidem com a coleta da API;
- os totais do período (views, curtidas, seguidores ganhos);
- uma amostra das linhas.

O dono confere e confirma; só então os dias entram no banco.

**Why this priority**: É o objetivo da spec: sem o histórico gravado, nada mais acontece.

**Independent Test**: Com os ZIPs sintéticos de teste (7 dias, conta de teste), enviar, conferir a
pré-visualização (período, contagens e totais iguais aos do arquivo), confirmar e verificar que os 7 dias
estão gravados com a fonte "Studio", ligados à conta e com o autor da importação.

**Acceptance Scenarios**:

1. **Given** o dono e os ZIPs válidos da Visão geral e de Seguidores, **When** ele envia os dois na tela da
   conta, **Then** vê a pré-visualização com o período, as seções lidas, o número de dias novos, já
   existentes e coincidentes com a coleta, e os totais, e nada é gravado até confirmar.
2. **Given** a pré-visualização aberta, **When** o dono confirma, **Then** os dias são gravados com a fonte
   "Studio", a importação aparece na lista da conta (quem, quando, seções, período, dias gravados) e o
   histórico registra o ato.
3. **Given** a pré-visualização aberta, **When** o dono cancela ou não confirma dentro do prazo, **Then**
   nada é gravado.
4. **Given** um membro ou um cliente que não é humano (IA, agente, MCP), **When** tenta pré-visualizar,
   confirmar ou desfazer, **Then** é recusado ("só o dono"), e a recusa a um não humano fica registrada.
5. **Given** os mesmos arquivos já importados e ativos, **When** o dono os envia de novo, **Then** a
   pré-visualização diz "já importado em <data> por <dono>", com 0 dias novos, e confirmar não grava nada.
6. **Given** um arquivo diferente cujos dias se sobrepõem a uma importação ativa da mesma conta, **When** o
   dono pré-visualiza, **Then** os dias repetidos com os mesmos números aparecem como "já importados", os
   de números diferentes como "divergentes (vale o anterior)", e só os dias novos passam a valer.
7. **Given** só o ZIP da Visão geral (ou só o de Seguidores), **When** o dono importa, **Then** só as
   métricas daquela seção são gravadas, e a outra pode vir depois noutra importação.

---

### User Story 2 - Conferir que o arquivo é da conta certa e está íntegro (Priority: P1)

Antes de mostrar a pré-visualização, o SociMan confere os arquivos e explica em pt-BR o que está errado:
- seção ou formato não reconhecido, colunas obrigatórias faltando;
- datas inválidas, fora de ordem ou futuras;
- números negativos ou não numéricos, dias repetidos;
- arquivo grande demais, vazio ou ZIP inseguro.

O @ do nome do ZIP tem de bater com a conta escolhida. Com CSV solto (sem @), o dono confirma
explicitamente que o arquivo é daquela conta.

**Why this priority**: Gravar dados da conta errada ou um arquivo mal lido estraga o histórico de vez (as
observações são só de inserção), e o desfazer não deve ser o caminho normal.

**Independent Test**: Enviar um conjunto de arquivos sintéticos com cada defeito e conferir que todos são
recusados com a mensagem e a linha/coluna certas, e que um ZIP de outra conta é barrado.

**Acceptance Scenarios**:

1. **Given** um CSV sem a coluna de data ou sem a coluna obrigatória da seção, **When** o dono envia,
   **Then** recebe "formato não reconhecido", com as colunas esperadas e as encontradas.
2. **Given** um arquivo com uma data futura, um número negativo ou um valor não numérico, **When** o dono
   envia, **Then** a importação inteira é recusada com a lista dos problemas (arquivo, linha, coluna e
   valor) e nada pode ser confirmado.
3. **Given** um ZIP com nome `…_outraconta.zip`, **When** o dono envia na conta @atavernanerd, **Then** é
   recusado com "o arquivo é de @outraconta, não de @atavernanerd".
4. **Given** um CSV solto, **When** a pré-visualização abre, **Then** o botão de confirmar só fica
   disponível depois que o dono marca "confirmo que este arquivo é de @<conta>".
5. **Given** um envio acima do tamanho máximo, ou um ZIP que se expande demais, tem caminhos estranhos ou
   arquivos em excesso, **When** o dono envia, **Then** é recusado sem ser lido, com o motivo.
6. **Given** um arquivo cujo último dia é hoje (dia incompleto), **When** a pré-visualização abre, **Then**
   o dia de hoje aparece como "ignorado: dia incompleto" e não é gravado.
7. **Given** dias da coleta da API em que os números do arquivo divergem muito do coletado, **When** a
   pré-visualização abre, **Then** aparece o aviso "os números não batem com a coleta; confira se o arquivo
   é desta conta", sem bloquear.
8. **Given** um ZIP de outra seção (Conteúdo, Espectadores) ou um XLSX, **When** o dono envia, **Then**
   recebe "esta seção não é importada; envie o ZIP da Visão geral ou de Seguidores".

---

### User Story 3 - O analytics usa o histórico importado (Priority: P1)

Depois da importação, o analytics (019) passa a mostrar os dias anteriores à coleta. A série diária de
views, os indicadores (views, curtidas, engajamento, seguidores ganhos), o calendário e a comparação com o
período anterior usam os dias importados onde a coleta não cobre o dia inteiro. Cada lugar que usa dado
importado diz isso:
- a série diária pinta os dias do Studio de outro jeito, com a legenda "importado do Studio" × "coletado";
- o indicador mostra "inclui N dias importados do Studio".

**Why this priority**: É o motivo do pedido do dono: ver a evolução das contas antes da 016, ter base de
comparação já agora e corrigir o pico falso do dia da primeira coleta.

**Independent Test**: Com 7 dias importados que terminam no dia da primeira coleta semeada, mais 3 dias de
coleta, abrir a visão geral com o período de 14 dias e conferir que:
- a série diária mostra os 10 dias com dado;
- os dias do Studio estão marcados;
- o dia da primeira coleta usa o valor do Studio;
- os indicadores batem com a soma de referência.

**Acceptance Scenarios**:

1. **Given** dias importados e nenhum coletado no período, **When** o dono abre a visão geral, **Then** os
   indicadores de views, curtidas, engajamento e seguidores ganhos vêm dos dias importados, com a nota
   "inclui N dias importados do Studio", e a comparação com o período anterior funciona.
2. **Given** um período que mistura dias importados e coletados, **When** a série diária aparece, **Then**
   cada dia mostra de que fonte veio (cor ou traço diferente, legenda e tooltip com a fonte), e a tabela
   alternativa e o CSV do card têm a coluna "fonte".
3. **Given** um dia inteiro coberto pela coleta e também pelo Studio, **When** o analytics o usa, **Then**
   vale a coleta, e o tooltip mostra o valor do Studio para comparação.
4. **Given** o dia da primeira coleta de uma série com Studio importado para esse dia, **When** a série
   diária aparece, **Then** o dia usa o Studio, e não o salto das views acumuladas.
5. **Given** análises que dependem de vídeo ou de hora (mapas por horário, audiência, curvas, dispersões,
   marcos), **When** o período tem só dias importados, **Then** elas continuam mostrando só o coletado e
   dizem que o Studio não traz dado por vídeo nem por hora.
6. **Given** uma importação desfeita, **When** o analytics recarrega, **Then** os dias dela deixam de
   aparecer.

---

### User Story 4 - Desfazer uma importação (Priority: P2)

O dono vê a lista de importações de cada conta e pode **desfazer** uma. Os dias dela deixam de valer no
analytics e na exportação, mas continuam guardados como "desfeitos" (nada é apagado). O histórico registra
quem desfez e quando. Depois de desfazer, o dono pode importar outro arquivo (ou o mesmo) para aqueles
dias.

**Why this priority**: É a saída para um engano (arquivo da conta errada, versão mal lida). Com as
conferências da US2, deve ser raro.

**Independent Test**: Importar, desfazer e conferir que:
- o analytics voltou ao estado anterior;
- a lista e o histórico mostram a importação como desfeita, com o autor.

Depois, reimportar o mesmo arquivo e ver os dias valendo de novo.

**Acceptance Scenarios**:

1. **Given** uma importação ativa, **When** o dono desfaz (com confirmação), **Then** ela passa a "desfeita
   por <dono> em <data>", os dias dela saem do analytics e da exportação, e os registros continuam no
   banco.
2. **Given** uma importação desfeita, **When** o dono importa de novo o mesmo arquivo, **Then** a
   pré-visualização trata os dias como novos e a confirmação cria uma importação nova.
3. **Given** um dia coberto por duas importações ativas em que a mais antiga é desfeita, **When** o
   analytics recarrega, **Then** passa a usar o valor da importação que continua ativa.

---

### User Story 5 - Ver e exportar o histórico importado (Priority: P3)

Na tela "Histórico do Studio" da conta, o dono e os membros veem a cobertura de cada métrica: de que dia a
que dia há dados importados (visão geral e seguidores), desde quando há coleta e onde há buracos. A
exportação do dataset da 016 (só dono) ganha um arquivo com a série diária importada, com a coluna de
fonte e o id da importação.

**Why this priority**: Ajuda a saber se falta baixar mais algum período do Studio antes que ele suma
(a TikTok guarda cerca de 1 ano) e leva o histórico ao dataset de ML. É complemento, não o núcleo.

**Independent Test**: Com duas importações e uma coleta semeadas, conferir na tela a faixa de cobertura e
os buracos, e no arquivo exportado as linhas e as colunas.

**Acceptance Scenarios**:

1. **Given** importações que cobrem 01/08–29/09 e coleta desde 26/09, **When** o dono abre a cobertura,
   **Then** vê as duas faixas, a sobreposição e nenhum buraco. Com um dia faltando no arquivo, vê o
   buraco desse dia.
2. **Given** a exportação do dataset, **When** o dono exporta, **Then** recebe também o arquivo da série
   diária importada (só das importações ativas), com o dicionário das colunas.

---

### Edge Cases

- **Datas sem ano:** o ano vem do nome do ZIP da Visão geral (data de início e instante do fim). Num CSV
  solto, ou no ZIP de Seguidores enviado sem o da Visão geral, o último dia do arquivo é a data mais
  recente com aquele dia e mês que não passa de hoje, e os anteriores seguem para trás. A virada de ano
  (dezembro → janeiro) é tratada. A pré-visualização mostra o período com o ano para o dono conferir.
- **Linhas fora de ordem** ou intervalo maior que o dos dias: recusa, porque o ano não pode ser deduzido
  com segurança.
- **Cabeçalho em inglês ou pt-BR:** os dois idiomas são aceitos, comparando sem acento e sem caixa. Outro
  idioma dá "formato não reconhecido", com a dica de mudar o idioma do Studio para português ou inglês.
- **ZIP com arquivos a mais** (demografia, atividade): são ignorados e listados. O `Content.csv` (com
  títulos e links de vídeos) nunca é lido.
- **Visão geral e Seguidores com períodos diferentes:** cada seção vale para os seus dias, e a cobertura
  mostra cada uma.
- **Coluna opcional ausente** (ex.: visitas ao perfil): o dia é gravado sem ela. A pré-visualização lista
  as colunas que faltam, e o analytics trata o valor como "sem dado", e não zero.
- **Dias faltando no meio do arquivo:** são aceitos e aparecem na pré-visualização ("faltam 3 dias:
  …"). Nada é inventado para preenchê-los.
- **Dia repetido no arquivo:** com os mesmos números, conta uma vez; com números diferentes, o arquivo é
  recusado.
- **Linha com tudo zero:** é válida (um dia sem atividade é um dado).
- **Números com separador de milhar** ("1,234" ou "1.234"): são lidos. Abreviações ("1.2K") são recusadas,
  porque arredondam.
- **Fuso:** o dia do arquivo é gravado como dia de calendário, sem hora. A nota de leitura do analytics diz
  que o dia do Studio pode seguir o fuso da TikTok, e não o de Brasília.
- **Conta desconectada e anonimizada (016):** os dias importados seguem a anonimização como o resto (só
  números, sem @ e sem nome de arquivo). Uma conta sem série viva não aceita importação.
- **Conta reconectada (série nova):** a importação vai para a série viva. Dias que já estão numa série
  anônima antiga não contam como conflito.
- **Duas abas do dono confirmando ao mesmo tempo:** só a primeira confirmação grava. A outra recebe "esta
  pré-visualização já foi usada ou expirou; envie de novo".
- **Algo mudou entre a pré-visualização e a confirmação** (outra importação ou um desfazer na mesma
  conta): a confirmação é recusada com "os dados da conta mudaram; envie de novo".

## Requirements *(mandatory)*

### Functional Requirements

**Quem e onde**

- **FR-001**: Só um **dono humano** DEVE poder enviar, pré-visualizar, confirmar e desfazer importações. Os
  outros atores DEVEM ser recusados, como nas ações exclusivas de dono da 015: o membro recebe "só o
  dono", e a recusa a quem não é humano (IA, agente, cliente MCP) DEVE ficar registrada como evento de
  segurança. Membros DEVEM poder ver a lista de importações e a cobertura.
- **FR-002**: A importação DEVE ser feita a partir da tela de uma **conta TikTok do SociMan com série de
  métricas viva** (016). A conta aparece na pré-visualização com o @ e o perfil.
- **FR-003**: A importação **só lê arquivos enviados pelo dono**: não chama nenhuma API da TikTok, não
  publica, não altera post nem conexão (princípio I). Não DEVE haver segredo novo.

**Leitura e validação (US2)**

- **FR-004**: Num envio, o SociMan DEVE aceitar **1 ou 2 arquivos**, cada um sendo:
  - o **ZIP da Visão geral** (`Overview_<AAAA-MM-DD>_<instante>_<conta>.zip`, com `Overview.csv`);
  - o **ZIP de Seguidores** (`Followers_<conta>.zip`, com `FollowerHistory.csv`);
  - um desses dois CSVs solto.

  Cada seção pode vir no máximo uma vez por envio. Os ZIPs e CSVs de outras seções, o XLSX e o "Baixar
  seus dados" DEVEM ser recusados com a orientação de qual arquivo enviar.
- **FR-005**: As colunas são reconhecidas pelo cabeçalho, em inglês ou pt-BR, sem acento e sem caixa,
  numa tabela única de sinônimos.
  - **Visão geral:** obrigatórias **Date** e **Video Views**; opcionais Profile Views, Likes, Comments e
    Shares.
  - **Seguidores:** obrigatórias **Date** e **Followers** (total); opcional "Difference in followers from
    previous day".

  Colunas desconhecidas DEVEM ser ignoradas e listadas na pré-visualização.
- **FR-005a**: O **ano** de cada dia DEVE ser deduzido de forma determinística:
  - pelo nome do ZIP da Visão geral (data de início com ano e instante do fim), valendo também para o
    ZIP de Seguidores do mesmo envio quando os dias e meses coincidem;
  - senão, o último dia é a ocorrência mais recente daquele dia e mês que não passa de hoje, e os
    anteriores seguem para trás, um a um.

  Também são aceitas datas com ano (AAAA-MM-DD, DD/MM/AAAA). Os dias DEVEM estar em ordem crescente.
- **FR-006**: O envio DEVE ser recusado inteiro, antes da pré-visualização, quando:
  - **tamanho e ZIP:** passa de **5 MB**; um ZIP se expande além de 20 MB, tem mais de 20 entradas, tem
    caminho absoluto, `..`, link ou ZIP dentro de ZIP (nada é extraído para o disco);
  - **formato:** a seção não é reconhecida, falta coluna obrigatória ou o arquivo está vazio;
  - **linhas:** qualquer linha tem data inválida, fora de ordem ou **futura**, número **negativo**
    (exceto a diferença de seguidores), valor não numérico ou abreviado, ou dia repetido com números
    diferentes.

  A mensagem DEVE listar cada problema com arquivo, linha, coluna e valor (até 50, com o total).
- **FR-007**: O dia de hoje (incompleto) DEVE ser ignorado, com aviso na pré-visualização.
- **FR-008**: O @ do sufixo do nome do ZIP DEVE ser igual ao da conta (sem @, sem caixa), senão o envio é
  recusado. Dois arquivos com @ diferentes no mesmo envio também são recusados. Com CSV solto (sem @), a
  confirmação DEVE exigir a marcação explícita "confirmo que este arquivo é de @<conta>".
- **FR-009**: Nos dias inteiros cobertos pela coleta, a pré-visualização DEVE comparar os dois (views
  ganhas por dia e total de seguidores) e avisar, sem bloquear, quando a diferença passa de um limite fixo
  no código (padrão: 30% na soma dos dias em comum).

**Pré-visualização e confirmação (US1)**

- **FR-010**: Antes de gravar, o SociMan DEVE mostrar:
  - a conta e os arquivos (nome, seção, @ encontrado);
  - o período com o ano e a origem do ano (nome do ZIP ou deduzido);
  - por seção, o número de dias novos, já importados (iguais), divergentes de importação ativa (vale a
    anterior), coincidentes com a coleta inteira (vale a coleta), faltando e ignorados;
  - os totais do período, as colunas reconhecidas, ausentes e ignoradas, e uma amostra das linhas.

  Nada é gravado até o dono confirmar.
- **FR-011**: A pré-visualização DEVE expirar (padrão: 30 minutos) e ser de uso único. **Os arquivos
  enviados nunca são gravados em disco nem no armazenamento de arquivos**: são lidos na memória, e só o
  resultado da leitura fica guardado temporariamente até confirmar, cancelar ou expirar (ver Assumptions).
  Ficam registrados a impressão digital de cada CSV, o período e as contagens.
- **FR-012**: A confirmação DEVE:
  - gravar os dias de uma vez (tudo ou nada);
  - criar o registro da importação (conta, série, autor, data, seções, impressões digitais, período,
    contagens) e registrar no histórico (princípio VII);
  - gravar uma vez só, mesmo com dois cliques de confirmar sobre a mesma pré-visualização.

  Se os dados da conta mudaram desde a pré-visualização (outra importação ou um desfazer), ela DEVE ser
  recusada.

**Regras de dado (princípio VII e 016)**

- **FR-013**: Os dias importados DEVEM ser guardados como observações **só de inserção**, com a fonte
  `studio` e a importação de origem, separadas das fotos da API: **nenhuma observação coletada é alterada
  ou apagada**. Um dia está **coberto pela coleta** quando a série já tinha alguma coleta antes de esse
  dia começar (fuso America/Sao_Paulo).
  - Nos dias cobertos, o analytics usa a coleta, e o Studio aparece como comparação no tooltip.
  - Nos outros dias (anteriores à primeira coleta e o próprio dia dela), usa o Studio quando há dado
    ativo; sem Studio, segue o cálculo atual da 019.
- **FR-014**: Reimportar um CSV com a **mesma impressão digital** de uma importação ativa da mesma série
  DEVE ser idempotente: 0 dias, e o aviso "já importado". Num arquivo diferente, todos os dias são
  guardados, mas um dia que já tem valor de importação ativa **continua com o valor anterior** (a mais
  antiga ativa vale): números iguais contam como "já importados" e diferentes, como "divergentes".
- **FR-015**: Desfazer DEVE marcar a importação como desfeita (autor e data), sem apagar os dias. A partir
  daí, os dias dela deixam de valer no analytics, na cobertura e na exportação, e a próxima importação
  ativa daquele dia passa a valer. Desfazer DEVE ir para o histórico e é a reversão da importação: não há
  "refazer", importa-se de novo.
- **FR-016**: Os seguidores (total e ganhos por dia) DEVEM vir só do `FollowerHistory.csv`. Sem ele, os
  dias importados ficam "sem dado" de seguidores (nada é estimado).
- **FR-017**: A anonimização da 016 DEVE cobrir as importações: ao anonimizar a série, os dias importados
  continuam só com números e dia, e o registro da importação perde os nomes dos arquivos (que contêm o
  @). Nada que identifique a conta entra no histórico da importação.

**Analytics (US3) e cobertura (US5)**

- **FR-018**: Os indicadores e as séries do analytics (019) que dependem de totais diários da conta DEVEM
  usar os dias importados ativos segundo FR-013, em todos os períodos e comparações e nas comparações
  por conta e perfil. São eles: views ganhas, curtidas ganhas, engajamento, seguidores ganhos, a série
  diária e o calendário de views por dia.
- **FR-019**: Todo card que usa dado importado DEVE dizer isso:
  - a série diária e o calendário diferenciam as fontes por cor ou traço, legenda e tooltip (com o valor
    da outra fonte quando existir);
  - os indicadores mostram "inclui N dias importados do Studio";
  - a tabela alternativa e o CSV do card têm a coluna `fonte` (`coletado` ou `studio`).
- **FR-020**: As análises por vídeo ou por hora (mapas por horário, audiência por hora, curvas, dispersões,
  lift, marcos, alertas, mediana por post) NÃO DEVEM usar o histórico do Studio. Num período só com dias
  importados, elas dizem que o Studio não traz dado por vídeo nem por hora.
- **FR-021**: "Visitas ao perfil", que só o Studio informa, DEVE aparecer como série opcional na série
  diária quando houver dado, sem virar indicador novo da visão geral.
- **FR-022**: A tela "Histórico do Studio" da conta DEVE mostrar a **cobertura**:
  - por seção (visão geral, seguidores), as faixas com dado importado ativo, a faixa da coleta, a
    sobreposição e os buracos;
  - a lista de importações (data, autor, seções, período, dias, estado).

  Ela é acessível pela conta e pela aba Contas do analytics.
- **FR-023**: A exportação do dataset da 016 (só dono) DEVE incluir um arquivo da série diária importada,
  com `importacao_id`, a indicação de qual valor vale (`efetivo`) e o dicionário das colunas. Importações
  desfeitas ficam fora.

**Escopo do arquivo**

- **FR-024**: O arquivo por vídeo (seção "Conteúdo"), a seção "Espectadores" e a demografia ou atividade
  dos seguidores ficam **fora desta spec**. O `Content.csv` nunca é lido (ele traz títulos e links).

### Key Entities

- **Importação do Studio:** uma confirmação do dono para uma série. Guarda:
  - autor, data, seções lidas, impressão digital de cada CSV, período e contagens por seção;
  - os nomes dos arquivos, que somem na anonimização;
  - o estado (`ativa` ou `desfeita`, com autor e data) e o histórico.
- **Dia importado:** observação só de inserção de um dia de uma série vinda de uma importação. Tem views
  de vídeo, visitas ao perfil, curtidas, comentários e compartilhamentos (Visão geral), e seguidores
  totais e diferença (Seguidores), cada um podendo faltar.
- **Pré-visualização:** resultado temporário e de uso único da leitura dos arquivos para uma conta, com
  prazo. Tem o que seria gravado, os conflitos, os avisos e o estado da conta no momento da leitura. Não é
  domínio.
- **Cobertura:** derivada (não é gravada). São as faixas de dias por fonte e por seção numa série, com os
  buracos.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O dono importa os dois ZIPs de uma conta (do envio à confirmação) em menos de 2 minutos, sem
  ajuda.
- **SC-002**: 100% dos dias gravados batem, número a número e com o ano certo, com os arquivos de teste
  (inglês e pt-BR, com e sem virada de ano).
- **SC-003**: 100% dos arquivos de teste defeituosos (cada defeito de FR-006, conta errada, seção errada,
  ZIP inseguro) são recusados com a mensagem certa, e nenhum dia deles é gravado.
- **SC-004**: Reimportar o mesmo arquivo grava 0 dias, e nenhuma observação coletada pela API é alterada
  ou apagada por importar ou desfazer (verificado por teste).
- **SC-005**: Depois de importar, a série diária do analytics mostra os dias anteriores à primeira coleta
  e o dia dela com o valor do Studio, cada um identificado pela fonte. Os indicadores batem com o cálculo
  de referência.
- **SC-006**: Desfazer uma importação faz o analytics voltar exatamente aos números de antes da importação.
- **SC-007**: 0 ações de importação aceitas de membro, IA, agente ou MCP (verificado por teste).

## Assumptions

- **Formato confirmado** com um arquivo real em inglês (`notas-pesquisa.md`). **Os cabeçalhos em pt-BR são
  provisórios:** os sinônimos são suposição até o dono exportar com a interface em português. Sinônimo
  novo é uma linha na tabela, e um cabeçalho desconhecido dá recusa clara, nunca leitura errada.
- **Período:** o Studio exporta até 60 dias por download (talvez 365). Mais tempo exige vários downloads, e
  cada um vira uma importação.
- **Contas pessoais:** o download funciona para @atavernanerd (conferido). Assume-se o mesmo para
  @meusqueridinhos10.
- **Arquivos nunca guardados:** os ZIPs e CSVs são lidos na memória e descartados. Motivos:
  1. eles trazem o @ no nome e, no ZIP de Conteúdo, títulos e links, e guardar um arquivo identificável
     quebraria a anonimização prometida na 016 (o armazenamento de arquivos do SociMan não tem delete);
  2. os números já ficam inteiros no banco, e a impressão digital garante a idempotência;
  3. o arquivo pode ser baixado de novo do Studio dentro do ano que a TikTok guarda.

  A pré-visualização guarda só o resultado da leitura (poucos KB), em estado efêmero com prazo. Por isso
  nada é escrito no HD.
- **Sem DELETE:** desfazer marca a importação; os dias ficam guardados (como as fotos da 016). Os dias
  importados não têm `version` próprio: o histórico fica na importação, no mesmo padrão das observações da
  016.
- **Fuso:** o dia do arquivo é gravado como dia de calendário. A diferença possível entre o dia da TikTok e
  o de Brasília é aceita e aparece na nota de leitura.
- **Sem IA:** nenhuma chamada de modelo. A leitura e as regras são determinísticas.
- **Tamanho máximo de 5 MB por envio:** os arquivos reais têm menos de 1 KB por semana de dados. O limite
  cabe no limite geral do edge (8 MB), sem rota especial.
- **Limiares** (divergência de 30%, prazo de 30 min, 50 erros listados, limites do ZIP) são constantes no
  código, e os que o dono vê aparecem na tela.
- **Fora do escopo:** demografia, atividade dos seguidores, espectadores, origem do tráfego, tempo
  assistido, alcance e métricas de loja do Studio; agendar ou automatizar o download (o Studio não tem
  API); outras redes.
- **Dependências:** séries, fotos e anonimização da 016; analytics da 019 (indicadores, série diária,
  calendário e CSV por card); ações só de dono humano e registro de recusa da 015; histórico (princípio
  VII).
