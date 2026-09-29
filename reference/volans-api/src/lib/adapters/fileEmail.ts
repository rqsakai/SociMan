// Provider de e-mail "file" (dev/teste): grava cada envio como JSON-line em
// EMAIL_FILE. É o que o e2e usa para ler links de verificação/reset de forma
// determinística. Vive em adapters/ porque usa node:fs — nunca vai para edge.
import { appendFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import type { EmailProvider } from "../../services/emailService";

export function createFileEmailProvider(filePath: string): EmailProvider {
  const write = (kind: "verification" | "reset", to: string, link: string) => {
    mkdirSync(dirname(filePath), { recursive: true });
    appendFileSync(filePath, `${JSON.stringify({ kind, to, link, at: Date.now() })}\n`);
    console.log(`[email file] ${kind} para ${to}: ${link}`);
  };
  return {
    async sendVerificationEmail(to, link) {
      write("verification", to, link);
    },
    async sendPasswordResetEmail(to, link) {
      write("reset", to, link);
    },
  };
}
