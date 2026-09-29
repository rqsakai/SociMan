import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

// Antes × depois (R11): lado a lado a partir de `sm`, empilhado no celular.
export function IaDiff({ antes, depois, rotuloDepois = "Proposta" }: { antes: ReactNode; depois: ReactNode; rotuloDepois?: string }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      <Lado titulo="Antes" muted>
        {antes}
      </Lado>
      <Lado titulo={rotuloDepois}>{depois}</Lado>
    </div>
  );
}

function Lado({ titulo, muted, children }: { titulo: string; muted?: boolean; children: ReactNode }) {
  const vazio = children === "" || children === null || children === undefined;
  return (
    <div className="min-w-0 space-y-1">
      <p className="text-xs font-semibold text-muted-foreground uppercase">{titulo}</p>
      <div
        className={cn("min-h-10 rounded-md border bg-card p-2 text-sm break-words whitespace-pre-wrap", muted && "text-muted-foreground")}
      >
        {vazio ? <span className="text-muted-foreground italic">(vazio)</span> : children}
      </div>
    </div>
  );
}
