import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

// "Mover para a esquerda/direita" de um card numa lista ordenada (poses e referências, Q3 = A).
// Funciona no toque e no teclado; arrastar (HTML5 nativo) é só um atalho no desktop.
export function ReorderButtons({
  index,
  count,
  name,
  disabled,
  onMove,
}: {
  index: number;
  count: number;
  // Nome do item nos rótulos acessíveis ("Mover piscando para a esquerda").
  name: string;
  disabled?: boolean;
  onMove: (from: number, to: number) => void;
}) {
  return (
    <div className="flex gap-1">
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label={`Mover ${name} para a esquerda`}
        title="Mover para a esquerda"
        disabled={disabled || index === 0}
        onClick={() => onMove(index, index - 1)}
      >
        <ChevronLeft aria-hidden="true" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label={`Mover ${name} para a direita`}
        title="Mover para a direita"
        disabled={disabled || index >= count - 1}
        onClick={() => onMove(index, index + 1)}
      >
        <ChevronRight aria-hidden="true" />
      </Button>
    </div>
  );
}

// Nova ordem de ids depois de mover o item de `from` para `to`.
export function moveItem<T>(list: readonly T[], from: number, to: number): T[] {
  const next = [...list];
  const [item] = next.splice(from, 1);
  if (item !== undefined) next.splice(to, 0, item);
  return next;
}
