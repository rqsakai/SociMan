# ADR 0006 — E-mail BYOK (cliente traz a key e paga o provider direto)

**Status:** Aceita

## Contexto

O app precisa enviar e-mail (verificação/reset). A Azion **não tem serviço de
e-mail**. Duas questões: (1) quem paga, e (2) restrição de runtime — no isolate
da borda só dá para enviar via **API HTTP (`fetch`)**, não SMTP (sem socket TCP).

O objetivo do produto: deixar o **cliente pagar o provider direto**, reduzindo
custo direto do Volans e evitando bitributação (Volans comprar e revender).

## Decisão

- **BYOK (Bring Your Own Key)**: o cliente tem a própria conta no provider (o
  cartão é dele) e fornece uma API key, guardada como Variable secret por app. O
  dinheiro vai direto do cliente ao provider.
- **Sem teto de gasto no app**: é BYOK — o Resend/cliente bloqueia sozinho ao
  bater o limite do plano. Não replicamos essa lógica (simplificação deliberada).
- **Provider default: Resend** (API HTTP, funciona na borda e em Node; 3k/mês
  grátis). Adapter agnóstico por `EMAIL_PROVIDER`.
- **SMTP** disponível para o cliente que já tem servidor — mas **só no deploy
  Node/Docker** (SMTP é TCP, não roda na borda). Interface `EmailProvider`
  idêntica; trocar é config.
- Subcontas de Mailgun/SendGrid foram **rejeitadas**: o billing sobe para a
  conta-mãe (Volans pagaria) — exatamente a bitributação a evitar.

## Consequências

- Domínio `mail.theitnerd.io` verificado no Resend (SPF/DKIM/MX no Route53).
- Adapters: `resendEmail.ts` (HTTP), `smtpEmail.ts` (Node), `stubEmail.ts`,
  `fileEmail.ts`. Contrato em `services/emailService.ts`.
- Detalhes: [../config/email.md](../config/email.md).
