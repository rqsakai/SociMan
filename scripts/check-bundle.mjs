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

// Spec 019 (R1, cuidado 3): nenhum chunk JS pode avaliar código em runtime. A CSP de produção
// (script-src 'self', sem 'unsafe-eval') quebraria a tela, e um ECharts importado inteiro traz o
// `new Function` do GeoJSON. Chamada direta a `eval(` ou `Function(` (com ou sem `new`) reprova;
// `isFunction(`, `obj.eval(` e afins não casam. Única exceção: a sonda de CSP com corpo vazio
// dentro de try (`try{return Function(``),!0}catch`, do zod), que não executa nada e só detecta
// se eval é permitido (com a nossa CSP, não é).
const evalCall = /(?<![\w$.])(?:new\s+)?(Function|eval)\s*\(/g;
const sondaVazia = /^(?:new\s+)?Function\s*\(\s*(?:``|""|'')\s*\)/;
let chunks = 0;
for (const file of walk(distDir)) {
  if (!/\.m?js$/.test(file)) continue;
  chunks++;
  const content = readFileSync(file, "utf8");
  for (const m of content.matchAll(evalCall)) {
    const resto = content.slice(m.index, m.index + 40);
    const antes = content.slice(Math.max(0, m.index - 12), m.index);
    if (sondaVazia.test(resto) && /try\s*\{\s*(?:return\s*)?$/.test(antes)) continue;
    const trecho = content.slice(Math.max(0, m.index - 40), m.index + 40).replace(/\s+/g, " ");
    console.error(`✗ ${m[1]}( em ${file}: …${trecho}…`);
    failed = true;
  }
}

if (failed) {
  console.error("\nSegredo ou execução dinâmica de código no bundle do frontend — corrija antes de publicar.");
  process.exit(1);
}
console.log("✓ Nenhum segredo no bundle do frontend.");
console.log(`✓ Nenhum eval( nem Function( nos ${chunks} chunks JS do build.`);
