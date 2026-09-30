/*
 * Rodapé de listas paginadas por cursor no servidor (spec 014, R10): "N de T itens" e o botão
 * "Carregar mais" enquanto houver `nextCursor`. Usado pelo DataTable no modo `manual`.
 *
 * <CursorPagination loaded={rows.length} total={total} hasMore={Boolean(nextCursor)} onLoadMore={…} />
 */
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface CursorPaginationProps {
  loaded: number;
  // Total do filtro (o COUNT do servidor, sem o cursor); sem ele, só "N itens carregados".
  total?: number;
  hasMore: boolean;
  onLoadMore: () => void;
  loadingMore?: boolean;
}

export function CursorPagination({ loaded, total, hasMore, onLoadMore, loadingMore }: CursorPaginationProps) {
  const text =
    total === undefined
      ? loaded === 1
        ? "1 item carregado"
        : `${loaded} itens carregados`
      : `${loaded.toLocaleString("pt-BR")} de ${total.toLocaleString("pt-BR")} ${total === 1 ? "item" : "itens"}`;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pt-3 text-sm text-muted-foreground">
      <p aria-live="polite">{text}</p>
      {hasMore && (
        <Button variant="outline" size="sm" disabled={loadingMore} aria-busy={loadingMore} onClick={onLoadMore}>
          {loadingMore && <Loader2 className="animate-spin" aria-hidden="true" />}
          Carregar mais
        </Button>
      )}
    </div>
  );
}
