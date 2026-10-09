import {
  ApiError,
  type Guia,
  type GuiaCampos,
  type GuiaEmojis,
  type GuiaExemplo,
  type GuiaIn,
  type GuiaLimites,
} from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { normalizeHashtag } from "./postagem";

export type {
  Guia,
  GuiaCampos,
  GuiaConflito,
  GuiaContaOut,
  GuiaEfetivo,
  GuiaEmojis,
  GuiaExemplo,
  GuiaIn,
  GuiaLimites,
  GuiaVariacao,
} from "@sociman/contract";

// Guia de comunicação do perfil e da conta (spec 017): queries, o formulário (listas "uma por
// linha"), os contadores de tamanho e a marcação das palavras proibidas numa proposta da IA.
// Os limites vêm sempre da API (`guia.limites`), nunca copiados aqui (princípio IV).

export const guiaPerfilKey = (perfilId: string) => ["guia-perfil", perfilId] as const;
export const guiaContaKey = (contaId: string) => ["guia-conta", contaId] as const;
export const guiaPerfilVersionsKey = (perfilId: string) => ["guia-perfil-versions", perfilId] as const;
export const guiaContaVersionsKey = (contaId: string) => ["guia-conta-versions", contaId] as const;

// Onde fica o guia (e o histórico) de cada nível.
export const guiaPerfilPath = (perfilId: string) => `/app/perfis/${perfilId}?aba=guia`;
export const guiaContaPath = (contaId: string) => `/app/contas/${contaId}/guia`;

export function useGuiaPerfil(perfilId: string) {
  return useQuery({ queryKey: guiaPerfilKey(perfilId), queryFn: () => api.guias.perfil(perfilId) });
}

export function useGuiaConta(contaId: string) {
  return useQuery({ queryKey: guiaContaKey(contaId), queryFn: () => api.guias.conta(contaId) });
}

export function useGuiaPerfilVersions(perfilId: string) {
  return useQuery({ queryKey: guiaPerfilVersionsKey(perfilId), queryFn: () => api.guias.perfilVersions(perfilId) });
}

export function useGuiaContaVersions(contaId: string) {
  return useQuery({ queryKey: guiaContaVersionsKey(contaId), queryFn: () => api.guias.contaVersions(contaId) });
}

// Salvar e reverter. O guia do perfil entra na tela de cada conta ("vem do perfil"), então mudar o
// do perfil invalida todos os guias de conta em cache.
export function useGuiaMutations() {
  const qc = useQueryClient();
  const aposPerfil = (perfilId: string) =>
    Promise.all([
      qc.invalidateQueries({ queryKey: guiaPerfilKey(perfilId) }),
      qc.invalidateQueries({ queryKey: guiaPerfilVersionsKey(perfilId) }),
      qc.invalidateQueries({ queryKey: ["guia-conta"] }),
    ]);
  const aposConta = (contaId: string) =>
    Promise.all([
      qc.invalidateQueries({ queryKey: guiaContaKey(contaId) }),
      qc.invalidateQueries({ queryKey: guiaContaVersionsKey(contaId) }),
    ]);
  return {
    salvarPerfil: async (perfilId: string, body: GuiaIn) => {
      const out = await api.guias.updatePerfil(perfilId, body);
      await aposPerfil(perfilId);
      return out;
    },
    reverterPerfil: async (perfilId: string, version: number, toVersion: number) => {
      const out = await api.guias.revertPerfil(perfilId, version, toVersion);
      await aposPerfil(perfilId);
      return out;
    },
    salvarConta: async (contaId: string, body: GuiaIn) => {
      const out = await api.guias.updateConta(contaId, body);
      await aposConta(contaId);
      return out;
    },
    reverterConta: async (contaId: string, version: number, toVersion: number) => {
      const out = await api.guias.revertConta(contaId, version, toVersion);
      await aposConta(contaId);
      return out;
    },
    aposPerfil,
    aposConta,
  };
}

// ---------------------------------------------------------------------------------------------
// Formulário: as listas ficam como texto "uma por linha". As linhas vão como estão (vazias
// inclusive): o servidor apara e descarta as vazias, e o índice dos erros (`faca.3`) é o da linha.

export type Nivel = "perfil" | "conta";

export interface GuiaForm {
  tom: string;
  faca: string;
  naoFaca: string;
  vocabulario: string;
  proibidas: string;
  emojis: GuiaEmojis | "";
  emojisPreferidos: string;
  hashtagsFixas: string;
  maxHashtagsFixas: string;
  exemplos: GuiaExemplo[];
}

export const LISTAS = ["faca", "naoFaca", "vocabulario", "proibidas", "emojisPreferidos", "hashtagsFixas"] as const;
export type CampoLista = (typeof LISTAS)[number];

