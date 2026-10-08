import { CircleAlert } from "lucide-react";
import { cortesResumoPartes, type CortesResumo } from "@/lib/envios";
import { cn } from "@/lib/utils";

// Clipes da geração (spec 024, FR-018): "3 aceitos · 2 pendentes · 1 arquivado · 1 com falha", só
// os não zero. Os pendentes (esperando "Aplicar marca") vêm em destaque; sem clipe, nada.
export function ResumoCortes({ resumo, className }: { resumo: CortesResumo | null | undefined; className?: string }) {
  const partes = cortesResumoPartes(resumo);
  if (partes.length === 0) return null;
  return (
    <p className={cn("text-xs text-muted-foreground", className)} data-testid="resumo-cortes">
      {partes.map((p, i) => (
        <span key={p.chave} data-parte={p.chave}>
          {i > 0 && " · "}
          {p.chave === "pendentes" ? (
            <span className="inline-flex items-center gap-0.5 font-semibold text-foreground">
              <CircleAlert className="size-3.5 text-warning" aria-hidden="true" />
              {p.texto}
            </span>
          ) : (
            <span className={cn(p.chave === "falhou" && "text-destructive")}>{p.texto}</span>
          )}
        </span>
      ))}
    </p>
  );
}
