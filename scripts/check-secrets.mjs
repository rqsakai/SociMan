// Guardrail: falha se algum SEGREDO aparecer em arquivo rastreado pelo git.
// Roda no CI (e pode virar pre-commit). Varre só o que o git rastreia — nunca
// os gitignored (.env, poc.auto.tfvars, certs). Padrões, não valores fixos.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const patterns = [
  { name: "Azion personal token", re: /\bazion[0-9a-f]{32,}\b/i },
  { name: "Resend API key", re: /\bre_[A-Za-z0-9]{20,}\b/ },
  { name: "AWS access key id", re: /\bAKIA[0-9A-Z]{16}\b/ },
  { name: "Anthropic API key", re: /\bsk-ant-[A-Za-z0-9_-]{20,}/ },
  { name: "Google/YouTube/Gemini API key", re: /\bAIza[0-9A-Za-z_-]{35}\b/ },
  { name: "chave privada PEM", re: /-----BEGIN (?:RSA |EC )?PRIVATE KEY-----/ },
  { name: "atribuição jwt_secret literal", re: /jwt_secret\s*=\s*["'][A-Za-z0-9+/=]{24,}["']/i },
  { name: "Bearer token longo hardcoded", re: /Bearer\s+[A-Za-z0-9._-]{40,}/ },
];

// caminhos onde exemplos/placeholders são esperados (não são segredos reais)
const allowFile = (p) => p.endsWith(".env.example") || p === "scripts/check-secrets.mjs";

const files = execFileSync("git", ["ls-files"], { encoding: "utf8" }).split("\n").filter(Boolean);

let failed = false;
for (const file of files) {
  if (allowFile(file)) continue;
  let content;
  try {
    content = readFileSync(file, "utf8");
  } catch {
    continue; // binário/ilegível
  }
  for (const { name, re } of patterns) {
    const m = content.match(re);
    if (m) {
      console.error(`✗ possível ${name} em ${file}: ${m[0].slice(0, 12)}…`);
      failed = true;
    }
  }
}

if (failed) {
  console.error("\nSegredo detectado em arquivo rastreado — NÃO commitar. Mova para .env/Variable.");
  process.exit(1);
}
console.log("✓ Nenhum segredo em arquivos rastreados pelo git.");
