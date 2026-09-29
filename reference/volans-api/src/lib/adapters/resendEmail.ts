// Adapter Resend via API HTTP (fetch) — funciona na borda (isolate) e em Node.
// BYOK: a apiKey é do CLIENTE (conta/cartão dele), o Volans não carrega custo.
// EMAIL_PROVIDER=resend + RESEND_API_KEY (Azion Variable na borda) + EMAIL_FROM.
import { emailMessages, type EmailProvider } from "../../services/emailService";

export interface ResendConfig {
  apiKey: string;
  from: string;
}

export function createResendEmailProvider(config: ResendConfig): EmailProvider {
  async function send(to: string, subject: string, text: string): Promise<void> {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${config.apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ from: config.from, to, subject, text }),
    });
    if (!res.ok) {
      throw new Error(`Resend ${res.status}: ${(await res.text()).slice(0, 200)}`);
    }
  }
  return {
    async sendVerificationEmail(to, link) {
      const m = emailMessages.verification(link);
      await send(to, m.subject, m.text);
    },
    async sendPasswordResetEmail(to, link) {
      const m = emailMessages.reset(link);
      await send(to, m.subject, m.text);
    },
  };
}
