/*
 * Curva de um vídeo desde a publicação (spec 016, US4): visualizações ou interações (curtidas,
 * comentários e compartilhamentos, que têm outra escala) pela idade do vídeo, com os marcos
 * 1 h/24 h/7 d/30 d como linhas verticais e os números de cada marco no <MarcosCard>.
 */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { formatCompacto, formatIdadeHoras, MARCOS, type VideoDetalhe } from "@/lib/metricas";
import { LinhaChart, type Ponto, type Serie } from "./LinhaChart";
import { MarcosCard } from "./MarcosCard";

type Vista = "views" | "interacoes";

const SERIES: Record<Vista, { series: Serie[]; campos: ("views" | "likes" | "comments" | "shares")[] }> = {
  views: { series: [{ label: "Visualizações", cor: "primary" }], campos: ["views"] },
  interacoes: {
    series: [
      { label: "Curtidas", cor: "success" },
      { label: "Comentários", cor: "info" },
      { label: "Compartilhamentos", cor: "warning" },
    ],
    campos: ["likes", "comments", "shares"],
  },
};

export function CurvaVideo({ video }: { video: Pick<VideoDetalhe, "fotos" | "marcos"> }) {
  const [vista, setVista] = useState<Vista>("views");
  const { series, campos } = SERIES[vista];
  // A idade 0 vale 0 em todos os contadores (a âncora do R15): a curva começa na publicação.
  const pontos: Ponto[] = [{ x: 0, y: campos.map(() => 0) }, ...video.fotos.map((f) => ({ x: f.idadeS / 3600, y: campos.map((c) => f[c]) }))];
  const idadeMax = pontos[pontos.length - 1]?.x ?? 0;
  const marcadores = MARCOS.filter((m) => m.horas <= Math.max(idadeMax, 1)).map((m) => ({ x: m.horas, label: m.label }));

  return (
    <div className="space-y-4">
      <MarcosCard marcos={video.marcos} />
      {video.fotos.length === 0 ? (
        <p className="text-sm text-muted-foreground">Ainda não há fotos deste vídeo. A primeira chega na próxima coleta.</p>
      ) : (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-1" role="group" aria-label="O que mostrar no gráfico">
            {(["views", "interacoes"] as const).map((v) => (
              <Button key={v} type="button" size="sm" variant={vista === v ? "default" : "outline"} aria-pressed={vista === v} onClick={() => setVista(v)}>
                {v === "views" ? "Visualizações" : "Interações"}
              </Button>
            ))}
          </div>
          <LinhaChart
            titulo={vista === "views" ? "Visualizações pela idade do vídeo" : "Curtidas, comentários e compartilhamentos pela idade do vídeo"}
            series={series}
            pontos={pontos}
            marcadores={marcadores}
            formatX={formatIdadeHoras}
            formatY={formatCompacto}
          />
          <p className="text-xs text-muted-foreground">
            {video.fotos.length} {video.fotos.length === 1 ? "foto" : "fotos"} desde a publicação. Contagens que caem são correções da TikTok e ficam como vieram.
          </p>
        </div>
      )}
    </div>
  );
}
