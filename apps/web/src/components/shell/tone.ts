// Tons em degradê do tema (utilitários `tone-*` em src/index.css): selo do MetricCard,
// faixa do HeaderCard e cabeçalho do AuthShell. As classes ficam literais aqui para o
// Tailwind encontrá-las no código-fonte.
export type Tone = "primary" | "success" | "warning" | "info" | "destructive" | "dark";

export const toneClass: Record<Tone, string> = {
  primary: "tone-primary",
  success: "tone-success",
  warning: "tone-warning",
  info: "tone-info",
  destructive: "tone-destructive",
  dark: "tone-dark",
};
