/*
 * O cartão mínimo do produto (spec 026, US1; exemplo do dono): preço, comissão %, comissão por
 * venda, loja (com o selo "Loja oficial"), vendas e GMV no período, crescimento, vendas totais,
 * GMV total e a projeção de lucro para 10, 100 e 1.000 vendas (calculada aqui: comissão por venda
 * × N). Todo derivado leva o selo "estimado" (<Estimado>); "coletando" e "amostra pequena" como
 * chips. Clicar no título abre o detalhe.
 */
import type { MercadoCartaoProduto } from "@sociman/contract";
import { ImageOff, Store } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { estadoLabel, formatBp, formatCentavos, formatCrescimento, formatInteiro, formatUmaCasa, produtoMercadoPath, projecao } from "@/lib/mercado";
import { cn } from "@/lib/utils";
import { Estimado } from "./Estimado";

export const PROJECOES = [10, 100, 1000] as const;

export function CartaoProduto({ produto: p, compacto = false, className }: { produto: MercadoCartaoProduto; compacto?: boolean; className?: string }) {
  return (
    <article data-produto={p.redeProdutoId} className={cn("flex min-w-0 gap-3 rounded-lg border bg-card p-3 text-card-foreground", className)}>
      <div className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted">
        {p.imagemUrl ? <img src={p.imagemUrl} alt="" className="size-full object-cover" loading="lazy" /> : <ImageOff className="size-5 text-muted-foreground" aria-hidden="true" />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <Link to={produtoMercadoPath(p.id)} className="truncate font-medium hover:underline">
            {p.titulo ?? p.redeProdutoId}
          </Link>
          {p.estado !== "ok" && <Badge variant="outline">{estadoLabel(p.estado)}</Badge>}
          {p.novoEmAlta && <Badge>novo em alta</Badge>}
          {p.altoRetornoPoucosAfiliados && <Badge variant="secondary">alto retorno, poucos afiliados</Badge>}
        </div>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
          {p.loja && (
            <span className="inline-flex items-center gap-1">
              <Store className="size-3" aria-hidden="true" />
              {p.loja.nome}
              {p.loja.oficial && <Badge variant="outline">Loja oficial</Badge>}
            </span>
          )}
          {p.categoria && <span>{p.categoria.caminho}</span>}
        </p>
        <dl className={cn("mt-2 grid gap-x-4 gap-y-1 text-sm", compacto ? "grid-cols-2 sm:grid-cols-3" : "grid-cols-2 sm:grid-cols-4")}>
          <Item rotulo="Preço">{p.preco ? <span className="tabular-nums">{formatCentavos(p.preco.minCentavos)}{p.preco.maxCentavos !== null && p.preco.maxCentavos !== p.preco.minCentavos ? ` – ${formatCentavos(p.preco.maxCentavos)}` : ""}</span> : "—"}</Item>
          <Item rotulo="Comissão">
            <Estimado numero={p.comissaoBp} formatar={formatBp} />
          </Item>
          <Item rotulo="Comissão por venda">
            <Estimado numero={p.comissaoPorVendaCentavos} formatar={formatCentavos} />
          </Item>
          <Item rotulo="Criadores">
            <Estimado numero={p.nCriadores} formatar={formatInteiro} />
          </Item>
          <Item rotulo="Vendas no período">
            <Estimado numero={p.vendasPeriodo} formatar={formatInteiro} />
          </Item>
          <Item rotulo="GMV no período">
            <Estimado numero={p.gmvPeriodoCentavos} formatar={formatCentavos} />
          </Item>
          <Item rotulo="Crescimento">
            <Estimado numero={p.crescimento} formatar={formatCrescimento} />
          </Item>
          <Item rotulo="Vendas/dia">
            <Estimado numero={p.vendasDia} formatar={formatUmaCasa} />
          </Item>
          {!compacto && (
            <>
              <Item rotulo="Vendas totais">
                <Estimado numero={p.vendasTotais} formatar={formatInteiro} />
              </Item>
              <Item rotulo="GMV total">
                <Estimado numero={p.gmvTotalCentavos} formatar={formatCentavos} />
              </Item>
              <Item rotulo="Retorno por afiliado/dia">
                <Estimado numero={p.retornoAfiliadoCentavosDia} formatar={formatCentavos} />
              </Item>
              <Item rotulo="Projeção 10 / 100 / 1.000 vendas">
                <span className="tabular-nums" title="comissão por venda × quantidade (estimado)">
                  {PROJECOES.map((n) => formatCentavos(projecao(p.comissaoPorVendaCentavos, n))).join(" / ")}
                  {p.comissaoPorVendaCentavos.valor !== null && p.comissaoPorVendaCentavos.valor !== undefined && (
                    <abbr className="ml-0.5 text-muted-foreground no-underline" title="estimado">
                      *
                    </abbr>
                  )}
                </span>
              </Item>
            </>
          )}
        </dl>
      </div>
    </article>
  );
}

function Item({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-xs text-muted-foreground">{rotulo}</dt>
      <dd className="truncate">{children}</dd>
    </div>
  );
}
