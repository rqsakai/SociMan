/*
 * Coletor falso do e2e (spec 026): semeia o lago pela API de ingestão, com um token `scol_` criado
 * pelo dono pela própria API (aceite de risco, botão da tela, cliente). Nada passa pelo banco a não
 * ser as tarefas da fila (dias passados, que a fila de hoje não entrega) via `sqlE2e`. O token só
 * existe em memória do teste. Nenhum teste chama a rede real.
 */
import { createHash } from "node:crypto";
import { deflateSync, gzipSync } from "node:zlib";
import { expect, type APIRequestContext } from "@playwright/test";
import { sqlE2e } from "./helpers";

export const PROTOCOLO_COLETA = { "X-Sociman-Coleta-Protocolo": "1", "X-Sociman-Coletor-Versao": "0.1.0-e2e" };
const URL_BASE = "https://exemplo.test/shop";
export const TEXTO_RISCO_VERSAO = "2026-10-08";

export function produtoRedeId(i: number): string {
  return `${7290000000000000000n + BigInt(i)}`;
}
export const urlProduto = (i: number) => `${URL_BASE}/product/${produtoRedeId(i)}`;

function diaLocal(offsetDias: number): string {
  // dia local em São Paulo (UTC−3), como o servidor decide
  const agora = new Date(Date.now() - 3 * 3600_000);
  agora.setUTCDate(agora.getUTCDate() + offsetDias);
  return agora.toISOString().slice(0, 10);
}

function bruto(obj: unknown): string {
  return gzipSync(Buffer.from(JSON.stringify(obj))).toString("base64");
}

export async function aceitarRiscoEligar(request: APIRequestContext, donoToken: string): Promise<void> {
  const auth = { Authorization: `Bearer ${donoToken}` };
  let cfg = (await (await request.get("/api/coleta/config", { headers: auth })).json()) as {
    version: number;
    riscoAceito: boolean;
    habilitada: boolean;
    paginasDia: number;
    imagensDia: number;
    imagensPorProduto: number;
    itensPorColeta: number;
    pausaMinS: number;
    pausaMaxS: number;
  };
  if (!cfg.riscoAceito) {
    const r = await request.post("/api/coleta/config/aceitar-risco", { headers: auth, data: { version: cfg.version, textoVersao: TEXTO_RISCO_VERSAO, confirmo: true } });
    expect(r.status(), "aceitar risco").toBe(200);
    cfg = (await r.json()) as typeof cfg;
  }
  if (!cfg.habilitada) {
    const r = await request.put("/api/coleta/config", {
      headers: auth,
      data: {
        version: cfg.version,
        habilitada: true,
        janelaInicio: 0,
        janelaFim: 23,
        paginasDia: cfg.paginasDia,
        imagensDia: cfg.imagensDia,
        imagensPorProduto: cfg.imagensPorProduto,
        itensPorColeta: cfg.itensPorColeta,
        pausaMinS: cfg.pausaMinS,
        pausaMaxS: cfg.pausaMaxS,
      },
    });
    expect(r.status(), "ligar a coleta").toBe(200);
  }
}

export interface ClienteColetaE2e {
  id: string;
  tokenId: string;
  token: string; // só em memória
  version: number;
}

export async function criarClienteColeta(request: APIRequestContext, donoToken: string, nome = `desktop e2e ${Date.now()}`): Promise<ClienteColetaE2e> {
  const r = await request.post("/api/coleta/clientes", { headers: { Authorization: `Bearer ${donoToken}` }, data: { nome, mercado: "BR" } });
  expect(r.status(), "POST /api/coleta/clientes").toBe(201);
  const body = (await r.json()) as { cliente: { id: string; tokenId: string; version: number }; token: string };
  return { id: body.cliente.id, tokenId: body.cliente.tokenId, token: body.token, version: body.cliente.version };
}

