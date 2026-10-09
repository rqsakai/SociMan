// Features do TanStack Table v9 usadas pelo DataTable (a v9 registra cada recurso
// explicitamente). Colunas das páginas usam `dataTableColumns<T>()` para ficar com os
// tipos certos. Detalhes de uso no topo de DataTable.tsx.
import {
  columnFilteringFeature,
  createColumnHelper,
  createFilteredRowModel,
  createPaginatedRowModel,
  createSortedRowModel,
  filterFn_includesString,
  globalFilteringFeature,
  metaHelper,
  rowPaginationFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_basic,
  sortFn_datetime,
  sortFn_text,
  tableFeatures,
  type ColumnDef,
  type RowData,
} from "@tanstack/react-table";

// meta por coluna: classes extras na <th> e nas <td> (ex.: "text-right", "hidden md:table-cell")
export interface DataTableColumnMeta {
  className?: string;
  headerClassName?: string;
}

export const dataTableFeatures = tableFeatures({
  columnMeta: metaHelper<DataTableColumnMeta>(),
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { alphanumeric: sortFn_alphanumeric, text: sortFn_text, datetime: sortFn_datetime, basic: sortFn_basic },
  columnFilteringFeature, // pré-requisito do filtro global
  globalFilteringFeature,
  filteredRowModel: createFilteredRowModel(),
  filterFns: { includesString: filterFn_includesString },
  rowPaginationFeature,
  paginatedRowModel: createPaginatedRowModel(),
});

export type DataTableFeatures = typeof dataTableFeatures;

// `any` no TValue: as colunas são heterogêneas (cada uma com o tipo do seu valor)
export type DataTableColumnDef<T extends RowData> = ColumnDef<DataTableFeatures, T, any>;

export function dataTableColumns<T extends RowData>() {
  return createColumnHelper<DataTableFeatures, T>();
}
