/*
 * Tabela de dados genérica (spec 005, US2) sobre o TanStack Table v9 e o <Table> do shadcn.
 *
 * Props de <DataTable<T>>:
 *   columns: DataTableColumnDef<T>[]  colunas (crie com dataTableColumns<T>(), ver abaixo)
 *   data: T[] | undefined             linhas; undefined conta como vazio
 *   loading?: boolean                 mostra linhas de Skeleton no lugar dos dados
 *   getRowId?: (row: T) => string     id estável da linha (recomendado: row.id)
 *   search?: boolean | { placeholder?: string; label?: string }
 *                                     campo de filtro global por texto (padrão "Filtrar"; o filtro
 *                                     roda sobre as colunas com accessor)
 *   toolbar?: ReactNode               filtros extras à direita da busca (ex.: <select> de status).
 *                                     Com uma <FilterBar> (spec 024), a tabela não desenha a própria
 *                                     busca: a busca é a "Buscar" da barra. Com `search` (dados locais)
 *                                     e a barra sem `busca`, a "Buscar" filtra as linhas carregadas.
 *   initialSorting?: { id: string; desc: boolean }[]
 *   initialPageSize?: 10 | 25 | 50    padrão 10
 *   emptyMessage?: ReactNode          padrão "Nenhum resultado"
 *   empty?: ReactNode                 vazio rico (spec 024): um <EmptyState> no lugar do texto; ganha
 *                                     do `emptyMessage`
 *   label?: string                    aria-label da <table> (ex.: "Perfis")
 *   pagination?: DataTableExternalPagination
 *                                     sem a prop: paginação no cliente (10/25/50 com o total).
 *                                     Com { hasMore, onLoadMore, loadingMore? }: modo externo para
 *                                     listas por cursor; mostra todas as linhas recebidas e o botão
 *                                     "Carregar mais" (ordenação e filtro valem sobre o que já veio).
 *                                     Com { modo: "servidor", total, pagina, tamanho, onPagina,
 *                                     onTamanho } (spec 024): páginas numeradas no servidor; a tela
 *                                     busca só a página (offset) e o rodapé é o <ServerPagination>.
 *   manual?: boolean                  filtro, ordenação e paginação ficam no servidor (spec 014): a
 *                                     tabela mostra as linhas como vieram, sem cabeçalho ordenável
 *                                     nem busca local, e o rodapé é o <CursorPagination> (com o
 *                                     `pagination.total`, quando houver). Sem a prop, nada muda.
 *   isRowSelected?: (row: T) => boolean  destaca a linha marcada (seleção em lote fica na página).
 *
 * Colunas:
 *   const col = dataTableColumns<Perfil>();
 *   const columns = col.columns([
 *     col.accessor("nome", { header: "Nome", cell: (c) => <strong>{c.getValue()}</strong> }),
 *     col.accessor("status", { header: "Status", meta: { className: "hidden md:table-cell" } }),
 *     col.display({ id: "acoes", header: "", cell: (c) => <Link to={…}>Editar</Link> }),
 *   ]);
 *   - `header` string + coluna com accessor ⇒ cabeçalho ordenável automático (SortableHeader).
 *     Para não ordenar: enableSorting: false. Para não entrar na busca: enableGlobalFilter: false.
 *   - meta.className / meta.headerClassName: classes extras nas <td>/<th> dessa coluna.
 *   - Defina `columns` fora do componente ou com useMemo (referência estável).
 *
 * Visual: cabeçalho em caixa alta pequena e cinza, linhas altas com separador fino; a tabela rola
 * na horizontal dentro do próprio contêiner (a página nunca rola de lado). Coloque dentro de um
 * HeaderCard ou Card.
 */
import { useTable, type RowData } from "@tanstack/react-table";
import { Search } from "lucide-react";
import { cloneElement, isValidElement, useState, type ReactElement, type ReactNode } from "react";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { CursorPagination } from "./CursorPagination";
import { ClientPagination, LoadMorePagination } from "./DataTablePagination";
import { ServerPagination, type ServerPaginationProps } from "./ServerPagination";
import { dataTableFeatures, type DataTableColumnDef } from "./features";
import { FilterBar, type FilterBarProps } from "./FilterBar";
import { SortableHeader } from "./SortableHeader";

export interface DataTableExternalPagination {
  hasMore: boolean;
  onLoadMore: () => void;
  loadingMore?: boolean;
  // Total do filtro no servidor (modo `manual`).
  total?: number;
}

// Paginação numerada no servidor (spec 024): as linhas recebidas são a página inteira.
export interface DataTableServerPagination extends ServerPaginationProps {
  modo: "servidor";
}

export interface DataTableProps<T extends RowData> {
  columns: DataTableColumnDef<T>[];
  data: T[] | undefined;
  loading?: boolean;
  getRowId?: (row: T) => string;
  search?: boolean | { placeholder?: string; label?: string };
  toolbar?: ReactNode;
  initialSorting?: { id: string; desc: boolean }[];
  initialPageSize?: 10 | 25 | 50;
  emptyMessage?: ReactNode;
  empty?: ReactNode;
  label?: string;
  pagination?: DataTableExternalPagination | DataTableServerPagination;
  manual?: boolean;
  // Linha marcada (seleção em lote da página): recebe data-state="selected".
  isRowSelected?: (row: T) => boolean;
}

const EMPTY: never[] = [];
const SKELETON_ROWS = 5;