// A tarefa é sempre do dia de hoje (a trilha `mercado` roda na stack e2e e expira dias passados; o dia
// da foto vem do `coletadoEm` do item, não da tarefa). Se a trilha já criou a tarefa viva de hoje,
// reaproveita-a (reserva para este cliente); senão insere.
function tarefaReservada(cliente: ClienteColetaE2e, tipo: string, chave: string, url: string, nivel: number, fonte: string): string {
  const hoje = diaLocal(0);
  const [id] = sqlE2e(
    `with viva as (update mercado_fila set estado = 'reservada', cliente_id = '${cliente.id}', reservada_ate = now() + interval '30 minutes' ` +
      `where tipo = '${tipo}' and chave = '${chave}' and data_local = '${hoje}' and turno is null and estado in ('pendente', 'reservada') returning id), ` +
      `nova as (insert into mercado_fila (id, tipo, rede, mercado, fonte, chave, url, nivel, prioridade, data_local, estado, cliente_id, reservada_ate) ` +
      `select gen_random_uuid(), '${tipo}', 'tiktok', 'BR', '${fonte}', '${chave}', '${url}', ${nivel}, 0, '${hoje}', 'reservada', '${cliente.id}', now() + interval '30 minutes' ` +
      `where not exists (select 1 from viva) returning id) ` +
      `select id from viva union all select id from nova`,
  );
  expect(id, `tarefa ${chave}`).toBeTruthy();
  return id!;
}

export function camposProduto(i: number, diaN: number, comAffiliate: boolean, titulo?: string): Record<string, unknown> {
  const passo = [20, 5, 12, 0][i % 4]!;
  const vendidos = 1000 + i * 100 + diaN * passo;
  const campos: Record<string, unknown> = {
    redeProdutoId: produtoRedeId(i),
    urlCanonica: urlProduto(i),
    ficha: {
      titulo: titulo ?? `Produto e2e ${i}`,
      descricao: `Descrição do produto ${i}`,
      atributos: [{ nome: "Material", valor: "Linho" }],
      variantes: [{ redeVarianteId: `v${i}`, nome: "Bege / M", precoCentavos: 4990 + i * 100 }],
      argumentos: ["Frete grátis"],
      selos: ["Mais vendido"],
      categoria: {
        redeCategoriaId: "cat789",
        caminho: [
          { redeCategoriaId: "cat1", nome: "Moda" },
          { redeCategoriaId: "cat45", nome: "Feminino" },
          { redeCategoriaId: "cat789", nome: "Shorts" },
        ],
      },
      loja: { redeLojaId: "loja123", nome: "Loja X", oficial: true },
      imagensSha: [],
    },
    paginaPublica: {
      vendidos: { valor: vendidos, min: vendidos, max: vendidos, exato: true },
      precoMinCentavos: 4990 + i * 100,
      precoMaxCentavos: 5990 + i * 100,
      precoOriginalCentavos: 7990,
      moeda: "BRL",
      nota: 4.8,
      nAvaliacoes: 300 + diaN,
      estoqueVisivel: 230,
      disponivel: true,
      campos: { freteGratis: true },
    },
  };
  if (comAffiliate) campos.affiliate = { comissaoBp: 1200, nCriadores: 37 + i, precoMinCentavos: 4990 + i * 100, moeda: "BRL", campos: { planoAberto: true } };
  return campos;
}

export interface SementeMercado {
  cliente: ClienteColetaE2e;
  produtos: string[]; // redeProdutoId
  dias: string[];
}

