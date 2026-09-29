// Inlining seguro de parâmetros SQL — a barreira de injeção do driver de borda
// (o REST do Edge SQL / bind nativo azion:sql estão quebrados para parâmetros;
// ver apps/api-edge/src/edgeDb.ts). Todos os valores já passaram por Zod na
// borda de entrada; isto é defesa em profundidade. Módulo puro e edge-safe,
// testado em tests/sqlInline.test.ts.

export function inlineSqlValue(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("número inválido em SQL");
    return String(value);
  }
  if (typeof value === "boolean") return value ? "1" : "0";
  if (value instanceof Date) return String(value.getTime());
  if (typeof value === "string") return `'${value.replaceAll("'", "''")}'`;
  if (value instanceof Uint8Array) {
    return `X'${Array.from(value, (b) => b.toString(16).padStart(2, "0")).join("")}'`;
  }
  throw new Error(`tipo de parâmetro não suportado: ${typeof value}`);
}

export function inlineParams(sql: string, params: readonly unknown[]): string {
  let i = 0;
  const out = sql.replace(/\?/g, () => {
    if (i >= params.length) throw new Error("placeholders e params divergem");
    return inlineSqlValue(params[i++]);
  });
  if (i !== params.length) throw new Error("params sobrando para os placeholders");
  return out;
}
