# Insumo da 032: variantes de vídeo (cenas intercambiáveis, produto cartesiano)

Pedido do dono em 2026-10-13. Este arquivo é insumo para o `/speckit-specify`, não é spec. Depende da 031
(grade de duração: todas as cenas de uma posição com o mesmo tamanho) e da 011 (roteiro, narração, montagem e
entrega).

## Objetivo
Fazer de um produto **vários vídeos diferentes** gastando GPU de vídeo uma vez só. Para cada posição do
roteiro, gera-se e aprova-se **mais de uma versão de cena**. Os vídeos saem das **combinações** dessas versões,
com **narrações diferentes**. O gasto extra fica no TTS (barato), não na geração de imagem e vídeo (caro).

## Exemplo do dono
Vídeo A com 3 posições e 2 versões de cada:

| Posição | Versões |
|---|---|
| Cena A | V1, V2 |
| Cena B | V1, V2 |
| Cena C | V1, V2 |

Combinações possíveis: 2 × 2 × 2 = **8 vídeos**. Por exemplo, A1-B1-C1, A2-B2-C2, A1-B1-C2, A1-B2-C2,
A2-B1-C1 e assim por diante.

## O que a spec precisa cobrir
- **Versões por posição:**
  - pedir N versões de uma cena;
  - aprovar cada uma separadamente (só humano);
  - a versão aprovada fica na biblioteca, ligada ao produto.
- **Montar as combinações:**
  - mostrar o total possível;
  - deixar o operador escolher quantos vídeos quer;
  - sugerir as combinações **mais diferentes entre si**.
- **Narração por variante:**
  - texto e voz podem mudar por vídeo;
  - cada bloco de fala fica preso à posição e tem de caber no tamanho da grade.
- **Entrega:**
  - cada variante vira um conteúdo da 014 (`gerado_ia`, sem conta);
  - o conteúdo registra a combinação usada (quais versões e qual narração), para a análise da 023 dizer qual
    cena e qual fala rendem mais.
- **Custo à vista:** antes de gerar, quanto custa em GPU e em TTS; depois, quanto se economizou contra gerar
  tudo do zero.

## Riscos (levantados em 2026-10-13)
- **A conta explode:** 5 posições × 2 versões = 32 vídeos; × 3 versões = 243. Precisa de um teto e da escolha
  das mais diferentes. Por exemplo, diferir em pelo menos 2 posições e sempre variar o gancho (posição 1).
- **Conteúdo repetido:** a TikTok derruba o alcance de vídeos quase iguais (conteúdo não original ou
  duplicado). Espalhar entre contas e datas (o intervalo mínimo por conta da 014 ajuda) e variar o gancho e a
  narração. A spec deve avisar quando duas variantes na mesma conta forem parecidas demais.
- **Fala e imagem casadas:** a fala de uma posição precisa servir para todas as versões daquela cena. A cena
  e a fala devem ser planejadas por **intenção da posição** (ex.: "mostrar a leveza do tecido"), não por
  versão.
- **Limpeza de 90 dias (constitution 4.5.0):** versão aprovada que entrou em algum vídeo entregue fica
  protegida; versão aprovada e nunca usada segue a regra de desuso.

## Para decidir no clarify
- [ ] As versões de uma posição saem de **seeds diferentes do mesmo prompt** ou de **prompts diferentes**
      (ângulo, movimento)?
- [ ] Qual o teto de variantes por lote?
- [ ] A narração varia só o texto (mesma voz) ou também a voz?
- [ ] As variantes saem já com destino (conta e data espalhadas) ou ficam sem destino, como na 011?