// `produtos` × `dias` fotos (uma rodada por dia, hoje incluído); o último produto fica sem Affiliate.
// `primeiro` desloca os ids (para semear um lote à parte, ex.: um produto com 1 dia só).
export async function semearMercado(
  request: APIRequestContext,
  donoToken: string,
  opts: { produtos: number; dias: number; primeiro?: number; cliente?: ClienteColetaE2e; ranking?: boolean; rankingJanela?: "1d" | "7d" | "30d" | "total" },
): Promise<SementeMercado> {
  // Um ranking por categoria × tipo × janela × dia: testes que semeiam nos mesmos dias na mesma stack
  // usam janelas diferentes para não colidir (a 2ª foto do mesmo ranking no mesmo dia é "repetida").
  const janela = opts.rankingJanela ?? "7d";
  await aceitarRiscoEligar(request, donoToken);
  const cliente = opts.cliente ?? (await criarClienteColeta(request, donoToken));
  const auth = { Authorization: `Bearer ${cliente.token}`, ...PROTOCOLO_COLETA };
  const primeiro = opts.primeiro ?? 0;
  const dias = Array.from({ length: opts.dias }, (_, n) => diaLocal(-(opts.dias - 1 - n)));
  for (const [n, dia] of dias.entries()) {
    const aberta = await request.post("/api/coleta/coletas", { headers: auth, data: { versaoColetor: "0.1.0-e2e", protocolo: 1 } });
    expect(aberta.status(), "abrir rodada").toBe(201);
    const coletaId = ((await aberta.json()) as { id: string }).id;
    const itens: Record<string, unknown>[] = [];
    for (let k = 0; k < opts.produtos; k++) {
      const i = primeiro + k;
      const tid = tarefaReservada(cliente, "produto", `produto:${produtoRedeId(i)}`, urlProduto(i), 1, "ambas");
      const campos = camposProduto(i, n, k !== opts.produtos - 1);
      itens.push({ tarefaId: tid, status: "ok", coletadoEm: `${dia}T10:00:00-03:00`, duracaoMs: 1000, esquemaVersao: "tiktok_shop/1", campos, bruto: bruto({ campos }), imagens: [] });
    }
    if (opts.ranking ?? true) {
      const tid = tarefaReservada(cliente, "ranking", `ranking:cat45:mais_vendidos:${janela}`, `${URL_BASE}/ranking/cat45/${janela}`, 3, "affiliate");
      const ids = Array.from({ length: opts.produtos }, (_, k) => primeiro + k);
      if (n % 2 === 1 && ids.length > 1) [ids[0], ids[1]] = [ids[1]!, ids[0]!]; // o 2º dia troca as posições 1 e 2 (variação)
      const campos = {
        rankingTipo: "mais_vendidos",
        janela,
        categoria: {
          redeCategoriaId: "cat45",
          caminho: [
            { redeCategoriaId: "cat1", nome: "Moda" },
            { redeCategoriaId: "cat45", nome: "Feminino" },
          ],
        },
        itens: ids.map((i, p) => ({ posicao: p + 1, redeProdutoId: produtoRedeId(i), urlCanonica: urlProduto(i), titulo: `Produto e2e ${i}`, valorExibido: `${1000 - p * 100} vendidos`, valorNum: 1000 - p * 100, campos: {} })),
      };
      itens.push({ tarefaId: tid, status: "ok", coletadoEm: `${dia}T11:00:00-03:00`, esquemaVersao: "tiktok_shop/1", campos, bruto: bruto({ campos }), imagens: [] });
    }
    const r = await request.post(`/api/coleta/coletas/${coletaId}/itens`, { headers: auth, data: { itens } });
    expect(r.status(), "enviar itens").toBe(200);
    const res = (await r.json()) as { resultados: { status: string; erroCodigo?: string; erroCampo?: string }[] };
    for (const x of res.resultados) expect(["gravado", "repetido"], `${x.erroCodigo ?? ""} ${x.erroCampo ?? ""}`).toContain(x.status);
    const fim = await request.post(`/api/coleta/coletas/${coletaId}/fim`, { headers: auth, data: { motivo: "fila_vazia" } });
    expect(fim.status(), "fechar rodada").toBe(200);
  }
  return { cliente, produtos: Array.from({ length: opts.produtos }, (_, k) => produtoRedeId(primeiro + k)), dias };
}

