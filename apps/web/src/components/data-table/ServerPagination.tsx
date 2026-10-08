/*
 * Rodapé de paginação numerada no servidor (spec 024, US6, R7), no visual do <ClientPagination>:
 * "N itens" (o total do filtro), seletor "Itens por página" 10/25/50, "Página X de Y" e botões
 * Anterior/Próxima. Quem busca a página é a tela (offset = (pagina-1)*tamanho). Usado pelo
 * DataTable com pagination={{ modo: "servidor", ... }}.
 *
 * <ServerPagination total={data.total} pagina={2} tamanho={25} onPagina={…} onTamanho={…} />
 */
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useId } from "react";
import { Button } from "@/components/ui/button";
import { PAGE_SIZES } from "./DataTablePagination";

export interface ServerPaginationProps {
  total: number;
  // 1-based
  pagina: number;
  tamanho: number;
  onPagina: (pagina: number) => void;
  // Trocar o tamanho volta para a página 1 (responsabilidade de quem recebe).
  onTamanho: (tamanho: number) => void;
}

export function ServerPagination({ total, pagina, tamanho, onPagina, onTamanho }: ServerPaginationProps) {
  const sizeId = useId();
  const pageCount = Math.max(Math.ceil(total / tamanho), 1);
  // Página além do fim (ex.: o filtro encolheu) ainda mostra "Página X de Y" e deixa voltar.
  const atual = Math.max(pagina, 1);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pt-3 text-sm text-muted-foreground">
      <p aria-live="polite">{total === 1 ? "1 item" : `${total.toLocaleString("pt-BR")} itens`}</p>
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor={sizeId} className="flex items-center gap-2">
          Itens por página
          <select
            id={sizeId}
            value={tamanho}
            onChange={(e) => onTamanho(Number(e.target.value))}
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
          Página {atual} de {pageCount}
        </span>
        <div className="flex gap-1">
          <Button
            variant="outline"
            size="icon-sm"
            aria-label="Página anterior"
            disabled={atual <= 1}
            onClick={() => onPagina(Math.min(atual - 1, pageCount))}
          >
            <ChevronLeft aria-hidden="true" />
          </Button>
          <Button
            variant="outline"
            size="icon-sm"
            aria-label="Próxima página"
            disabled={atual >= pageCount}
            onClick={() => onPagina(atual + 1)}
          >
            <ChevronRight aria-hidden="true" />
          </Button>
        </div>
      </div>
    </div>
  );
}
