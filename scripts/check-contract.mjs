// Princípio IV: o contrato do SPA é gerado do OpenAPI do FastAPI.
// Regenera e compara com o que está em disco; falha se alguém editou à mão ou esqueceu de regenerar.
// (Comparar com o disco, e não com o git, funciona também antes do commit.)
import { execSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";

const files = ["packages/contract/openapi.json", "packages/contract/src/generated/schema.d.ts"];
const before = files.map((f) => (existsSync(f) ? readFileSync(f, "utf8") : null));
execSync("npm run -s gen:contract", { stdio: "inherit" });
const stale = files.filter((f, i) => before[i] !== readFileSync(f, "utf8"));
if (stale.length) {
  console.error(`check:contract FALHOU — contrato desatualizado (já regenerado agora): ${stale.join(", ")}`);
  console.error("Revise o diff e rode de novo.");
  process.exit(1);
}
console.log("check:contract ok — contrato bate com o OpenAPI da API");
