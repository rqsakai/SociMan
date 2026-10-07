# Feature Specification: Público (022-publico)

**Feature Branch**: `022-publico`

**Created**: 2026-10-06

**Status**: Draft

**Input**: User description: "Ampliar a importação do TikTok Studio (020) para as seções de público:
distribuição dos seguidores por gênero e por território, atividade dos seguidores por dia × hora e
espectadores únicos, novos e recorrentes por dia. Mesmas regras da 020 (só dono humano, prévia de uso
único, idempotente, desfazer, fonte `studio`, nunca sobrescreve a API). Tratar os arquivos vazios ('ainda
sem dados de público: a TikTok libera com mais seguidores') e o valor 'undefined'. Nova aba **Público** no
analytics (019) com gênero, territórios, atividade dos seguidores (heatmap dia × hora, que também entra
como 3º mapa em 'Quando postar'), espectadores únicos e novos × recorrentes, tudo com amostra, fonte e
período, e as regras de acessibilidade e paleta da 019. As distribuições são fotos do momento da
exportação (série por data de exportação, não diária). A anonimização da 016 cobre esses dados. Nada
publica."

## Contexto

A 020 importa do TikTok Studio só duas coisas: a **Visão geral** (`Overview.csv`, números do dia) e o
**total de seguidores** (`FollowerHistory.csv`). Todo o resto é recusado ("esta seção não é importada") ou
ignorado. Só que o resto é justamente o que a API pública da TikTok (016) **não tem**: quem é o público e
quando ele está on-line. A 019 já registra essa falta ("alcance, retenção, audiência e tráfego seguem na
etapa 2").

O formato foi conferido com os arquivos reais de @atavernanerd exportados em 02/10/2026 (interface em
inglês). Os originais nunca entram no repositório.

| Arquivo | Conteúdo | No arquivo real |
|---|---|---|
| `Followers_<conta>.zip` → `FollowerGender.csv` | `"Gender","Distribution"` | **só o cabeçalho** |
| `Followers_<conta>.zip` → `FollowerTopTerritories.csv` | `"Top territories","Distribution"` | **só o cabeçalho** |
| `Followers_<conta>.zip` → `FollowerActivity.csv` | `"Date","Hour","Active followers"` | **só o cabeçalho** |
| `Followers_<conta>.zip` → `FollowerHistory.csv` | já importado pela 020 | 7 dias, de 0 a 4 seguidores |
| `Viewers_<conta>.zip` → `Viewers.xlsx` | planilha `Viewers`: `Date`, `Total Viewers`, `New Viewers`, `Returning Viewers` | 7 dias; `Total Viewers` = `undefined` no 1º dia |

Detalhes do formato real:
- os CSVs seguem o padrão da 020 (UTF-8 com BOM, `,`, tudo entre aspas, sem quebra de linha no fim);
- o `Viewers.xlsx` é uma planilha de verdade (um ZIP com XML dentro, entradas sem compressão), com uma
  aba só, `Viewers`, e **todas as células como texto**, inclusive os números ("104", "622");
- as datas vêm **sem ano** ("September 25"), como na 020, e o @ só aparece no nome do ZIP;
- no arquivo real, `Total Viewers` = `New Viewers` + `Returning Viewers` em todos os dias com número
  (ex.: 663 = 622 + 41), e no dia com `undefined` os outros dois são 0;
- os três CSVs de público vieram **vazios** porque a conta tinha 4 seguidores. Os guias de analytics
  dizem que a aba Seguidores só mostra os dados de público a partir de **100 seguidores**
  ([Buffer, 18/09/2026](https://buffer.com/resources/tiktok-analytics/): "the Followers tab won't display
  detailed audience data until you have at least 100 followers"; o mesmo limite aparece em
  [Brand24](https://brand24.com/blog/tiktok-analytics/) e
  [Later](https://later.com/blog/tiktok-analytics/)). A TikTok não publica esse limite numa página
  oficial que pudemos ler, então ele é tratado como **indicativo** (ver Assumptions). Os mesmos guias
  dizem que os territórios listam **no máximo 5 países**, cada um com pelo menos 1% dos seguidores.

**Nenhum dos arquivos de público tem uma série histórica completa.** Gênero e territórios são **uma foto
do momento da exportação** (a distribuição de hoje, sem data no arquivo). A atividade dos seguidores
cobre só os últimos dias. Os espectadores são diários, como a Visão geral. Por isso, o histórico de
público só nasce de **exportações repetidas**: cada importação acrescenta uma foto (gênero, territórios)
ou mais dias (atividade, espectadores).

## Clarifications

### Session 2026-10-06

- Q: De onde vem a data da foto de gênero e territórios, se o ZIP de Seguidores não traz data no nome? →
  A: do dia seguinte ao último dia do `FollowerHistory.csv` do mesmo ZIP (o Studio exporta até ontem; no
  arquivo real, último dia 01/10 → foto de 02/10, o dia do download), nunca depois de hoje; sem esse CSV
  no mesmo ZIP, vale o dia da importação, com aviso. A prévia mostra a data e a origem.
- Q: O que os cards de distribuição mostram quando não há foto dentro do período escolhido? → A: a foto
  mais recente até o fim do período, mesmo que seja de antes do início, com a data em destaque ("foto de
  01/10, anterior ao período"), e a mudança em p.p. contra a foto válida no fim do período anterior quando
  ela é outra.
- Q: Como o mapa de atividade trata o período quando a atividade cobre poucos dias? → A: média sobre os
  dias com dado dentro do período, com o n por célula; se o período não tem nenhum dia com dado, estado
  vazio com o atalho "ver os últimos dias com dado" (que muda o período global).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Importar o público junto com o histórico (Priority: P1)

O dono baixa no TikTok Studio o ZIP de Seguidores e o de Espectadores e envia os dois (com ou sem o da
Visão geral) na mesma tela "Histórico do Studio" da conta, criada na 020. A pré-visualização passa a
mostrar, além do que a 020 já mostra:
- **Gênero** e **Territórios:** a data da foto e a distribuição (rótulo e %), ou "ainda sem dados de
  público";
- **Atividade dos seguidores:** os dias e as horas cobertos e o pico (dia e hora com mais seguidores
  ativos), ou "ainda sem dados de público";
- **Espectadores:** o período, os dias novos, já importados e divergentes, os totais diários e os dias
  "sem dado" (`undefined`).

O dono confere e confirma; só então tudo entra no banco, numa importação só.

**Why this priority**: É a base de tudo o que a spec mostra. Sem dados gravados, a aba Público fica
vazia.

**Independent Test**: Com ZIPs sintéticos de uma conta de teste (Seguidores com os 4 CSVs preenchidos e
Espectadores com 7 dias, um deles `undefined`), enviar, conferir na pré-visualização a distribuição, o
pico de atividade e os totais diários iguais aos do arquivo, confirmar e verificar que cada seção ficou
gravada com a fonte "Studio", ligada à conta, à importação e ao autor.

**Acceptance Scenarios**:

1. **Given** o dono e os ZIPs de Seguidores e Espectadores com dados, **When** ele envia na tela da
   conta, **Then** a pré-visualização mostra cada seção de público (data da foto, distribuição, dias,
   pico, totais), e nada é gravado até confirmar.
2. **Given** a pré-visualização aberta, **When** o dono confirma, **Then** as seções de público e as da
   020 são gravadas juntas (tudo ou nada), numa importação com a lista de seções, e o histórico registra
   o ato.
3. **Given** o ZIP de Seguidores real de uma conta com menos de 100 seguidores (gênero, territórios e
   atividade só com o cabeçalho), **When** o dono envia, **Then** a pré-visualização importa o
   `FollowerHistory.csv` como na 020 e mostra, para as outras três seções, "ainda sem dados de público:
   a TikTok libera esses dados quando a conta tem mais seguidores (cerca de 100)", sem erro e sem gravar
   nada delas.
4. **Given** um `Viewers.xlsx` com `undefined` num dia, **When** a pré-visualização abre, **Then** aquele
   valor aparece como "sem dado (a TikTok não informou)", os outros valores do dia são gravados, e o
   total de dias com `undefined` aparece no resumo.
5. **Given** os mesmos arquivos já importados e ativos, **When** o dono envia de novo, **Then** cada seção
   diz "já importado em <data> por <dono>" e confirmar não grava nada.
6. **Given** um membro ou um cliente que não é humano (IA, agente, MCP), **When** tenta pré-visualizar,
   confirmar ou desfazer, **Then** é recusado como na 020, e a recusa a um não humano fica registrada.
7. **Given** uma importação com seções de público ativa, **When** o dono a desfaz, **Then** todas as
   seções dela (as da 020 e as de público) deixam de valer juntas, e nada é apagado.

---

### User Story 2 - Conferir que os arquivos de público estão íntegros (Priority: P1)

Antes da pré-visualização, o SociMan confere as seções novas com o mesmo rigor da 020 e explica em pt-BR
o que está errado:
- planilha que não é a de Espectadores, com mais de uma aba sem a `Viewers`, protegida, com macro ou
  com fórmulas;
- colunas obrigatórias faltando, datas inválidas, fora de ordem ou futuras, horas fora de 0 a 23;
- números negativos ou não numéricos (fora o `undefined`), dias ou horas repetidos com números
  diferentes;
- distribuições que não fecham (gênero longe de 100%, territórios acima de 100%, % negativa);
- ZIP ou planilha grande demais ou insegura.

**Why this priority**: As observações são só de inserção. Um arquivo mal lido estraga o histórico de
público, e o desfazer não deve ser o caminho normal.

**Independent Test**: Enviar um conjunto de arquivos sintéticos, um por defeito, e conferir que cada um é
recusado com a mensagem, o arquivo, a linha (ou célula) e a coluna certos, e que nada é gravado.

**Acceptance Scenarios**:

1. **Given** um `FollowerGender.csv` cujas % somam 80%, **When** o dono envia, **Then** o envio é
   recusado com "a distribuição por gênero soma 80%; esperado perto de 100%".
2. **Given** um `FollowerActivity.csv` com a hora 24 ou com o mesmo dia e hora duas vezes com números
   diferentes, **When** o dono envia, **Then** o envio é recusado com a linha e o valor.
3. **Given** um `Viewers.xlsx` com uma célula "abc" (que não é número nem `undefined`), **When** o dono
   envia, **Then** o envio é recusado com a célula (ex.: "B4"), a coluna e o valor.
4. **Given** um XLSX com macro, com planilha protegida, com link externo, ou que se expande demais,
   **When** o dono envia, **Then** é recusado sem ser lido, com o motivo.
5. **Given** um `Viewers_<outraconta>.zip`, **When** o dono envia na conta @atavernanerd, **Then** é
   recusado com "o arquivo é de @outraconta, não de @atavernanerd", como na 020.
6. **Given** um `Viewers.xlsx` ou um CSV de público solto (sem o @ no nome), **When** a pré-visualização
   abre, **Then** confirmar exige a marcação "confirmo que este arquivo é de @<conta>", como na 020.
7. **Given** um dia em que `Total Viewers` é diferente de `New Viewers` + `Returning Viewers`, **When** a
   pré-visualização abre, **Then** aparece o aviso com os dias afetados, sem bloquear.

---

### User Story 3 - Aba Público no analytics (Priority: P1)

O dono abre a nova aba **Público** do analytics e vê, para o período e os filtros globais da 019:
- **Gênero dos seguidores:** a distribuição da foto válida para o período, com a data da foto e, se houver
  outra foto antes, a mudança em pontos percentuais;
- **Territórios dos seguidores:** os até 5 países, com a %, e "Outros" com o resto;
- **Atividade dos seguidores:** um mapa de calor dia da semana × hora com a média de seguidores ativos;
- **Espectadores:** a série diária de espectadores e a divisão entre novos e recorrentes.

Cada card diz a fonte ("importado do TikTok Studio"), a data da foto ou os dias cobertos, a amostra e o
que falta (ex.: "a TikTok libera os dados de público com mais seguidores; reimporte quando a conta
crescer").

**Why this priority**: É o motivo do pedido: saber quem é o público e quando ele está on-line, o que a
API pública não dá.

**Independent Test**: Com fotos de gênero e territórios em duas datas, 14 dias de atividade e 14 dias de
espectadores semeados para uma conta, abrir a aba Público com 7 dias e conferir cada número (% de gênero
e território da foto certa, a mudança em p.p., a média de cada célula do mapa com o n de dias, a série
diária e os totais de novos e recorrentes) contra o cálculo de referência.

**Acceptance Scenarios**:

1. **Given** fotos de gênero em 01/10 e 15/10, **When** o dono abre a aba com o período de 09/10 a
   15/10, **Then** o card mostra a foto de 15/10, a data dela e a mudança contra a foto de 01/10 em
   p.p. (regra da foto válida: FR-016).
2. **Given** uma conta sem nenhuma foto de público, **When** o dono abre a aba, **Then** cada card mostra
   o estado vazio com o motivo ("ainda sem dados de público: a TikTok libera com mais seguidores" ou
   "nenhuma importação de público ainda") e o atalho para a tela "Histórico do Studio".
3. **Given** atividade importada em 14 dias, **When** o mapa aparece, **Then** cada célula mostra a média
   de seguidores ativos naquele dia da semana e hora, o n de dias com dado, e as células com n abaixo do
   mínimo ficam marcadas como amostra pequena.
4. **Given** espectadores importados, **When** o card de espectadores aparece, **Then** mostra a série
   diária (total, novos e recorrentes), os novos somados no período e a **média diária** de espectadores
   e de recorrentes, sem somar recorrentes como se fossem pessoas diferentes (ver Assumptions).
5. **Given** um dia com `Total Viewers` = `undefined`, **When** a série aparece, **Then** o dia fica como
   "sem dado" (buraco na linha, e não zero), e o tooltip explica.
6. **Given** o filtro global com duas contas, **When** a aba abre, **Then** os cards de distribuição e o
   mapa mostram cada conta separadamente (nunca misturam as % de contas diferentes), e a série de
   espectadores usa as cores fixas de cada conta.
7. **Given** qualquer card da aba, **When** o dono abre a tabela alternativa ou o CSV, **Then** vê os
   mesmos números, com as colunas `fonte`, `data_foto` (distribuições) ou `dia` e `hora`.

---

### User Story 4 - Atividade dos seguidores em "Quando postar" (Priority: P2)

Na aba "Quando postar" da 019, o mapa de atividade dos seguidores entra como **3º mapa**, ao lado do
desempenho por horário de publicação e da audiência, com a mesma grade 7 × 24, para o dono comparar
"quando eu posto e rende" com "quando meus seguidores estão on-line".

**Why this priority**: Responde à decisão diária de agenda com um dado que só o Studio tem. Depende da
US1 e reaproveita o cálculo da US3.

**Independent Test**: Com atividade semeada, abrir "Quando postar" e conferir que o 3º mapa tem as mesmas
células que o mapa da aba Público, no mesmo período e filtro, e que sem dados aparece o estado vazio.

**Acceptance Scenarios**:

1. **Given** atividade importada no período, **When** o dono abre "Quando postar", **Then** vê o 3º mapa
   "Seguidores on-line (TikTok Studio)" com a nota de fonte, de fuso e de amostra.
2. **Given** nenhuma atividade importada, **When** o dono abre "Quando postar", **Then** o 3º mapa mostra
   o estado vazio com o motivo e o atalho para importar, e os outros dois mapas continuam iguais.

---

### User Story 5 - Ver a cobertura e exportar o público (Priority: P3)

Na tela "Histórico do Studio", a cobertura da 020 ganha as seções de público: as datas das fotos de
gênero e territórios, os dias com atividade e com espectadores, e os buracos. A exportação do dataset
(016/020, só dono) ganha os arquivos de público, com o dicionário das colunas.

**Why this priority**: Mostra ao dono quando reimportar (a atividade cobre poucos dias, e as fotos só
existem se ele exportar) e leva o público ao dataset. É complemento.

**Independent Test**: Com duas importações semeadas, conferir na tela as datas das fotos e as faixas de
dias, e no arquivo exportado as linhas e as colunas, sem as importações desfeitas.

**Acceptance Scenarios**:

1. **Given** fotos em 01/10 e 15/10 e atividade de 25/09 a 01/10 e de 09/10 a 15/10, **When** o dono abre
   a cobertura, **Then** vê as duas fotos e as duas faixas de atividade, com o buraco entre elas.
2. **Given** a exportação do dataset, **When** o dono exporta, **Then** recebe também os arquivos de
   distribuição, atividade e espectadores (só importações ativas), com `importacao_id`, `efetivo` e o
   dicionário.

---

### Edge Cases

- **Arquivo de público vazio** (só o cabeçalho, como no real): não é erro. A seção aparece como "ainda sem
  dados de público" e não é gravada. Fica anotada na importação que a acompanha (a cobertura mostra
  "veio sem dados em <data>"). Se **todas** as seções do envio vierem vazias, o envio é recusado com a
  mesma explicação (não há o que pré-visualizar nem o que anotar). Um arquivo de público sem nem o
  cabeçalho continua sendo "formato não reconhecido".
- **`undefined`** (e célula vazia) num número dos espectadores, da atividade ou da distribuição: vira "sem
  dado" naquela célula, nunca zero. Uma linha só com "sem dado" nos números é gravada como dia sem dado
  (o dia existe no arquivo, mas a TikTok não informou). Numa coluna de data ou de hora, é erro.
- **Dia de hoje:** ignorado na atividade e nos espectadores, como na 020 (dia incompleto).
- **Datas sem ano:** a regra de ano da 020 (FR-005a) vale para a atividade e os espectadores. Num envio
  com o ZIP da Visão geral, o ano vem do nome dele; sem ele, do "último dia que não passa de hoje".
- **A foto de gênero e territórios não tem data no arquivo:** a data da foto segue FR-012.
- **Formato da %:** "52%", "52" ou "0.52". Uma seção usa um formato só; misturado é erro. A soma de
  gênero precisa ficar perto de 100% (tolerância de arredondamento); a de territórios pode ficar abaixo
  (o resto é "Outros"), nunca acima.
- **Rótulos:** gênero `Male`/`Female`/`Other` (e os sinônimos em pt-BR, provisórios) viram Masculino,
  Feminino e Outro; um rótulo desconhecido é recusado com a lista dos aceitos. Território é guardado como
  veio (código ou nome do país) e exibido em pt-BR quando reconhecido.
- **Viewers.xlsx com números como texto** (o real) ou como número: os dois são lidos. Data como número de
  série do Excel também é aceita. Fórmulas, macros, abas ocultas a mais e links externos são recusados.
- **XLSX dentro do ZIP de Espectadores:** é a única exceção à regra "nada de ZIP dentro de ZIP" da 020,
  só para a entrada `Viewers.xlsx`, com os mesmos limites aplicados à planilha por dentro.
- **Overview e Viewers com números parecidos:** espectadores e views são métricas diferentes (uma pessoa
  pode ver vários vídeos). Nenhuma comparação entre eles é feita.
- **Atividade sobreposta entre importações:** o mesmo dia e hora com o mesmo número conta como "já
  importado"; com número diferente, "divergente (vale o anterior)", como os dias da 020.
- **Fotos no mesmo dia:** duas importações ativas com foto do mesmo dia valem pela mais antiga, e a outra
  aparece como divergente quando os números diferem.
- **Fuso da atividade:** o arquivo não diz em que fuso estão as horas. A hora é gravada como veio, e o
  mapa traz a nota "horas conforme a TikTok" (ver Assumptions).
- **Conta anonimizada (016):** as fotos, a atividade e os espectadores continuam só com números, dia,
  hora e rótulos de gênero e país; o registro da importação perde os nomes dos arquivos, como na 020. Na
  aba Público, a conta aparece como "Conta anônima N".
- **Conta com menos seguidores que o limite depois de ter tido mais:** fotos antigas continuam valendo
  como fotos daquela data; uma exportação nova vazia não apaga nada.
- **Celular:** os mapas rolam na horizontal dentro do card, e as distribuições viram barras horizontais
  numa coluna (regra da 019).

## Requirements *(mandatory)*

### Functional Requirements

**Quem, onde e o que não muda**

- **FR-001**: As regras de acesso, tela e escopo da 020 (FR-001 a FR-003) DEVEM valer sem mudança: só um
  dono humano envia, pré-visualiza, confirma e desfaz; membros veem a cobertura e o analytics; a recusa a
  quem não é humano fica registrada; a importação só lê arquivos enviados pelo dono, não chama a TikTok,
  não publica e não cria segredo novo.
- **FR-002**: Os dados de público DEVEM ter sempre a fonte `studio`. A API pública (016) não informa
  nenhum deles, então não existe conflito com o coletado; nenhuma observação coletada é alterada.

**Leitura (US1, US2)**

- **FR-003**: Um envio DEVE aceitar **de 1 a 3 arquivos**: os da 020 (ZIP ou CSV da Visão geral e de
  Seguidores) e, agora, o **ZIP de Espectadores** (`Viewers_<conta>.zip`, com `Viewers.xlsx`) ou o
  `Viewers.xlsx` solto. Cada seção pode vir no máximo uma vez por envio. O ZIP e o CSV de Conteúdo
  continuam recusados, e o `Content.csv` continua nunca aberto.
- **FR-004**: No ZIP de Seguidores, além do `FollowerHistory.csv` da 020, DEVEM ser lidos o
  `FollowerGender.csv`, o `FollowerTopTerritories.csv` e o `FollowerActivity.csv`. Cada um também pode
  vir solto. A seção é reconhecida pelo cabeçalho, em inglês ou pt-BR, sem acento e sem caixa, na tabela
  de sinônimos da 020:
  - **gênero:** obrigatórias `Gender` e `Distribution`;
  - **territórios:** obrigatórias `Top territories` e `Distribution`;
  - **atividade:** obrigatórias `Date`, `Hour` e `Active followers`;
  - **espectadores:** obrigatórias `Date` e `Total Viewers`; opcionais `New Viewers` e `Returning
    Viewers`.
- **FR-005**: O `Viewers.xlsx` DEVE ser lido sem dependência nova (princípio VIII), só a aba `Viewers`
  (ou a única aba), com as células de texto ou de número, e com as proteções de ZIP da 020 aplicadas
  também à planilha por dentro (entradas, tamanho expandido, razão de compressão, caminhos, links). DEVE
  ser recusado o XLSX com macro, fórmula, link externo, cifrado ou com várias abas sem a `Viewers`. O
  XLSX dentro do ZIP de Espectadores é a única exceção ao "ZIP dentro de ZIP" da 020, e só um nível.
- **FR-006**: Um arquivo de público que tem só o cabeçalho DEVE ser aceito como **"ainda sem dados de
  público"**, sem erro e sem gravação de observação, com a explicação "a TikTok libera esses dados quando
  a conta tem mais seguidores (cerca de 100)", e a importação confirmada anota a seção como vazia. Se
  todas as seções do envio vierem vazias, o envio é recusado com essa explicação. Isso vale para gênero,
  territórios, atividade e espectadores. Para a
  Visão geral e o `FollowerHistory.csv`, o "arquivo vazio" continua sendo recusado (020).
- **FR-007**: O valor **`undefined`**, e a célula vazia, num número de público DEVEM virar "sem dado"
  naquela célula, sem recusar o envio. A pré-visualização DEVE contar os "sem dado" por seção. Nunca
  viram zero nem são estimados (ex.: o total não é deduzido de novos + recorrentes).
- **FR-008**: O envio DEVE ser recusado inteiro, antes da pré-visualização, com a lista dos problemas
  (arquivo, linha ou célula, coluna e valor; até 50, com o total), quando, além dos casos da 020:
  - **distribuição:** % negativa ou acima de 100; formatos de % misturados; gênero com soma fora de 100%
    ± tolerância; territórios com soma acima de 100% + tolerância; rótulo de gênero desconhecido; rótulo
    repetido;
  - **atividade:** hora fora de 0 a 23, data inválida, futura ou fora de ordem, número negativo ou não
    numérico (fora o `undefined`), mesmo dia e hora repetidos com números diferentes;
  - **espectadores:** as mesmas regras de dia da 020, com números negativos ou não numéricos (fora o
    `undefined`).
- **FR-009**: A regra do @ da 020 (FR-008) DEVE valer para o ZIP de Espectadores e para todos os arquivos
  do envio. O `Viewers.xlsx` e os CSVs de público soltos exigem a marcação "confirmo que este arquivo é de
  @<conta>".
- **FR-010**: Quando `Total Viewers`, `New Viewers` e `Returning Viewers` estão todos presentes num dia e o
  total é diferente da soma, a pré-visualização DEVE avisar (com os dias), sem bloquear e sem corrigir.

**Pré-visualização, confirmação e desfazer**

- **FR-011**: A pré-visualização da 020 (FR-010 e FR-011: prazo, uso único, arquivos nunca gravados em
  disco) DEVE ganhar, por seção de público:
  - **gênero e territórios:** a data da foto (com a origem, FR-012), a distribuição, e se ela é nova, igual
    a uma foto ativa da mesma data ou divergente;
  - **atividade:** os dias e as horas, o pico, e as contagens de novos, iguais, divergentes, ignorados
    (hoje) e "sem dado";
  - **espectadores:** o período, as contagens da 020 (novos, iguais, divergentes, faltando, ignorados), os
    "sem dado", os totais diários e o aviso de FR-010;
  - **vazias:** "ainda sem dados de público", com a explicação de FR-006.
- **FR-012**: A **data da foto** de gênero e de territórios DEVE ser a data da exportação.
  Ela é o **dia seguinte ao último dia do `FollowerHistory.csv` do mesmo ZIP** (o Studio exporta até
  ontem), limitado a hoje. Sem esse CSV no mesmo ZIP (CSV de público solto, ou ZIP sem ele), vale o
  **dia da importação**, com o aviso "data da foto = dia da importação; confira se o arquivo foi baixado
  hoje". A prévia mostra a data e a origem (`historico` ou `importacao`).
- **FR-013**: A confirmação DEVE gravar as seções de público e as da 020 de uma vez (tudo ou nada), numa
  importação só, com as seções lidas, a impressão digital de cada arquivo (cada CSV e o XLSX), o período
  e as contagens, e registrar no histórico (princípio VII), nos termos da 020 (FR-012).
- **FR-014**: A idempotência e a precedência da 020 (FR-014) DEVEM valer para cada seção nova:
  - mesma impressão digital de uma importação ativa da mesma série → 0 gravações e "já importado";
  - **atividade** (por dia e hora) e **espectadores** (por dia): vale a importação ativa mais antiga;
    números iguais contam como "já importados" e diferentes como "divergentes (vale o anterior)";
  - **gênero e territórios** (por data da foto): vale a foto da importação ativa mais antiga daquela data,
    com a mesma classificação.
- **FR-015**: Desfazer (020, FR-015) DEVE tirar de uso todas as seções da importação, as da 020 e as de
  público, juntas, sem apagar nada. Não há desfazer por seção: para trocar uma seção, desfaz-se a
  importação e importa-se de novo.

**Regras de dado**

- **FR-016**: As fotos de gênero e territórios DEVEM ser guardadas como **fotos datadas pela exportação**,
  nunca como série diária: uma foto vale para a data dela, e entre duas fotos **não há interpolação**. No
  analytics, a foto válida para um período é a mais recente com data até o fim do período, e a
  comparação é com a foto válida no fim do período anterior.
  Sem foto dentro do período, vale a mais recente até o fim dele, mesmo que seja de antes do início,
  com a data em destaque ("foto de 01/10, anterior ao período"). Sem nenhuma foto até o fim do período,
  o card fica vazio (FR-026).
- **FR-017**: A **atividade dos seguidores** DEVE ser guardada por (dia, hora), como observação só de
  inserção, e acumulada entre importações. O mapa dia da semana × hora DEVE mostrar a **média** de
  seguidores ativos nos dias do período que têm dado naquela célula, com o n de dias.
  Só entram os dias **dentro do período**. Se o período não tem nenhum dia com atividade, o mapa fica
  vazio com o atalho "ver os últimos dias com dado", que muda o período global para os 7 dias que
  terminam no último dia com atividade.
- **FR-018**: Os **espectadores** DEVEM ser guardados por dia (total, novos, recorrentes, cada um podendo
  ser "sem dado"), como observação só de inserção, no mesmo padrão dos dias da 020.
- **FR-019**: A anonimização da 016 DEVE cobrir os dados de público: ao anonimizar a série, as fotos, a
  atividade e os espectadores ficam só com números, dia, hora e rótulos de gênero e país, e o registro da
  importação perde os nomes dos arquivos (020, FR-017). Nada que identifique a conta entra no histórico.

**Analytics (US3, US4)**

- **FR-020**: O analytics DEVE ganhar a aba **Público**, logo depois de "Quando postar", com a aba ativa e
  os filtros na URL (019, FR-001). Ela obedece ao período global e aos filtros por perfil, conta e rede
  (019, FR-002 e FR-003).
- **FR-021**: A aba Público DEVE ter 4 cards:
  1. **Gênero dos seguidores:** a distribuição da foto válida (FR-016), com a data da foto e a mudança em
     p.p. contra a foto anterior quando houver;
  2. **Territórios dos seguidores:** os países da foto válida, ordenados pela %, com "Outros" = 100% − a
     soma, e a mesma comparação;
  3. **Atividade dos seguidores:** o mapa 7 × 24 de FR-017;
  4. **Espectadores:** a série diária do total, dos novos e dos recorrentes por conta, com os novos
     somados no período e as médias diárias de total e de recorrentes, cada um com a variação contra o
     período anterior (019, FR-012).
- **FR-022**: Com mais de uma conta no filtro, as distribuições e o mapa de atividade DEVEM aparecer por
  conta (pequenos múltiplos ou seletor local do card, na ordem de contas da 019), sem nunca juntar as %
  ou as médias de contas diferentes. A série de espectadores DEVE usar as cores fixas de cada conta.
- **FR-023**: O mapa de atividade DEVE entrar também em "Quando postar" como **3º mapa** ("Seguidores
  on-line"), com o mesmo cálculo, período e filtros da aba Público, sem mudar os outros dois mapas.
- **FR-024**: Todo card de público DEVE seguir a 019 (FR-004 a FR-008): título, frase de leitura,
  tooltip, tabela alternativa, CSV do card, paleta validada para daltonismo em claro e escuro
  (sequencial de um tom no mapa, cores fixas de conta, e as distribuições em barras de um tom só, com o
  rótulo e a % em texto, sem depender de cor), uso no celular e amostra mínima. Além disso, DEVE mostrar:
  - a **fonte** ("importado do TikTok Studio") e a importação de origem no tooltip;
  - a **data da foto** (distribuições) ou os **dias cobertos** (atividade, espectadores);
  - a **amostra:** os dias com dado (n por célula no mapa) e os "sem dado".
- **FR-025**: Um mapa com células de n abaixo do mínimo (padrão: 2 dias) DEVE marcá-las como amostra
  pequena, sem cor de intensidade cheia (019, FR-004). As distribuições não têm amostra própria (a TikTok
  não diz sobre quantos seguidores calculou); o card mostra o total de seguidores da 020 na data da foto,
  quando houver, como referência.
- **FR-026**: Cada card sem dado DEVE ter um estado vazio com o motivo certo: "nenhuma importação de
  público ainda", "ainda sem dados de público: a TikTok libera com mais seguidores" (a última importação
  da seção veio vazia) ou "sem dado no período", com o atalho para a tela "Histórico do Studio" (só para o
  dono; o membro vê o motivo).
- **FR-027**: A aba Público e o 3º mapa são **só leitura** (019, FR-009): nada publica, aprova, agenda ou
  altera dado. Nenhum insight novo é criado nesta spec.

**Cobertura e exportação (US5)**

- **FR-028**: A cobertura da 020 (FR-022) DEVE ganhar as seções de público: as datas das fotos de gênero e
  territórios, as faixas de dias de atividade e de espectadores, os buracos, e a última importação vazia
  de cada seção ("veio sem dados em <data>").
- **FR-029**: A exportação do dataset (020, FR-023; só dono) DEVE incluir os arquivos de distribuição
  (foto, rótulo, %), atividade (dia, hora, seguidores ativos) e espectadores (dia, total, novos,
  recorrentes), com `importacao_id`, `efetivo` e o dicionário das colunas, só das importações ativas.

### Key Entities

- **Importação do Studio** (da 020, ampliada): passa a guardar também as seções de público lidas, a
  impressão digital de cada arquivo novo, a data da foto e a origem dela, e as contagens por seção. O
  estado (`ativa` ou `desfeita`) vale para todas as seções juntas.
- **Foto de distribuição:** observação só de inserção de uma série numa data de exportação, de um tipo
  (`genero` ou `territorio`), com os rótulos e as %. Não é diária.
- **Atividade de seguidores:** observação só de inserção de uma série num dia e numa hora, com o número
  de seguidores ativos (ou "sem dado").
- **Dia de espectadores:** observação só de inserção de uma série num dia, com total, novos e recorrentes
  (cada um podendo ser "sem dado").
- **Seção vazia:** o fato de uma seção ter vindo só com o cabeçalho numa importação; não grava
  observação, mas aparece na cobertura e no estado vazio da aba.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O dono importa os ZIPs de Seguidores e de Espectadores de uma conta (do envio à confirmação)
  em menos de 2 minutos, sem ajuda.
- **SC-002**: 100% dos valores gravados batem com os arquivos de teste (distribuições, cada dia e hora da
  atividade, cada dia dos espectadores, com o ano e a data da foto certos), e todo `undefined` vira "sem
  dado", nunca zero.
- **SC-003**: Os arquivos reais exportados pelo dono em 02/10/2026 (Seguidores e Espectadores) são aceitos:
  o `FollowerHistory.csv` como na 020, as três seções vazias como "ainda sem dados de público", e os 7
  dias de espectadores com o 1º dia "sem dado" no total.
- **SC-004**: 100% dos arquivos de teste defeituosos (cada defeito de FR-005 e FR-008, conta errada, XLSX
  inseguro) são recusados com a mensagem certa, e nada deles é gravado.
- **SC-005**: Reimportar os mesmos arquivos grava 0 linhas, e desfazer uma importação faz a aba Público e o
  3º mapa voltarem exatamente ao estado anterior (verificado por teste).
- **SC-006**: Todos os números da aba Público e do 3º mapa batem com o cálculo de referência sobre os dados
  semeados, e nenhum card mistura % ou médias de contas diferentes.
- **SC-007**: 100% dos cards novos têm fonte, data da foto ou dias cobertos, tabela alternativa, frase de
  leitura e CSV; a paleta passa na validação de daltonismo em claro e escuro; no celular (390 px), nada
  rola a página na horizontal.
- **SC-008**: 0 ações de importação aceitas de membro, IA, agente ou MCP (verificado por teste).

## Assumptions

- **Formato confirmado** com os arquivos reais em inglês (Contexto). **Ficam provisórios:** os
  cabeçalhos e os rótulos em pt-BR, o formato da % e dos rótulos de gênero e território, e o formato de
  data e hora do `FollowerActivity.csv`, porque os três CSVs reais vieram vazios. Assume-se que seguem o
  padrão dos outros arquivos (data "September 25", hora de 0 a 23, % como "52%" ou fração). Um formato
  desconhecido dá recusa clara, nunca leitura errada, e o ajuste é uma linha na tabela de sinônimos.
  Confirmar com um arquivo real assim que uma conta passar do limite.
- **Limite de 100 seguidores:** vem de guias de terceiros (Buffer, Brand24, Later), não de uma página
  oficial da TikTok. O texto da tela diz "cerca de 100" e não depende do número: o que vale é o arquivo
  vir vazio ou não. As duas contas de hoje estão abaixo dele (@atavernanerd tinha 4 seguidores em
  01/10/2026), então, na prática, a aba Público começa com os espectadores e com estados vazios nas
  outras seções.
- **Espectadores não se somam:** `Total Viewers` e `Returning Viewers` de cada dia são pessoas únicas
  **naquele dia**; a mesma pessoa em dois dias conta duas vezes. Por isso, o período mostra a média diária
  desses dois, e não a soma. Os `New Viewers` (quem viu a conta pela 1ª vez) podem ser somados no período.
  O total de espectadores únicos do período, que o Studio mostra na tela, não vem no arquivo e não é
  estimado.
- **Fuso da atividade:** o arquivo não diz o fuso. Assume-se o fuso que o Studio mostra ao dono (o da
  conta, provavelmente o de Brasília). A hora é gravada como veio, e o mapa traz a nota "horas conforme a
  TikTok". Se um arquivo real mostrar que é UTC, a conversão é uma regra de leitura, sem mudar os dados
  gravados (a importação guarda a hora do arquivo).
  É a única exceção à regra da 019 de "toda hora em America/Sao_Paulo" (019, FR-007), e a nota do mapa a
  deixa visível.
- **Atividade parcial:** o Studio parece exportar só os últimos dias de atividade (poucos dias por
  arquivo). O histórico só cresce com importações repetidas; a cobertura mostra os buracos para o dono
  saber quando reimportar. Nada agenda nem lembra a exportação.
- **Idade:** os guias citam também faixa etária na aba Seguidores, mas o ZIP real não traz arquivo
  de idade. Idade fica fora até aparecer num arquivo real.
- **Demografia dos espectadores** (gênero, idade e local de quem assiste) e "o que seus espectadores também
  assistem": aparecem na tela do Studio, mas não no `Viewers.xlsx` real. Ficam fora.
- **Uma importação, várias seções:** as seções novas entram na importação da 020 (mesma tela, mesma
  pré-visualização, mesmo desfazer), e não numa importação separada.
- **Sem dependência nova:** XLSX lido com a biblioteca padrão (ZIP + XML), como os CSVs (princípio VIII).
  O tamanho máximo do envio continua 5 MB (o `Viewers.xlsx` real tem 17 KB).
- **Sem IA:** nenhuma chamada de modelo; leitura, regras e cálculos são determinísticos.
- **Limiares** (tolerância da soma de gênero, n mínimo do mapa, limites do XLSX) são constantes no código,
  e os que o dono vê aparecem na nota de leitura do card.
- **Posição da aba:** "Público" fica logo depois de "Quando postar" (as duas falam de audiência). As 8 abas
  da 019 passam a 9.
- **Fora do escopo:** Conteúdo (por vídeo), idade, cidades, interesses, demografia de espectadores, LIVE,
  tráfego, tempo assistido, insights novos sobre público, agendar ou automatizar o download do Studio,
  outras redes.
- **Amplia a 020:** o FR-024 da 020 (Espectadores, demografia e atividade fora do escopo) deixa de valer
  para essas seções; o Conteúdo continua fora e nunca aberto.
- **Dependências:** importação, prévia, idempotência, desfazer, cobertura e exportação da 020; séries e
  anonimização da 016; abas, filtros, paleta, acessibilidade e "Quando postar" da 019; ações só de dono
  humano e registro de recusa da 015; histórico (princípio VII).
