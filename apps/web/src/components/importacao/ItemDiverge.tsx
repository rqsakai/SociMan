/*
 * Os dois lados de um item que diverge (spec 013, FR-008): o valor no SociMan e o valor no
 * markdown, campo a campo, lado a lado (empilhados abaixo de 640 px). Textos longos já vêm cortados
 * pela API em 300 caracteres (`cortado: true`).
 */
import { rotuloCampo, valorTexto } from "@/lib/importacao";

const OCULTOS = new Set(["cortado"]);

export function ItemDiverge({ atual, proposto }: { atual?: Record<string, unknown> | null; proposto?: Record<string, unknown> | null }) {
  const a = atual ?? {};
  const p = proposto ?? {};
  const campos = [...new Set([...Object.keys(a), ...Object.keys(p)])].filter((c) => !OCULTOS.has(c));
  if (campos.length === 0) return null;
  return (
    <div className="grid gap-2 text-xs sm:grid-cols-2" data-diverge>
      <div className="min-w-0 rounded-md border p-2" data-lado="sociman">
        <p className="mb-1 font-semibold">No SociMan</p>
        <Campos campos={campos} valores={a} outro={p} />
        {a.cortado === true && <p className="mt-1 text-muted-foreground">(texto cortado)</p>}
      </div>
      <div className="min-w-0 rounded-md border border-dashed p-2" data-lado="markdown">
        <p className="mb-1 font-semibold">No markdown</p>
        <Campos campos={campos} valores={p} outro={a} />
        {p.cortado === true && <p className="mt-1 text-muted-foreground">(texto cortado)</p>}
      </div>
    </div>
  );
}

function Campos({ campos, valores, outro }: { campos: string[]; valores: Record<string, unknown>; outro: Record<string, unknown> }) {
  return (
    <dl className="space-y-1">
      {campos.map((c) => {
        const v = valorTexto(valores[c]);
        const difere = v !== valorTexto(outro[c]);
        return (
          <div key={c} className="min-w-0">
            <dt className="text-muted-foreground">{rotuloCampo(c)}</dt>
            <dd className={difere ? "font-medium break-words whitespace-pre-wrap" : "break-words whitespace-pre-wrap text-muted-foreground"}>{v}</dd>
          </div>
        );
      })}
    </dl>
  );
}
