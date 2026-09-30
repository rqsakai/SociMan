/*
 * Marcos 1 h / 24 h / 7 d / 30 d de um vídeo (spec 016, R15): visualizações em destaque e
 * curtidas, comentários e compartilhamentos embaixo. "estimado" quando as fotos em volta do marco
 * estão longe dele; "ainda não" quando o vídeo é mais novo; "sem dado" quando a coleta parou antes.
 */
import { Badge } from "@/components/ui/badge";
import { formatNumero, MARCOS, type MarcoValor, type Marcos } from "@/lib/metricas";

function valorTexto(m: MarcoValor): string {
  if (m.valor !== null) return formatNumero(Math.round(m.valor));
  return m.motivo === "ainda_nao" ? "ainda não" : "sem dado";
}

export function MarcosCard({ marcos }: { marcos: Marcos }) {
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Marcos do vídeo">
      {MARCOS.map(({ id, label }) => {
        const m = marcos[id];
        const estimado = [m.views, m.likes, m.comments, m.shares].some((x) => x.valor !== null && x.estimado);
        const vazio = m.views.valor === null;
        return (
          <div key={id} className="rounded-lg border bg-muted/30 p-3">
            <dt className="flex items-center justify-between gap-1 text-xs text-muted-foreground">
              <span>Em {label}</span>
              {estimado && (
                <Badge variant="outline" className="text-[0.65rem]" title="Interpolado entre fotos distantes do marco">
                  estimado
                </Badge>
              )}
            </dt>
            <dd className={vazio ? "mt-1 text-sm text-muted-foreground" : "mt-1 text-xl font-bold tabular-nums"}>
              {valorTexto(m.views)}
              {!vazio && <span className="ml-1 text-xs font-normal text-muted-foreground">views</span>}
            </dd>
            {!vazio && (
              <dd className="mt-1 text-xs text-muted-foreground tabular-nums">
                {valorTexto(m.likes)} curtidas · {valorTexto(m.comments)} coment. · {valorTexto(m.shares)} compart.
              </dd>
            )}
          </div>
        );
      })}
    </dl>
  );
}
