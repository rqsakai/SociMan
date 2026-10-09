import { OWNER } from "./fixtures";
import { clearInbox, compose, waitForHealth } from "./helpers";

// Estado limpo a cada execução: banco e Redis zerados, só o dono de teste
// cadastrado e caixa do Mailpit vazia.
export default async function globalSetup(): Promise<void> {
  await waitForHealth(60_000);
  compose(["exec", "-T", "api", "uv", "run", "sociman", "reset-db", "--yes"]);
  compose(
    [
      "exec", "-T", "api", "uv", "run", "sociman", "create-owner",
      "--email", OWNER.email,
      "--name", OWNER.name,
      "--password-stdin",
    ],
    `${OWNER.password}\n`,
  );
  await clearInbox();
}
