import { useQueryClient } from "@tanstack/react-query";
import { AndamentoGeracao } from "@/components/geracao/AndamentoGeracao";
import { OpcoesGeracao } from "@/components/geracao/OpcoesGeracao";
import { Badge } from "@/components/ui/badge";
import { statusGeracaoLabel, statusGeracaoTone, useGeracao } from "@/lib/geracoes";
import { invalidarProduto, passoAberto, type Produto, type ProdutoPasso } from "@/lib/produtos";

// Um passo do produto (spec 012, T029): o andamento vem do `produto.passos` (o `useProduto` faz o
// polling); as opções, o erro e as ações ("Usar opção N", "Gerar outras", "Tentar de novo" e
// "Cancelar geração") são os componentes da 021, sobre a geração inteira.
export function PassoGeracao({ produto, passo, titulo, disabled }: { produto: Produto; passo: ProdutoPasso; titulo: string; disabled?: boolean }) {
  const queryClient = useQueryClient();
  const geracao = useGeracao(passo.id);
  return (
    <section aria-label={titulo} className="space-y-3" data-testid={`passo-${passo.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{titulo}</h3>
        <Badge className={statusGeracaoTone[passo.status]}>{statusGeracaoLabel[passo.status]}</Badge>
      </div>
      {passoAberto(passo.status) && <AndamentoGeracao geracao={passo} />}
      {passo.status === "falhou" && passo.erro && !geracao.data && (
        <p role="alert" className="text-sm text-destructive">
          {passo.erro.message}
        </p>
      )}
      {geracao.data && (
        <OpcoesGeracao
          geracao={geracao.data}
          alvoVersion={produto.version}
          disabled={disabled}
          onRenovarLinks={() => void geracao.refetch()}
          onEscolhido={() => void invalidarProduto(queryClient, produto.id, produto.perfilId)}
        />
      )}
    </section>
  );
}
