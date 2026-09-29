import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import type { Uso } from "../../lib/assets";

// "Onde é usado" (FR-005, R5): o kit bloqueia o arquivamento; os cortes só informam (Q1 = A).
export function UsosList({ usos, empty = "Não é usado em nenhum lugar." }: { usos: Uso[]; empty?: string }) {
  if (usos.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="space-y-1.5" aria-label="Onde é usado">
      {usos.map((uso, i) => (
        <li key={`${uso.origem}-${uso.campo ?? ""}-${uso.fileId}-${i}`} className="flex flex-wrap items-center gap-2 text-sm">
          {uso.href ? (
            <Link to={uso.href} className="font-medium hover:underline">
              {uso.rotulo}
            </Link>
          ) : (
            <span className="font-medium">{uso.rotulo}</span>
          )}
          {uso.bloqueia ? (
            <Badge variant="outline">impede arquivar</Badge>
          ) : (
            <Badge variant="secondary">só informativo</Badge>
          )}
        </li>
      ))}
    </ul>
  );
}

// Lista curta para mensagens de erro: "Card final (kit v3), Marca d'água (kit v3)".
export const usosText = (usos: Uso[]) => usos.map((u) => u.rotulo).join(", ");
