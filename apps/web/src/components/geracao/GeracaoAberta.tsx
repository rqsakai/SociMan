import { Badge } from "@/components/ui/badge";
import { statusGeracaoLabel, statusGeracaoTone, useGeracao, type GeracaoResumo } from "../../lib/geracoes";
import { AndamentoGeracao } from "./AndamentoGeracao";
import { OpcoesGeracao } from "./OpcoesGeracao";

// A geração aberta de um passo (spec 025, FR-032; reaproveitada do T029 da 012): o estado, o
// andamento com a mensagem da 021 ("Gerando opção 2 de 2", "Aguardando a GPU ficar livre") e as
// opções com "Usar opção N", "Gerar outras", "Tentar de novo" e "Cancelar geração". O resumo vem do
// alvo; o detalhe (opções, versão) do `useGeracao`, que faz o polling.
export function GeracaoAberta({
  resumo,
  alvoVersion,
  titulo,
  disabled,
  onEscolhido,
}: {
  resumo: GeracaoResumo;
  alvoVersion?: number;
  titulo?: string;
  disabled?: boolean;
  onEscolhido?: () => void;
}) {
  const geracao = useGeracao(resumo.id);
  const g = geracao.data ?? resumo;
  const andando = g.status === "na_fila" || g.status === "rodando";
  return (
    <section aria-label={titulo ?? "Geração"} className="space-y-3" data-testid={`geracao-${resumo.passo}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {titulo && <h4 className="text-sm font-semibold">{titulo}</h4>}
        <Badge className={statusGeracaoTone[g.status]} data-testid="geracao-status">
          {statusGeracaoLabel[g.status]}
        </Badge>
      </div>
      {andando && <AndamentoGeracao geracao={g} />}
      {geracao.data ? (
        <OpcoesGeracao
          geracao={geracao.data}
          alvoVersion={alvoVersion}
          disabled={disabled}
          onRenovarLinks={() => void geracao.refetch()}
          onEscolhido={onEscolhido}
        />
      ) : (
        g.status === "falhou" &&
        g.erro && (
          <p role="alert" className="text-sm text-destructive">
            {g.erro.message}
          </p>
        )
      )}
    </section>
  );
}
