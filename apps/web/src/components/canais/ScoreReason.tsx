import { HelpCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { scoreComponentLabel, scoreTone, scoreWeights, type VideoFonte } from "@/lib/canais";
import { cn } from "@/lib/utils";

// Selo da pontuação (0–100).
export function ScoreBadge({ score, className }: { score: number; className?: string }) {
  return (
    <span
      className={cn("inline-flex h-7 min-w-10 items-center justify-center rounded-md px-1.5 text-sm font-bold tabular-nums", scoreTone(score), className)}
      title="Pontuação de recomendação (0 a 100)"
    >
      {Math.round(score)}
    </span>
  );
}

// Motivo da recomendação em uma linha e o "Por quê?" com a conta (R3): cada componente de 0 a 1,
// o peso e a contribuição. O componente de maior contribuição é o que gera o motivo.
export function ScoreReason({ video, compact }: { video: Pick<VideoFonte, "title" | "score" | "scoreReason" | "scoreDetail" | "recomendavel">; compact?: boolean }) {
  const detail = video.scoreDetail as Record<string, unknown>;
  const rows = (["v", "e", "r", "d"] as const).map((key) => {
    const value = typeof detail[key] === "number" ? (detail[key] as number) : 0;
    return { key, value, weight: scoreWeights[key]!, points: value * scoreWeights[key]! * 100 };
  });
  const main = typeof detail.componente === "string" ? detail.componente : null;

  return (
    <div className="flex min-w-0 items-start gap-1">
      <p className={cn("min-w-0 text-xs text-muted-foreground", compact ? "line-clamp-1" : "line-clamp-2")}>
        {video.scoreReason || (video.recomendavel ? "Recomendado" : "Não recomendado")}
      </p>
      <Dialog>
        <DialogTrigger asChild>
          <Button type="button" variant="ghost" size="icon" className="-my-1 size-6 shrink-0" aria-label={`Por quê? (${video.title})`}>
            <HelpCircle className="size-3.5" aria-hidden="true" />
          </Button>
        </DialogTrigger>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Por que {Math.round(video.score)} pontos?</DialogTitle>
            <DialogDescription className="line-clamp-2">{video.title}</DialogDescription>
          </DialogHeader>
          <p className="text-sm">{video.scoreReason || "Sem motivo registrado."}</p>
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted-foreground uppercase">
              <tr>
                <th className="py-1 font-semibold">Componente</th>
                <th className="py-1 text-right font-semibold">Nota</th>
                <th className="py-1 text-right font-semibold">Peso</th>
                <th className="py-1 text-right font-semibold">Pontos</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key} className={cn("border-t", main === r.key && "font-semibold")}>
                  <td className="py-1.5">{scoreComponentLabel[r.key]}</td>
                  <td className="py-1.5 text-right tabular-nums">{r.value.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}</td>
                  <td className="py-1.5 text-right tabular-nums">{Math.round(r.weight * 100)}%</td>
                  <td className="py-1.5 text-right tabular-nums">{r.points.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-muted-foreground">
            Vídeos já cortados para o perfil do filtro valem 30% da pontuação. Indisponíveis, ao vivo, com mais de 3 horas ou
            menos de 45 segundos ficam fora da recomendação. O status de direito não entra na conta.
          </p>
        </DialogContent>
      </Dialog>
    </div>
  );
}
