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
  // Spec 009: credencial de cliente MCP (smcp_<8 base32>_<43 base64url>).
  { name: "token de cliente MCP", re: /\bsmcp_[a-z2-7]{8}_[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])/ },
];

// Spec 015: a chave dos tokens e o client secret da TikTok com VALOR (formas `=` e `:`).
// Referências sem valor (`${SOCIMAN_TOKENS_KEY:-}`, `SOCIMAN_TOKENS_KEY=` em docs) não casam.
const valuePatterns = [
  {
    name: "SOCIMAN_TOKENS_KEY com valor",
    re: /\bSOCIMAN_TOKENS_KEY(?:_ANTERIOR)?\s*[=:]\s*["']?([A-Za-z0-9_\-+/]{20,}={0,2})/g,
  },
  {
    name: "TIKTOK_CLIENT_SECRET com valor",
    re: /\bTIKTOK_CLIENT_SECRET\s*[=:]\s*["']?([A-Za-z0-9_\-]{16,})/g,
  },
  // Spec 021: o token do dockerctl (poder sobre o docker.sock), gerado pelo dono.
  {
    name: "DOCKERCTL_TOKEN com valor",
    re: /\bDOCKERCTL_TOKEN\s*[=:]\s*["']?([A-Za-z0-9_\-]{16,})/g,
  },
];
// Valores FIXOS de teste, públicos de propósito (stack efêmera do pytest e do e2e). Lista
// explícita de valores, nunca uma liberação por arquivo.
const allowedTestValues = new Set([
  "dGVzdGUtZWZlbWVyby1jaGF2ZS1kby10b2tlbi0zMmI=", // pytest: "teste-efemero-chave-do-token-32b"
  "ZTJlLWVmZW1lcm8tY2hhdmUtZG9zLXRva2Vucy0zMmI=", // e2e: "e2e-efemero-chave-dos-tokens-32b"
  "e2e-client-secret-de-teste", // e2e: TIKTOK_CLIENT_SECRET do fake
  "e2e-token-do-dockerctl-de-teste", // e2e (spec 021): DOCKERCTL_TOKEN do fake
]);

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
  for (const { name, re } of valuePatterns) {
    for (const m of content.matchAll(re)) {
      if (allowedTestValues.has(m[1])) continue;
      console.error(`✗ possível ${name} em ${file}: ${m[0].slice(0, 22)}…`);
      failed = true;
    }
  }
}

if (failed) {
  console.error("\nSegredo detectado em arquivo rastreado — NÃO commitar. Mova para .env/Variable.");
  process.exit(1);
}
console.log("✓ Nenhum segredo em arquivos rastreados pelo git.");
