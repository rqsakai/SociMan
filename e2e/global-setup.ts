import { execFileSync } from "node:child_process";
import { rmSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Banco e outbox zerados a cada execução do e2e, migrations aplicadas antes
// dos servidores subirem.
export default function globalSetup(): void {
  const apiDir = fileURLToPath(new URL("../apps/api", import.meta.url));
  rmSync(`${apiDir}/data/dev.db`, { force: true });
  rmSync(`${apiDir}/data/outbox.jsonl`, { force: true });
  execFileSync("npm", ["run", "migrate", "-w", "@sociman/api"], {
    cwd: fileURLToPath(new URL("..", import.meta.url)),
    stdio: "inherit",
  });
}
