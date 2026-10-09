import { Field, NativeSelect } from "@/components/ui/field";
import type { FonteRef, FontOption } from "../../lib/marca";

// Fonte de um token do kit (FR-010): as padrão e as ativas do perfil, em grupos. Uma referência
// que saiu das opções (fonte arquivada depois) continua aparecendo, marcada, para não sumir.
export function FontSelect({
  label,
  value,
  options,
  onChange,
  error,
}: {
  label: string;
  value: FonteRef;
  options: FontOption[];
  onChange: (value: FonteRef) => void;
  error?: string;
}) {
  const padrao = options.filter((o) => o.ref.startsWith("padrao:"));
  const proprias = options.filter((o) => !o.ref.startsWith("padrao:"));
  const missing = !options.some((o) => o.ref === value);
  return (
    <Field label={label} error={error}>
      {({ id, describedBy, invalid }) => (
        <NativeSelect
          id={id}
          aria-invalid={invalid}
          aria-describedby={describedBy}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          {missing && <option value={value}>Fonte indisponível</option>}
          <optgroup label="Padrão">
            {padrao.map((o) => (
              <option key={o.ref} value={o.ref}>
                {o.name}
              </option>
            ))}
          </optgroup>
          {proprias.length > 0 && (
            <optgroup label="Do perfil">
              {proprias.map((o) => (
                <option key={o.ref} value={o.ref}>
                  {o.name}
                </option>
              ))}
            </optgroup>
          )}
        </NativeSelect>
      )}
    </Field>
  );
}
