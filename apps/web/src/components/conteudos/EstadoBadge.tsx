import type { EstadoEfetivo } from "@sociman/contract";
import { Badge } from "@/components/ui/badge";
import { estadoEfetivoLabel, estadoEfetivoTone } from "@/lib/conteudos";
import { cn } from "@/lib/utils";

// Estado efetivo de um destino (spec 014, R3). `motivo` aparece no `atencao` ("Conta pausada").
export function EstadoBadge({ estado, motivo, className }: { estado: EstadoEfetivo; motivo?: string | null; className?: string }) {
  return (
    <Badge className={cn(estadoEfetivoTone[estado], className)} title={motivo ?? undefined}>
      {estadoEfetivoLabel[estado]}
      {estado === "atencao" && motivo ? `: ${motivo}` : ""}
    </Badge>
  );
}
