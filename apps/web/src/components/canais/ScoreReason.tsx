import { HelpCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  afinidadeMotivoLabel,
  FATOR_JA_CORTADO,
  scoreComponentLabel,
  scoreTone,
  scoreWeights,
  temaAcaoLabel,
  type AfinidadeEstado,
  type VideoFonte,
} from "@/lib/canais";
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

const pontosFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const sinalFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1, signDisplay: "exceptZero" });

// O motivo resumido da pontuação (a linha do Descobrir e o "Por quê?").
export function motivoCurto(video: Pick<VideoFonte, "scoreReason" | "recomendavel">): string {
  return video.scoreReason || (video.recomendavel ? "Recomendado" : "Não recomendado");
}

type ScoreVideo = Pick<VideoFonte, "title" | "score" | "scoreReason" | "scoreDetail" | "recomendavel"> &
  Partial<Pick<VideoFonte, "jaCortado" | "afinidade">>;

// Motivo da recomendação em uma linha e o "Por quê?" com a conta (R3; spec 024, R9): cada componente
// de 0 a 1, o peso e a contribuição; o "já cortado" (×0,3) e a afinidade com o perfil, para a soma
// bater com a pontuação. `perfilId` e `afinidadeEstado` vêm da lista do Descobrir; `semTexto` deixa só o
// botão (o motivo aparece em outro lugar da linha).
export function ScoreReason({
  video,
  compact,
  semTexto,
  perfilId,
  afinidadeEstado,
}: {
  video: ScoreVideo;
  compact?: boolean;
  semTexto?: boolean;
  perfilId?: string | null;
  afinidadeEstado?: AfinidadeEstado | null;
}) {
  const detail = video.scoreDetail as Record<string, unknown>;
  const rows = (["v", "e", "r", "d"] as const).map((key) => {
    const value = typeof detail[key] === "number" ? (detail[key] as number) : 0;
    return { key, value, weight: scoreWeights[key]!, points: value * scoreWeights[key]! * 100 };
  });
  const main = typeof detail.componente === "string" ? detail.componente : null;
  const base = rows.reduce((soma, r) => soma + r.points, 0);
  const jaCortado = Boolean(perfilId) && (video.jaCortado ?? []).some((j) => j.perfilId === perfilId);
  const descontoCortado = jaCortado ? base * FATOR_JA_CORTADO - base : 0;
  const afinidade = video.afinidade ?? null;
  const temas = afinidade?.temas ?? [];
  // A pontuação é limitada a 0..100: o que passar vira uma linha própria, para a soma fechar.
  const soma = base + descontoCortado + (afinidade?.pontos ?? 0);
  const ajusteLimite = Math.abs(video.score - soma) > 0.5 && (video.score >= 99.5 || video.score <= 0.5) ? video.score - soma : 0;
  const motivoNeutro =!afinidade && afinidadeEstado?.motivo ? afinidadeMotivoLabel[afinidadeEstado.motivo] : null;

  return (
    <div className="flex min-w-0 items-start gap-1">
      {!semTexto && (
        <p className={cn("min-w-0 text-xs text-muted-foreground", compact ? "line-clamp-1" : "line-clamp-2")}>{motivoCurto(video)}</p>
      )}
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
                <th className="py-1 text-right font-semibold">Nota (0 a 1)</th>
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
                  <td className="py-1.5 text-right tabular-nums">{pontosFmt.format(r.points)}</td>
                </tr>
              ))}
              {jaCortado && (
                <tr className="border-t">
                  <td className="py-1.5" colSpan={3}>
                    Já cortado para este perfil (×0,3)
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{sinalFmt.format(descontoCortado)}</td>
                </tr>
              )}
              {afinidade && (
                <tr className="border-t">
                  <td className="py-1.5" colSpan={3}>
                    Afinidade (tema e canal)
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{sinalFmt.format(afinidade.pontos)}</td>
                </tr>
              )}
              {ajusteLimite !== 0 && (
                <tr className="border-t">
                  <td className="py-1.5" colSpan={3}>
                    Limite da escala (0 a 100)
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{sinalFmt.format(ajusteLimite)}</td>
                </tr>
              )}
            </tbody>
            <tfoot>
              <tr className="border-t-2 font-semibold">
                <td className="py-1.5" colSpan={3}>
                  Total (0 a 100)
                </td>
                <td className="py-1.5 text-right tabular-nums">{pontosFmt.format(video.score)}</td>
              </tr>
            </tfoot>
          </table>
          {afinidade && (
            <section aria-label="Temas casados" className="flex flex-col gap-1.5">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase">Temas casados</h3>
              {temas.length === 0 ? (
                <p className="text-xs text-muted-foreground">Nenhum tema casou com este vídeo: a afinidade vem só do canal.</p>
              ) : (
                <ul className="flex flex-col gap-1 text-sm">
                  {temas.map((t) => (
                    <li key={t.temaId} className={cn("flex items-center gap-2", t.decisivo && "font-semibold")}>
                      <span className="min-w-0 flex-1 truncate">{t.nome}</span>
                      {t.decisivo && <Badge variant="secondary">Decidiu a afinidade</Badge>}
                      {t.acao && <Badge variant={t.acao === "cortar" ? "destructive" : "outline"}>{temaAcaoLabel[t.acao]}</Badge>}
                      <span className="w-12 text-right tabular-nums">{sinalFmt.format(t.pontos)}</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-xs text-muted-foreground">Pontos de cada tema isolado (até ±20). A afinidade soma 70% do tema que decidiu e 30% do canal.</p>
            </section>
          )}
          {motivoNeutro && <p className="text-xs text-muted-foreground">{motivoNeutro}</p>}
          <p className="text-xs text-muted-foreground">
            Indisponíveis, ao vivo, com mais de 3 horas ou menos de 45 segundos ficam fora da recomendação. O status de direito não entra na
            conta.
          </p>
        </DialogContent>
      </Dialog>
    </div>
  );
}
