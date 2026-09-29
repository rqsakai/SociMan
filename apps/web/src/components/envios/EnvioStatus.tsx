import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ProgressBar } from "@/components/marca/CorteStatusBadge";
import { emAndamento, envioStatusText, envioStatusTone, type Envio } from "@/lib/envios";
import { cn } from "@/lib/utils";

type EnvioLike = Pick<Envio, "status" | "queuePosition" | "progress" | "clipsTotal" | "clipsImportados">;

// Status ao vivo do envio (US3): "Na fila (2º)", "Processando: 3 clipes prontos", "Importando 4/6",
// "Pronto", "Sem clipes", "Falhou".
export function EnvioStatusBadge({ envio, className }: { envio: EnvioLike; className?: string }) {
  return (
    <Badge className={cn(envioStatusTone[envio.status], className)}>
      {emAndamento(envio) && <Loader2 className="animate-spin" aria-hidden="true" />}
      {envioStatusText(envio)}
    </Badge>
  );
}

// Badge + barra de progresso (processando/importando).
export function EnvioStatus({ envio, className }: { envio: EnvioLike; className?: string }) {
  const pct =
    envio.status === "importando" && envio.clipsTotal
      ? envio.clipsImportados / envio.clipsTotal
      : envio.status === "processando"
        ? envio.progress / 100
        : null;
  return (
    <div className={cn("min-w-32 space-y-1", className)}>
      <EnvioStatusBadge envio={envio} />
      {pct !== null && <ProgressBar value={pct} label="Progresso do envio" className="h-1.5" />}
    </div>
  );
}