// Uma rodada com a tarefa `vitrine` do dia: os produtos viram interesses `vitrine` (perfil nulo).
export async function semearVitrine(request: APIRequestContext, cliente: ClienteColetaE2e, indices: number[]): Promise<void> {
  const auth = { Authorization: `Bearer ${cliente.token}`, ...PROTOCOLO_COLETA };
  const dia = diaLocal(0);
  const aberta = await request.post("/api/coleta/coletas", { headers: auth, data: { versaoColetor: "0.1.0-e2e", protocolo: 1 } });
  expect(aberta.status(), "abrir rodada (vitrine)").toBe(201);
  const coletaId = ((await aberta.json()) as { id: string }).id;
  const tid = tarefaReservada(cliente, "vitrine", "vitrine", `${URL_BASE}/showcase`, 1, "affiliate");
  const campos = { itens: indices.map((i) => ({ redeProdutoId: produtoRedeId(i), urlCanonica: urlProduto(i), titulo: `Produto e2e ${i}`, adicionadoEm: dia, campos: {} })) };
  const r = await request.post(`/api/coleta/coletas/${coletaId}/itens`, {
    headers: auth,
    data: { itens: [{ tarefaId: tid, status: "ok", coletadoEm: `${dia}T12:00:00-03:00`, esquemaVersao: "tiktok_shop/1", campos, bruto: bruto({ campos }), imagens: [] }] },
  });
  expect(r.status(), "enviar vitrine").toBe(200);
  const res = (await r.json()) as { resultados: { status: string; erroCodigo?: string }[] };
  expect(["gravado", "repetido"], res.resultados[0]?.erroCodigo ?? "").toContain(res.resultados[0]?.status);
  await request.post(`/api/coleta/coletas/${coletaId}/fim`, { headers: auth, data: { motivo: "fila_vazia" } });
}