export const emojisLabel: Record<GuiaEmojis, string> = {
  nao: "Não usar",
  moderado: "Com moderação",
  livre: "Livre",
};

export const exemploTipoLabel: Record<GuiaExemplo["tipo"], string> = {
  titulo: "Título",
  legenda: "Legenda",
  bordao: "Bordão",
};

export function formDe(c: GuiaCampos): GuiaForm {
  const linhas = (xs: string[] | undefined) => (xs ?? []).join("\n");
  return {
    tom: c.tom,
    faca: linhas(c.faca),
    naoFaca: linhas(c.naoFaca),
    vocabulario: linhas(c.vocabulario),
    proibidas: linhas(c.proibidas),
    emojis: c.emojis ?? "",
    emojisPreferidos: linhas(c.emojisPreferidos),
    hashtagsFixas: linhas(c.hashtagsFixas),
    maxHashtagsFixas: c.maxHashtagsFixas == null ? "" : String(c.maxHashtagsFixas),
    exemplos: (c.exemplos ?? []).map((e) => ({ ...e })),
  };
}

const semFimVazio = (texto: string) => {
  const linhas = texto.split("\n");
  while (linhas.length > 0 && linhas[linhas.length - 1]!.trim() === "") linhas.pop();
  return linhas;
};

export function camposDe(f: GuiaForm, nivel: Nivel): GuiaCampos {
  const max = f.maxHashtagsFixas.trim();
  return {
    tom: f.tom,
    faca: semFimVazio(f.faca),
    naoFaca: semFimVazio(f.naoFaca),
    vocabulario: semFimVazio(f.vocabulario),
    proibidas: semFimVazio(f.proibidas),
    emojis: f.emojis || null,
    emojisPreferidos: semFimVazio(f.emojisPreferidos),
    hashtagsFixas: semFimVazio(f.hashtagsFixas),
    maxHashtagsFixas: nivel === "conta" && max !== "" ? Number(max) : null,
    exemplos: f.exemplos,
  };
}

// Itens de uma lista como a API vai contar (aparados, sem vazios).
export const itens = (texto: string) =>
  texto
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

// A mesma soma da API (R2): tom + todos os itens + os textos dos exemplos.
export function tamanhoDe(f: GuiaForm): number {
  const listas = LISTAS.map((l) => (l === "hashtagsFixas" ? fixasDe(f.hashtagsFixas) : itens(f[l])));
  return (
    f.tom.trim().length +
    listas.reduce((n, xs) => n + xs.reduce((m, i) => m + i.length, 0), 0) +
    f.exemplos.reduce((n, e) => n + e.texto.trim().length, 0)
  );
}

// Hashtags fixas normalizadas como no servidor (aproximado: a comparação ignora acentos).
export function fixasDe(texto: string): string[] {
  const out: string[] = [];
  for (const linha of itens(texto)) {
    const tag = normalizeHashtag(linha);
    if (tag && !out.some((t) => chaveHashtag(t) === chaveHashtag(tag))) out.push(tag);
  }
  return out;
}

const chaveHashtag = (tag: string) => normalizar(tag);

// Perfil, depois conta, sem repetir (a regra de soma do research R6).
export function fixasSomadas(perfil: string[], conta: string[]): string[] {
  const out: string[] = [];
  for (const t of [...perfil, ...conta]) if (!out.some((x) => chaveHashtag(x) === chaveHashtag(t))) out.push(t);
  return out;
}

// Máximo de fixas da conta: o do formulário, ou o padrão da API.
export function maximoFixas(f: GuiaForm, limites: GuiaLimites): number {
  const n = Number(f.maxHashtagsFixas.trim());
  return f.maxHashtagsFixas.trim() === "" || !Number.isInteger(n) ? limites.hashtagsFixasPadrao : n;
}

// ---------------------------------------------------------------------------------------------
// Erros de validação do PUT (`details.fields`, `details.contas`).

export interface ContaComProblema {
  contaId: string;
  rotulo: string;
  campos: string[];
  mensagem?: string;
}

export function errosDeCampo(err: unknown): Record<string, string> {
  if (!(err instanceof ApiError) || err.code !== "validation_error") return {};
  const fields = err.details.fields;
  if (!fields || typeof fields !== "object") return {};
  return Object.fromEntries(Object.entries(fields as Record<string, unknown>).filter(([, v]) => typeof v === "string")) as Record<
    string,
    string
  >;
}

export function contasComProblema(err: unknown): ContaComProblema[] {
  if (!(err instanceof ApiError) || !Array.isArray(err.details.contas)) return [];
  return (err.details.contas as ContaComProblema[]).filter((c) => typeof c?.contaId === "string");
}

