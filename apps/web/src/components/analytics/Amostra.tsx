/*
 * Chip de amostra (spec 019, FR-004): "amostra pequena (n = 3 de 5)" quando a análise não tem o
 * mínimo do código. O dado bruto continua visível; só a conclusão some. Com amostra suficiente,
 * mostra "n = 12" discreto (ou nada, com `soQuandoPequena`).
 */
import { TriangleAlert } from "lucide-react";
import { formatNumero } from "@/lib/metricas";
import { cn } from "@/lib/utils";

export interface AmostraDados {
  n: number;
  minimo: number;
  suficiente: boolean;
  faltam: number;
}

export function textoAmostra(a: AmostraDados): string {
  return a.suficiente ? `n = ${formatNumero(a.n)}` : `amostra pequena (n = ${formatNumero(a.n)} de ${formatNumero(a.minimo)})`;
}

export function Amostra({ amostra, soQuandoPequena = false, className }: { amostra: AmostraDados | null | undefined; soQuandoPequena?: boolean; className?: string }) {
  if (!amostra || (amostra.suficiente && soQuandoPequena)) return null;
  const pequena = !amostra.suficiente;
  return (
    <span
      data-amostra={pequena ? "pequena" : "ok"}
      title={pequena ? `Faltam ${formatNumero(amostra.faltam)} para uma conclusão; o dado bruto continua visível.` : undefined}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs whitespace-nowrap",
        pequena ? "bg-warning/15 text-foreground ring-1 ring-warning/50" : "text-muted-foreground",
        className,
      )}
    >
      {pequena && <TriangleAlert className="size-3 text-warning" aria-hidden="true" />}
      {textoAmostra(amostra)}
    </span>
  );
}