// Detalhe completo de um produto (US5): nova versão da ficha (título), 5 avaliações (uma com foto de
// cliente), 3 vídeos top e a foto da loja X, numa rodada só, no turno da noite.
export async function semearDetalhe(request: APIRequestContext, cliente: ClienteColetaE2e, i: number): Promise<void> {
  const auth = { Authorization: `Bearer ${cliente.token}`, ...PROTOCOLO_COLETA };
  const dia = diaLocal(0);
  const aberta = await request.post("/api/coleta/coletas", { headers: auth, data: { versaoColetor: "0.1.0-e2e", protocolo: 1 } });
  expect(aberta.status(), "abrir rodada (detalhe)").toBe(201);
  const coletaId = ((await aberta.json()) as { id: string }).id;
  const pid = produtoRedeId(i);
  const tProd = tarefaReservada(cliente, "produto", `produto:${pid}`, urlProduto(i), 1, "ambas");
  const tAv = tarefaReservada(cliente, "avaliacoes", `avaliacoes:${pid}:1`, urlProduto(i), 8, "pagina_publica");
  const tVid = tarefaReservada(cliente, "produto_videos", `produto_videos:${pid}`, urlProduto(i), 7, "affiliate");
  const tLoja = tarefaReservada(cliente, "loja", "loja:loja123", `${URL_BASE}/shop/loja123`, 6, "pagina_publica");
  // Foto de cliente: um PNG 96×96 válido (a validação pelo conteúdo recusa imagens minúsculas).
  const png = pngQuadrado(96, i);
  const sha = createHash("sha256").update(png).digest("hex");
  const up = await request.post(`/api/coleta/coletas/${coletaId}/imagens`, {
    headers: auth,
    multipart: { manifesto: JSON.stringify([{ sha256: sha, tarefaId: tAv, origem: "avaliacao" }]), arquivos: { name: "c.png", mimeType: "image/png", buffer: png } },
  });
  expect(up.status(), "enviar imagem da avaliação").toBe(200);
  const upRes = (await up.json()) as { aceitas: string[]; repetidas: string[]; recusadas: { motivo: string }[] };
  expect([...upRes.aceitas, ...upRes.repetidas], JSON.stringify(upRes.recusadas)).toContain(sha);
  const campos0 = camposProduto(i, 1, true, `Produto e2e ${i} v2`);
  const camposAv = {
    redeProdutoId: pid,
    pagina: 1,
    totalPaginas: 1,
    itens: Array.from({ length: 5 }, (_, k) => ({ redeAvaliacaoId: `av${i}-${k}`, autorRef: `autor-${k}`, texto: `Avaliação ${k} do produto e2e ${i}`, nota: 5 - (k % 3), dataAvaliacao: "2026-10-02", variante: "Bege / M", imagensSha: k === 0 ? [sha] : [], curtidas: k, campos: {} })),
  };
  const camposVid = {
    redeProdutoId: pid,
    itens: Array.from({ length: 3 }, (_, k) => ({ posicao: k + 1, redeVideoId: `${7320000000000 + i * 10 + k}`, autorHandle: `criadora.${k}`, views: 100000 * (3 - k), likes: 5000 * (3 - k), comentarios: 120, compartilhamentos: 30, legenda: `Legenda ${k}`, publicadoEm: "2026-09-28T19:02:00-03:00", campos: {} })),
  };
  const camposLoja = {
    redeLojaId: "loja123",
    nome: "Loja X",
    oficial: true,
    url: `${URL_BASE}/shop/loja123`,
    foto: { nota: 4.7, seguidores: 15800, envioNoPrazoPct: 97.5, nProdutos: 84, vendidosTotal: { valor: 230000, exato: false, min: 225000, max: 234999 } },
    produtos: [],
  };
  const item = (tid: string, campos: unknown, imagens: string[] = []) => ({ tarefaId: tid, status: "ok", coletadoEm: `${dia}T20:00:00-03:00`, esquemaVersao: "tiktok_shop/1", campos, bruto: bruto({ campos }), imagens });
  const r = await request.post(`/api/coleta/coletas/${coletaId}/itens`, {
    headers: auth,
    data: { itens: [item(tProd, campos0), item(tAv, camposAv, [sha]), item(tVid, camposVid), item(tLoja, camposLoja)] },
  });
  expect(r.status(), "enviar detalhe").toBe(200);
  const res = (await r.json()) as { resultados: { status: string; erroCodigo?: string; erroCampo?: string }[] };
  for (const x of res.resultados) expect(["gravado", "repetido"], `${x.erroCodigo ?? ""} ${x.erroCampo ?? ""}`).toContain(x.status);
  await request.post(`/api/coleta/coletas/${coletaId}/fim`, { headers: auth, data: { motivo: "fila_vazia" } });
}

// PNG RGB `lado`×`lado` de cor única (semente), gerado aqui para o e2e não depender de arquivo.
function pngQuadrado(lado: number, semente: number): Buffer {
  const crcTable = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc32 = (buf: Buffer) => {
    let c = 0xffffffff;
    for (const b of buf) c = crcTable[(c ^ b) & 0xff]! ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };
  const chunk = (tipo: string, dados: Buffer) => {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(dados.length);
    const corpo = Buffer.concat([Buffer.from(tipo, "ascii"), dados]);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(corpo));
    return Buffer.concat([len, corpo, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(lado, 0);
  ihdr.writeUInt32BE(lado, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 2; // RGB
  const linha = Buffer.alloc(1 + lado * 3);
  for (let x = 0; x < lado; x++) {
    linha[1 + x * 3] = (semente * 37) & 0xff;
    linha[2 + x * 3] = (semente * 59 + x) & 0xff;
    linha[3 + x * 3] = (semente * 83) & 0xff;
  }
  const raw = Buffer.concat(Array.from({ length: lado }, () => linha));
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}
