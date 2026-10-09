/*
 * Aba Produtos do perfil (spec 012, US1/US5; FR-022): o catálogo de produtos do TikTok Shop com
 * miniatura (recorte da 1ª variante ativa, senão a original), nome comercial (ou o interno, antes da
 * ficha), categoria, variantes, estado e data; filtro por estado, busca por nome e "Ver arquivados".
 * Os filtros ficam na URL (`q`, `status`, `arquivados=1`). "Novo produto" abre o diálogo de cadastro.
 */
import type { Perfil } from "@sociman/contract";
import { Package, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns, FilterBar, type FiltroAtivo } from "@/components/data-table";
import { NovoProdutoDialog } from "@/components/produtos/NovoProdutoDialog";
import { EmptyState, HeaderCard, Page } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Switch } from "@/components/ui/switch";
import { useFiltroUrl } from "@/lib/filtros";
import { estadoProdutoLabel, estadoProdutoTone, STATUS_PRODUTO, useProdutos, type ProdutoResumo, type ProdutoStatus } from "@/lib/produtos";
import { formatDateTime } from "@/lib/tz";

function Miniatura({ produto }: { produto: ProdutoResumo }) {
  return (
    <span className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-white">
      {produto.thumbUrl ? (
        <img src={produto.thumbUrl} alt="" loading="lazy" className="size-full object-contain" />
      ) : (
        <Package className="size-5 text-muted-foreground" aria-hidden="true" />
      )}
    </span>
  );
}

function colunas() {
  const col = dataTableColumns<ProdutoResumo>();
  return col.columns([
    col.accessor((p) => p.nomeComercial ?? p.name, {
      id: "nome",
      header: "Produto",
      cell: (c) => {
        const p = c.row.original;
        return (
          <div className="flex min-w-0 items-center gap-3">
            <Miniatura produto={p} />
            <div className="min-w-0">
              <Link to={`/app/produtos/${p.id}`} className="font-medium break-words underline-offset-2 hover:underline">
                {c.getValue()}
              </Link>
              {p.nomeComercial && p.nomeComercial !== p.name && <p className="text-xs break-words text-muted-foreground">{p.name}</p>}
            </div>
          </div>
        );
      },
    }),
    col.accessor((p) => p.categoria ?? "", {
      id: "categoria",
      header: "Categoria",
      meta: { className: "hidden md:table-cell" },
      cell: (c) => c.getValue() || "—",
    }),
    col.accessor("variantesAtivas", {
      header: "Variantes",
      enableGlobalFilter: false,
      meta: { className: "hidden sm:table-cell" },
      cell: (c) => <span className="tabular-nums">{c.getValue()}</span>,
    }),
    col.accessor((p) => estadoProdutoLabel[p.estado], {
      id: "estado",
      header: "Estado",
      cell: (c) => <Badge className={estadoProdutoTone[c.row.original.estado]}>{c.getValue()}</Badge>,
    }),
    col.accessor("updatedAt", {
      header: "Alterado",
      enableGlobalFilter: false,
      meta: { className: "hidden lg:table-cell" },
      cell: (c) => (
        <time dateTime={c.getValue()} className="whitespace-nowrap">
          {formatDateTime(c.getValue())}
        </time>
      ),
    }),
  ]);
}

export function ProdutosTab({ perfil }: { perfil: Perfil }) {
  const [params, set] = useFiltroUrl();
  const q = params.get("q") ?? "";
  const status = (params.get("status") ?? "") as ProdutoStatus | "";
  const arquivados = params.get("arquivados") === "1";
  const [novo, setNovo] = useState(false);
  const produtos = useProdutos(perfil.id, { q: q || undefined, status: status || undefined, arquivados: arquivados ? "true" : "false" });
  const itens = useMemo(() => produtos.data?.pages.flatMap((p) => p.itens), [produtos.data]);
  const columns = useMemo(() => colunas(), []);
  const filtrando = Boolean(q || status);

  const ativos: FiltroAtivo[] = [
    ...(status ? [{ chave: "status", rotulo: "Estado", valor: estadoProdutoLabel[status] ?? status, limpar: () => set({ status: null }) }] : []),
    ...(arquivados ? [{ chave: "arquivados", rotulo: "Arquivados", valor: "mostrando", limpar: () => set({ arquivados: null }) }] : []),
  ];

  return (
    <Page>
      <HeaderCard
        title="Produtos"
        description="O catálogo do TikTok Shop: fotos por variante, ficha técnica com as palavras exatas para os prompts, recorte e flat lay."
        actions={
          !perfil.archived && (
            <Button variant="secondary" size="sm" onClick={() => setNovo(true)}>
              <Plus aria-hidden="true" />
              Novo produto
            </Button>
          )
        }
      >
        {produtos.isError && <ApiErrorAlert error={produtos.error} />}
        <DataTable
          label="Produtos do perfil"
          columns={columns}
          data={itens}
          loading={produtos.isPending}
          getRowId={(p) => p.id}
          empty={
            filtrando ? (
              <EmptyState titulo="Nenhum produto com esses filtros." icone={Package} />
            ) : (
              <EmptyState
                titulo="Nenhum produto ainda."
                descricao="Cadastre um produto com uma foto por cor ou variante: a ficha técnica, o recorte e o flat lay saem daqui."
                icone={Package}
                acao={
                  !perfil.archived && (
                    <Button size="sm" onClick={() => setNovo(true)}>
                      <Plus aria-hidden="true" />
                      Novo produto
                    </Button>
                  )
                }
              />
            )
          }
          toolbar={
            <FilterBar
              busca={{
                valor: q,
                onChange: (v) => set({ q: v || null }, { replace: true }),
                rotulo: "Buscar produtos",
                placeholder: "Nome interno ou comercial",
              }}
              principais={
                <>
                  <Field label="Estado" className="w-full sm:w-44">
                    {({ id }) => (
                      <NativeSelect id={id} value={status} onChange={(e) => set({ status: e.target.value })}>
                        <option value="">Todos</option>
                        {STATUS_PRODUTO.map((st) => (
                          <option key={st} value={st}>
                            {estadoProdutoLabel[st]}
                          </option>
                        ))}
                      </NativeSelect>
                    )}
                  </Field>
                  <label className="flex h-9 items-center gap-2 text-sm">
                    <Switch checked={arquivados} onCheckedChange={(on) => set({ arquivados: on ? "1" : null })} aria-label="Ver arquivados" />
                    Ver arquivados
                  </label>
                </>
              }
              ativos={ativos}
              onLimpar={() => set({ q: null, status: null, arquivados: null })}
            />
          }
          pagination={{ hasMore: produtos.hasNextPage, onLoadMore: () => void produtos.fetchNextPage(), loadingMore: produtos.isFetchingNextPage }}
        />
      </HeaderCard>
      <NovoProdutoDialog perfilId={perfil.id} open={novo} onOpenChange={setNovo} />
    </Page>
  );
}
