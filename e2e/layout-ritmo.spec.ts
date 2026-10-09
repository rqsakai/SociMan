import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { OWNER } from "./fixtures";
import { apiToken, createPerfilViaApi, login, syntheticMp4 } from "./helpers";

// Spec 024, US2 (FR-028..033, FR-038; SC-002..004; research R17): o ritmo do layout é medido, não
// olhado. Em 1280 e 390 px, nas telas Agentes (MCP), Propostas, Gerar cortes, Conteúdos, Descobrir
// e Perfil:
// - o espaço entre filhos diretos de cada <Page> (e entre as abas e o conteúdo) varia no máximo
//   4 px entre as telas e nunca é 0;
// - os cartões empilhados têm a mesma largura (1280 px);
// - a distância da faixa do HeaderCard até o corpo é no máximo 16 px;
// - a página não rola de lado.
// As medidas vêm do getBoundingClientRect (o mesmo retângulo do boundingBox(), num único evaluate).

const LARGURAS = [
  { nome: "desktop", width: 1280, height: 900 },
  { nome: "celular", width: 390, height: 844 },
] as const;

interface Medidas {
  gaps: { entre: string; px: number }[];
  larguras: { cartao: string; px: number }[];
  faixaCorpo: { cartao: string; px: number }[];
  scrollWidth: number;
  clientWidth: number;
}

// Perfil com uma conta e um vídeo próprio: Conteúdos e o Perfil têm o que listar.
async function semear(request: APIRequestContext, token: string): Promise<string> {
  const sfx = randomUUID().slice(0, 8);
  const auth = { Authorization: `Bearer ${token}` };
  const perfilId = await createPerfilViaApi(request, token, { name: `Ritmo ${sfx}`, slug: `ritmo-${sfx}` });
  const conta = await request.post(`/api/perfis/${perfilId}/contas`, {
    headers: auth,
    data: { platform: "tiktok", handle: `ritmo${sfx}`, status: "ativa" },
  });
  expect(conta.status(), `POST contas: ${await conta.text()}`).toBe(201);
  const arquivo = join(tmpdir(), `sociman-e2e-ritmo-${sfx}.mp4`);
  syntheticMp4(arquivo, 2);
  const up = await request.post(`/api/perfis/${perfilId}/conteudos/arquivo`, {
    headers: auth,
    multipart: { file: { name: `ritmo-${sfx}.mp4`, mimeType: "video/mp4", buffer: readFileSync(arquivo) }, titulo: `Ritmo ${sfx}` },
  });
  expect(up.status(), `POST conteudos/arquivo: ${await up.text()}`).toBe(201);
  return perfilId;
}

async function medir(page: Page): Promise<Medidas> {
  return page.evaluate(() => {
    const visivel = (el: Element) => {
      const st = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return st.display !== "none" && st.position !== "fixed" && st.position !== "absolute" && r.height > 0;
    };
    const nome = (el: Element) =>
      el.querySelector("h1, h2")?.textContent?.trim() || el.getAttribute("data-slot") || el.tagName.toLowerCase();
    const main = document.querySelector("main")!;

    // contêineres de ritmo: o Page e as abas (lista de abas → conteúdo)
    const gaps: Medidas["gaps"] = [];
    for (const c of main.querySelectorAll('[data-slot="page"], [data-slot="tabs"][data-orientation="horizontal"]')) {
      const filhos = [...c.children].filter(visivel);
      for (let i = 1; i < filhos.length; i++) {
        const a = filhos[i - 1].getBoundingClientRect();
        const b = filhos[i].getBoundingClientRect();
        gaps.push({ entre: `${nome(filhos[i - 1])} → ${nome(filhos[i])}`, px: Math.round(b.top - a.bottom) });
      }
    }

    // cartões empilhados: filhos diretos de um Page ou do conteúdo de uma aba
    const larguras: Medidas["larguras"] = [];
    const seletor = ["page", "tabs-content"]
      .flatMap((p) => [`[data-slot="${p}"] > [data-slot="header-card"]`, `[data-slot="${p}"] > [data-slot="card"]`])
      .join(", ");
    for (const el of main.querySelectorAll(seletor)) {
      if (visivel(el)) larguras.push({ cartao: nome(el), px: Math.round(el.getBoundingClientRect().width) });
    }

    const faixaCorpo: Medidas["faixaCorpo"] = [];
    for (const card of main.querySelectorAll('[data-slot="header-card"]')) {
      const faixa = card.querySelector('[data-slot="header-card-band"]');
      const primeiro = card.querySelector('[data-slot="header-card-body"]')?.firstElementChild;
      if (!faixa || !primeiro || !visivel(card)) continue;
      faixaCorpo.push({
        cartao: nome(card),
        px: Math.round(primeiro.getBoundingClientRect().top - faixa.getBoundingClientRect().bottom),
      });
    }

    return {
      gaps,
      larguras,
      faixaCorpo,
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    };
  });
}