export function DataTable<T extends RowData>({
  columns,
  data,
  loading,
  getRowId,
  search,
  toolbar,
  initialSorting,
  initialPageSize = 10,
  emptyMessage = "Nenhum resultado",
  empty,
  label,
  pagination,
  manual,
  isRowSelected,
}: DataTableProps<T>) {
  const external = pagination !== undefined || Boolean(manual);
  const [initialState] = useState(() => ({
    sorting: initialSorting ?? [],
    pagination: { pageIndex: 0, pageSize: initialPageSize },
  }));

  const table = useTable({
    features: dataTableFeatures,
    columns,
    data: data ?? (EMPTY as T[]),
    getRowId: getRowId ? (row: T) => getRowId(row) : undefined,
    initialState,
    globalFilterFn: "includesString",
    // modo externo: a tabela mostra tudo o que já veio (o "Carregar mais" traz o resto)
    manualPagination: external,
    // modo manual (spec 014): o servidor filtra, ordena e pagina
    ...(manual ? { manualSorting: true, manualFiltering: true, enableSorting: false } : {}),
  });

  const searchOptions = typeof search === "object" ? search : {};
  // com a <FilterBar> no toolbar, a busca é a dela (spec 024)
  const comFilterBar = isValidElement(toolbar) && toolbar.type === FilterBar;
  const buscaPropria = Boolean(search) && !manual && !comFilterBar;
  // dados locais (Usuários, Importação): a "Buscar" da barra vira o filtro global da tabela
  const barra = toolbar as ReactElement<FilterBarProps>;
  const toolbarFinal =
    comFilterBar && search && !manual && !barra.props.busca
      ? cloneElement(barra, {
          busca: {
            valor: table.state.globalFilter ?? "",
            onChange: (v: string) => table.setGlobalFilter(v),
            placeholder: searchOptions.placeholder,
            rotulo: searchOptions.label,
          },
        })
      : toolbar;
  const rows = table.getRowModel().rows;
  const columnCount = table.getAllLeafColumns().length;

  return (
    <div className="min-w-0">
      {(buscaPropria || toolbar) && (
        <div className="flex flex-wrap items-center gap-3 pb-3">
          {buscaPropria && (
            <div className="relative w-full sm:w-64">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                type="search"
                aria-label={searchOptions.label ?? "Filtrar"}
                placeholder={searchOptions.placeholder ?? "Filtrar"}
                value={table.state.globalFilter ?? ""}
                onChange={(e) => table.setGlobalFilter(e.target.value)}
                className="pl-9"
              />
            </div>
          )}
          {toolbarFinal}
        </div>
      )}

      <Table aria-label={label} aria-busy={loading || undefined}>
        <TableHeader>
          {table.getHeaderGroups().map((group) => (
            <TableRow key={group.id} className="hover:bg-transparent">
              {group.headers.map((header) => {
                const { column } = header;
                const sorted = column.getIsSorted();
                const headerDef = column.columnDef.header;
                return (
                  <TableHead
                    key={header.id}
                    aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined}
                    className={cn(
                      "h-10 text-[0.68rem] font-semibold tracking-wider text-muted-foreground uppercase",
                      column.columnDef.meta?.headerClassName ?? column.columnDef.meta?.className,
                    )}
                  >
                    {header.isPlaceholder ? null : typeof headerDef === "string" && column.getCanSort() ? (
                      <SortableHeader column={column} title={headerDef} />
                    ) : (
                      <table.FlexRender header={header} />
                    )}
                  </TableHead>
                );
              })}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {loading ? (
            Array.from({ length: SKELETON_ROWS }, (_, i) => (
              <TableRow key={`skeleton-${i}`} className="hover:bg-transparent">
                {Array.from({ length: columnCount }, (_, j) => (
                  <TableCell key={j} className="py-4">
                    <Skeleton className="h-4 w-full max-w-40" />
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : rows.length === 0 ? (
            <TableRow className="hover:bg-transparent">
              {empty ? (
                <TableCell colSpan={columnCount} className="whitespace-normal">
                  {empty}
                </TableCell>
              ) : (
                <TableCell colSpan={columnCount} className="py-10 text-center text-muted-foreground">
                  {emptyMessage}
                </TableCell>
              )}
            </TableRow>
          ) : (
            rows.map((row) => (
              <TableRow key={row.id} data-state={isRowSelected?.(row.original) ? "selected" : undefined}>
                {row.getAllCells().map((cell) => (
                  <TableCell key={cell.id} className={cn("py-3.5", cell.column.columnDef.meta?.className)}>
                    <table.FlexRender cell={cell} />
                  </TableCell>
                ))}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      {!loading &&
        (pagination && "modo" in pagination ? (
          <ServerPagination
            total={pagination.total}
            pagina={pagination.pagina}
            tamanho={pagination.tamanho}
            onPagina={pagination.onPagina}
            onTamanho={pagination.onTamanho}
          />
        ) : manual ? (
          pagination && (
            <CursorPagination
              loaded={table.getRowCount()}
              total={pagination.total}
              hasMore={pagination.hasMore}
              onLoadMore={pagination.onLoadMore}
              loadingMore={pagination.loadingMore}
            />
          )
        ) : pagination ? (
          <LoadMorePagination
            loaded={table.getRowCount()}
            hasMore={pagination.hasMore}
            onLoadMore={pagination.onLoadMore}
            loadingMore={pagination.loadingMore}
          />
        ) : (
          <ClientPagination table={table} />
        ))}
    </div>
  );
}
