import { Field, NativeSelect } from "@/components/ui/field";
import { SEM_PERFIL_BASE_TEXTO, usePerfisTodos } from "@/lib/estudio";

// "Perfil base" de um item ou de uma geração (spec 029, T025; FR-005/FR-008): os perfis ativos e
// "Nenhum". Vazio, a geração usa só as regras do tipo, sem o guia de comunicação nem as proibidas.
// O perfil arquivado já escolhido continua na lista (marcado), mas a geração com ele é recusada.
export function PerfilBaseField({
  value,
  onChange,
  label = "Perfil base",
  hint,
  disabled,
  className,
}: {
  value: string | null;
  onChange: (perfilId: string | null) => void;
  label?: string;
  hint?: string;
  disabled?: boolean;
  className?: string;
}) {
  const perfis = usePerfisTodos();
  const lista = (perfis.data ?? []).filter((p) => !p.archived || p.id === value);
  return (
    <Field label={label} className={className} hint={value ? hint : SEM_PERFIL_BASE_TEXTO}>
      {({ id, describedBy }) => (
        <NativeSelect
          id={id}
          value={value ?? ""}
          disabled={disabled}
          aria-describedby={describedBy}
          data-testid="perfil-base"
          onChange={(e) => onChange(e.target.value || null)}
        >
          <option value="">Nenhum</option>
          {value && !lista.some((p) => p.id === value) && <option value={value}>Perfil escolhido</option>}
          {lista.map((p) => (
            <option key={p.id} value={p.id}>
              {p.archived ? `${p.name} (arquivado)` : p.name}
            </option>
          ))}
        </NativeSelect>
      )}
    </Field>
  );
}

// "Perfil base desta geração" (029 FR-008): o padrão é o perfil base do item; trocar vale só para este
// pedido (o item continua com o dele).
export function PerfilBaseGeracao({ value, onChange, disabled }: { value: string | null; onChange: (perfilId: string | null) => void; disabled?: boolean }) {
  return (
    <PerfilBaseField
      label="Perfil base desta geração"
      value={value}
      onChange={onChange}
      disabled={disabled}
      className="sm:max-w-sm"
      hint="O guia de comunicação e as palavras proibidas deste perfil entram na geração. Trocar aqui vale só para este pedido."
    />
  );
}
