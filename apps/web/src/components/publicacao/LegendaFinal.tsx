import { LEGENDA_TIKTOK_MAX } from "@/lib/postagem";
import { cn } from "@/lib/utils";

// Prévia da legenda que vai para a TikTok (T102): descrição + linha em branco + hashtags.
export function LegendaFinal({ legenda }: { legenda: string }) {
  const passou = legenda.length > LEGENDA_TIKTOK_MAX;
  return (
    <section aria-label="Legenda final" className="space-y-1 rounded-lg border bg-muted/30 p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium">Legenda final</h3>
        <span className={cn("text-xs tabular-nums", passou ? "font-semibold text-destructive" : "text-muted-foreground")}>
          {legenda.length.toLocaleString("pt-BR")}/{LEGENDA_TIKTOK_MAX.toLocaleString("pt-BR")}
        </span>
      </div>
      <p className="text-sm whitespace-pre-wrap">{legenda || <span className="text-muted-foreground">Sem legenda ainda.</span>}</p>
    </section>
  );
}
