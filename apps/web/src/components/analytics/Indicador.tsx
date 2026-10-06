/*
 * Indicador do período (spec 019, FR-012): rótulo, valor, valor anterior e variação com ▲/▼.
 * Sem anterior (ou anterior zero), "sem base de comparação" no lugar da variação. A seta e o texto
 * carregam o sentido (cor nunca sozinha); `estimado` marca valor vindo de marco interpolado.
 */
import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import type { ReactNode } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const pct = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 1, signDisplay: "exceptZero" });

export function variacao(valor: number | null | undefined, anterior: number | null | undefined): number | null {
  if (valor === null || valor === undefined || anterior === null || anterior === undefined || anterior === 0) return null;
  return (valor - anterior) / Math.abs(anterior);
}

export interface IndicadorProps {
  rotulo: string;
  valor: number | null | undefined;
  anterior?: number | null;
  formatar: (n: number | null | undefined) => string;
  estimado?: boolean;
  dica?: ReactNode;
  carregando?: boolean;
  className?: string;
}

export function Indicador({ rotulo, valor, anterior, formatar, estimado, dica, carregando, className }: IndicadorProps) {
  const v = variacao(valor, anterior);
  const Seta = v === null || v === 0 ? Minus : v > 0 ? ArrowUp : ArrowDown;
  return (
    <div className={cn("min-w-0 rounded-xl bg-card p-4 text-card-foreground shadow-card", className)} data-indicador={rotulo}>
      <p className="truncate text-sm text-muted-foreground">{rotulo}</p>
      {carregando ? (
        <Skeleton className="mt-1 h-8 w-20" />
      ) : (
        <p className="text-2xl font-bold tabular-nums">
          {formatar(valor)}
          {estimado && (
            <span className="text-base text-muted-foreground" title="estimado">
              *
            </span>
          )}
        </p>
      )}
      <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
        {v === null ? (
          <span>sem base de comparação</span>
        ) : (
          <>
            <span className={cn("inline-flex items-center gap-0.5 font-medium", v > 0 ? "text-success" : v < 0 ? "text-destructive" : "text-foreground")}>
              <Seta className="size-3.5" aria-hidden="true" />
              <span className="sr-only">{v > 0 ? "subiu" : v < 0 ? "caiu" : "igual"}</span>
              {pct.format(v)}
            </span>
            <span>antes: {formatar(anterior)}</span>
          </>
        )}
      </p>
      {dica && <p className="mt-1 text-xs text-muted-foreground">{dica}</p>}
    </div>
  );
}