// Espera a tela assentar: título, sem skeleton e duas leituras iguais seguidas.
async function assentar(page: Page): Promise<Medidas> {
  await expect(page.locator("main h1").first()).toBeVisible();
  await expect(page.locator('main [data-slot="skeleton"]')).toHaveCount(0, { timeout: 15_000 });
  let antes = JSON.stringify(await medir(page));
  for (let i = 0; i < 10; i++) {
    await page.waitForTimeout(250);
    const agora = await medir(page);
    if (JSON.stringify(agora) === antes) return agora;
    antes = JSON.stringify(agora);
  }
  return JSON.parse(antes) as Medidas;
}

test.describe("Ritmo do layout (spec 024, US2)", () => {
  let perfilId: string;

  test.beforeAll(async ({ request }) => {
    perfilId = await semear(request, await apiToken(request, OWNER.email, OWNER.password));
  });

  for (const tela of LARGURAS) {
    test(`espaços, larguras e faixa iguais nas telas (${tela.width} px)`, async ({ page }) => {
      await page.setViewportSize({ width: tela.width, height: tela.height });
      await login(page, OWNER.email, OWNER.password);
      await expect(page).toHaveURL(/\/app$/);

      const telas = [
        "/app/configuracoes/agentes",
        "/app/propostas",
        "/app/envios",
        "/app/conteudos",
        "/app/descobrir",
        `/app/perfis/${perfilId}`,
      ];
      const todosGaps: { tela: string; entre: string; px: number }[] = [];
      for (const path of telas) {
        await page.goto(path);
        const m = await assentar(page);

        expect(m.scrollWidth, `${path}: rolagem horizontal (${m.scrollWidth} > ${m.clientWidth})`).toBeLessThanOrEqual(
          m.clientWidth,
        );
        expect(m.gaps.length, `${path}: nenhum bloco medido`).toBeGreaterThan(0);
        for (const g of m.gaps) {
          expect(g.px, `${path}: bloco encostado (${g.entre})`).toBeGreaterThan(0);
          todosGaps.push({ tela: path, ...g });
        }
        for (const f of m.faixaCorpo) {
          expect(f.px, `${path}: faixa → corpo em "${f.cartao}"`).toBeGreaterThanOrEqual(0);
          expect(f.px, `${path}: faixa → corpo em "${f.cartao}"`).toBeLessThanOrEqual(16);
        }
        if (tela.width === 1280 && m.larguras.length > 1) {
          const ws = new Set(m.larguras.map((l) => l.px));
          expect(ws.size, `${path}: cartões com larguras diferentes ${JSON.stringify(m.larguras)}`).toBe(1);
        }
      }

      const pxs = todosGaps.map((g) => g.px);
      const min = Math.min(...pxs);
      const max = Math.max(...pxs);
      const fora = todosGaps.filter((g) => g.px - min > 4);
      expect(max - min, `espaços entre blocos variam ${min}..${max} px: ${JSON.stringify(fora)}`).toBeLessThanOrEqual(4);
    });
  }
});
