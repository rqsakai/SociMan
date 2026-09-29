// Checagem do DoD §11: "Zero segredo no bundle". Varre o build da SPA em busca
// de nomes de variáveis exclusivas do backend e, se houver .env, dos VALORES
// reais dos segredos. Roda após `npm run build -w @sociman/web`.
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const distDir = fileURLToPath(new URL("../apps/web/dist", import.meta.url));
const apiEnvPath = fileURLToPath(new URL("../apps/api/.env", import.meta.url));

if (!existsSync(distDir)) {
  console.error("apps/web/dist não existe — rode `npm run build -w @sociman/web` antes.");
  process.exit(1);
}

// Nomes que jamais podem aparecer no bundle do front
const forbiddenNames = ["JWT_SECRET", "EMAIL_API_KEY", "DATABASE_URL", "PASSWORD_HASH="];

// Valores reais de segredos definidos no .env do backend (se houver)
const secretValueKeys = ["JWT_SECRET", "EMAIL_API_KEY", "DATABASE_URL"];
const forbiddenValues = [];
if (existsSync(apiEnvPath)) {
  for (const line of readFileSync(apiEnvPath, "utf8").split("\n")) {
    const match = line.match(/^([A-Z0-9_]+)=(.+)$/);
    if (match && secretValueKeys.includes(match[1]) && match[2].trim().length >= 8) {
      forbiddenValues.push({ name: match[1], value: match[2].trim() });
    }
  }
}

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) yield* walk(full);
    else yield full;
  }
}

let failed = false;
for (const file of walk(distDir)) {
  const content = readFileSync(file, "utf8");
  for (const name of forbiddenNames) {
    if (content.includes(name)) {
      console.error(`✗ "${name}" encontrado em ${file}`);
      failed = true;
    }
  }
  for (const { name, value } of forbiddenValues) {
    if (content.includes(value)) {
      console.error(`✗ VALOR de ${name} encontrado em ${file}`);
      failed = true;
    }
  }
}

if (failed) {
  console.error("\nSegredo vazou para o bundle do frontend — corrija antes de publicar.");
  process.exit(1);
}
console.log("✓ Nenhum segredo no bundle do frontend.");
