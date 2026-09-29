import { useEffect, useState } from "react";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

// Campo numérico de um token do kit. Guarda o texto digitado (vazio, "0," no meio da digitação)
// e só repassa quando é número; vírgula decimal vale.
export function NumberField({
  label,
  value,
  min,
  max,
  step = 1,
  hint,
  onChange,
  error,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  hint?: string;
  onChange: (value: number) => void;
  error?: string;
}) {
  const [text, setText] = useState(String(value));
  useEffect(() => {
    setText((prev) => (Number(prev.replace(",", ".")) === value ? prev : String(value)));
  }, [value]);

  return (
    <Field label={label} error={error} hint={hint ?? `De ${min} a ${max}`}>
      {({ id, describedBy, invalid }) => (
        <Input
          id={id}
          type="number"
          inputMode="decimal"
          min={min}
          max={max}
          step={step}
          value={text}
          aria-invalid={invalid}
          aria-describedby={describedBy}
          onChange={(e) => {
            setText(e.target.value);
            const n = Number(e.target.value.replace(",", "."));
            onChange(e.target.value.trim() === "" ? Number.NaN : n);
          }}
        />
      )}
    </Field>
  );
}
