// Dono de teste criado pelo global setup via `sociman create-owner`.
export const OWNER = {
  email: "dono.e2e@sociman.local",
  name: "Dono E2E",
  password: "Senha-forte-e2e-2026",
} as const;

// Endereços da stack EFÊMERA (docker-compose.e2e.yml), definidos pelo scripts/test-e2e.sh.
// Sem eles o teste falha: nunca cai no dev (:8180), cujo banco o global setup apagaria.
function e2eEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `${name} não definida: rode os e2e via \`npm run test:e2e\` (ou \`npm run test:e2e:pwa\`), ` +
        "que sobem a stack efêmera. Nunca rode o Playwright direto contra a stack de dev.",
    );
  }
  return value;
}

export const BASE_URL = e2eEnv("E2E_BASE_URL");
export const MAILPIT_URL = e2eEnv("E2E_MAILPIT_URL");

// Argumentos do `docker compose` da stack e2e (ex.: "-p sociman-e2e -f docker-compose.e2e.yml").
// Recusa qualquer projeto que não seja sociman-e2e: exec/cp nunca podem cair no projeto de dev.
export const COMPOSE_ARGS = ((): string[] => {
  const args = e2eEnv("E2E_COMPOSE").trim().split(/\s+/);
  const project = args[args.indexOf("-p") + 1];
  if (!args.includes("-p") || project !== "sociman-e2e") {
    throw new Error(`E2E_COMPOSE precisa usar o projeto sociman-e2e (-p sociman-e2e); veio "${args.join(" ")}"`);
  }
  return args;
})();

// Banco da stack e2e (os mesmos de docker-compose.e2e.yml).
export const PG_USER = "sociman_e2e";
export const PG_DB = "sociman_e2e";
