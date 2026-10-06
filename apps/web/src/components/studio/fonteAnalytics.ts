// Fonte do dia no analytics (spec 020, FR-013/FR-019): os campos aditivos da 019 que dizem se o
// número veio da coleta pela API ou do histórico importado do Studio. Lidos por estes acessores
// (com o padrão "coletado"), para as abas tratarem do mesmo jeito qualquer item da série.

export type FonteDia = "coletado" | "studio";
export type FonteCalendario = FonteDia | "misto";

export const fonteLabel: Record<FonteCalendario, string> = {
  coletado: "coletado",
  studio: "importado do Studio",
  misto: "coletado e importado do Studio",
};

export const NOTA_FUSO_STUDIO = "Os dias do Studio seguem o calendário da TikTok, que pode não ser o de Brasília.";
export const NOTA_SEM_VIDEO_STUDIO = "O período só tem dias importados do Studio, que não traz dado por vídeo nem por hora: esta aba mostra só o coletado.";

interface ComFonte {
  fonte?: FonteCalendario | null;
  comparacao?: number | null;
  visitasPerfil?: number | null;
  contasStudio?: number | null;
  diasStudio?: number | null;
}

export const fonteDe = (x: object): FonteCalendario => (x as ComFonte).fonte ?? "coletado";
export const comparacaoDe = (x: object): number | null => (x as ComFonte).comparacao ?? null;
export const visitasDe = (x: object): number | null => (x as ComFonte).visitasPerfil ?? null;
export const contasStudioDe = (x: object): number => (x as ComFonte).contasStudio ?? 0;
export const diasStudioDe = (x: object | undefined): number => (x as ComFonte | undefined)?.diasStudio ?? 0;

// `contexto.studio` (dias e séries do período que usaram o Studio).
export function studioDoContexto(ctx: object | undefined): { dias: number; series: number } {
  const s = (ctx as { studio?: { dias: number; series: number } | null } | undefined)?.studio;
  return s ?? { dias: 0, series: 0 };
}

// FR-020: nas abas por vídeo ou por hora, a nota quando o período tem Studio e nenhum post coletado.
export function notaSemVideo(ctx: { postsNoPeriodo: number } | undefined): string | null {
  return ctx && studioDoContexto(ctx).dias > 0 && ctx.postsNoPeriodo === 0 ? NOTA_SEM_VIDEO_STUDIO : null;
}
