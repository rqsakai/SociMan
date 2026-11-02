/*
 * A narração no wizard (spec 031, US3, T037; FR-015): só o áudio, sem o texto das frases. "Aprovar"
 * passa o portão da narração; "Não aprovo" abre o chat na narração (mais animada, mais devagar…).
 */
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, ThumbsDown } from "lucide-react";
import { useState } from "react";
import { fmtSeg } from "@/components/roteiro/LinhaTempos";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useLinkEstavel } from "@/lib/linkEstavel";
import { roteiroKey } from "@/lib/roteiros";
import { ajusteAberto } from "@/lib/videoGuiado";
import { Andamentos, type EtapaProps } from "../etapas/comum";
import { NaoAprovo } from "./NaoAprovo";

export function NarracaoWizard({ roteiro: r, rodar, travado }: EtapaProps) {
  const queryClient = useQueryClient();
  const [recusando, setRecusando] = useState(false);
  const [busy, setBusy] = useState(false);
  const n = r.narracao;
  const audio = useLinkEstavel(n?.audioUrl ? { url: n.audioUrl } : null, n?.id ?? null, () => void queryClient.invalidateQueries({ queryKey: roteiroKey(r.id) }));
  const parado = r.status === "aguardando_narracao";
  const ajustando = ajusteAberto(r);
  const pronta = n !== null && !n.desatualizada && !n.limpa;

  return (
    <div className="flex flex-col gap-4" data-testid="wizard-narracao">
      <p className="text-sm text-muted-foreground">Ouça a narração inteira. Se a voz, o ritmo ou o tom não estiverem bons, diga o que trocar.</p>
      <Andamentos geracoes={r.geracoesAbertas} filtro={(g) => g.passo === "roteiro.narracao"} />

      {n && audio.url && !n.limpa ? (
        <div className="flex flex-col gap-2">
          <audio key={n.id} controls preload="metadata" src={audio.url} onError={audio.onErro} aria-label="Narração do vídeo" className="w-full" data-testid="player-narracao" />
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="tabular-nums">{fmtSeg(n.totalS)}</span>
            {n.desatualizada && (
              <Badge className="bg-warning text-warning-foreground" data-testid="narracao-desatualizada">
                Sendo refeita
              </Badge>
            )}
          </p>
        </div>
      ) : (
        r.status !== "narrando" && <p className="text-sm text-muted-foreground">A narração ainda não saiu.</p>
      )}

      {parado && !travado && (
        <div className="flex flex-wrap items-center gap-2" data-testid="aprovar-narracao">
          <Button
            type="button"
            disabled={busy || ajustando || !pronta}
            aria-busy={busy}
            onClick={async () => {
              setBusy(true);
              await rodar(() => api.roteiros.aprovar(r.id, r.version, "narracao"), "Narração aprovada. Agora os quadros de cada cena.");
              setBusy(false);
            }}
          >
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
            Aprovar narração
          </Button>
          <Button type="button" variant="outline" disabled={busy} aria-expanded={recusando} onClick={() => setRecusando(true)}>
            <ThumbsDown aria-hidden="true" />
            Não aprovo
          </Button>
        </div>
      )}
      {recusando && parado && !travado && <NaoAprovo roteiro={r} alvo={{ tipo: "narracao" }} rotulo="a narração" onFechar={() => setRecusando(false)} />}
    </div>
  );
}
