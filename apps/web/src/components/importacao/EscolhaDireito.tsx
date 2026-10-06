/*
 * Direito de um canal-fonte na prévia (spec 013, US3; FR-014/FR-015; princípio II). Mostra o status
 * do markdown e o `<select>` dos 4 status do SociMan. Canal novo: o padrão é o proposto pela API
 * (`autorizado` → `sem_acordo`, trocável para `parceiro`). Canal existente que diverge: o direito
 * só muda com "Usar o markdown" e este select.
 */
import { useId } from "react";
import { NativeSelect } from "@/components/ui/field";
import { DIREITOS, direitoLabel, type Direito } from "@/lib/importacao";

export function EscolhaDireito({
  valor,
  statusMarkdown,
  rotulo,
  disabled,
  onChange,
}: {
  valor: Direito;
  statusMarkdown?: string | null;
  rotulo: string;
  disabled?: boolean;
  onChange: (d: Direito) => void;
}) {
  const id = useId();
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="sr-only">
        {rotulo}
      </label>
      <NativeSelect id={id} value={valor} disabled={disabled} onChange={(e) => onChange(e.target.value as Direito)} className="min-w-40">
        {DIREITOS.map((d) => (
          <option key={d} value={d}>
            {direitoLabel[d]}
          </option>
        ))}
      </NativeSelect>
      {statusMarkdown && (
        <p className="text-xs text-muted-foreground">
          No markdown: <span className="font-medium">{statusMarkdown}</span>
          {statusMarkdown === "autorizado" && " (risco aceito pelo dono, sem acordo; troque para Parceiro se houver acordo)"}
        </p>
      )}
    </div>
  );
}
