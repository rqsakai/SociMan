/*
 * Card do analytics (spec 019, FR-004/FR-005; R10): a moldura de todo gráfico.
 *
 * <CardAnalytics titulo comoLer tabela? amostra? vazio? carregando? erro? acoes? onAmpliarPeriodo? largo?>
 *   {gráfico}
 * </CardAnalytics>
 *   titulo       <h3> do card (também o nome do CSV)
 *   comoLer      uma frase de leitura, sempre visível abaixo do título
 *   tabela       a tabela alternativa (DadosTabela); a mesma fonte do CSV. Sem ela, sem "Ver tabela" nem "CSV"
 *   amostra      chip "amostra pequena (n = X de Y)" (FR-004)
 *   vazio        motivo do estado vazio (string) ou null; com motivo, o corpo vira o aviso
 *                e o atalho "Ampliar período" (quando há `onAmpliarPeriodo`)
 *   carregando   esqueleto no lugar do corpo
 *   erro         erro da query (ApiErrorAlert)
 *   acoes        filtros locais do card (à direita, antes dos botões)
 *   largo        ocupa as 2 colunas da grade em telas grandes
 *   acoesVazio   atalhos extras no estado vazio (ex.: "Histórico do Studio", spec 022)
 *   children     o gráfico (normalmente um <Grafico/>)
 *
 * Cabeçalho: título (e chip) e botões na mesma linha a partir de sm; no celular os botões descem para
 * uma linha própria. O "Como ler" fica sempre abaixo, com a largura toda do card.
 * "Ver tabela"/"Ver gráfico" é um botão de alternância focável (o ECharts não navega por teclado).
 */
import { BarChart3, Download, Table2 } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { Amostra, type AmostraDados } from "./Amostra";
import { baixarCsv } from "./csv";
import { TabelaAlternativa, type DadosTabela } from "./TabelaAlternativa";

export interface CardAnalyticsProps {
  titulo: string;
  comoLer: ReactNode;
  tabela?: DadosTabela | null;
  amostra?: AmostraDados | null;
  vazio?: string | null;
  carregando?: boolean;
  erro?: unknown;
  acoes?: ReactNode;
  onAmpliarPeriodo?: () => void;
  acoesVazio?: ReactNode;
  largo?: boolean;
  className?: string;
  children?: ReactNode;
}

export function CardAnalytics({
  titulo,
  comoLer,
  tabela,
  amostra,
  vazio,
  carregando,
  erro,
  acoes,
  onAmpliarPeriodo,
  acoesVazio,
  largo,
  className,
  children,
}: CardAnalyticsProps) {
  const [vista, setVista] = useState<"grafico" | "tabela">("grafico");
  const idTitulo = useId();
  const temTabela = Boolean(tabela && tabela.linhas.length > 0);
  const mostrarCorpo = !carregando && !erro && !vazio;

  return (
    <section
      aria-labelledby={idTitulo}
      data-card={titulo}
      className={cn("flex min-w-0 flex-col gap-3 rounded-xl bg-card p-4 text-card-foreground shadow-card sm:p-5", largo && "lg:col-span-2", className)}
    >
      <header className="flex flex-col gap-2">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
            <h3 id={idTitulo} className="text-base font-semibold">
              {titulo}
            </h3>
            <Amostra amostra={amostra} soQuandoPequena />
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {acoes}
            {mostrarCorpo && temTabela && (
              <>
                <Button type="button" size="sm" variant="outline" aria-pressed={vista === "tabela"} onClick={() => setVista(vista === "grafico" ? "tabela" : "grafico")}>
                  {vista === "grafico" ? <Table2 aria-hidden="true" /> : <BarChart3 aria-hidden="true" />}
                  {vista === "grafico" ? "Ver tabela" : "Ver gráfico"}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  title={`Baixar os dados de "${titulo}" em CSV`}
                  onClick={() =>
                    baixarCsv(
                      titulo,
                      tabela!.colunas.map((c) => c.titulo),
                      tabela!.linhas,
                    )
                  }
                >
                  <Download aria-hidden="true" />
                  CSV
                </Button>
              </>
            )}
          </div>
        </div>
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">Como ler: </span>
          {comoLer}
        </p>
      </header>

      {erro ? (
        <ApiErrorAlert error={erro} />
      ) : carregando ? (
        <Skeleton className="h-60 w-full" />
      ) : vazio ? (
        <div className="flex flex-col items-start gap-2 rounded-lg border border-dashed p-4 text-sm text-muted-foreground" role="status">
          <p>{vazio}</p>
          {onAmpliarPeriodo && (
            <Button type="button" size="sm" variant="outline" onClick={onAmpliarPeriodo}>
              Ampliar período
            </Button>
          )}
          {acoesVazio}
        </div>
      ) : vista === "tabela" && temTabela ? (
        <TabelaAlternativa titulo={titulo} dados={tabela!} />
      ) : (
        <div className="min-w-0">{children}</div>
      )}
    </section>
  );
}
