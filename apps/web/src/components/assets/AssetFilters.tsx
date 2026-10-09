import type { ReactNode } from "react";
import { FilterBar, type FiltroAtivo } from "@/components/data-table";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { TIPOS, tipoLabel, type AssetListFilters, type AssetTipo, type TagCount } from "../../lib/assets";

function Chip({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "inline-flex h-7 items-center gap-1 rounded-full border px-3 text-xs font-medium transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
        pressed ? "border-primary bg-primary text-primary-foreground" : "bg-background hover:bg-accent",
      )}
    >
      {children}
    </button>
  );
}

const toggle = <T,>(list: T[], item: T) => (list.includes(item) ? list.filter((x) => x !== item) : [...list, item]);

// Filtros da biblioteca (FR-005, R8) na barra única da spec 024: busca por nome ou tag (debounce da
// barra), "Mostrar arquivados" à vista e, em "Mais filtros", os chips de tipo (OU) e de tag com
// contagem (E). Cada tipo ou tag escolhido vira uma etiqueta removível.
export function AssetFilters({
  value,
  tags,
  onChange,
  onLimpar,
}: {
  value: AssetListFilters;
  tags: TagCount[];
  onChange: (patch: Partial<AssetListFilters>) => void;
  onLimpar: () => void;
}) {
  const ativos: FiltroAtivo[] = [
    ...value.tipo.map((tipo) => ({
      chave: `tipo:${tipo}`,
      rotulo: "Tipo",
      valor: tipoLabel[tipo],
      limpar: () => onChange({ tipo: value.tipo.filter((t) => t !== tipo) }),
      mais: true,
    })),
    ...value.tag.map((tag) => ({
      chave: `tag:${tag}`,
      rotulo: "Tag",
      valor: `#${tag}`,
      limpar: () => onChange({ tag: value.tag.filter((t) => t !== tag) }),
      mais: true,
    })),
    ...(value.archived === "all"
      ? [{ chave: "arquivados", rotulo: "Arquivados", valor: "mostrando", limpar: () => onChange({ archived: "false" }) }]
      : []),
  ];

  return (
    <FilterBar
      busca={{ valor: value.q, onChange: (q) => onChange({ q }), rotulo: "Buscar por nome ou tag" }}
      principais={
        <div className="flex h-9 items-center gap-2">
          <Switch
            id="assets-arquivados"
            checked={value.archived === "all"}
            onCheckedChange={(on) => onChange({ archived: on ? "all" : "false" })}
          />
          <Label htmlFor="assets-arquivados">Mostrar arquivados</Label>
        </div>
      }
      mais={
        <>
          <div className="space-y-2">
            <p className="text-sm font-medium">Tipo</p>
            <div role="group" aria-label="Filtrar por tipo" className="flex flex-wrap gap-1.5">
              {TIPOS.map((tipo: AssetTipo) => (
                <Chip key={tipo} pressed={value.tipo.includes(tipo)} onClick={() => onChange({ tipo: toggle(value.tipo, tipo) })}>
                  {tipoLabel[tipo]}
                </Chip>
              ))}
            </div>
          </div>
          {tags.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Tag</p>
              <div role="group" aria-label="Filtrar por tag" className="flex flex-wrap gap-1.5">
                {tags.map((t) => (
                  <Chip key={t.tag} pressed={value.tag.includes(t.tag)} onClick={() => onChange({ tag: toggle(value.tag, t.tag) })}>
                    #{t.tag}
                    <span className="opacity-70">{t.count}</span>
                  </Chip>
                ))}
              </div>
            </div>
          )}
        </>
      }
      ativos={ativos}
      onLimpar={onLimpar}
    />
  );
}
