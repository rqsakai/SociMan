# Insumo da 033: banco de prompts (absorve "regras de quadro")

Pedido do dono em 2026-10-16. Insumo para o `/speckit-specify`, não é spec. Substitui o item
`033-regras-de-quadro` do backlog (o estudo da 030, §4.4, continua valendo como parte dele).

## O pedido
> "Precisamos incorporar o máximo possível desse conhecimento na nossa ferramenta para otimizar geração de
> avatares, fundos, imagens de produto, implementar POV, avatar, modelo espelho etc. O ideal seria ter um admin
> de prompts para visualizar os prompts salvos, como eles são usados e poder modificar na ferramenta."

Material recebido:
- dois prompts "universais" do dono (vídeo geral e vídeo POV), colados no chat de 2026-10-16;
- o e-book "120 Prompts Poderosos" da Influencers Lab (extraído em
  `docs/insumos/prompts-externos/120-prompts-influlab.json`: número, título, categoria, prompt, para que serve);
- a ferramenta deles (`app.influencerslab.com.br`), vista pelo Chrome do dono em 2026-10-16: Lab de Imagens
  (24 prompts, categorias COPA, POV, POV roupa na cama, Restaurar, UGC), Lab de Vídeos (prompts validados em
  pares "Prompt do Flow" longo e "Prompt do Create" comprimido; categorias CTA, Formato dinâmico, Formato viral,
  Moda, Moda masculina, Movimento, Movimento masculino, POV, UGC) e Banco de Modelos (personagem = descrição
  fixa colada em todo prompt + foto-mãe 9:16 com blusa branca e fundo neutro).

**Direito:** o material é de terceiros, comprado pelo dono. Serve como referência de padrões; os blocos do
SociMan são escritos por nós, com as nossas palavras e os nossos campos. Nada é redistribuído.

## 1. O que a ferramenta deles é, e o que a nossa é
Eles **não geram nada**: são uma biblioteca de prompts para colar no Google Flow, Sora ou "Create", com um
"modelo" (descrição do personagem) que o app concatena nos prompts. Nós **geramos** (ComfyUI local hoje,
provedores externos depois) e já temos o equivalente do "modelo" deles bem mais forte: o kit do avatar da
025 (`descricao_prompt` fixa, rosto frontal, 3/4, corpo-base), o cenário com prompt congelado, o produto com
recorte, flat e ficha, e o guia do perfil. O que falta não é o conteúdo dos prompts; é **ver e editar os blocos
que já usamos** e **ter formatos de cena além do "avatar no cenário"**.

## 2. Inventário: os blocos de prompt fixos no código hoje
| Bloco | Arquivo | Usado em |
|---|---|---|
| `REGRAS_QUADRO` (produto como na referência, nada por baixo/por cima, inteiro no quadro, mesmo ambiente e pessoa) | `roteiros/pedidos.py` | toda imagem de quadro da 031 e o keyframe da 011 |
| `composicao_do_quadro` (quadro 0 = cenário + corpo-base + produto; quadro i = quadro i-1 + produto + rosto frontal) | `roteiros/pedidos.py` | cadeia de quadros |
| `GENERICAS` (início/meio/fim a partir da ação) | `roteiros/plano_guiado.py` | fallback das cenas reaproveitadas (a matar na frente A) |
| `AMBIENTE_FIXO`, `MOUTH_CLOSED`, `REALISMO` (uma frase) | `cenas/prompt_local.py` | prompt do clipe (MiniMax/Wan/LTX) |
| `REALISMO` do passo de imagem | `geracao/passos.py` | passos `keyframe` |
| instruções fixas do kit (rosto frontal, 3/4, corpo-base) | `assets/padrao.py` | 025 |
| instrução do flat do produto | `produtos/flat.py` | 012 |
| prompt da cena do cenário | aplicador `cenario.cena` | 021 |
| regras das tarefas de texto (plano v2, perguntas, ajuste, ficha, identidade) | `ia/regras_padrao.py` | já **editáveis** em Assistente de IA › Regras (`ia_regras`) |

