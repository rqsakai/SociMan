# Perguntas abertas para o dono: 007-assets-do-perfil

> **Resolvido em 2026-09-29.** O dono escolheu a opção recomendada nas três: **Q1 = A**, **Q2 = A**,
> **Q3 = A**. As respostas estão em `spec.md` (Clarifications, Session 2026-09-29), e o plano já
> seguia essas opções. Nenhum impacto adicional.

Três decisões de alto impacto (registro histórico).

## Q1. Um corte que usou a imagem impede arquivar o asset?
Hoje o corte guarda a imagem já resolvida no envio (a chave do arquivo), e arquivos nunca são
apagados. Arquivar o asset não muda nenhum corte já feito.

| Opção | Resposta | Impacto |
|---|---|---|
| **A (recomendada)** | Só o **kit** bloqueia o arquivamento. Os cortes aparecem em "Onde é usado" ("12 cortes") só como informação | o que está no plano (R5) |
| B | Cortes também bloqueiam: quem usou a imagem uma vez nunca mais deixa arquivá-la | provedor de cortes com `bloqueia = true`; na prática, fundos e marcas d'água antigos ficam presos na biblioteca para sempre |
| C | Cortes nem aparecem em "Onde é usado" | remove o provedor de cortes; a US4 perde a parte "cortes" da spec |

## Q2. Quais tipos cada seletor do kit mostra?
Sticker e marca d'água exigem transparência; cenário e fundo aceitam imagem opaca com mínimo de
540×540.

| Opção | Resposta | Impacto |
|---|---|---|
| **A (recomendada)** | Fundo do gancho e do card: **fundos e cenários**. Marca d'água: **marcas d'água e stickers** | o que está no plano (R3, R6): mesmas regras técnicas, nenhuma mudança no corte |
| B | Estrito: fundo só `fundo`, marca d'água só `marca_dagua` | o `ref_context` passa a filtrar pelo tipo do asset; para usar a imagem de um cenário como fundo, o dono envia de novo como fundo (arquivo duplicado) |
| C | Qualquer imagem compatível (fundo: qualquer uma ≥ 540×540, inclusive de avatar; marca d'água: qualquer uma com transparência) | o corte e os links de mídia passam a aceitar outras classes de imagem (toca `cortes/service.py`, área da 006) |

## Q3. Como reordenar poses e referências?

| Opção | Resposta | Impacto |
|---|---|---|
| **A (recomendada)** | Botões "mover ←/→" em cada card (funcionam no celular e no teclado) e, no computador, arrastar com o recurso nativo do navegador. Sem biblioteca nova | o que está no plano (R9); arrastar não funciona no toque (no celular, só os botões) |
| B | Biblioteca de arrastar (`@dnd-kit`), com arrastar também no celular | dependência nova no SPA: exige justificativa no Complexity Tracking (princípio VIII) e aumenta o bundle |
| C | Só os botões, sem arrastar | um pouco menos de código; no computador, reordenar 10 poses fica mais lento |
