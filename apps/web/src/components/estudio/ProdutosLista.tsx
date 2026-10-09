/*
 * Produtos da agência (spec 029, T017; antes a aba Produtos do perfil, 012 US1/US5, FR-022): o
 * catálogo do TikTok Shop de todos os perfis e sem perfil, com miniatura (recorte da 1ª variante
 * ativa, senão a original), nome comercial (ou o interno, antes da ficha), perfil base, categoria,
 * variantes, estado e data; filtros por perfil base e estado, busca por nome e "Ver arquivados", na
 * URL (`perfil`, `q`, `status`, `arquivados=1`). "Novo produto" nasce com o perfil do filtro.
 */
import { Package, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns, FilterBar, type FiltroAtivo } from "@/components/data-table";
import { NovoProdutoDialog } from "@/components/produtos/NovoProdutoDialog";
import { EmptyState, HeaderCard } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Switch } from "@/components/ui/switch";
import { perfilDoFiltro, perfilNomeDe, usePerfisTodos, vazioDoPerfil, type PerfilFiltro } from "@/lib/estudio";
import { useFiltroUrl } from "@/lib/filtros";
import { estadoProdutoLabel, estadoProdutoTone, STATUS_PRODUTO, useProdutosAgencia, type ProdutoResumo, type ProdutoStatus } from "@/lib/produtos";
import { formatDateTime } from "@/lib/tz";
import { PerfilBaseFiltro, usePerfilBaseAtivo } from "./PerfilBaseFiltro";

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

function colunas(nomePerfil: (p: ProdutoResumo) => string) {
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
    col.accessor((p) => nomePerfil(p), {
      id: "perfilBase",
      header: "Perfil base",
      meta: { className: "hidden sm:table-cell" },
      cell: (c) => <span className="whitespace-nowrap">{c.getValue()}</span>,
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

export function ProdutosLista({ perfilFiltro, onPerfilFiltro }: { perfilFiltro: PerfilFiltro; onPerfilFiltro: (v: PerfilFiltro) => void }) {
  const perfis = usePerfisTodos();
  const [params, set] = useFiltroUrl();
  const q = params.get("q") ?? "";
  const status = (params.get("status") ?? "") as ProdutoStatus | "";
  const arquivados = params.get("arquivados") === "1";
  const [novo, setNovo] = useState(false);
  const produtos = useProdutosAgencia(perfilFiltro, { q: q || undefined, status: status || undefined, arquivados: arquivados ? "true" : "false" });
  const itens = useMemo(() => produtos.data?.pages.flatMap((p) => p.itens), [produtos.data]);
  const columns = useMemo(() => colunas((p) => perfilNomeDe(p, perfis.data)), [perfis.data]);
  // o filtro de perfil sozinho não conta: quem vem do card do perfil vê o convite para criar
  const filtrando = Boolean(q || status);
  const vazio = vazioDoPerfil(perfilFiltro, perfis.data);

  const ativosPerfil = usePerfilBaseAtivo(perfilFiltro, () => onPerfilFiltro("todos"));
  const ativos: FiltroAtivo[] = [
    ...ativosPerfil,
    ...(status ? [{ chave: "status", rotulo: "Estado", valor: estadoProdutoLabel[status] ?? status, limpar: () => set({ status: null }) }] : []),
    ...(arquivados ? [{ chave: "arquivados", rotulo: "Arquivados", valor: "mostrando", limpar: () => set({ arquivados: null }) }] : []),
  ];

  return (
    <>
      <HeaderCard
        title="Biblioteca da agência"
        description="O catálogo do TikTok Shop: fotos por variante, ficha técnica com as palavras exatas para os prompts, recorte e flat lay."
        actions={
          <Button variant="secondary" size="sm" onClick={() => setNovo(true)}>
            <Plus aria-hidden="true" />
            Novo produto
          </Button>
        }
      >
        {produtos.isError && <ApiErrorAlert error={produtos.error} />}
        <DataTable
          label="Produtos"
          columns={columns}
          data={itens}
          loading={produtos.isPending}
          getRowId={(p) => p.id}
          empty={
            filtrando ? (
              <EmptyState titulo="Nenhum produto com esses filtros." icone={Package} />
            ) : (
              <EmptyState
                titulo={`Nenhum produto${vazio.trecho} ainda.`}
                descricao={`Cadastre um produto com uma foto por cor ou variante: a ficha técnica, o recorte e o flat lay saem daqui.${vazio.criarComPerfil ? " O novo produto já nasce com este perfil base." : ""}`}
                icone={Package}
                acao={
                  <Button size="sm" onClick={() => setNovo(true)}>
                    <Plus aria-hidden="true" />
                    Novo produto
                  </Button>
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
                  <PerfilBaseFiltro valor={perfilFiltro} onChange={onPerfilFiltro} />
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
              onLimpar={() => set({ perfil: null, q: null, status: null, arquivados: null })}
            />
          }
          pagination={{ hasMore: produtos.hasNextPage, onLoadMore: () => void produtos.fetchNextPage(), loadingMore: produtos.isFetchingNextPage }}
        />
      </HeaderCard>
      <NovoProdutoDialog perfilId={perfilDoFiltro(perfilFiltro)} open={novo} onOpenChange={setNovo} />
    </>
  );
}
