# Perguntas abertas para o dono: 006-cortes-openshorts

> **Resolvido em 2026-09-29.** O dono respondeu **Q1 A, Q2 A, Q3 A, Q4 A** (todas as
> recomendações). As respostas estão em `spec.md` → Clarifications → Session 2026-09-29, e o plano
> já seguia essas opções. O texto abaixo fica como registro da decisão.

## Q1. "Hora de postar" com o app fechado
Hoje o aviso aparece no sino e como notificação do navegador **enquanto o SociMan está aberto**
(numa aba ou no app instalado). Com tudo fechado, nada chega ao celular até você abrir o app.

| Opção | O que significa |
|---|---|
| **A (recomendada, escolhida)** | Só com o app aberto nesta spec. Simples, sem dependência nem serviço externo. Os avisos ficam guardados no sino |
| B | Web Push: o aviso chega com o app fechado (Android e desktop; no iPhone, só com o app instalado e de forma instável). Exige chaves VAPID, a dependência `pywebpush` e mandar os avisos pelo serviço de push do Google/Mozilla (dados saem da rede de casa). Soma cerca de 1 fase ao plano (R11) |
| C | Aviso pelo Telegram, com o bot do OpenClaw. Fica fora do SociMan, e o Telegram da agência ainda está adiado |

**Por que A:** a rotina de postar já acontece com o celular na mão. O Web Push é uma peça extra
que vale a pena só se você perder horários na prática, e dá para acrescentar depois sem refazer
nada (a tabela de notificações já existe).

## Q2. Um corte em várias redes
O mesmo corte pode ir para TikTok e YouTube Shorts (e Kwai…), cada um com seu texto e horário?

| Opção | O que significa |
|---|---|
| **A (recomendada, escolhida)** | Sim: uma **postagem por conta de destino**, cada uma com textos, data e hora e "Postado" próprios, e uma aba por conta na tela do corte (data-model `postagens`) |
| B | Não: uma plataforma por corte. Os campos ficam no próprio corte. Postar em outra rede exige duplicar o corte |

**Por que A:** o repost em várias redes é o normal em perfis de cortes, e cada rede tem limites e
tom diferentes. O custo é uma tabela, que também deixa o histórico dos textos separado do corte.

## Q3. Membro pode enviar vídeo "Sem acordo" ou avulso?
A constitution 3.0.0 deixa o direito sob sua responsabilidade: o sistema avisa e registra, mas não
bloqueia. Só você muda o status do canal. A dúvida é quem pode **enviar** um vídeo que exige o
aviso.

| Opção | O que significa |
|---|---|
| **A (recomendada, escolhida)** | Dono e membro enviam; os dois veem o aviso e confirmam. O histórico mostra quem confirmou |
| B | Só o dono envia vídeo de canal "Sem acordo" ou avulso; o membro vê "Peça ao dono" (403). Vídeos de canais "Próprio", "Parceiro" e "Programa de cortes" continuam liberados para os dois |

**Por que A:** segue a 3.0.0 ao pé da letra (nada bloqueia) e não trava o trabalho do membro. Se
você quiser que o risco jurídico só seja assumido por você, escolha B: é uma checagem de papel na
rota `enviar`, com teste (R12).

## Q4. Estilo da legenda dos clipes
Hoje o OpenShorts queima a legenda padrão dele (Anton branca, karaokê amarelo). O plano pede ao
OpenShorts que refaça a legenda de cada clipe no **estilo do kit do perfil**, antes de importar.

| Opção | O que significa |
|---|---|
| **A (recomendada, escolhida)** | Legenda do kit (fonte, cores, posição e efeito da aba Marca), via `/api/subtitle`. Soma cerca de 30 a 60 s de CPU **por clipe** (de 3 a 6 min num envio de 6 clipes). O padrão de corte do perfil ainda permite escolher "gerador" ou "nenhuma" |
| B | Legenda padrão do OpenShorts em todos os perfis: mais rápido, mas igual em todos os perfis e fora do kit |
| C | Sem legenda no OpenShorts. A legenda passaria para o worker do SociMan, o que exige outra spec (transcrição por palavra e render de karaokê no SociMan) |

**Por que A:** é o que dá a cara de cada perfil (princípio III, marca em tokens), com código que a
004 já validou (a seção `openshorts.subtitle`). O custo é tempo de CPU enquanto não há GPU, e ele
diminui quando a RTX 5060 Ti entrar.
