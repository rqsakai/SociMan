# Perguntas abertas para o dono: 008-assistente-ia

> **RESOLVIDO em 2026-09-29.** Respostas do dono, já aplicadas em spec.md (Clarifications), plan.md,
> research.md, data-model.md, contracts/http-api.md, quickstart.md e tasks.md:
> - **Q1 = B**: "Aplicar" salva na hora só aquele campo (1 clique), pelo save normal da entidade
>   (validação, versão com 409, histórico com autor humano e `details.ia`). As outras alterações não
>   salvas continuam no formulário. No kit (`PUT` inteiro): os tokens salvos com só aquele campo
>   trocado. "Editar e aplicar" edita no painel e salva.
> - **Q2 = B**: `avatar.regras_imagem` no idioma do perfil (pt-BR). `avatar.descricao_prompt` e
>   `cenario.prompt_ambiente` continuam em inglês.
> - **Q3 = lista com seleção**: em `kit.bordoes` e `kit.series`, a IA devolve sugestões; o usuário
>   marca as que aceita (entram no fim da lista ao aplicar) e pode pedir "Gerar mais", que leva os
>   já aceitos (do kit e marcados na sessão) e os rejeitados na sessão. Limite de 20 itens, com
>   aviso quando a lista enche.
>
> O texto abaixo é o registro das perguntas como foram feitas.

O plano seguia a opção recomendada de cada pergunta. Se a resposta for outra, o impacto está
descrito em cada uma. As três decisões padrão das Assumptions da spec (regras globais, sem conversa
persistida, sem teto de gasto) ficam como estão: são fáceis de mudar depois sem refazer nada
(`ia_regras` aceita `perfil_id`, e o resumo do mês já mostra o gasto).

## Q1. O que o botão "Aplicar" faz
A spec diz "o campo recebe o texto, a entidade é salva pelo caminho normal" (US1-4) e também "só
aquele campo muda; o resto do que ele digitou continua lá" (US1-7).

| Opção | O que significa |
|---|---|
| **A (recomendada)** | "Aplicar" põe a proposta **no campo**, e você clica em **Salvar** como sempre (2 cliques, SC-002). O que você digitou nos outros campos continua lá e é salvo junto, se você quiser. A versão sai com o seu nome e o selo "com ajuda da IA" |
| B | "Aplicar" já **salva** só aquele campo (1 clique). Os outros campos editados continuam no formulário, sem salvar. Exige um segundo caminho de salvar em cada tela e, no kit (que é salvo inteiro), um "salvar só os bordões" novo |

**Por que A:** é o mesmo caminho da edição manual (FR-006) em todas as telas, sem exceção, e
nunca grava nada que você não viu no formulário. O custo é um clique a mais. A frase da US1-4
seria ajustada para "o campo recebe o texto, e salvar grava pelo caminho normal".

## Q2. Idioma das "Regras de imagem" do avatar
A descrição para prompt e o prompt do cenário saem em **inglês** (vão para o Flow/Veo). As regras
de imagem ("nunca mostrar de costas", "sempre com avental rosa") podem ser lidas por você ou
coladas no prompt.

| Opção | O que significa |
|---|---|
| **A (recomendada)** | Inglês, como os outros prompts de imagem: dá para colar no Flow junto com a descrição |
| B | No idioma do perfil (pt-BR): mais fácil de ler e revisar, mas precisa traduzir antes de colar no Flow |

**Por que A:** o uso principal é montar o prompt da geração; misturar idiomas no prompt do Veo piora
a consistência da personagem. Se você usa as regras só como lembrete para você, escolha B (muda
uma linha do registro e o texto padrão).

## Q3. Bordões e séries: a lista inteira ou um item
Na aba Marca, bordões e séries são listas (até 20 itens cada).

| Opção | O que significa |
|---|---|
| **A (recomendada)** | Um botão por lista. A IA propõe **a lista inteira** ("crie 5 bordões", "deixe as séries mais curtas", "acrescente 2 no tom da Achadinhos"), e você vê antes e depois item a item |
| B | Um botão por item: melhora só aquele bordão. Criar vários exige clicar várias vezes |

**Por que A:** os pedidos reais são sobre o conjunto (criar, completar, padronizar), e a lista
inteira deixa a IA evitar repetição entre os itens. Melhorar um só continua possível pela
instrução ("mude só o terceiro").
