/*
 * Rodapé de paginação do DataTable (spec 005, US2). Usado pelo próprio DataTable.
 *
 * Modo cliente (<ClientPagination>): "N itens" (total filtrado), seletor "Por página" 10/25/50,
 *   "Página X de Y" e botões Anterior/Próxima.
 * Modo externo (<LoadMorePagination>): para listas por cursor — "N itens carregados" e o
 *   botão "Carregar mais" enquanto houver mais.
 */
import type { ReactTable, RowData } from "@tanstack/react-table";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { useId } from "react";
import { Button } from "@/components/ui/button";
import type { DataTableFeatures } from "./features";

export const PAGE_SIZES = [10, 25, 50] as const;

function itemCount(n: number) {
  return n === 1 ? "1 item" : `${n} itens`;
}

export function ClientPagination<T extends RowData>({ table }: { table: ReactTable<DataTableFeatures, T> }) {
  const sizeId = useId();
  const { pageIndex, pageSize } = table.state.pagination;
  const total = table.getRowCount();
  const pageCount = Math.max(table.getPageCount(), 1);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pt-3 text-sm text-muted-foreground">
      <p aria-live="polite">{itemCount(total)}</p>
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor={sizeId} className="flex items-center gap-2">
          Por página
          <select
            id={sizeId}
            value={pageSize}
            onChange={(e) => table.setPageSize(Number(e.target.value))}
            className="h-8 rounded-md border border-input bg-card px-2 text-foreground outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <span>
          Página {pageIndex + 1} de {pageCount}
        </span>
        <div className="flex gap-1">
          <Button
            variant="outline"
            size="icon-sm"
            aria-label="Página anterior"
            disabled={!table.getCanPreviousPage()}
            onClick={() => table.previousPage()}
          >
            <ChevronLeft aria-hidden="true" />
          </Button>
          <Button
            variant="outline"
            size="icon-sm"
            aria-label="Próxima página"
            disabled={!table.getCanNextPage()}
            onClick={() => table.nextPage()}
          >
            <ChevronRight aria-hidden="true" />
          </Button>
        </div>
      </div>
    </div>
  );
}

export interface LoadMorePaginationProps {
  loaded: number;
  hasMore: boolean;
  onLoadMore: () => void;
  loadingMore?: boolean;
}

export function LoadMorePagination({ loaded, hasMore, onLoadMore, loadingMore }: LoadMorePaginationProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pt-3 text-sm text-muted-foreground">
      <p aria-live="polite">{loaded === 1 ? "1 item carregado" : `${loaded} itens carregados`}</p>
      {hasMore && (
        <Button variant="outline" size="sm" disabled={loadingMore} aria-busy={loadingMore} onClick={onLoadMore}>
          {loadingMore && <Loader2 className="animate-spin" aria-hidden="true" />}
          Carregar mais
        </Button>
      )}
    </div>
  );
}
