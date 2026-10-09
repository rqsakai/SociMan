# Perguntas abertas para o dono: 015-tiktok-rascunho

> **Resolvido em 2026-09-29.** O dono escolheu as opções recomendadas: **Q1 A, Q2 A, Q3 A, Q4 A**.
> As respostas estão em `spec.md` → Clarifications (Session 2026-09-29). Este arquivo fica só como
> registro das alternativas consideradas.

## Q1. Como contar o limite de "5 rascunhos pendentes em 24 h"?
A TikTok não informa quando você finaliza um rascunho no app.

| Opção | O que significa |
|---|---|
| **A (recomendada)** | Contar localmente: 5 rascunhos criados nas últimas 24 h para a conta, mesmo que você já tenha finalizado algum no app. O 6º espera "aguardando vaga" até o mais antigo completar 24 h. Se a TikTok recusar antes disso, também espera |
| B | Não contar: tentar sempre e só esperar quando a TikTok recusar |

**Por que A:** a recusa da TikTok por excesso pode contar como sinal de spam na conta. Com A, o
pior caso é esperar um pouco mais. Depois do teste real (quickstart §4.2), dá para afrouxar.

## Q2. Editar textos de um "Publicar no horário" já agendado

| Opção | O que significa |
|---|---|
| **A (recomendada)** | Só um dono pode editar. A edição vale como nova confirmação: o SociMan guarda o texto novo como o que será publicado e registra no histórico |
| B | Ninguém edita: para mudar o texto, cancele e agende de novo, passando outra vez pela tela da TikTok |
| C | Membro também edita, e o agendamento volta a pedir a confirmação de um dono |

**Por que A:** no modo publicar, quem posta é o SociMan, e o texto publicado precisa ser o que um
dono confirmou. A é o jeito mais curto de manter isso. No rascunho e no lembrete, os textos
continuam livres, como na 014.

## Q3. O interruptor geral

| Opção | O que significa |
|---|---|
| **A (recomendada)** | Dois níveis: `PUBLICACAO_HABILITADA` no `.env` do servidor (desligado por padrão) **e** o botão "Envios automáticos" na tela. Só envia com os dois ligados |
| B | Só o botão na tela |
| C | Só o `.env` (desligar exige mexer no servidor) |

**Por que A:** o `.env` é um corte físico que nenhuma sessão (nem uma sessão de dono roubada)
consegue ligar. O botão é o controle do dia a dia que a spec pede. Na prática, você liga o
`.env` uma vez e usa o botão.

## Q4. "Tentar de novo" quando a TikTok talvez tenha recebido
Se o SociMan cair entre o pedido e a resposta, ele não sabe se o rascunho foi criado.

| Opção | O que significa |
|---|---|
| **A (recomendada)** | Mostrar "Falhou: a TikTok pode ter recebido". "Tentar de novo" exige marcar "Conferi no app e o rascunho não chegou" |
| B | Bloquear "Tentar de novo" nesse caso: só agendar outra vez pelo conteúdo |

**Por que A:** é raro, e você é quem vê a caixa de entrada do app. A confirmação evita o
rascunho duplicado sem obrigar a refazer o agendamento.
