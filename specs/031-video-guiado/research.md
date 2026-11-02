# Research: 031-video-guiado

Fase 0 do plano. Fontes: o código da 011 na main (`apps/api/src/sociman_api/roteiros/`, `cenas/`,
`geracao/`), a SPA (`apps/web/src/pages/roteiros/`), os blocos do ComfyUI copiados em `geracao/workflows/` e o
pipeline de referência em `../comfyui-docker/pipeline/` (só leitura). Data: 2026-10-13.

## R1. Trecho-base de 5 s

**Decisão:**
- trecho-base padrão de **5 s** (`ROTEIRO_TRECHO_BASE_S=5`);
- grade de 1× a 6× (`ROTEIRO_GRADE_MAX=6`), ou seja, 5, 10, 15, 20, 25 e 30 s;
- o roteiro guarda a grade com que nasceu: `trecho_base_s` e `duracao_alvo_s`.

**Por quê:** 5 s é o ponto em que os três motores de clipe se encontram:
- **MiniMax-H3** gera 17k+5 quadros a 24 fps. O alcance treinado vai de 124 a 362 quadros, ou seja, de
  ~5,2 a 15 s. Com 124 quadros, 5 s é o mínimo do alcance.
- **Wan 2.2** gera 4k+1 quadros a 16 fps: 81 quadros dão 5,06 s.
- **LTX-2.5** gera 8k+1 quadros a 24 fps: 121 quadros dão 5,04 s.

Os testes do pipeline também apontam para 5 s. O planejador do pipeline diz "cena livre ≤ 5 s" e manda
ancorar num keyframe a cada 2 ou 3 cenas, para o produto não derivar. Na 011, os tetos por motor já são
8/5/7/5 s, então 5 s cabe em todos. Medido nos `runs/`, em 736×1280: o MiniMax leva ~57 s por segundo de
vídeo, e o Wan leva ~27–32 s/s em 480p.

**Medição com o dono** (quickstart §3): gerar o mesmo trecho com início e fim em 5 s e em 8 s no MiniMax.
Se o de 8 s seguir o quadro final tão bem quanto o de 5 s, trocar o padrão para 8 s (grade 8–32 s). É só
mudar o `.env`, sem código. Os roteiros que já existem mantêm a sua grade.

**Alternativas descartadas:**
- uma grade por motor: a 032 precisa que todas as versões de uma posição tenham o mesmo tamanho, e o motor
  pode variar por cena;
- deixar a grade solta: é o problema que o dono apontou.

## R2. Encadear trechos com par de quadros

**Decisão:** cada trecho é um `cena.clipe` com `start_image = quadro[t]` e `end_image = quadro[t+1]`. Os
quatro blocos de clipe já aceitam o `end_image`, como `image_optional`:
- MiniMax: `MiniMaxH3ImageToVideo.last_frame`;
- Wan: `WanFirstLastFrameToVideo.end_image`;
- LTX: `LTXVAddGuide frame_idx=-1`, com força 0,7.

O `geracao/aplicadores.py:128-134` já mapeia `refs[1]` para o `end_image`. A colagem segue estas regras:
- **Duração exata:** o trecho é ajustado para exatamente o trecho-base por `setpts`, sem cortar o fim. Por
  exemplo, 124 quadros viram 120 a 24 fps, uma mudança de 3% de velocidade que não se percebe. Assim o
  último quadro continua sendo o keyframe de fim. O corte por `trim` da 011 tiraria justamente o fim.
- **Sem quadro repetido:** a partir do 2º trecho, o 1º quadro sai, porque é o mesmo keyframe que fechou o
  trecho anterior. O tempo perdido (1 quadro) é compensado no `setpts`.
- **Colagem:** `concat` seco, como no pipeline, sem cross-fade. Se o teste com o dono (quickstart §3)
  mostrar salto, a opção é um cross-fade de 2 quadros, já prevista na montagem por um parâmetro, desligado
  por padrão.

**Alternativa descartada:** o `MiniMaxH3AddGuide`, que fixa uma imagem num índice qualquer e permitiria uma
geração só com os quadros do meio. Ele só existe no MiniMax e nunca foi testado aqui, e a regra FR-027
(1 trecho = 1 trecho-base) já resolve o problema. Fica registrado para uma spec futura.

