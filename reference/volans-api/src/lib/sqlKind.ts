// Decide se um statement pode ir para leitura nativa via azion:sql (na borda)
// ou precisa ir pelo REST — o driver nativo abre réplica read-only, então só
// SELECT é seguro. Conservador de propósito: WITH/CTE, PRAGMA, BEGIN e afins
// caem pro REST (WITH pode conter DML; PRAGMA/tx têm efeito). Módulo puro,
// edge-safe, testado em tests/sqlKind.test.ts.

const LEADING_COMMENTS_AND_WS = /^(?:\s+|--[^\n]*\n|\/\*[\s\S]*?\*\/)*/;

export function isReadOnlyStatement(sql: string): boolean {
  const trimmed = sql.replace(LEADING_COMMENTS_AND_WS, "");
  // \b garante fronteira de palavra — "SELECTFOO" não bate.
  return /^select\b/i.test(trimmed);
}
