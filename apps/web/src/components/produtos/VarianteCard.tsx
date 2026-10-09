import { Archive, ArchiveRestore, ArrowDown, ArrowUp, TriangleAlert } from "lucide-react";
import { ConfirmButton } from "@/components/ConfirmButton";
import { Button } from "@/components/ui/button";
import { avisoVarianteLabel, type ProdutoVariante } from "@/lib/produtos";
import { SeloLiteral } from "./FichaForm";

// Uma variante (spec 012, T033): a foto (recorte, senão a original), as cores (editadas na ficha),
// os avisos ("flat feito com a ficha anterior", "sem cor"), a ordem e arquivar/restaurar. A API
// recusa arquivar a última ativa e restaurar além de 6 ativas.
export function VarianteCard({
  variante,
  numero,
  total,
  disabled,
  onMover,
  onArquivar,
  onRestaurar,
}: {
  variante: ProdutoVariante;
  // posição de exibição entre as ativas (1..N); arquivada: null
  numero: number | null;
  total: number;
  disabled?: boolean;
  onMover?: (delta: -1 | 1) => void;
  onArquivar?: () => Promise<void>;
  onRestaurar?: () => Promise<void>;
}) {
  const arquivada = Boolean(variante.archivedAt);
  const nome = numero !== null ? `Variante ${numero}` : `Variante arquivada (${variante.corPt ?? "sem cor"})`;
  const foto = variante.recorte ?? variante.original;
  return (
    <li aria-label={nome} data-testid={numero !== null ? `variante-${numero}` : `variante-arquivada-${variante.id}`} className="flex gap-3 rounded-lg border p-3">
      <img src={foto.thumbUrl} alt={nome} loading="lazy" className="size-16 shrink-0 rounded-md border bg-white object-contain" />
      <div className="min-w-0 flex-1 space-y-1.5">
        <p className="text-sm font-semibold">
          {numero !== null ? `${numero}. ` : ""}
          {variante.corPt ?? "Sem cor"}
        </p>
        <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <span lang="en" className="font-mono">
            {variante.corEn ?? "—"}
          </span>
          {variante.corEn && <SeloLiteral />}
        </p>
        {variante.avisos.length > 0 && (
          <ul className="space-y-1" aria-label={`Avisos da ${nome.toLowerCase()}`}>
            {variante.avisos.map((a) => (
              <li key={a} className="flex items-start gap-1.5 text-xs" data-testid={`aviso-${a}`}>
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden="true" />
                <span>{avisoVarianteLabel[a]}</span>
              </li>
            ))}
          </ul>
        )}
        {!disabled && (
          <div className="flex flex-wrap items-center gap-1 pt-1">
            {!arquivada && onMover && numero !== null && (
              <>
                <Button type="button" variant="ghost" size="icon-sm" aria-label={`Subir variante ${numero}`} disabled={numero === 1} onClick={() => onMover(-1)}>
                  <ArrowUp aria-hidden="true" />
                </Button>
                <Button type="button" variant="ghost" size="icon-sm" aria-label={`Descer variante ${numero}`} disabled={numero === total} onClick={() => onMover(1)}>
                  <ArrowDown aria-hidden="true" />
                </Button>
              </>
            )}
            {!arquivada && onArquivar && (
              <ConfirmButton
                label="Arquivar variante"
                icon={Archive}
                size="sm"
                variant="ghost"
                disabled={total <= 1}
                title={`Arquivar a ${nome.toLowerCase()}?`}
                description="A variante sai da folha, da aprovação e dos seletores. As imagens continuam guardadas, e dá para restaurar depois."
                onConfirm={onArquivar}
              />
            )}
            {arquivada && onRestaurar && (
              <ConfirmButton
                label="Restaurar variante"
                icon={ArchiveRestore}
                size="sm"
                variant="ghost"
                title="Restaurar esta variante?"
                description="A variante volta para a folha. Num produto aprovado, ele volta para revisão."
                onConfirm={onRestaurar}
              />
            )}
          </div>
        )}
      </div>
    </li>
  );
}
