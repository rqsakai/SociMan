# Estudo: biblioteca de movimentos e a UX do gerador de vídeo

Pedido do dono em 2026-10-15, durante a T059 da 031. É um estudo, não é spec: serve de base para revisar o
`docs/insumos/030-clonagem-movimento.md` antes do `/speckit-specify`.

**Pergunta:** como uma biblioteca de movimentos pode (1) melhorar o vídeo do gerador atual (031) e (2) virar
um segundo jeito de criar vídeo, "clonar um movimento com o avatar", com uma interface que um leigo use sem
ajuda? A Voomi é a referência de facilidade, não um modelo a copiar.

## 1. O que a Voomi faz (visto em 2026-10-15, conta da Roberta, sem gerar nada)

### Creator Lab V2 (equivalente ao nosso wizard)
10 passos agrupados em 3 fases visíveis no topo: **Criar cena → Gerar imagem → Gerar vídeo**.

| # | Passo | O que o usuário faz |
|---|---|---|
| 1 | Câmera | 5 cartões com foto: De frente, Selfie, Mãos (POV), Vestindo, Frente ao espelho. Cada um diz **para que tipo de produto serve** ("Vestindo: roupas, calçados, óculos…") |
| 2 | Produto | Escolhe o produto e escreve **como ele aparece** (mín. 15 caracteres), com exemplos bons e um aviso: "a foto pode ter vários itens, diga qual" |
| 3 | Influencer | Cartões com foto, "Criar o meu" ou "Nenhum" |
| 4 | Cenário | Os do usuário + 12 prontos (Casa, Quarto, Cozinha, Loja…) |
| 5 | Imagem | Resumo das 4 escolhas com "Editar" em cada uma, "Gerar imagem" ou "Pular" |
| 6 | Config | Duração em **takes de 8 s** (8/16/24/32/40 s); mostra **quanto custa e quanto demora antes** ("cada take leva de 1 a 3 min", "restam 2 na sua conta"); instruções livres opcionais |
| 7 | Voz | Mood (animado, calmo, urgente, divertido), tipo e tonalidade |
| 8 | Fala | Uma caixa por take, com **papel do take** (Gancho, Prova social, Chamada), meta de 14–18 palavras, contador e "Regenerar"; em branco = a IA escreve |
| 9 | Revisão | Tudo numa tela, cada item com "Editar" |
| 10 | Gerar | — |

Detalhes que fazem diferença: **rascunho retomado** ("Rascunho retomado no passo 5"), barra de passos clicável,
botão "Começar do zero", e o vídeo final é gerado no Flow/Veo 3 (com fala na câmera).

### Clonagem de Movimento
Três colunas lado a lado: **1 Movimento → 2 Influencer + Cenário → 3 Produto na cena**, e embaixo duração
(3/5/8 s), resolução (480p = 1 crédito, 720p = 2) e "Gerar vídeo".

- **Biblioteca** com ~60 movimentos com vídeo de capa e filtros (Movimentos, POV, CTA, Selfie, Mirror Selfie):
  "Destaque de Tecido", "Ajustando o Caimento", "Giro Lento e Olhar", "Esticando o Tecido", "Toque Sutil no
  Tecido", "Admirando o Produto", "Caminhada Casual"…
