import { Loader2, RefreshCcw, TriangleAlert } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { IaDiff } from "@/components/ia/IaDiff";
import type { Aviso } from "@/lib/cenas";

// Avisos da cena (spec 010, FR-005; research R4): nenhum bloqueia o salvar. O "assets_mudaram" sai à
// parte (<AvisoMudou>), com a diferença e "Remontar prompt".
export function Avisos({ avisos }: { avisos: Aviso[] }) {
  const lista = avisos.filter((a) => a.codigo !== "assets_mudaram");
  if (lista.length === 0) return null;
  return (
    <Alert className="border-warning/60" data-testid="cena-avisos">
      <TriangleAlert className="text-warning" aria-hidden="true" />
      <AlertTitle>Avisos</AlertTitle>
      <AlertDescription>
        <ul aria-label="Avisos da cena" className="list-disc space-y-0.5 pl-5">
          {lista.map((a, i) => (
            <li key={`${a.codigo}-${i}`}>{a.mensagem}</li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

// "O avatar/cenário mudou desde que esta cena ficou pronta" (FR-006a): a diferença de cada parte e o
// botão que recongela o prompt sem mudar o status.
export function AvisoMudou({
  avisos,
  podeRemontar,
  remontando,
  onRemontar,
}: {
  avisos: Aviso[];
  podeRemontar: boolean;
  remontando: boolean;
  onRemontar: () => void;
}) {
  const mudou = avisos.filter((a) => a.codigo === "assets_mudaram");
  if (mudou.length === 0) return null;
  return (
    <Alert className="border-warning/60" role="region" aria-label="O avatar ou o cenário mudou">
      <RefreshCcw className="text-warning" aria-hidden="true" />
      <AlertTitle>O avatar ou o cenário mudou</AlertTitle>
      <AlertDescription className="space-y-3">
        {mudou.map((a, i) => (
          <div key={i} className="w-full space-y-2">
            <p>{a.mensagem}</p>
            {a.detalhe && (a.detalhe.antes != null || a.detalhe.depois != null) && (
              <IaDiff antes={String(a.detalhe.antes ?? "")} depois={String(a.detalhe.depois ?? "")} rotuloDepois="Agora" />
            )}
          </div>
        ))}
        <p>O prompt congelado continua o antigo até você remontar. As tomadas já enviadas guardam o prompt com que foram geradas.</p>
        {podeRemontar && (
          <Button type="button" size="sm" disabled={remontando} aria-busy={remontando} onClick={onRemontar}>
            {remontando ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RefreshCcw aria-hidden="true" />}
            Remontar prompt
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}
