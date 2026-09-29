import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { corteStatusLabel, type Corte } from "../../lib/marca";

const tone: Record<Corte["status"], string> = {
  na_fila: "bg-info text-info-foreground",
  processando: "bg-warning text-warning-foreground",
  pronto: "bg-success text-success-foreground",
  falhou: "bg-destructive text-white",
};

// Status do corte em badge: "Processando 42%", "Na fila (2º)", "Pronto", "Falhou".
export function CorteStatusBadge({ corte, className }: { corte: Pick<Corte, "status" | "progress" | "queuePosition">; className?: string }) {
  const label = corteStatusLabel[corte.status];
  const extra =
    corte.status === "processando"
      ? ` ${corte.progress}%`
      : corte.status === "na_fila" && corte.queuePosition
        ? ` (${corte.queuePosition}º)`
        : "";
  return (
    <Badge className={cn(tone[corte.status], className)}>
      {corte.status === "processando" && <Loader2 className="animate-spin" aria-hidden="true" />}
      {label}
      {extra}
    </Badge>
  );
}

// Barra fina de progresso (0..1), acessível.
export function ProgressBar({ value, label, className }: { value: number; label: string; className?: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      className={cn("h-2 w-full overflow-hidden rounded-full bg-muted", className)}
    >
      <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${pct}%` }} />
    </div>
  );
}
