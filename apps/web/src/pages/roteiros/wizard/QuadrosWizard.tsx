/*
 * Os quadros no wizard (spec 031, US3/US5, T037/T046; FR-025, FR-026, FR-028): por cena, a sequência
 * de 2 a 4 quadros lado a lado (início, meio 1, meio 2, fim), gerada de uma vez em 1 versão. O
 * operador aprova a sequência da cena ou recusa um quadro: o recusado e os seguintes são refeitos a
 * partir do último mantido. Sem a instrução de cada quadro (FR-015).
 */
import { CheckCircle2, ImageOff, Loader2, ThumbsDown } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { RoteiroPosicao } from "@/lib/roteiros";
import { ajusteAberto, papelLabel, type RoteiroQuadro } from "@/lib/videoGuiado";
import { Andamentos, type EtapaProps } from "../etapas/comum";
import { NaoAprovo } from "./NaoAprovo";

const NA_ETAPA = new Set(["gerando_keyframes", "aguardando_keyframes"]);

export function QuadrosWizard({ roteiro: r, rodar, travado }: EtapaProps) {
  const faltam = r.posicoes.filter((p) => p.aprovadoKeyframesEm == null).length;
  return (
    <div className="flex flex-col gap-4" data-testid="wizard-quadros">
      <p className="text-sm text-muted-foreground" role="status">
        {faltam > 0
          ? `Confira os quadros de cada cena e aprove a sequência. ${faltam === 1 ? "Falta 1 cena." : `Faltam ${faltam} cenas.`}`
          : "Todas as sequências aprovadas. Os clipes vêm a seguir."}
      </p>
      <ol className="flex flex-col gap-4" aria-label="Quadros por cena">
        {r.posicoes.map((p) => (
          <SequenciaCena key={p.ordem} roteiro={r} posicao={p} rodar={rodar} travado={travado} />
        ))}
      </ol>
    </div>
  );
}

function SequenciaCena({ roteiro: r, posicao: p, rodar, travado }: EtapaProps & { posicao: RoteiroPosicao }) {
  const [recusado, setRecusado] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const n = p.ordem + 1;
  const quadros = p.quadros ?? [];
  const gerando = p.geracoesAbertas.some((g) => g.passo === "cena.keyframe");
  const aprovada = p.aprovadoKeyframesEm != null;
  const naEtapa = !travado && NA_ETAPA.has(r.status);
  const ajustando = ajusteAberto(r);
  const completa = quadros.length >= 2 && quadros.every((q) => q.imageId != null);
  const qRecusado = quadros.find((q) => q.ordem === recusado);

  return (
    <li className="flex flex-col gap-3 rounded-xl border p-3" data-testid={`quadros-cena-${n}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">Cena {n}</h3>
        <span className="text-xs text-muted-foreground">
          {quadros.length} {quadros.length === 1 ? "quadro" : "quadros"}
        </span>
        {aprovada ? (
          <Badge className="bg-success text-success-foreground" data-testid="sequencia-aprovada">
            Aprovada
          </Badge>
        ) : (
          completa && !gerando && <Badge variant="outline">Para aprovar</Badge>
        )}
      </div>
      <Andamentos geracoes={p.geracoesAbertas} filtro={(g) => g.passo === "cena.keyframe"} />

      <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label={`Sequência da cena ${n}`}>
        {quadros.map((q) => (
          <Quadro
            key={q.ordem}
            q={q}
            cena={n}
            gerando={gerando}
            recusavel={naEtapa && !ajustando && q.imageId != null}
            recusando={recusado === q.ordem}
            onRecusar={() => setRecusado(q.ordem)}
          />
        ))}
      </ol>

      {naEtapa && !aprovada && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            disabled={busy || !completa || gerando || ajustando}
            aria-busy={busy}
            onClick={async () => {
              setBusy(true);
              await rodar(() => api.roteiros.aprovarPosicao(r.id, p.ordem, { etapa: "keyframes", version: r.version }), `Sequência da cena ${n} aprovada.`);
              setBusy(false);
            }}
          >
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
            Aprovar a sequência da cena {n}
          </Button>
          {!completa && <span className="text-xs text-muted-foreground">Espere todos os quadros saírem.</span>}
        </div>
      )}

      {qRecusado && naEtapa && (
        <NaoAprovo
          key={qRecusado.ordem}
          roteiro={r}
          alvo={{ tipo: "quadros", ordem: p.ordem, quadro: qRecusado.ordem }}
          rotulo={`o quadro ${papelLabel[qRecusado.papel]} da cena ${n}`}
          onFechar={() => setRecusado(null)}
        />
      )}
    </li>
  );
}

function Quadro({
  q,
  cena,
  gerando,
  recusavel,
  recusando,
  onRecusar,
}: {
  q: RoteiroQuadro;
  cena: number;
  gerando: boolean;
  recusavel: boolean;
  recusando: boolean;
  onRecusar: () => void;
}) {
  const papel = papelLabel[q.papel];
  return (
    <li className="flex min-w-0 flex-col gap-1.5" data-testid={`quadro-${q.ordem}`} data-image-id={q.imageId ?? ""}>
      <p className="flex flex-wrap items-center gap-1 text-xs font-medium">
        {papel}
        {q.imageId && q.provisorio && (
          <Badge variant="outline" className="h-4 px-1 text-[10px]">
            provisório
          </Badge>
        )}
      </p>
      <div className="aspect-[9/16] overflow-hidden rounded-md border bg-muted">
        {q.imageUrl ? (
          <img src={q.imageUrl} alt={`Quadro ${papel} da cena ${cena}`} className="size-full object-cover" />
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-1 p-2 text-center text-xs text-muted-foreground" role="status" data-testid="quadro-gerando">
            {gerando ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <ImageOff className="size-4" aria-hidden="true" />}
            {gerando ? "Gerando…" : "Na fila"}
          </div>
        )}
      </div>
      {recusavel && (
        <Button type="button" variant={recusando ? "secondary" : "ghost"} size="sm" className="h-7 text-xs" aria-expanded={recusando} onClick={onRecusar} aria-label={`Não aprovo o quadro ${papel} da cena ${cena}`}>
          <ThumbsDown aria-hidden="true" />
          Não aprovo
        </Button>
      )}
    </li>
  );
}
