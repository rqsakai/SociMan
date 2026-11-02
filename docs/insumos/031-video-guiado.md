# Insumo da 031: vídeo guiado (wizard + chat, keyframes por cena, grade de duração)

Pedido do dono em 2026-10-13, depois do primeiro teste real da 011 (saída de praia kaftan preta). Este
arquivo é insumo para o `/speckit-specify`, não é spec. Evolui a 011 (roteiros com vídeo local) e usa a 029
(biblioteca da agência), a 025 (avatar e voz), a 012 (produtos) e a 021 (geração local). A 032 (variantes)
depende da grade de duração desta spec.

> **Virou spec:** `specs/031-video-guiado/` (spec, plan, research, data-model, contracts, tasks), implementada em 2026-10-14. A fonte da verdade passa a ser a spec; este insumo fica como registro do pedido.

## Problemas que o dono viu no teste (2026-10-13)
1. **As cenas surgem de forma obscura.** O planejador já reaproveita uma cena da biblioteca ou cria uma nova
   (`roteiros/plano.py`, campos `cena_id` ou `nova`), mas isso acontece escondido dentro da etapa Texto. O dono
   achou que a cena precisava estar criada antes.
2. **Uma cena tem só 1 keyframe.** A IA não sabe onde a cena começa e onde termina, e "delira".
3. **Falta escolher a duração do vídeo.** Hoje a duração sai do texto, sem uma grade.
4. **A tela é de especialista.** Mostra prompts e textos de fala que um operador comum não precisa ver.

## O que o dono pediu (palavras dele, resumidas)

### Início em blocos grandes e simples (nesta ordem)
1. **Tipo de vídeo:** "Avatar & POV". No futuro haverá outros tipos.
2. **Perfil.**
3. **Avatar e voz**, com a voz padrão do avatar já carregada.
4. **Cenário.**
5. **Produto.**
6. **Duração** (ver "Grade de duração" abaixo).

### Chat com a IA, com perguntas fechadas
- Ao fim da escolha, abre um chat. A IA pergunta sobre o produto e sobre o que o cliente espera.
- As perguntas são **específicas e de múltipla escolha**, "para um leigo responder", nunca totalmente
  abertas. Exemplos:
  - quais aspectos focar;
  - tipo de chamada (CTA);
  - tipo de movimento.
- O chat traz **exemplos de pedidos prontos** para clicar.
- No fim, **a IA gera sozinha** todos os prompts e configurações: roteiro, falas, cenas, keyframes e
  movimentos.

### Modo wizard (padrão) e modo avançado (switch no topo)
- **Wizard:**
  - sem texto de prompt e sem texto de fala;
  - mostra só o **áudio gerado** e os **keyframes gerados**, e o operador aprova ou não cada um;
  - "não aprovo" abre o chat: o operador pede a troca, combina com a IA, e a IA troca os prompts e gera de
    novo.
- **Avançado:** o que existe hoje na 011, com textos, prompts e portões.
- A meta: "simples o suficiente para um leigo trabalhar, mas flexível para um expert usar o avançado".

### Cenas: reuso transparente
- A cena não precisa existir antes. Se faltar, o fluxo continua, e a cena nova é **salva na biblioteca** para
  uso futuro.
- Se houver cena que sirva, **o padrão é propor o reuso**. Só se cria nova quando o operador pedir.
- Gerar cenas novas tem de ser **transparente**: um modal que mostra, por posição, "reaproveitar X" ou "criar
  nova", e permite conversar sobre as cenas.

### Keyframes por cena (2 a 4)
- Cada cena tem **no mínimo início e fim**, e se possível 1 ou 2 quadros do meio (meio 1 e meio 2 opcionais).
- Motivo: com mais quadros, a IA segue o plano e delira menos.

### Grade de duração
- No começo, a duração é escolhida numa **grade de múltiplos** do tamanho de clipe que o motor gera bem.
  Exemplos do dono:
  - limite de 6 s: 6, 12, 18, 24, 30…;
  - limite de 8 s: 8, 16, 24, 32….
- O vídeo é a soma das cenas. Um vídeo de 5 cenas de 6 s tem 30 s.

