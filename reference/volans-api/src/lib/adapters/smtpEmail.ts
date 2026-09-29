// Provider de e-mail SMTP para o cliente que JÁ TEM um servidor SMTP (BYO SMTP).
// EMAIL_PROVIDER=smtp + SMTP_HOST/SMTP_PORT/SMTP_FROM (+ SMTP_USER/SMTP_PASS/
// SMTP_SECURE quando o servidor exige auth/TLS). Mailpit (docker) usa sem auth.
//
// ATENÇÃO: SMTP é TCP e NÃO roda no isolate da borda Azion (sem socket). Este
// adapter serve o deploy Node/Docker (ou um container). Na borda, use um
// provider HTTP (Resend) — a interface EmailProvider é a mesma, então trocar é
// só configuração.
import { createTransport } from "nodemailer";
import { emailMessages, type EmailProvider } from "../../services/emailService";

export interface SmtpConfig {
  host: string;
  port: number;
  from: string;
  user?: string;
  pass?: string;
  secure?: boolean; // true = TLS na conexão (porta 465); false = STARTTLS/none
}

export function createSmtpEmailProvider(config: SmtpConfig): EmailProvider {
  const transporter = createTransport({
    host: config.host,
    port: config.port,
    secure: config.secure ?? false,
    // auth só quando o servidor do cliente exige (Mailpit não exige)
    auth: config.user ? { user: config.user, pass: config.pass } : undefined,
  });

  return {
    async sendVerificationEmail(to, link) {
      const m = emailMessages.verification(link);
      await transporter.sendMail({ from: config.from, to, subject: m.subject, text: m.text });
    },
    async sendPasswordResetEmail(to, link) {
      const m = emailMessages.reset(link);
      await transporter.sendMail({ from: config.from, to, subject: m.subject, text: m.text });
    },
  };
}
