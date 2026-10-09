/*
 * Aba "Cockpit" (spec 026, FR-051): quatro cards dos mesmos dados que a tabela e o CSV. "Mais
 * vendidos", "Novos em alta" e "Alto retorno com poucos afiliados" listam cartões de produto (com
 * "Ver tabela" e "CSV" pelo <CardAnalytics>); "Estado da coleta" mostra a situação, o orçamento do
 * dia e a rodada atual.
 */
import type { MercadoCartaoProduto } from "@sociman/contract";
import { Link } from "react-router-dom";
import { CardAnalytics } from "@/components/analytics/CardAnalytics";
import type { DadosTabela } from "@/components/analytics/TabelaAlternativa";
import { CartaoProduto } from "@/components/mercado/CartaoProduto";
import { Estimado } from "@/components/mercado/Estimado";
import { Badge } from "@/components/ui/badge";
import {
  estadoLabel,
  formatBp,
  formatCentavos,
  formatCrescimento,
  formatInteiro,
  formatUmaCasa,
  textoNumero,
  useMercadoResumo,
  type EstadoFiltroMercado,
} from "@/lib/mercado";
import { formatDateKey, formatDateTime } from "@/lib/tz";

export function tabelaProdutos(itens: MercadoCartaoProduto[]): DadosTabela {
  return {
    colunas: [
      { titulo: "Produto" },
      { titulo: "Loja", secundaria: true },
      { titulo: "Estado", secundaria: true },
      { titulo: "Preço", numerica: true, formatar: (v) => (typeof v === "number" ? formatCentavos(v) : "—") },
      { titulo: "Comissão", numerica: true, formatar: (v) => (typeof v === "number" ? formatBp(v) : "—") },
      { titulo: "Comissão por venda", numerica: true, secundaria: true, formatar: (v) => (typeof v === "number" ? formatCentavos(v) : "—") },
      { titulo: "Vendas no período", numerica: true },
      { titulo: "GMV no período", numerica: true, formatar: (v) => (typeof v === "number" ? formatCentavos(v) : "—") },
      { titulo: "Crescimento", numerica: true, secundaria: true, formatar: (v) => (typeof v === "number" ? formatCrescimento(v) : "—") },
      { titulo: "Vendas totais", numerica: true, secundaria: true },
      { titulo: "Criadores", numerica: true, secundaria: true },
      { titulo: "Retorno por afiliado/dia", numerica: true, secundaria: true, formatar: (v) => (typeof v === "number" ? formatCentavos(v) : "—") },
      { titulo: "Última foto", secundaria: true },
    ],
    linhas: itens.map((p) => [
      p.titulo ?? p.redeProdutoId,
      p.loja ? `${p.loja.nome}${p.loja.oficial ? " (oficial)" : ""}` : null,
      estadoLabel(p.estado),
      p.preco?.minCentavos ?? null,
      p.comissaoBp.valor ?? null,
      p.comissaoPorVendaCentavos.valor ?? null,
      p.vendasPeriodo.valor ?? null,
      p.gmvPeriodoCentavos.valor ?? null,
      p.crescimento.valor ?? null,
      p.vendasTotais.valor ?? null,
      p.nCriadores.valor ?? null,
      p.retornoAfiliadoCentavosDia.valor ?? null,
      p.ultimaFotoEm ? formatDateKey(p.ultimaFotoEm) : null,
    ]),
  };
}

function ListaCartoes({ itens }: { itens: MercadoCartaoProduto[] }) {
  return (
    <div className="flex flex-col gap-2">
      {itens.map((p) => (
        <CartaoProduto key={p.id} produto={p} compacto />
      ))}
    </div>
  );
}

const situacaoLabel: Record<string, string> = {
  desligada_no_servidor: "desligada no servidor",
  desligada: "desligada",
  aceite_pendente: "aceite de risco pendente",
  pausada: "pausada",
  aguardando_continuar: "aguardando Continuar",
  fora_da_janela: "fora da janela",
  ociosa: "ociosa",
  coletando: "coletando",
  pausada_captcha: "pausada (verificação)",
  pausada_login: "pausada (login)",
  sem_cliente: "sem token de coletor",
  parada: "parada há mais de 48 h",
};

