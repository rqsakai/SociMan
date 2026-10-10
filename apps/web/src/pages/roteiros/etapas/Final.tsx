import { useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import { PlayerVideo } from "@/components/roteiro/PlayerVideo";
import { fmtSeg } from "@/components/roteiro/LinhaTempos";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { roteiroKey } from "@/lib/roteiros";
import { Andamentos, BotaoAprovar, type EtapaProps } from "./comum";

// Etapa Final (spec 011, US5, T045): a prévia (as tomadas cortadas na duração de cada cena, com a
// narração), aprovar (o acabamento HD entra na fila da GPU) e, com o roteiro pronto, o vídeo HD e o
// link para o conteúdo da 014 (sem destino aprovado: agendar e publicar são as telas da 014/015).
export function Final({ roteiro, rodar, travado }: EtapaProps) {
  const { previa, acabamento } = roteiro;
  const queryClient = useQueryClient();
  const renovar = () => void queryClient.invalidateQueries({ queryKey: roteiroKey(roteiro.id) });
  return (
    <div className="space-y-4" data-testid="etapa-final">
      <BotaoAprovar roteiro={roteiro} rodar={rodar} travado={travado} portao="final" motivo="Assista à prévia. Aprovar faz o acabamento HD (1080×1920, 24 fps), o passo mais demorado." />
      <Andamentos geracoes={roteiro.geracoesAbertas} filtro={(g) => g.passo === "roteiro.montagem" || g.passo === "roteiro.acabamento"} />

      {roteiro.status === "pronto" && roteiro.conteudoId && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-success/60 bg-success/5 p-3" data-testid="roteiro-pronto">
          <p className="min-w-0 flex-1 text-sm">O vídeo final virou um conteúdo do perfil, marcado como gerado por IA e sem destino aprovado.</p>
          <Button type="button" asChild>
            <Link to={`/app/conteudos/${roteiro.conteudoId}`}>
              <ExternalLink aria-hidden="true" />
              Abrir o conteúdo
            </Link>
          </Button>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <section className="space-y-2" aria-label="Prévia" data-testid="roteiro-previa">
          <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            Prévia
            {previa?.duracaoMs != null && <span className="text-xs font-normal text-muted-foreground tabular-nums">{fmtSeg(previa.duracaoMs / 1000)}</span>}
            {previa && !previa.atual && <Badge className="bg-warning text-warning-foreground">desatualizada</Badge>}
          </h3>
          {previa?.videoUrl ? (
            <PlayerVideo chave={previa.geracaoId} url={previa.videoUrl} rotulo="Prévia do vídeo" testId="player-previa" onRenovar={renovar} />
          ) : (
            <p className="text-sm text-muted-foreground">A prévia sai quando todas as cenas tiverem tomada.</p>
          )}
        </section>
        {acabamento && (
          <section className="space-y-2" aria-label="Vídeo HD" data-testid="roteiro-hd">
            <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold">
              Vídeo HD
              {acabamento.duracaoMs != null && <span className="text-xs font-normal text-muted-foreground tabular-nums">{fmtSeg(acabamento.duracaoMs / 1000)}</span>}
              {!acabamento.atual && <Badge className="bg-warning text-warning-foreground">desatualizado</Badge>}
            </h3>
            {acabamento.videoUrl ? <PlayerVideo chave={acabamento.geracaoId} url={acabamento.videoUrl} rotulo="Vídeo HD" testId="player-hd" onRenovar={renovar} /> : <p className="text-sm text-muted-foreground">Sem arquivo.</p>}
          </section>
        )}
      </div>
    </div>
  );
}
