# Perguntas abertas para o dono: 014-central-de-conteudos

> **RESOLVIDO em 2026-09-29.** Respostas do dono: **Q1 A, Q2 A, Q3 C (padrão de 30 min), Q4 A**.
> Registradas em `spec.md` → Clarifications (Session 2026-09-29) e refletidas em plan, research
> (R6, R7, R9, R13), data-model (`contas.intervalo_min_minutos`), contrato e quickstart.
>
> - **Q1 A:** dono e membro agendam/reagendam/cancelam o que já está aprovado; aprovar só dono. Na
>   015, os modos automáticos ficam restritos a donos (constitution 4.0.0, princípio I).
> - **Q2 A:** editar textos depois da aprovação não desfaz a aprovação; tudo no histórico.
> - **Q3 C:** intervalo mínimo por conta (`intervalo_min_minutos`, padrão 30, 0..1.440, só dono
>   edita, com histórico). A sequência **pula** os horários em conflito; o agendamento individual
>   **avisa** (409 `intervalo_conflito`) e deixa manter (`ignorarIntervalo: true`, registrado no
>   histórico).
> - **Q4 A:** vídeo próprio de 1 s a 10 min, até 2 GB, qualquer proporção, aviso "não é vertical".
>
> O texto abaixo fica como registro das opções apresentadas.

## Q1. Quem pode agendar um conteúdo já aprovado?
Aprovar ("pode ir para esta conta") já é só do dono. A dúvida é o "quando".

| Opção | O que significa |
|---|---|
| **A (recomendada)** | Dono e membro agendam, reagendam e cancelam o que **já está aprovado**. Membro diante de um item não aprovado vê "Pedir aprovação" |
| B | Só o dono agenda. O membro prepara os textos e pede aprovação; o dono escolhe data e hora |

**Por que A:** a decisão sensível (esta conta pode receber este vídeo) continua com o dono, e
montar a grade da semana é trabalho operacional que um membro pode fazer. Na 014, agendar só gera
lembrete; quando a 015 trouxer modos automáticos, dá para restringir por modo.

## Q2. Editar os textos depois da aprovação desfaz a aprovação?

| Opção | O que significa |
|---|---|
| **A (recomendada)** | Não. A aprovação vale para o vídeo naquela conta; os textos seguem editáveis e cada mudança fica no histórico |
| B | Sim. Qualquer mudança de título, descrição ou hashtags volta o destino para "Pronto" e exige nova aprovação |

**Por que A:** no lembrete manual, quem posta é você e revê o texto na hora. Exigir nova aprovação a
cada ajuste de hashtag travaria a fila. Na 015, para "publicar no horário", podemos exigir que o
texto aprovado seja o texto enviado (research R13).

## Q3. O que conta como "horário em conflito" na sequência?
Ao agendar em sequência, os horários que conflitam com outro agendamento **da mesma conta** são
pulados.

| Opção | O que significa |
|---|---|
| **A (recomendada)** | Conflito = outro agendamento da mesma conta a menos de **30 min** |
| B | Só o **mesmo horário exato** conflita |
| C | Um intervalo mínimo configurável por conta (ex.: 2 h no TikTok) |

**Por que A:** evita dois posts colados na mesma conta sem precisar de configuração nova. É uma
constante: mudar para outro valor depois é uma linha. C só vale a pena se as contas tiverem
rotinas muito diferentes.

## Q4. Limites do vídeo próprio

| Opção | O que significa |
|---|---|
| **A (recomendada)** | De 1 s a **10 min**, até 2 GB, qualquer proporção; vídeo que não é vertical entra com o aviso "não é vertical" |
| B | Só vertical (9:16) e até 3 min (o limite do Shorts); o resto é recusado |
| C | Até 60 min, sem aviso de proporção |

**Por que A:** 10 min é o máximo que a API do TikTok aceita (a 015 vai usar); o aviso cobre o caso
comum (Shorts e Reels querem vertical) sem impedir um vídeo horizontal para outra rede.