Ou seja: a infraestrutura de "padrão em código + texto editado no banco + voltar ao padrão + versão + histórico"
já existe para os prompts de **texto** (spec 008). O banco de prompts estende isso aos blocos de **imagem e
vídeo** e aos **formatos de cena**.

## 3. O que entra do material recebido (triagem)
**Dos dois prompts do dono** (vídeo geral e POV), cabe no nosso clipe first-last-frame de 5 s em voice over:
- realismo visual (pele com poros, cabelo com física, tecido com peso e reflexo, sem pós-processamento nem
  efeito cinematográfico);
- comportamento natural (postura relaxada, gestos suaves, piscadas, microexpressões, sem atuação de vendedora;
  interação adaptada ao tipo de produto);
- interação com o produto (fiel sempre, pegada e pressão proporcionais, sem distorção nem mudança de escala);
- POV: câmera = olhos, mão real com anatomia correta, micro-tremor de celular, nunca mostrar rosto.

**Fica de fora**, por bater com decisões da T059 e do formato aprovado: câmera com push-in e "evitar plano
estático" (o MiniMax reenquadrou; `AMBIENTE_FIXO` trava o enquadramento do 1º quadro) e fala na câmera (voice
over; a boca fica fechada; o áudio do modelo é descartado). O POV é a exceção natural: sem rosto, o micro-tremor
de câmera na mão é desejável.

**Da ferramenta deles**, os padrões que valem a pena (reescritos por nós):
- "product lock" / "identity lock": lista explícita do que preservar (cor, estampa, costura, alças, proporção,
  transparência) e "se a referência mostra 1 peça, 1 peça; se mostra um kit, o mesmo número";
- "strict rules" de vídeo: anatomia de 5 dedos, nada de mão extra, sem morphing, sem texto, sem corte, sem zoom;
- linha do tempo por segundos dentro de um clipe (0–2 s abre a embalagem, 2–4 s estica o tecido…): na nossa
  grade isso é a sequência de quadros; o que falta é o **vocabulário de ações por tipo de produto** (abrir,
  desdobrar, esticar, amassar, virar, pôr no pé, pôr na caixa);
- prompt negativo explícito (dedos extras, mão deformada, reflexo irreal, CGI, texto);
- cenário "casa brasileira de classe média" como ambiente padrão de POV, não loja de luxo;
- formatos: POV mãos (produto na cama, no cabide, na mão, na caixa, no pé), modelo sem rosto (corpo da
  influenciadora, enquadramento abaixo do rosto, mãos sempre ativas), produto na loja/fábrica (cena de
  ambiente), kit com variações de cor, "foto-mãe" do personagem (nós já temos: o kit da 025).

**Do e-book (120):** 36 prompts são de imagem, vídeo (Veo 3) e TikTok Shop; são curtos e genéricos
("foto estilo iPhone", "antes e depois", "unboxing"). Servem como **sementes de formato** e de estilo, não como
blocos prontos. Os outros 84 são pedidos de texto (precificação, e-mails, conteúdo evergreen) e cabem, se
quiserem, como "pedidos prontos" do Assistente de IA, fora desta spec.

## 4. O que a spec 033 precisa cobrir
### 4.1 Blocos de prompt editáveis (o "admin de prompts")
- Cada bloco fixo do inventário vira um **bloco com chave** (ex.: `quadro.regras`, `clipe.ambiente_fixo`,
  `clipe.realismo`, `clipe.boca`, `quadro.composicao.0`, `kit.rosto_frontal`, `produto.flat`), com o padrão em
  código, texto editado no banco (`ia_regras` ampliada ou tabela irmã), "voltar ao padrão", versão e histórico,
  igual à 008.
- **Três níveis**, como o estudo da 030 propôs: global → perfil base → formato/movimento. O nível mais específico
  vence; a tela mostra a cadeia.
