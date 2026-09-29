// Adapter stub (dev/PoC): NÃO envia nada — loga o link no console. É assim que
// se completa verificação/reset em dev sem provider real. EMAIL_PROVIDER=stub.
import type { EmailProvider } from "../../services/emailService";

export function createStubEmailProvider(): EmailProvider {
  return {
    async sendVerificationEmail(to, link) {
      console.log(`\n[email stub] Verificação de e-mail para ${to}:\n  ${link}\n`);
    },
    async sendPasswordResetEmail(to, link) {
      console.log(`\n[email stub] Redefinição de senha para ${to}:\n  ${link}\n`);
    },
  };
}
