import { Loader2 } from "lucide-react";
import { statusGeracaoLabel, type Geracao, type GeracaoResumo } from "../../lib/geracoes";

// Andamento (spec 021, T027): porcentagem com barra e a mensagem da etapa. O polling de 2 s fica no
// `useGeracao`; aqui só a apresentação.
export function AndamentoGeracao({ geracao }: { geracao: Geracao | GeracaoResumo }) {
  const pct = Math.max(0, Math.min(100, Math.round(geracao.progress)));
  const mensagem = geracao.etapaMensagem ?? (geracao.status === "na_fila" ? "Esperando a vez na fila" : statusGeracaoLabel[geracao.status]);
  return (
    <div data-testid="andamento-geracao" className="space-y-1.5" aria-live="polite">
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="flex min-w-0 items-center gap-1.5 text-muted-foreground">
          <Loader2 className="size-4 shrink-0 animate-spin" aria-hidden="true" />
          <span className="truncate">{mensagem}</span>
        </span>
        <span className="font-medium tabular-nums">{pct}%</span>
      </div>
      <div
        role="progressbar"
        aria-label="Andamento da geração"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        className="h-2 w-full overflow-hidden rounded-full bg-muted"
      >
        <div className="h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