- Tela **Assistente de IA › Prompts** (só dono): lista por grupo (texto, quadro, clipe, kit, produto, cenário),
  para cada bloco **onde é usado** (passos e telas), o texto padrão e o editado, e a **prévia do prompt
  montado** com uma geração real recente (as `geracoes` guardam o prompt enviado em `params`; a tela monta o
  antes/depois com a edição ainda não salva).
- O texto da fala e os prompts nunca aparecem no wizard do leigo (FR da 031 continua).
- Prompt negativo do bloco keyframe: exige mexer no `../comfyui-docker` (bloco `V2 - Keyframe`); fica marcado
  "com autorização do dono" e entra só se o bloco expuser o parâmetro.

### 4.2 Formatos de cena (o "POV, avatar, modelo espelho")
- Hoje só existe `tipo_video = avatar_pov` (avatar no cenário, voice over). A spec define **formato de cena**
  como um valor da cena/posição que muda a **composição do quadro** e os **blocos do clipe**:
  - `avatar` (o de hoje): cenário + corpo-base + produto; rosto frontal nos quadros seguintes; boca fechada;
    enquadramento travado;
  - `pov_maos`: sem avatar; cenário + produto + mãos (gênero e unhas como atributo do perfil ou da cena);
    câmera na mão com micro-tremor; nunca rosto; ações do vocabulário por tipo de produto;
  - `sem_rosto`: corpo-base do avatar recortado abaixo do rosto, mãos sempre ativas no produto;
  - `espelho`: selfie no espelho com o celular (o avatar segura o celular; o produto vestido); exige teste na
    GPU antes de entrar (o MiniMax e o Qwen desenham a moldura do celular quando o prompt diz "phone");
  - `produto_so`: flat lay / na cama / no cabide / na caixa, sem pessoa (quadro único + clipe de 5 s).
- Cada formato tem os seus blocos (chaves com prefixo do formato) e o seu **vocabulário de ações** por tipo de
  produto (roupa, calçado, óculos, cinto, perfume, lingerie, utilidades), que o plano v2 usa em vez de inventar.
- A 030 (movimentos) continua sendo "ficha de movimento com quadro final"; o formato é o nível acima (o
  movimento pertence a um formato). A 032 (variantes) ganha de graça: versões de uma posição podem ser formatos
  diferentes.

### 4.3 Checagem do quadro por visão (do estudo da 030)
- Passo `cena.quadro_checagem` (Claude com imagem) contra as regras do bloco `quadro.regras` efetivo; reprovou →
  nova seed até N; esgotou → cartão "atenção" no wizard; registro das reprovações (motivo, bloco, formato) para
  evoluir os blocos. Fica como história separada, depois dos blocos e formatos.

### 4.4 Primeiro passo, antes da spec (pode ir na frente A)
Ampliar `clipe.realismo` com os três blocos do item 3 (realismo, comportamento, interação com o produto) e
somar uma frase de pele e tecido às `REGRAS_QUADRO`. Sem migration, só testes de prompt. Gerar um clipe para
comparar com o do Queridinha antes de seguir.

## Para decidir no clarify
- [ ] Os blocos editáveis moram em `ia_regras` (chave = bloco, `entity_type` novo) ou numa tabela própria
      `prompt_blocos` com o nível (global/perfil/formato)?
- [ ] Quais formatos entram na primeira versão: só `avatar` + `pov_maos`? (`espelho` e `sem_rosto` exigem
      teste na GPU.)
- [ ] As mãos do POV são atributo do **perfil** (gênero, tom de pele, unhas, acessórios) ou da **cena**?
- [ ] O vocabulário de ações por tipo de produto é fixo em código (como os 13 tipos da 008) ou editável?
- [ ] A prévia do prompt montado usa a última geração real do perfil ou um exemplo sintético?
- [ ] Os 84 prompts de texto do e-book viram "pedidos prontos" do Assistente de IA ou ficam fora?
