import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { formatoLabel, layoutLabel, legendaLabel, type PadroesCorte } from "@/lib/envios";

// Campos da configuração do corte (FR-008): usados pela aba "Padrões de corte" do perfil e pelo
// diálogo "Gerar cortes" (padrões do perfil, ajustáveis geração a geração). O gancho automático do
// OpenShorts não é campo: fica sempre desligado (quem queima o gancho é o SociMan, com o kit).
export interface ConfigValues {
  clipMinS: number;
  clipMaxS: number;
  quantidade: number | null;
  layout: PadroesCorte["layout"];
  formato: PadroesCorte["formato"];
  legenda: PadroesCorte["legenda"];
  marcaAutomatica: boolean;
}

export function configFrom(p: ConfigValues): ConfigValues {
  return {
    clipMinS: p.clipMinS,
    clipMaxS: p.clipMaxS,
    quantidade: p.quantidade ?? null,
    layout: p.layout,
    formato: p.formato,
    legenda: p.legenda,
    marcaAutomatica: p.marcaAutomatica,
  };
}

const toInt = (v: string) => (v.trim() === "" ? Number.NaN : Number(v));

export function ConfigCampos({
  value,
  onChange,
  errors,
  disabled,
}: {
  value: ConfigValues;
  onChange: (next: ConfigValues) => void;
  errors: Record<string, string>;
  disabled?: boolean;
}) {
  const set = <K extends keyof ConfigValues>(key: K, v: ConfigValues[K]) => onChange({ ...value, [key]: v });
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <Field label="Duração mínima (s)" error={errors.clipMinS}>
        {({ id, describedBy, invalid }) => (
          <Input
            id={id}
            type="number"
            inputMode="numeric"
            min={5}
            max={175}
            disabled={disabled}
            value={Number.isNaN(value.clipMinS) ? "" : value.clipMinS}
            aria-invalid={invalid}
            aria-describedby={describedBy}
            onChange={(e) => set("clipMinS", toInt(e.target.value))}
          />
        )}
      </Field>
      <Field label="Duração máxima (s)" error={errors.clipMaxS}>
        {({ id, describedBy, invalid }) => (
          <Input
            id={id}
            type="number"
            inputMode="numeric"
            min={10}
            max={180}
            disabled={disabled}
            value={Number.isNaN(value.clipMaxS) ? "" : value.clipMaxS}
            aria-invalid={invalid}
            aria-describedby={describedBy}
            onChange={(e) => set("clipMaxS", toInt(e.target.value))}
          />
        )}
      </Field>
      <Field label="Quantidade de clipes" error={errors.quantidade} hint="Vazio: o SociShorts decide.">
        {({ id, describedBy, invalid }) => (
          <Input
            id={id}
            type="number"
            inputMode="numeric"
            min={1}
            max={15}
            placeholder="Automática"
            disabled={disabled}
            value={value.quantidade ?? ""}
            aria-invalid={invalid}
            aria-describedby={describedBy}
            onChange={(e) => set("quantidade", e.target.value.trim() === "" ? null : Number(e.target.value))}
          />
        )}
      </Field>
      <Field label="Layout">
        {({ id }) => (
          <NativeSelect id={id} disabled={disabled} value={value.layout} onChange={(e) => set("layout", e.target.value as ConfigValues["layout"])}>
            {Object.entries(layoutLabel).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      <Field label="Formato">
        {({ id }) => (
          <NativeSelect id={id} disabled={disabled} value={value.formato} onChange={(e) => set("formato", e.target.value as ConfigValues["formato"])}>
            {Object.entries(formatoLabel).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      <Field label="Legenda" hint={value.legenda === "kit" ? "Refeita com o estilo do kit (+30 a 60 s por clipe)." : undefined}>
        {({ id, describedBy }) => (
          <NativeSelect id={id} aria-describedby={describedBy} disabled={disabled} value={value.legenda} onChange={(e) => set("legenda", e.target.value as ConfigValues["legenda"])}>
            {Object.entries(legendaLabel).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      <label className="flex items-start gap-2 text-sm sm:col-span-3">
        <input
          type="checkbox"
          className="mt-0.5 size-4 accent-primary"
          disabled={disabled}
          checked={value.marcaAutomatica}
          onChange={(e) => set("marcaAutomatica", e.target.checked)}
        />
        <span>
          Aplicar a marca do kit sozinho quando os clipes chegarem
          <span className="block text-xs text-muted-foreground">Desligado: os clipes chegam "Em revisão" e você escolhe quais marcar.</span>
        </span>
      </label>
    </div>
  );
}