## R3. Gerar a sequência de quadros

**Decisão:** cada quadro é um `cena.keyframe` (o bloco `keyframe`, Qwen Edit), com
`extras.quadro = i`.
- **Quadro 0:** `base_image` = a imagem `cena` do **cenário** escolhido no "Novo vídeo"; `ref1` = o slot
  `corpo_base` do avatar; `ref2` = o flat (ou o recorte) da variante do produto. Hoje a 011 não passa o
  cenário. Os três cabem nos 3 refs do bloco.
- **Quadros 1 a 3:** `base_image` = o quadro anterior; `ref1` = o produto; `ref2` = o `rosto_frontal` do
  avatar. As âncoras seguram o produto e o rosto, e reduzem a deriva de edição sobre edição.
- **Instrução:** sempre o **estado final** daquele quadro (lição de 2026-10-01). O planejador escreve uma
  instrução por quadro.

**"Gerada de uma vez" (clarify 2) e "1 versão no wizard" (clarify 3):**
- Com 1 opção por quadro, quando a opção sai, ela vira o quadro **provisoriamente**, e o pedido do quadro
  seguinte nasce dela. Isso é feito pela máquina (`roteiros/automatico.py`, que passa a cobrir "opção
  única de vídeo guiado", com o ator `system:roteiro` e versão no histórico).
- O operador aprova a **sequência** da cena. A aprovação humana continua sendo o portão: nada passa para
  os clipes sem ela.
- Com 2 ou mais opções (só no modo avançado), a cadeia espera a escolha humana de cada quadro antes de pedir
  o seguinte.

**Recusar o quadro i:** o quadro i e os seguintes viram "a refazer". Os candidatos antigos não são apagados
(`desuso_em`). A cadeia recomeça do último quadro mantido.

## R4. Narração dentro da grade

**Decisão:**
- **Uma narração contínua** (`/v2/tts_paragraph`, como na 011), porque a prosódia fica natural.
- O áudio é **cortado por bloco de fala**, pelos tempos das frases que o shop-tts já devolve.
- Cada bloco é **colocado no início do slot** da sua posição: `adelay` = início do slot + 0,15 s.
- O vídeo tem exatamente a duração-alvo, e as posições têm duração fixa (trechos × base). Na 011, a
  duração vinha da fala; aqui, a fala é que se ajusta.

**Orçamento do planejador:**
- cada posição recebe `≤ 0,85 × slot × 14` caracteres. A conta: cerca de 14 caracteres por segundo em
  pt-BR a 1,08×, medido nas narrações da 011 (`bia_vo`);
- o `problemas()` do plano confere o orçamento e pede uma nova tentativa (como os limites atuais).

**Ajuste depois do TTS:**
- um bloco que passa do slot (menos 0,3 s de margem) ganha `atempo` próprio na montagem, até a velocidade
  total chegar a 1,20 (o teto da 011);
- se não couber nem assim, o roteiro ganha o aviso `fala_nao_cabe` com a posição, e o wizard oferece "texto
  mais curto", que vira um ajuste pela IA, ou "duração maior".

**Alternativa descartada:** um TTS por bloco. A prosódia fica quebrada entre as frases, e são N chamadas.

## R5. O chat: perguntas numa chamada só

**Decisão:**
- Depois dos blocos, um passo novo, **`roteiro.perguntas`** (motor `claude`, `sem_escolha`), gera **de uma
  vez** as até 5 perguntas.
  - Entrada: produto (ficha da 012), avatar, cenário, duração, guia do perfil base e as cenas candidatas.
  - Cada pergunta tem `id`, `texto`, `multipla`, 2 a 6 `opcoes` e `exemplos`.
- A tela mostra uma pergunta por vez. As respostas são gravadas sem IA (só banco).
- "Montar" chama o `roteiro.plano` já existente, com as respostas num bloco `<respostas>`.

Custo: 1 chamada de perguntas + 1 de plano, contra até 6 se fosse uma chamada por pergunta.

**Por quê:**
- o fluxo é previsível e barato;
- as perguntas ficam no banco, então o chat retoma de onde parou (FR-011);
- nenhuma infraestrutura de conversa de múltiplos turnos com o Claude é necessária, e ela não existe hoje (o
  `IaClient` manda sempre uma mensagem só, com saída estruturada).

**Formato novo** `perguntas_roteiro` em `ia/tipos.py`/`ia/saida.py`, com o `usa_guia="completo"` do perfil
base: as proibidas e os padrões entram, como nos outros tipos.

**Alternativa descartada:** uma conversa livre com histórico (multi-turn). É cara, imprevisível e contra o
pedido do dono, que quer perguntas fechadas.

## R6. "Não aprovo" vira ajuste pela IA

**Decisão:** um passo novo, **`roteiro.ajuste`** (motor `claude`, `sem_escolha`).
- **Entrada:**
  - o **alvo**: narração, quadros de uma posição a partir do quadro i, trecho t de uma posição, ou final;
  - o **pedido**: opções clicadas e/ou um texto curto;
  - o estado atual do alvo: instrução, ação, frases e velocidade.
- **Saída** (formato `ajuste_roteiro`), uma de duas:
  - `pergunta`: a IA não entendeu. Volta como uma pergunta com opções no chat, e nada é gerado;
  - `mudanca`: os campos novos do alvo. Por exemplo, nova `instrucao` do quadro, nova `acao`/`motor` do
    trecho, `velocidade`, ou frases do bloco (respeitando o orçamento de R4).
- **Aplicação:** a mudança é aplicada pelo aplicador pelo save normal do roteiro (`service.editar`). O autor é
  o **humano que recusou** (`details.ia` com o `chamadaId`, como na 008). A máquina reposiciona e refaz só o
  que mudou (FR-016, SC-005).
- **Princípio VII:** a IA não decide sozinha. O humano pediu a troca, e o resultado volta para aprovação
  humana no mesmo portão.

**Alternativa descartada:** no wizard, mostrar a proposta para o humano confirmar antes de gerar. Seria
expor o texto do prompt (FR-015) e uma etapa a mais.

## R7. Reuso em dois níveis (clarify 4)

**Decisão:**
- `cenas_para_reuso` (`roteiros/aplicadores.py:122`) passa a devolver as candidatas com o **nível**:
  - **`total`**: mesmo avatar, mesmo cenário, mesma variante de produto, cena `pronta`/`usada` com todos os
    quadros e todas as tomadas dos trechos válidas;
  - **`plano`**: o resto das candidatas que servem.
  - Uma cena com outro produto **não** entra (FR-024).
- O planejador recebe o nível de cada candidata no bloco `<cenas>` e devolve `cena_id` + `nivel`.
- **Reuso do plano:** cria uma **cena derivada** (`cenas.origem_cena_id`), que copia ação, câmera, movimento,
  motor, trechos e as instruções dos quadros, troca avatar, cenário e produto, e nasce em `rascunho`. Vai para
  a biblioteca com o perfil base do roteiro (FR-022, FR-023).
- **Reuso total:** usa a cena como está (`tomada_serve` estendido por trecho, R8). Nenhuma geração (SC-003).
- **Modal de cenas** (FR-019/021): `PUT /api/roteiros/{id}/posicoes/{ordem}/cena` troca a decisão de uma
  posição (`total`/`plano` com `cenaId`, ou `nova`). Uma `nova` pede ao planejador só aquela posição, pelo
  `roteiro.ajuste` com alvo `posicao`.

## R8. Tomada por trecho e a chave do reuso

**Decisão:** `cena_tomadas` ganha `trecho` (0..2) e `keyframe_fim_image_id`. O `tomada_serve` de um trecho
exige todas estas condições:
- mesma cena e mesmo `trecho`;
- não arquivada e não limpa;
- `keyframe_image_id` = quadro[t] e `keyframe_fim_image_id` = quadro[t+1];
- `duracao_ms` ≥ trecho-base × 1000 × 0,95: o `setpts` cobre a diferença.

Com isso, refazer o quadro i invalida só os trechos que tocam esse quadro (FR-028). A tomada da posição vira
uma lista por trecho (tabela `roteiro_trechos`). O `roteiro_cenas.tomada_id` continua para os roteiros da
011.

## R9. Wizard e avançado na mesma tela

**Decisão:**
- **Um roteiro só, duas apresentações.** O switch fica no topo do detalhe do roteiro.
- **Modo lembrado:** o último modo usado fica no `localStorage["sociman:roteiro:modo:<id>"]` (try/catch),
  porque é conveniência de quem está vendo (FR-014), não estado de negócio.
- **Padrão:**
  - `wizard` para os roteiros guiados (`tipo_video` preenchido);
  - `avancado` para os criados pela 011 (FR-018), que abrem sempre no avançado, porque não têm cenário nem
    grade;
  - o switch desses mostra o motivo.
- **Portões no wizard (FR-035):** os do roteiro continuam como estão no banco. No wizard, a tela **não deixa
  desligar** os de narração e keyframes, e o "texto" vira o **modal de cenas**: "Confirmar cenas" = aprovar o
  portão texto. Modo automático e portões ficam só no avançado.
- **Aprovar a sequência por cena:**
  - nova rota `POST …/posicoes/{ordem}/aprovar {etapa: "keyframes"|"clipe"}`;
  - o portão global passa quando todas as posições estão aprovadas;
  - o `aprovar` global da 011 continua (aprova todas de uma vez, no avançado).

## R10. O "Novo vídeo" em blocos e os seletores com imagem

**Decisão:**
- A rota `/app/estudio/videos/novo` passa a ser o **guiado** (FR-018). O `RoteiroNovo` atual sai.
- O `POST /api/perfis/{id}/roteiros` da 011 continua (`deprecated`, para o MCP e os testes).
- Rota nova `POST /api/roteiros` (`roteiros_criar_guiado`).
- **Blocos:** um componente `components/video-guiado/` com um cartão por bloco, no padrão a11y do
  `ProfileImagePicker` (`role="radiogroup"` / `role="radio"` + `aria-checked`).
- **Miniaturas:** o produto já traz `thumbUrl` (`produtos/schemas.py:186`). Para avatar e cenário, conferir
  se a opção traz miniatura. Se não trouxer, somar `thumbUrl` (aditivo) aos resumos de asset. A voz toca
  pelo `PlayerAudio` com o áudio de teste da 025.
- Nenhuma dependência nova: sem radio-group do shadcn, só botões com os papéis ARIA.

## R11. Custo de GPU de um vídeo guiado (para o quickstart)

Para um vídeo de 30 s com 5 cenas, uma média de 2 trechos por cena dá cerca de 15 quadros e 6 trechos de
5 s.
- **Quadros:** pelo log de 2026-10-13, cada um leva ~3 min com o Qwen carregado do HD, o que dá ~45 min.
- **Clipes:** 6 trechos × 5 s × ~57 s/s, cerca de 28 min.
- **Acabamento:** ~20 min.

Total na GPU: ~1 h 30, contra ~75 min das 4 cenas da 011. O reuso total corta tudo isso por posição. O
wizard com 1 versão já corta pela metade em relação às 2 opções da 011.

## R12. Correção da memória do ComfyUI

A correção de 2026-10-13 (`/free` antes de devolver e o `dockerctl` conferindo o uso) é **pré-requisito
operacional**: um vídeo guiado tem muito mais keyframes seguidos. Ela entra na main antes desta spec, num PR
próprio, fora da 031.

## R13. T059: o primeiro vídeo real (2026-10-14 e 15, medido na GPU do dono)

Roteiro `53a12879` (Queridinha, voz Roberta, cozinha retrô, kaftan preto, 15 s = 3 posições × 1 trecho).
Modelos no HD (200 MB/s): o Qwen Edit e o Wan 14B não ficam na VRAM entre jobs.

**Tempos por etapa (GPU):**

| Etapa | Medido | Obs. |
|---|---|---|
| Quadro (Qwen Edit, 736×1344) | 2 a 4 min cada | 6 quadros do zero ≈ 15 min |
| Clipe MiniMax-H3, 5 s | 9 a 11 min | 124 quadros a 24 fps |
| Clipe Wan 2.2 qualidade, 5 s | **1 h 39** | 20 passos × ~290 s; o teto de 3 600 s do gerador cortou 8 vezes de madrugada |
| Montagem (ffmpeg) | segundos | |
| Acabamento HD (SeedVR2 por cena + hqdn3d + lanczos) | 17 min | para 15 s |
| Acabamento leve (lanczos 1080×1920 + loudnorm) | segundos | padrão desde 2026-10-15 |

**Primeira rodada (plano original: 2 cenas no Wan qualidade, 1 no MiniMax):** ruim.
- Cena 1 e 3 tinham `reuso = plano` e caíram no fallback genérico de `plano_guiado.GENERICAS`: o quadro
  inicial e o final nasceram da mesma frase, saíram quase iguais, e o first-last-frame sem diferença
  virou zoom (cena 1). A cena 3 sobreviveu porque o MiniMax segue o texto da ação.
- Cena 2 (caminhada, Wan qualidade): o corpo deslizou sem passos, e o fundo derivou entre os dois
  quadros (chaleira, armário). Locomoção não cabe num trecho de 5 s com quadro final.

**Segunda rodada (tudo no MiniMax, quadros refeitos pelo "Não aprovo"):** "ficou bem rápido e melhor"
(dono). 5 dos 6 quadros limpos; o quadro final da cena 3 veio com uma camiseta por baixo do kaftan
transparente. O MiniMax reenquadrou a cena 2 de corpo inteiro para plano médio fechado. Prévia a 736×1280,
7,3 Mb/s, nítida: "boa o suficiente para o TikTok" (dono). O HD do SeedVR2 fica mais nítido em close e no
tecido, mas não paga 17 min para o TikTok (que recomprime a 2 a 4 Mb/s).

**Decisões do dono (2026-10-15), já no código:**
1. O plano usa **sempre o MiniMax** (`plano.MOTOR_DO_PLANO`); Wan e LTX só à mão, no avançado.
2. O **motor escolhido no regerar de trecho fica na cena** (antes, a cadeia voltava ao motor do plano).
3. O gerador **não tem teto de tempo** nos blocos de vídeo (`comfyui.SEM_TETO`); o cancelamento pelo
   heartbeat continua.
4. **Acabamento `leve` por padrão** (linha ffmpeg, sem GPU) e `hd` opcional, escolhido ao aprovar a prévia
   (`roteiros.acabamento_modo`, migration `0029_acabamento_leve`). No futuro, o HD é cobrado à parte.
5. **Regras do quadro** (`pedidos.REGRAS_QUADRO`) em toda imagem de quadro: produto como na referência
   (cor, tecido, transparência), nada por baixo ou por cima do produto, produto inteiro no quadro, mesmo
   ambiente, mesma pessoa, sem texto ou moldura. E o clipe **mantém o enquadramento do 1º quadro**
   (`prompt_local.AMBIENTE_FIXO`). O estudo da 030 (§4.4) propõe torná-las editáveis e checadas por visão.

**Fica para a 030 / próximas:** matar o fallback genérico das cenas reaproveitadas (o plano deve pedir
os quadros da cena derivada como faz na `nova`); evitar locomoção num trecho de 5 s; a checagem automática
do quadro; o §3 do quickstart (5 s × 8 s, emenda de 3 trechos, SC-006) ainda não foi medido. Deriva de
identidade observada: o rosto da cena 3 saiu mais jovem que o da cena 1 (R3: somar o `rosto_34` às
âncoras é o próximo teste).


**2026-10-16, segundo vídeo real (10 s, 2 trechos), duas falhas no plano:** (1) "A resposta do Claude veio
fora do formato" sem motivo gravado (o cliente da IA só guardava `erro_code`); a reprodução da mesma mensagem
deu um plano válido, então a recusa era intermitente. Agora o motivo da validação fica em
`ia_chamadas.explicacao`, no log do gerador e na mensagem da geração (`cliente.Resultado.erro_detalhe`).
(2) "A IA propôs cenas que somam 15 s; a duração é 10 s": com `<grade>2 trechos de 5 s</grade>` o modelo
propôs 3 cenas de 1 trecho duas vezes seguidas, mesmo com o erro da 1ª tentativa na mensagem. A tag `<grade>`
passou a fazer a conta (`plano._regra_da_grade`: "1 cena com trechos=2, ou 2 cenas com trechos=1; nunca mais
de 2 cenas") e as regras padrão do `roteiro.plano_guiado` (versão 2) pedem a soma antes de responder. A
biblioteca de cenas do perfil já tem candidatas repetidas e uma com "8 seconds" na ação (resto do pipeline
antigo): limpar entra na frente A (031-qualidade-guiado).
