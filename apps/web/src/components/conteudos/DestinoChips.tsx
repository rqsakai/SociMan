/*
 * Chips por conta de destino na lista de Conteúdos (spec 014, US1): ícone da rede, @, estado
 * efetivo e a data (fuso da agência). Cada chip abre o detalhe já na aba daquela conta.
 * Sem destino: "Sem conta".
 */
import type { DestinoResumo } from "@sociman/contract";
import { TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { PlatformIcon } from "@/components/PlatformIcon";
import { estadoEfetivoLabel, estadoEfetivoTone } from "@/lib/conteudos";
import { contaPlatformText } from "@/lib/perfis";
import { formatDateTime } from "@/lib/tz";
import { cn } from "@/lib/utils";

export function DestinoChips({ conteudoId, destinos }: { conteudoId: string; destinos: DestinoResumo[] }) {
  if (destinos.length === 0) {
    return <span className="rounded-full border border-dashed px-2 py-0.5 text-xs text-muted-foreground">Sem conta</span>;
  }
  return (
    <ul className="flex flex-wrap gap-1" aria-label="Contas de destino">
      {destinos.map((d) => {
        const handle = `@${d.conta.handle.replace(/^@/, "")}`;
        const estado = estadoEfetivoLabel[d.estadoEfetivo];
        return (
          <li key={d.id}>
            <Link
              to={`/app/conteudos/${conteudoId}?conta=${d.conta.id}`}
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap hover:opacity-80",
                estadoEfetivoTone[d.estadoEfetivo],
              )}
              title={[contaPlatformText(d.conta), handle, estado, d.motivoAtencao, d.semTextos ? "sem textos" : null].filter(Boolean).join(" · ")}
            >
              <PlatformIcon platform={d.conta.platform} className="size-3" />
              <span>{handle}</span>
              <span aria-hidden="true">·</span>
              <span>{estado}</span>
              {d.plannedAt && <span className="tabular-nums">{formatDateTime(d.plannedAt)}</span>}
              {d.videoMudou && <TriangleAlert className="size-3" aria-label="O vídeo mudou desde a aprovação" />}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
