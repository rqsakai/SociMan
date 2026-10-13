import { Play } from "lucide-react";
import { cn } from "@/lib/utils";

export interface TempoFrase {
  inicio: number;
  fim: number;
}

const seg = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const fmtSeg = (s: number) => `${seg.format(s)} s`;

// A linha do tempo da narração (spec 011, US2, T026): uma faixa com cada frase no seu trecho do take
// contínuo (largura proporcional) e a lista das frases com início e fim. Clicar numa frase toca o
// áudio daquele ponto (`onTocar`). `ativa` destaca a frase que está tocando.
export function LinhaTempos({
  frases,
  tempos,
  totalS,
  ativa,
  onTocar,
}: {
  frases: string[];
  tempos: TempoFrase[];
  totalS: number;
  ativa?: number | null;
  onTocar?: (inicio: number, indice: number) => void;
}) {
  const total = totalS > 0 ? totalS : Math.max(0, ...tempos.map((t) => t.fim));
  return (
    <div className="space-y-3" data-testid="linha-tempos">
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted" aria-hidden="true">
        {tempos.map((t, i) => (
          <span
            key={i}
            className={cn("h-full border-r border-background", i === ativa ? "bg-primary" : i % 2 ? "bg-primary/50" : "bg-primary/30")}
            style={{ marginLeft: i === 0 && total ? `${(t.inicio / total) * 100}%` : undefined, width: total ? `${((t.fim - t.inicio) / total) * 100}%` : 0 }}
          />
        ))}
      </div>
      <ol className="space-y-1" aria-label="Frases da narração">
        {frases.map((f, i) => {
          const t = tempos[i];
          return (
            <li key={i} data-testid={`frase-tempo-${i + 1}`}>
              <button
                type="button"
                disabled={!t || !onTocar}
                onClick={() => t && onTocar?.(t.inicio, i)}
                aria-label={t ? `Tocar a frase ${i + 1} a partir de ${fmtSeg(t.inicio)}` : `Frase ${i + 1}`}
                className={cn(
                  "flex w-full items-start gap-3 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent disabled:hover:bg-transparent",
                  i === ativa && "bg-accent",
                )}
              >
                <Play className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                <span className="w-28 shrink-0 text-xs text-muted-foreground tabular-nums">
                  {t ? `${fmtSeg(t.inicio)} – ${fmtSeg(t.fim)}` : "—"}
                </span>
                <span className="min-w-0 break-words">{f}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