// Junta os erros de um campo: "faca" e "faca.3" viram "no máximo 10 itens · linha 4: item repetido".
export function erroDoCampo(erros: Record<string, string>, campo: string): string | undefined {
  const partes: string[] = [];
  for (const [k, v] of Object.entries(erros)) {
    if (k === campo) partes.unshift(v);
    else if (k.startsWith(`${campo}.`)) {
      const resto = k.slice(campo.length + 1);
      const i = Number(resto.split(".")[0]);
      partes.push(Number.isInteger(i) ? `linha ${i + 1}: ${v}` : v);
    }
  }
  return partes.length > 0 ? partes.join(" · ") : undefined;
}

// Erro de um exemplo (`exemplos.2.texto`, `exemplos.2.tipo`).
export function erroDoExemplo(erros: Record<string, string>, i: number): string | undefined {
  const partes = Object.entries(erros)
    .filter(([k]) => k.startsWith(`exemplos.${i}.`))
    .map(([, v]) => v);
  return partes.length > 0 ? partes.join(" · ") : undefined;
}

// ---------------------------------------------------------------------------------------------
// Histórico (snapshot em snake_case, data-model).

export const guiaFieldLabel: Record<string, string> = {
  tom: "Tom de voz",
  faca: "Faça",
  nao_faca: "Não faça",
  vocabulario: "Vocabulário da casa",
  proibidas: "Palavras proibidas",
  emojis: "Emojis",
  emojis_preferidos: "Emojis preferidos",
  hashtags_fixas: "Hashtags fixas",
  max_hashtags_fixas: "Máximo de hashtags fixas",
  exemplos: "Exemplos aprovados",
  perfil_id: "Perfil",
  conta_id: "Conta",
};

export function formatGuiaValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return field === "max_hashtags_fixas" ? "padrão" : field === "emojis" ? "não definido" : "—";
  }
  if (field === "emojis" && typeof value === "string") return emojisLabel[value as GuiaEmojis] ?? value;
  if (field === "exemplos" && Array.isArray(value)) {
    if (value.length === 0) return "—";
    return value
      .map((e) => {
        const ex = e as Partial<GuiaExemplo>;
        return `${exemploTipoLabel[ex.tipo as GuiaExemplo["tipo"]] ?? ex.tipo}: ${ex.texto ?? ""}`;
      })
      .join("\n");
  }
  if (Array.isArray(value)) return value.length === 0 ? "—" : value.join("\n");
  return String(value);
}

// ---------------------------------------------------------------------------------------------
// Palavras proibidas numa proposta: a mesma regra da API (R7), para marcar na tela. Palavra inteira
// sobre o texto sem acentos e sem maiúsculas; termo de várias palavras aceita pontuação no meio;
// hashtag inteira igual ao termo sem espaços (`#compreja` × "compre já").

export function normalizar(texto: string): string {
  return texto
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLocaleLowerCase("pt-BR");
}

const W = "[\\p{L}\\p{N}_]";
const NW = "[^\\p{L}\\p{N}_]+";

function padroes(termos: string[]): RegExp | null {
  const alternativas: string[] = [];
  for (const termo of termos) {
    const toks = normalizar(termo)
      .split(new RegExp(NW, "u"))
      .filter(Boolean)
      .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    if (toks.length === 0) continue;
    alternativas.push(`(?<!${W})${toks.join(NW)}(?!${W})`);
    alternativas.push(`#${toks.join("")}(?!${W})`);
  }
  return alternativas.length > 0 ? new RegExp(alternativas.join("|"), "gu") : null;
}

export interface Parte {
  texto: string;
  proibida: boolean;
}

// Divide o texto em partes, marcando as proibidas (com a grafia original do texto).
export function partesComProibidas(texto: string, termos: string[]): Parte[] {
  const re = termos.length > 0 ? padroes(termos) : null;
  if (!re || !texto) return [{ texto, proibida: false }];
  // Normaliza caractere a caractere, guardando de onde veio cada posição do texto normalizado.
  let norm = "";
  const origem: number[] = [];
  let i = 0;
  for (const ch of texto) {
    const n = normalizar(ch);
    for (let k = 0; k < n.length; k++) origem.push(i);
    norm += n;
    i += ch.length;
  }
  origem.push(texto.length);
  const partes: Parte[] = [];
  let ultimo = 0;
  for (const m of norm.matchAll(re)) {
    const ini = origem[m.index]!;
    const fim = origem[m.index + m[0].length]!;
    if (ini < ultimo || fim <= ini) continue;
    if (ini > ultimo) partes.push({ texto: texto.slice(ultimo, ini), proibida: false });
    partes.push({ texto: texto.slice(ini, fim), proibida: true });
    ultimo = fim;
  }
  if (ultimo < texto.length) partes.push({ texto: texto.slice(ultimo), proibida: false });
  return partes;
}
