import { useEffect, useState } from "react";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { HEX_RE, PALETTE_PREFIX, resolveColor, type Cor, type CorRef } from "../../lib/marca";

const CUSTOM = "__custom__";

// Cor de um token do kit: uma cor da paleta (`paleta:<chave>`) ou um hex livre. O <select> nativo
// lista a paleta e "Personalizada"; na personalizada aparecem o seletor de cor e o campo hex.
export function ColorTokenInput({
  label,
  value,
  palette,
  onChange,
  error,
}: {
  label: string;
  value: CorRef;
  palette: Cor[];
  onChange: (value: CorRef) => void;
  error?: string;
}) {
  const fromPalette = value.startsWith(PALETTE_PREFIX);
  const hex = resolveColor(value, palette);
  // O campo hex guarda o que está sendo digitado; só vira token quando é um hex válido.
  const [text, setText] = useState(fromPalette ? "" : value);
  useEffect(() => {
    if (!fromPalette) setText(value);
  }, [value, fromPalette]);

  return (
    <Field label={label} error={error}>
      {({ id, describedBy, invalid }) => (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span
              className="size-9 shrink-0 rounded-md border shadow-xs"
              style={{ backgroundColor: hex }}
              aria-hidden="true"
            />
            <div className="min-w-0 flex-1">
              <NativeSelect
                id={id}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                value={fromPalette ? value : CUSTOM}
                onChange={(e) => onChange(e.target.value === CUSTOM ? hex : e.target.value)}
              >
                {palette.map((c) => (
                  <option key={c.chave} value={`${PALETTE_PREFIX}${c.chave}`}>
                    {c.nome} ({c.valor})
                  </option>
                ))}
                <option value={CUSTOM}>Personalizada</option>
              </NativeSelect>
            </div>
          </div>
          {!fromPalette && (
            <div className="flex items-center gap-2">
              <input
                type="color"
                aria-label={`${label}: seletor`}
                value={HEX_RE.test(text) ? text.toLowerCase() : hex.toLowerCase()}
                onChange={(e) => onChange(e.target.value.toUpperCase())}
                className="h-9 w-12 shrink-0 cursor-pointer rounded-md border bg-transparent p-1"
              />
              <Input
                aria-label={`${label}: hex`}
                value={text}
                maxLength={7}
                spellCheck={false}
                className="font-mono uppercase"
                aria-invalid={!HEX_RE.test(text) || invalid}
                onChange={(e) => {
                  const next = e.target.value.startsWith("#") ? e.target.value : `#${e.target.value}`;
                  setText(next.toUpperCase());
                  if (HEX_RE.test(next)) onChange(next.toUpperCase());
                }}
              />
            </div>
          )}
        </div>
      )}
    </Field>
  );
}
