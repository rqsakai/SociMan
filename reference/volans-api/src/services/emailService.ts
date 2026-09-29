// Contrato de e-mail (§3): a interface e o conteúdo das mensagens. Cada provider
// é um ADAPTER em lib/adapters/ (resendEmail, smtpEmail, stubEmail, fileEmail),
// selecionado por EMAIL_PROVIDER. Aqui não há implementação — só o contrato,
// para poder ser importado tanto no Node quanto no isolate da borda.

export interface EmailProvider {
  sendVerificationEmail(to: string, link: string): Promise<void>;
  sendPasswordResetEmail(to: string, link: string): Promise<void>;
}

// Conteúdo dos e-mails, compartilhado por todos os adapters (sem drift).
export const emailMessages = {
  verification: (link: string) => ({
    subject: "Confirme seu e-mail",
    text: `Bem-vindo! Confirme seu e-mail abrindo o link:\n\n${link}\n\nSe você não criou esta conta, ignore esta mensagem.`,
  }),
  reset: (link: string) => ({
    subject: "Redefinição de senha",
    text: `Recebemos um pedido para redefinir sua senha. O link expira em alguns minutos:\n\n${link}\n\nSe não foi você, ignore — sua senha continua a mesma.`,
  }),
};
