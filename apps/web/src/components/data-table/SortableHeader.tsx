/*
 * Cabeçalho ordenável (spec 005, US2): botão que alterna a ordem e um ícone com a direção.
 * O DataTable já usa este componente sozinho quando o `header` da coluna é uma string e a
 * coluna é ordenável; use direto só para cabeçalhos customizados:
 *   header: ({ column }) => <SortableHeader column={column} title="Criado em" />
 * O <th> recebe aria-sort do próprio DataTable.
 */
import type { Column, RowData } from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DataTableFeatures } from "./features";

export interface SortableHeaderProps<T extends RowData> {
  // TValue da coluna não importa aqui
  column: Column<DataTableFeatures, T, any>;
  title: string;
  className?: string;
}

export function SortableHeader<T extends RowData>({ column, title, className }: SortableHeaderProps<T>) {
  const sorted = column.getIsSorted();
  const Icon = sorted === "asc" ? ArrowUp : sorted === "desc" ? ArrowDown : ChevronsUpDown;
  return (
    <button
      type="button"
      onClick={column.getToggleSortingHandler()}
      className={cn(
        "-mx-1 inline-flex items-center gap-1 rounded px-1 uppercase hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring",
        sorted && "text-foreground",
        className,
      )}
    >
      {title}
      <Icon className={cn("size-3.5", !sorted && "opacity-50")} aria-hidden="true" />
    </button>
  );
}