- **Criar movimento** de dois jeitos: "Montar meu movimento" (você descreve, a IA estrutura) ou "Enviar um
  vídeo" (a IA lê o clipe e preenche os passos para você conferir). A ficha tem 5 passos:
  1. **Enquadramento:** de frente / selfie no espelho / câmera nos olhos (só mãos); corpo inteiro / cintura
     para cima / rosto e ombros;
  2. **Produto:** "Vestido no corpo" ou "Na mão, mostrando". Isso liga a **trava de posse** ("produto na mão
     nunca troca de mão nem some"; avisa se a coreografia ocupa as duas mãos);
  3. **Coreografia:** texto na ordem dos acontecimentos, com sugestões clicáveis ("dá um giro de 360°", "leva
     a mão até a clavícula e segura", "aponta para o produto");
  4. **Câmera:** parada, tremidinho de celular, aproxima, recua, gira, varre para o lado, sobe ou desce;
  5. **Nome**, e "Salvar e gerar prévia (1 clonagem)" ou "Salvar sem prévia".
- **Depois do vídeo:** "Ajustar o movimento" com texto livre ("gire mais devagar", "segure o produto mais
  perto"); cada ajuste é uma geração nova.
- **Por dentro** (código público do app): não há cópia de pose. O clipe vira **texto de coreografia**
  (`extract-movement`), e o vídeo sai de imagem inicial + texto no **Seedance 1 Pro Fast** (nuvem). A própria
  tela avisa: "o movimento é uma referência, não um molde". Depois de editar a descrição, "vale o texto, não o
  vídeo".

## 2. O que temos hoje (031, wizard e avançado)

Mapeado no código em 2026-10-15:

- **Novo vídeo:** 7 passos (tipo, perfil, avatar + voz, cenário, produto, duração, resumo). Até aqui, parecido
  com a Voomi, e melhor em um ponto: avatar, voz, cenário e produto são **os nossos, aprovados**, com voz
  clonada e consentimento.
- **Depois:** chat de 3 a 5 perguntas → clique em "Montar o vídeo" → **Claude inventa a ação de cada cena** (`acao`,
  `camera`, `movimento`, instruções dos quadros, em inglês; `roteiros/plano.py`) → revisar cenas → narração →
  quadros (1 aprovação por cena) → clipes (1 aprovação por cena) → final. São **~2N+3 aprovações** num vídeo de
  N cenas.

**Dores, em ordem de impacto:**
1. **O movimento é invisível e não é escolhido.** O leigo não vê nem escolhe o que a avatar vai fazer: descobre
   quando os quadros saem, e só pode recusar com opções genéricas.
2. **O movimento é fraco quando a cena é reaproveitada pelo plano.** Sem instruções, cai no
   "Beginning/End of the shot: {acao}", e o quadro final sai quase igual ao inicial (visto na T059).
3. **Não há tempo nem custo antes.** O Wan qualidade levou 1 h 40 por trecho e ninguém sabia antes; o spinner do
   plano não diz nada.
4. **Jargão:** trecho, quadro, Início/Meio 1/Fim, "Refaz as imagens", portões, "provisório".
5. **Aprovações demais** e o clique extra em "Montar o vídeo".
6. **Só no avançado:** o texto da fala, a ação, as instruções e o motor.

## 3. O que temos e a Voomi não tem (onde dá para ir além)

| Nosso trunfo | Como ele vira resultado melhor |
|---|---|
| **Quadro inicial e final por trecho** (first-last frame, 031) | Cada **passo** da coreografia vira um quadro-alvo aprovado. O vídeo **tem de chegar** àquele estado, em vez de só "ler" o texto: mais controle do que imagem + texto |
| **"Não aprovo" que ajusta só o campo** (`roteiro.ajuste`) e refaz só os quadros e trechos afetados | O ajuste pós-resultado da Voomi refaz tudo; o nosso refaz o passo errado |
| **Reuso de cena** (031) e **variantes** (032) | Um movimento aprovado com um avatar vira cena da biblioteca, reaproveitada sem GPU |
| **Ficha do produto** (012: categoria, tecido, manga, cor) | Sugerir o movimento pelo produto: kaftan → "Destaque de tecido", "Mostra a manga"; tênis → "Caminhada", POV de pés |
| **Aprendizado** (023) e **métricas** (016) | Saber quais movimentos rendem mais views por conta e sugerir esses primeiro |
| **GPU local, sem custo por vídeo** | Gerar 2 opções por padrão onde importa; o custo que mostramos é **tempo**, não crédito |
| **Voz própria + narração contínua** | A fala é um texto só, cortado por cena; a Voomi gera fala por take |

## 4. Proposta

### 4.1 O movimento como ficha (o coração da 030)
Um **Movimento** da biblioteca do AI Studio (029, perfil base opcional):

| Campo | Exemplo | Para que serve |
|---|---|---|
| Nome e capa (vídeo curto) | "Mostra a manga de lado" | escolher olhando, não lendo |
| Para que produto | vestível · na mão · pequeno · calçado | filtrar e sugerir pelo produto (012) |
| Enquadramento | corpo inteiro · cintura para cima · rosto e ombros · só mãos (POV) · espelho | vira o enquadramento do quadro 0 |
| Como o produto aparece | vestido · na mão | trava de posse no prompt ("aparece uma vez só, nunca troca de mão") |
| **Passos** (1 a 3, cada um ≈ 5 s) | 1. vira de lado ¾; 2. levanta o braço e mostra a manga | **cada passo = um quadro final** (estado final, a lição de 2026-10-01) e um trecho |
| Câmera | parada · celular na mão · aproxima · recua · panorâmica | vira o `movimento`/`camera` da cena |
| Motor sugerido e **tempo estimado** | MiniMax ~9 min por trecho | mostrado antes de gerar |
| Origem | escrito · lido de um clipe · gravado (fase 2) | rastreio e direito autoral |

**Os passos são o que conecta tudo à 031:** hoje o Claude inventa as instruções dos quadros; com a ficha,
o plano **escolhe** um movimento por posição e as instruções dos quadros saem dos passos. Uma posição de 2
trechos usa um movimento de 2 passos. Isso resolve a dor 2 e torna a ação visível (dor 1).

**Como uma ficha nasce:**
1. **Escrita** pelo dono, com sugestões clicáveis, e o Claude estrutura em passos (como a Voomi).
2. **Lida de um clipe** (até 10 s): o Claude vê 6 a 8 quadros e preenche a ficha para o dono conferir. Guarda
   **só a ficha e uma capa**, não o clipe, o que resolve a dúvida de consentimento do insumo da 030 (a pessoa
   do clipe não fica guardada) e o risco de direito autoral (referência, não cópia; princípio II).
3. **Gravada no celular** e copiada por pose (Wan Animate/VACE): **fase 2**, só se o texto + quadros não
   bastar. É o insumo original da 030, que vira uma melhoria da ficha, não o ponto de partida.

### 4.2 Dois jeitos de criar vídeo

**A. "Vídeo com narração" (o wizard atual, melhorado)**
- O plano escolhe 1 movimento por posição **da biblioteca**, já filtrada pelo produto, e mostra as cenas como
  **cartões de movimento** (capa, nome, "cena 2 · 5 s") com "Trocar movimento" antes de gastar GPU.
- O dono aprova o plano olhando os movimentos, e o resto segue como hoje.

**B. "Clonar um movimento" (novo, rápido, sem narração)**
Uma tela só, em 3 colunas como a Voomi, mas com o que é nosso:
1. **Movimento** (biblioteca, com filtro pelo produto escolhido);
2. **Avatar + cenário** → quadro 0 (1 ou 2 opções);
3. **Produto** (catálogo aprovado; variante/cor visível);

Embaixo: duração (= passos × 5 s), **tempo estimado** e "Gerar". O resultado é um clipe com os quadros de cada
passo; "Não aprovo" ajusta o passo errado. O clipe aprovado pode virar **cena da biblioteca** (para o modo A)
ou **conteúdo** (014) para postar.

O modo B também é o **laboratório** dos movimentos: testar uma ficha nova com um avatar antes de usá-la em
vídeos com narração.

### 4.3 Regras de UX para os dois (o que levamos da Voomi, do nosso jeito)
1. **Escolha visual, com "ideal para…"**: cartões com capa em vídeo e uma frase sobre o produto, nunca listas
   de texto.
2. **Fases visíveis, passos clicáveis, rascunho retomado** (a Voomi guarda o passo; nós já guardamos o roteiro,
   falta retomar a tela de "Novo vídeo").
3. **Tempo antes de gerar:** a estimativa por motor (medida na T059) aparece no resumo e no botão ("Gerar, ~30
   min"). Na fila, "na fila, começa depois do clipe X", e não "Gerando…" (a dor de 2026-10-15).
4. **Vocabulário do resultado:** "cena", "movimento", "imagem inicial/final", "clipe"; sem trecho, quadro,
   portão, provisório e "refaz as imagens" na tela do leigo (ficam no avançado).
5. **Menos aprovações:** aprovar por cena (imagens + clipe juntos quando a imagem já foi aprovada no plano) e o
   "Montar o vídeo" automático depois da última resposta. Meta: **N+2 aprovações** em vez de 2N+3.
6. **Ajuste em linguagem natural depois do resultado**, mas no alvo certo (o passo, a fala, a imagem), que é o
   nosso "não aprovo".
7. **Exemplos bons do lado de cada campo de texto** (a Voomi faz isso muito bem no "como o produto aparece").

### 4.4 Regras do quadro e validação de qualidade (pedido do dono em 2026-10-15)
Evidência: no segundo teste da T059 (tudo no MiniMax, 9 min por clipe), 5 dos 6 quadros saíram limpos e o
quadro final da cena 3 veio com uma camiseta cinza por baixo do kaftan transparente. Hoje o que vai ao Qwen Edit
é: diretiva de composição fixa (`composicao_do_quadro`) + instrução do quadro + o sufixo "Vertical photo,
realistic, the product exactly as in the reference image". O prompt negativo do bloco keyframe está **vazio**.

Proposta, em três camadas, do mais barato ao mais caro:
1. **Regras do quadro (o "system prompt" do keyframe).** Um bloco fixo de DOs e DON'Ts que entra em todo pedido
   de quadro, antes da instrução, no modelo das regras editáveis da 008 (`ia_regras`: padrão em código, o dono
   edita em /app/assistente-ia, "Voltar ao padrão", histórico). Padrão inicial, só do que já nos custou:
   - DO: o produto exatamente como na referência (cor, tecido, transparência: **por baixo de tecido
     transparente há pele ou a mesma base da referência, nunca outra peça**); produto inteiro no enquadramento;
     mesmo quarto, parede, chão e luz; mesmo rosto, cabelo e corpo; mãos e peso do corpo descritos.
   - DON'T: peça extra por baixo ou por cima (camiseta, regata, casaco); mudança de luz; "phone video";
     texto, marca d'água, moldura; outra pessoa; produto cortado ou centrado no decote.
   Três níveis que se somam: global (padrão) → perfil (as proibidas do guia da 017, como já acontece) →
   **movimento** (os "cuidados" da ficha da 030, ex.: "mangas abertas = braços na altura dos ombros").
2. **Prompt negativo.** Os DON'Ts também vão ao nó negativo do bloco keyframe (hoje vazio). Precisa de um
   parâmetro `negative` novo no `keyframe.params.json` (contrato do bloco em `../comfyui-docker/workflows`,
   com autorização do dono, e a cópia em `geracao/workflows/` com o sha no MANIFEST).
3. **Checagem automática do quadro (Claude visão).** Um passo `cena.quadro_checagem` (motor `claude`, no
   molde do `avatar.identidade`) que recebe o quadro gerado, a referência do produto, o quadro anterior e a
   instrução, e responde um checklist com nota 0-10 e observação em pt-BR: fidelidade do produto (cor, tecido,
   **peça extra**), identidade, ambiente igual, pose igual à instrução, mãos. Abaixo do limiar: outra seed
   automática (até N vezes, configurável) e, se continuar, o cartão do quadro mostra "atenção: camiseta por
   baixo do produto" com "Refazer". Nunca escolhe pelo humano (constitution): só marca e refaz. Custo
   aproximado: uma chamada de visão por quadro (~US$ 0,01 a 0,02, 10 a 20 s), contra 2,5 min de GPU por
   quadro ruim e o tempo do dono.
4. **Aprendizado das regras.** Cada "Não aprovo" de quadro e cada reprovação da checagem ficam gravados com a
   regra violada (ou "sem regra"). O dono vê a lista e promove um motivo recorrente a DON'T; mais adiante, uma
   recomendação automática ("3 reprovações por peça extra em 7 dias: adicionar à regra?"), como as da 023.

Onde entra: as camadas 1 e 3 são genéricas (servem ao wizard de hoje) e cabem como a primeira história da 030
ou numa spec curta própria antes dela; a camada "cuidados por movimento" é da ficha da 030. A camada 2 depende
do dono (contrato do bloco).

## 5. Riscos e o que não sabemos
- **Texto + quadros basta?** Hipótese principal: os passos como quadros finais dão um movimento mais fiel do
  que só texto (Voomi) ou só ação genérica (031 hoje). **Não testado.**
- **Tempo de GPU:** MiniMax ~9 min/trecho; Wan qualidade ~1 h 40 (T059). A ficha precisa do motor e do tempo.
- **Vestível × mãos ocupadas:** coreografias com as duas mãos e produto na mão saem estranhas (a Voomi avisa).
  Para roupa, "vestido" é o padrão.
- **Corpo diferente** (plus size) só importa na fase 2 (pose); na ficha em texto, não.
- **Direito autoral e pessoa real** do clipe de referência: guardar só a ficha resolve a maior parte; decidir
  no clarify.

## 6. Próximos passos sugeridos
1. **Fechar a T059** (cena 2 deve ficar pronta perto das 11:50) e anotar onde o movimento falhou.
2. **Experimento no terminal** (`comfyui-docker/pipeline/`), com os quadros desta T059:
   - 3 fichas escritas à mão (ex.: "Mostra a manga de lado", "Giro lento", "Ajusta a cintura"), 2 passos cada;
   - comparar: ação genérica (hoje) × ficha em texto só no clipe × ficha com quadro final por passo;
   - medir tempo, fidelidade do movimento, rosto e fundo.
3. Se a ficha com quadros ganhar: **reescrever o insumo da 030** como "Movimentos" (ficha + modo B + integração
   no plano da 031), com a cópia por pose como fase 2.
4. Depois, um ajuste de UX da 031 (vocabulário, tempo estimado, "na fila", menos aprovações), que pode entrar
   na própria 030 ou numa spec pequena.

## Decisões abertas para o dono
1. O modo B ("Clonar um movimento") entra na 030 junto com a ficha, ou a 030 é só a ficha + integração no
   wizard e o modo B vem depois?
2. A biblioteca começa com movimentos escritos por nós (uns 10, para vestível) ou só com os que o dono criar?
3. A cópia por pose (gravação no celular) fica como fase 2, ou o dono quer testar já?
