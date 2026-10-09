# Perguntas abertas para o dono: 017-guia-de-comunicacao

**Status: RESOLVIDAS em 2026-09-30** (spec → Clarifications). Resumo:
- **Q1 → variante de A:** a voz do guia não entra nos 3 campos visuais, mas eles recebem as
  **palavras proibidas** do perfil (mesma detecção e bloqueio) e a tela mostra o link "Ver guia de
  comunicação do perfil". `usa_guia` passa a ser `"completo" | "so_proibidas"` (research R3).
- **Q2 → A:** editado por um humano, pode aplicar; o servidor recusa só o campo salvo igual à
  proposta que contém a proibida (research R7).
- **Q3 → nova opção:** padrão 5, **configurável por conta** (`maxHashtagsFixas`, 0..8, vazio = 5);
  as fixas do perfil (até 5) mais as da conta, sem repetir, não passam do máximo da conta
  (research R6). Muda o modelo de dados: uma coluna `max_hashtags_fixas` em `ia_guias`.

O texto abaixo é o registro original das perguntas.

## Q1. O guia entra nos campos visuais do avatar e do cenário?
A spec diz "em qualquer Melhorar com IA". Três campos não são comunicação: a descrição para
prompts do avatar e o prompt do ambiente do cenário (em inglês, para o Flow/Veo) e as regras de
imagem do avatar.

| Opção | O que significa |
|---|---|
| **A (recomendada)** | O guia **não** entra nesses 3 campos. Entra em todos os outros, inclusive no tom de voz do avatar. Tom, vocabulário e emojis de legenda não ajudam (e podem atrapalhar) um prompt de imagem em inglês |
| B | O guia entra em todos os campos. Custa um pouco mais por chamada e pode "vazar" vocabulário em português para o prompt em inglês |

Impacto de B: só o valor de `usa_guia` em 3 tipos (`tipos.py`).

## Q2. Palavra proibida no texto editado
Quando a proposta traz uma palavra proibida, o "Aplicar" direto fica bloqueado. A dúvida é o que
acontece depois que você **edita** a proposta.

| Opção | O que significa |
|---|---|
| **A (recomendada)** | Editou, pode aplicar: a decisão passa a ser sua (como a spec diz, "impede o Aplicar até o usuário editar"). O servidor recusa só a aplicação **sem edição** |
| B | Continua bloqueado enquanto a palavra estiver no texto editado. Exige conferir o texto no servidor a cada salvamento do painel (um aviso a mais no fluxo) |

Impacto de B: a checagem do `marcar` passa a valer também para o texto editado; sem mudança de
tela além da mensagem.

## Q3. Quantas hashtags fixas no máximo
O limite de hashtags de uma postagem é 8 (mínimo 3).

| Opção | O que significa |
|---|---|
| **A (recomendada)** | Até **5** somando perfil e conta. Sobram pelo menos 3 vagas para hashtags do vídeo |
| B | Até 8. Com 8 fixas, a IA não escolhe nenhuma hashtag do vídeo |

Impacto de B: só as constantes de limite e a mensagem.