## Limites técnicos que mudam o desenho (análise de 2026-10-13)
- **Quadros do meio:** o MiniMax-H3 e o Wan 2.2 aceitam no máximo **quadro inicial + quadro final**. Para
  respeitar 3 ou 4 keyframes, a cena vira **N−1 trechos** encadeados, cada um com um par de quadros
  (início→meio 1, meio 1→meio 2, meio 2→fim), e os trechos são colados.
  - **Custo:** mais GPU por cena (N keyframes = N−1 clipes).
  - **Duração:** a da cena é a soma dos trechos, e precisa casar com a grade. A pesquisa decide se o trecho
    tem o tamanho-base ou uma fração dele.
- **Identidade:** cada keyframe deve sair do anterior (Qwen Edit sobre o quadro anterior), não do zero, para o
  avatar e o produto não mudarem entre quadros. Lição de 2026-10-01: o keyframe descreve o **estado final**.
- **Tamanho-base:** sai da medição de cada motor. Hoje usamos ≤ 5 s por cena livre, e o MiniMax foi medido
  em cenas de 3 s. A grade deve ser configurável por motor, não fixa no código.
- **Narração e grade:** a narração precisa caber nos blocos. O ajuste de velocidade (`atempo`) já existe na
  011. Com a grade, cada cena tem um bloco de fala preso a ela, o que a 032 exige.
- **Lições que continuam valendo:**
  - não pedir mudança de luz;
  - quarto, paredes e luz não mudam;
  - close de lado (manga, laço), nunca centrado no decote;
  - plano de rosto sem fala vai no Wan 2.2;
  - a última cena termina em keyframe;
  - voice over, sem fala na câmera.

## Pesquisa necessária (fase 0 do plan)
- **Duração boa de cada motor** (MiniMax-H3, Wan 2.2, Wan 2.2 qualidade): a maior que ainda segue os
  quadros, em segundos e frames, com o tempo de GPU de cada uma.
- **Encadear trechos com par de quadros:** emenda visível? É preciso cross-fade? O último frame de um trecho
  é o primeiro do seguinte?
- **Chat:**
  - o formato de saída estruturada das perguntas de múltipla escolha (Claude);
  - quantas perguntas no máximo;
  - como gravar as respostas no roteiro e no histórico;
  - a regra 008/017: guia do perfil base e palavras proibidas.
- **"Não aprovo" no wizard:** a mensagem do chat vira a edição de qual campo? Reaproveitar a máquina da
  011 ("editar reposiciona na primeira etapa desatualizada").

## O que a spec precisa cobrir
- **Tela nova do vídeo guiado** (AI Studio → Vídeos → "Novo vídeo"):
  - blocos grandes (tipo, perfil, avatar e voz, cenário, produto, duração);
  - chat;
  - switch wizard/avançado, que também vale no detalhe do roteiro.
- **Dados novos:**
  - tipo de vídeo, cenário escolhido e duração-alvo;
  - respostas do chat no roteiro;
  - keyframes por cena: início, meio 1, meio 2 e fim, com 2 obrigatórios;
  - trechos por cena.
- **Planejador da 011:** recebe as respostas do chat, o cenário e a grade; propõe o reuso de cenas primeiro.
- **Modal de cenas:** reaproveitar ou criar nova, por posição. Cena nova salva na biblioteca (010/029).
- **Passos da 021:**
  - `cena.keyframe` com os quadros do meio, cada um derivado do anterior;
  - `cena.clipe` por trecho;
  - montagem que cola os trechos.
- **Regras que continuam:**
  - só humano aprova;
  - o automático da 011 continua valendo;
  - a IA nunca publica (constitution, princípio I).
- **Teste:** fakes no pytest e no e2e, e teste real na GPU com o dono, com o mesmo produto do teste de
  2026-10-13 para comparar.

## Para decidir no clarify
- [ ] O wizard substitui a tela "Novo vídeo" atual ou fica ao lado dela?
- [ ] Quantos keyframes por padrão: 2 (início e fim), com os do meio só no avançado, ou a IA decide por cena?
- [ ] A grade é por motor ou uma só, a do motor mais limitado?
- [ ] Quem vê o modo avançado: todos, ou só o dono?
