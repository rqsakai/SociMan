import { expect, test } from "@playwright/test";
import { HOME_IP, waitForActiveSW } from "./helpers";

// US1: o app é instalável (manifest + SW) e o modo casa redireciona HTTP → HTTPS
// só para o IP da casa.

test("manifest responde com nome SociMan e start_url /app", async ({ request }) => {
  const res = await request.get("/manifest.webmanifest");
  expect(res.status()).toBe(200);
  const manifest = await res.json();
  expect(manifest.name).toBe("SociMan");
  expect(manifest.start_url).toBe("/app");
});

test("o HTML aponta para o manifest e o SW fica activated", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator('link[rel="manifest"]')).toHaveCount(1);
  await waitForActiveSW(page);
});

test("localhost:8180 continua sem redirecionamento", async ({ request }) => {
  const res = await request.get("http://localhost:8180/", { maxRedirects: 0 });
  expect(res.status()).toBe(200);
});

test("HTTP pelo IP da casa redireciona para HTTPS", async ({ request }) => {
  const res = await request.get("http://localhost:8180/app", {
    headers: { Host: `${HOME_IP}:8180` },
    maxRedirects: 0,
  });
  expect(res.status()).toBe(301);
  expect(res.headers()["location"]).toBe(`https://${HOME_IP}:8543/app`);
});

test("a CA da casa é servida em HTTP, sem redirecionamento", async ({ request }) => {
  const res = await request.get("http://localhost:8180/sociman-ca.crt", {
    headers: { Host: `${HOME_IP}:8180` },
    maxRedirects: 0,
  });
  expect(res.status()).toBe(200);
  expect((await res.text()).startsWith("-----BEGIN CERTIFICATE-----")).toBe(true);
});

// A cadeia do HTTPS: confiando SÓ na CA da casa, o certificado do edge vale para o IP da casa
// e para localhost (FR-004). Sem isso os aparelhos não instalam o app.
test("o HTTPS do edge é válido para a CA da casa (IP da casa e localhost)", async () => {
  const { readFileSync } = await import("node:fs");
  const https = await import("node:https");
  const ca = readFileSync("docker/certs/ca/sociman-ca.crt");
  for (const host of ["192.168.86.47", "localhost"]) {
    const status = await new Promise<number>((resolve, reject) => {
      https
        .get({ host, port: 8543, path: "/api/health", ca, servername: host === "localhost" ? host : undefined },
          (res) => { res.resume(); resolve(res.statusCode ?? 0); })
        .on("error", reject);
    });
    expect(status, `HTTPS em ${host}`).toBe(200);
  }
});
