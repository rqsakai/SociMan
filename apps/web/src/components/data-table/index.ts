// Tabela de dados genérica (spec 005). A API está no comentário do topo de DataTable.tsx.
export {
  DataTable,
  type DataTableExternalPagination,
  type DataTableProps,
  type DataTableServerPagination,
} from "./DataTable";
export { CursorPagination, type CursorPaginationProps } from "./CursorPagination";
export { FilterBar, type FilterBarProps, type FiltroAtivo } from "./FilterBar";
export { PAGE_SIZES } from "./DataTablePagination";
export { ServerPagination, type ServerPaginationProps } from "./ServerPagination";
export { dataTableColumns, type DataTableColumnDef, type DataTableColumnMeta } from "./features";
export { SortableHeader } from "./SortableHeader";