export function Cockpit({ estado }: { estado: EstadoFiltroMercado }) {
  const resumo = useMercadoResumo(estado.filtro);
  const d = resumo.data;
  const vazioLista = (n: number | undefined) => (resumo.isPending || resumo.isError ? null : n === 0 ? "Nenhum produto neste recorte. Acompanhe um produto por link na aba Mercado do perfil ou escolha as categorias do nicho." : null);
  const coleta = d?.estadoColeta;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <CardAnalytics
        titulo="Mais vendidos"
        comoLer="Os produtos com mais vendas no período (diferença entre fotos de ‘vendidos’), do maior para o menor. Tudo estimado."
        tabela={d ? tabelaProdutos(d.maisVendidos.itens) : null}
        carregando={resumo.isPending}
        erro={resumo.error}
        vazio={vazioLista(d?.maisVendidos.total)}
        acoes={d && d.maisVendidos.total > d.maisVendidos.itens.length ? <Badge variant="outline">{formatInteiro(d.maisVendidos.total)} no total</Badge> : null}
      >
        {d && <ListaCartoes itens={d.maisVendidos.itens} />}
      </CardAnalytics>

      <CardAnalytics
        titulo="Novos em alta"
        comoLer="Produtos vistos há até 30 dias, com ao menos 10 vendas por dia e crescendo (ou em ranking de alta). Só com estado ‘ok’."
        tabela={d ? tabelaProdutos(d.novosEmAlta.itens) : null}
        carregando={resumo.isPending}
        erro={resumo.error}
        vazio={vazioLista(d?.novosEmAlta.total)}
      >
        {d && <ListaCartoes itens={d.novosEmAlta.itens} />}
      </CardAnalytics>

      <CardAnalytics
        titulo="Alto retorno com poucos afiliados"
        comoLer={
          d?.altoRetornoPoucosAfiliados.criterio?.porCategoria
            ? `Comissão de ao menos 5%, foto do Affiliate Center recente, criadores no quartil inferior da categoria (≤ ${formatInteiro(d.altoRetornoPoucosAfiliados.criterio.p25Criadores as number)}) e retorno por afiliado no superior.`
            : "Comissão de ao menos 5%, foto do Affiliate Center recente e até 50 criadores promovendo (sem categoria comparável para quartis)."
        }
        tabela={d ? tabelaProdutos(d.altoRetornoPoucosAfiliados.itens) : null}
        carregando={resumo.isPending}
        erro={resumo.error}
        vazio={vazioLista(d?.altoRetornoPoucosAfiliados.total)}
      >
        {d && <ListaCartoes itens={d.altoRetornoPoucosAfiliados.itens} />}
      </CardAnalytics>

      <CardAnalytics
        titulo="Estado da coleta"
        comoLer="O que o coletor do desktop fez hoje: páginas e imagens do orçamento, a rodada aberta e os totais deste recorte. Ligar, pausar e aceitar o risco ficam em Configurações."
        tabela={
          d
            ? {
                colunas: [{ titulo: "Indicador" }, { titulo: "Valor", numerica: true }],
                linhas: [
                  ["Situação", situacaoLabel[coleta?.situacao ?? ""] ?? coleta?.situacao ?? "—"],
                  ["Páginas hoje", coleta?.orcamento.paginasHoje ?? null],
                  ["Páginas restantes", coleta?.orcamento.paginasRestantes ?? null],
                  ["Imagens hoje", coleta?.orcamento.imagensHoje ?? null],
                  ["Produtos no recorte", d.totais.produtos],
                  ["Acompanhados", d.totais.acompanhados],
                  ["Coletando", d.totais.coletando],
                  ["Amostra pequena", d.totais.amostraPequena],
                  ["Vendas no período", d.totais.vendasPeriodo.valor ?? null],
                  ["GMV no período", textoNumero(d.totais.gmvPeriodoCentavos, formatCentavos)],
                ],
              }
            : null
        }
        carregando={resumo.isPending}
        erro={resumo.error}
      >
        {d && coleta && (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3" data-card-estado-coleta>
            <div>
              <dt className="text-xs text-muted-foreground">Situação</dt>
              <dd>
                <Badge variant={coleta.situacao === "coletando" ? "default" : "outline"}>{situacaoLabel[coleta.situacao] ?? coleta.situacao}</Badge>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Páginas hoje</dt>
              <dd className="tabular-nums">
                {formatInteiro(coleta.orcamento.paginasHoje)} <span className="text-muted-foreground">/ {formatInteiro(coleta.orcamento.paginasHoje + coleta.orcamento.paginasRestantes)}</span>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Imagens hoje</dt>
              <dd className="tabular-nums">{formatInteiro(coleta.orcamento.imagensHoje)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Rodada atual</dt>
              <dd>{coleta.rodadaAtual ? `${coleta.rodadaAtual.estado} desde ${formatDateTime(coleta.rodadaAtual.iniciadaEm)}` : "nenhuma"}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Último resultado</dt>
              <dd>{coleta.ultimoResultadoEm ? formatDateTime(coleta.ultimoResultadoEm) : "—"}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Produtos no recorte</dt>
              <dd className="tabular-nums">
                {formatInteiro(d.totais.produtos)} <span className="text-muted-foreground">({formatInteiro(d.totais.acompanhados)} acompanhados)</span>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Vendas no período</dt>
              <dd>
                <Estimado numero={d.totais.vendasPeriodo} formatar={formatInteiro} />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">GMV no período</dt>
              <dd>
                <Estimado numero={d.totais.gmvPeriodoCentavos} formatar={formatCentavos} />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Estados</dt>
              <dd className="text-xs">
                {formatInteiro(d.totais.ok)} ok · {formatInteiro(d.totais.amostraPequena)} amostra pequena · {formatInteiro(d.totais.coletando)} coletando
              </dd>
            </div>
            <div className="col-span-full text-xs">
              <Link to="/app/configuracoes/coleta" className="underline">
                Configuração da coleta
              </Link>
              {" · "}
              <span className="text-muted-foreground">vendas/dia médio do recorte: {formatUmaCasa(d.totais.vendasPeriodo.valor === null || d.totais.vendasPeriodo.valor === undefined ? null : d.totais.vendasPeriodo.valor / Math.max(1, Math.round((Date.parse(`${d.contexto.ate}T00:00:00Z`) - Date.parse(`${d.contexto.de}T00:00:00Z`)) / 86_400_000) + 1))}</span>
            </div>
          </dl>
        )}
      </CardAnalytics>
    </div>
  );
}
