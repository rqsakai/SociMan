/*
 * CSV de um card do analytics, gerado no navegador (spec 019, R10).
 *
 * Mesmo formato do `_Escritor` da 016 (metricas/export.py): UTF-8 com BOM, separador `,`, aspas
 * só quando o campo tem vírgula, aspas ou quebra de linha (aspas internas dobradas) e `\r\n`.
 * Vazio para null/undefined, true/false para booleanos; texto com cara de fórmula ganha `'`. Os
 * dados são os mesmos da tabela alternativa do card: o que se vê é o que se baixa.
 */

export type ValorCsv = string | number | boolean | null | undefined;

// Injeção de fórmula: títulos e legendas vêm da rede, e o CSV é aberto em planilha. Texto que
// começa com `=`, `+`, `-`, `@`, tab ou CR ganha um apóstrofo na frente; números continuam números.
// O @ de uma conta (`@atavernanerd`) não forma fórmula e sai limpo.
const FORMULA = /^[=+\-@\t\r]/;
const HANDLE = /^@[A-Za-z0-9._]+$/;

function campo(v: ValorCsv): string {
  if (v === null || v === undefined) return "";
  let s = typeof v === "boolean" ? (v ? "true" : "false") : String(v);
  if (typeof v === "string" && FORMULA.test(s) && !HANDLE.test(s)) s = `'${s}`;
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function montarCsv(colunas: string[], linhas: ValorCsv[][]): string {
  return [colunas, ...linhas].map((l) => l.map(campo).join(",")).join("\r\n") + "\r\n";
}

// "Views por dia" → "views-por-dia.csv"
export function nomeArquivo(nome: string): string {
  const base = nome
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${base || "dados"}.csv`;
}

export function baixarCsv(nome: string, colunas: string[], linhas: ValorCsv[][]): void {
  const blob = new Blob(["﻿", montarCsv(colunas, linhas)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome.endsWith(".csv") ? nome : nomeArquivo(nome);
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();
  // o clique já começou o download; revoga no próximo ciclo
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
