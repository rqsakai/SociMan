// Situação de um item da importação da agência (spec 013): novo, igual, diverge, fora…
import { Badge } from "@/components/ui/badge";
import { situacaoLabel, situacaoTone, type Situacao } from "@/lib/importacao";

export function SituacaoBadge({ situacao }: { situacao: Situacao }) {
  return (
    <Badge className={situacaoTone[situacao]} data-situacao={situacao}>
      {situacaoLabel[situacao]}
    </Badge>
  );
}
