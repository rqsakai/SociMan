/*
 * O final no wizard (spec 031, US3, T037; FR-036): a prévia montada (aprovar faz o acabamento, leve ou HD;
 * "Não aprovo" abre o chat no vídeo final) e, pronto, o vídeo HD com o link para o conteúdo da 014,
 * gerado por IA e sem destino (a conta só é escolhida ao agendar).
 */
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, Loader2, ThumbsDown } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { PlayerVideo } from "@/components/roteiro/PlayerVideo";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { api } from "@/lib/api";
import { roteiroKey } from "@/lib/roteiros";
import { ajusteAberto } from "@/lib/videoGuiado";
import { ACABAMENTOS, type AcabamentoModo, Andamentos, type EtapaProps } from "../etapas/comum";
import { NaoAprovo } from "./NaoAprovo";

export function FinalWizard({ roteiro: r, rodar, travado }: EtapaProps) {
  const queryClient = useQueryClient();
  const [recusando, setRecusando] = useState(false);
  const [busy, setBusy] = useState(false);
  const [modo, setModo] = useState<AcabamentoModo>(r.acabamentoModo);
  const escolha = ACABAMENTOS.find((a) => a.id === modo);
  const renovar = () => void queryClient.invalidateQueries({ queryKey: roteiroKey(r.id) });
  const parado = !travado && r.status === "aguardando_final";
  const pronto = r.status === "pronto";
  const video = pronto && r.acabamento?.videoUrl ? r.acabamento : r.previa;

  return (
    <div className="flex flex-col gap-4" data-testid="wizard-final">
      <Andamentos geracoes={r.geracoesAbertas} filtro={(g) => g.passo === "roteiro.montagem" || g.passo === "roteiro.acabamento"} />
      {r.status === "finalizando" && (
        <p className="text-sm text-muted-foreground">{r.acabamentoModo === "hd" ? "Fazendo o acabamento HD com IA. É o passo mais demorado." : "Fazendo o acabamento. Leva segundos."}</p>
      )}

      {pronto && r.conteudoId && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-success/60 bg-success/5 p-3" data-testid="roteiro-pronto">
          <p className="min-w-0 flex-1 text-sm">Pronto! O vídeo virou um conteúdo do perfil, marcado como gerado por IA e ainda sem destino. Escolha a conta ao agendar.</p>
          <Button type="button" asChild>
            <Link to={`/app/conteudos/${r.conteudoId}`}>
              <ExternalLink aria-hidden="true" />
              Abrir o conteúdo
            </Link>
          </Button>
        </div>
      )}

      {video?.videoUrl ? (
        <div className="mx-auto w-full max-w-sm">
          <PlayerVideo chave={video.geracaoId} url={video.videoUrl} rotulo={pronto ? "Vídeo final" : "Prévia do vídeo"} testId={pronto ? "player-hd" : "player-previa"} onRenovar={renovar} />
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">O vídeo é montado quando todos os clipes estiverem aprovados.</p>
      )}

      {parado && (
        <div className="flex flex-wrap items-end gap-2" data-testid="aprovar-final">
          <Field label="Acabamento" hint={escolha?.dica} className="min-w-48">
            {({ id, describedBy }) => (
              <NativeSelect id={id} value={modo} aria-describedby={describedBy} data-testid="acabamento-modo" onChange={(e) => setModo(e.target.value as AcabamentoModo)}>
                {ACABAMENTOS.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.rotulo}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Button
            type="button"
            disabled={busy || ajusteAberto(r) || !r.previa?.videoUrl}
            aria-busy={busy}
            onClick={async () => {
              setBusy(true);
              await rodar(() => api.roteiros.aprovar(r.id, r.version, "final", modo), modo === "hd" ? "Vídeo aprovado. O acabamento HD com IA começou." : "Vídeo aprovado. O acabamento começou.");
              setBusy(false);
            }}
          >
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
            Aprovar o vídeo
          </Button>
          <Button type="button" variant="outline" disabled={busy} aria-expanded={recusando} onClick={() => setRecusando(true)}>
            <ThumbsDown aria-hidden="true" />
            Não aprovo
          </Button>
        </div>
      )}
      {recusando && parado && <NaoAprovo roteiro={r} alvo={{ tipo: "final" }} rotulo="o vídeo final" onFechar={() => setRecusando(false)} />}
    </div>
  );
}
