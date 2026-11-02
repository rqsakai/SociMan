/*
 * Os clipes no wizard (spec 031, US3/US5, T037/T046; FR-027, FR-028): por cena, um player por trecho
 * (cada trecho vai de um quadro ao seguinte e dura 1 trecho-base). O operador aprova os clipes da
 * cena ou recusa um trecho específico: só aquele trecho é refeito. Sem a ação nem o prompt (FR-015).
 */
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, ThumbsDown } from "lucide-react";
import { useState } from "react";
import { PlayerVideo } from "@/components/roteiro/PlayerVideo";
import { fmtSeg } from "@/components/roteiro/LinhaTempos";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { roteiroKey, type RoteiroPosicao } from "@/lib/roteiros";
import { ajusteAberto, papelLabel, type RoteiroQuadro } from "@/lib/videoGuiado";
import { Andamentos, type EtapaProps } from "../etapas/comum";
import { NaoAprovo } from "./NaoAprovo";

const NA_ETAPA = new Set(["gerando_clipes", "aguardando_clipes"]);

export function ClipesWizard({ roteiro: r, rodar, travado }: EtapaProps) {
  const faltam = r.posicoes.filter((p) => p.aprovadoClipeEm == null).length;
  return (
    <div className="flex flex-col gap-4" data-testid="wizard-clipes">
      <p className="text-sm text-muted-foreground" role="status">
        {faltam > 0 ? `Assista aos clipes de cada cena e aprove. ${faltam === 1 ? "Falta 1 cena." : `Faltam ${faltam} cenas.`}` : "Todos os clipes aprovados. O vídeo vai ser montado."}
      </p>
      <ol className="grid gap-4 lg:grid-cols-2" aria-label="Clipes por cena">
        {r.posicoes.map((p) => (
          <ClipesCena key={p.ordem} roteiro={r} posicao={p} rodar={rodar} travado={travado} />
        ))}
      </ol>
    </div>
  );
}

// "Início → Meio 1": o par de quadros do trecho.
function parDoTrecho(quadros: RoteiroQuadro[], t: number): string | null {
  const a = quadros.find((q) => q.ordem === t);
  const b = quadros.find((q) => q.ordem === t + 1);
  return a && b ? `${papelLabel[a.papel]} → ${papelLabel[b.papel]}` : null;
}

function ClipesCena({ roteiro: r, posicao: p, rodar, travado }: EtapaProps & { posicao: RoteiroPosicao }) {
  const queryClient = useQueryClient();
  const [recusado, setRecusado] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const n = p.ordem + 1;
  const total = p.trechos ?? 1;
  const porTrecho = new Map((p.tomadasTrechos ?? []).map((x) => [x.trecho, x.tomada]));
  const gerando = p.geracoesAbertas.some((g) => g.passo === "cena.clipe");
  const aprovada = p.aprovadoClipeEm != null;
  const naEtapa = !travado && NA_ETAPA.has(r.status);
  const ajustando = ajusteAberto(r);
  const trechos = Array.from({ length: total }, (_, t) => ({ t, tomada: porTrecho.get(t) ?? (total === 1 && t === 0 ? p.tomada : null) }));
  const completa = trechos.every((x) => x.tomada != null);
  const renovar = () => void queryClient.invalidateQueries({ queryKey: roteiroKey(r.id) });

  return (
    <li className="flex flex-col gap-3 rounded-xl border p-3" data-testid={`clipes-cena-${n}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">Cena {n}</h3>
        {p.duracaoS != null && <span className="text-xs text-muted-foreground tabular-nums">dura {fmtSeg(p.duracaoS)}</span>}
        {aprovada && (
          <Badge className="bg-success text-success-foreground" data-testid="clipes-aprovados">
            Aprovados
          </Badge>
        )}
      </div>
      <Andamentos geracoes={p.geracoesAbertas} filtro={(g) => g.passo === "cena.clipe"} />

      <ol className="flex flex-col gap-3" aria-label={`Trechos da cena ${n}`}>
        {trechos.map(({ t, tomada }) => {
          const par = parDoTrecho(p.quadros ?? [], t);
          const rotulo = total > 1 ? `trecho ${t + 1} da cena ${n}` : `clipe da cena ${n}`;
          return (
            <li key={t} className="flex flex-col gap-1.5" data-testid={`trecho-${t}`} data-tomada-id={tomada?.id ?? ""}>
              {total > 1 && (
                <p className="text-xs font-medium">
                  Trecho {t + 1}
                  {par && <span className="font-normal text-muted-foreground"> · {par}</span>}
                </p>
              )}
              {tomada?.videoUrl && !tomada.limpa ? (
                <PlayerVideo chave={tomada.id} url={tomada.videoUrl} miniaturaUrl={tomada.miniaturaUrl} rotulo={rotulo.charAt(0).toUpperCase() + rotulo.slice(1)} testId={`player-trecho-${n}-${t}`} onRenovar={renovar} />
              ) : (
                <p className="flex items-center gap-2 rounded-md border border-dashed p-3 text-sm text-muted-foreground" role="status">
                  {gerando && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
                  {gerando ? "Gerando…" : "Ainda sem clipe."}
                </p>
              )}
              {naEtapa && tomada && !ajustando && (
                <Button
                  type="button"
                  variant={recusado === t ? "secondary" : "ghost"}
                  size="sm"
                  className="self-start"
                  aria-expanded={recusado === t}
                  aria-label={`Não aprovo o ${rotulo}`}
                  onClick={() => setRecusado(t)}
                >
                  <ThumbsDown aria-hidden="true" />
                  Não aprovo
                </Button>
              )}
              {recusado === t && naEtapa && (
                <NaoAprovo roteiro={r} alvo={{ tipo: "trecho", ordem: p.ordem, trecho: t }} rotulo={`o ${rotulo}`} onFechar={() => setRecusado(null)} />
              )}
            </li>
          );
        })}
      </ol>

      {naEtapa && !aprovada && (
        <Button
          type="button"
          className="self-start"
          disabled={busy || !completa || gerando || ajustando}
          aria-busy={busy}
          onClick={async () => {
            setBusy(true);
            await rodar(() => api.roteiros.aprovarPosicao(r.id, p.ordem, { etapa: "clipe", version: r.version }), `Clipes da cena ${n} aprovados.`);
            setBusy(false);
          }}
        >
          {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
          Aprovar os clipes da cena {n}
        </Button>
      )}
    </li>
  );
}
