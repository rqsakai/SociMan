import { Search } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Input } from "@/components/ui/input";
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

// Filtros da biblioteca (FR-005, R8): chips de tipo (OU), chips de tag com contagem (E), busca por
// nome ou tag com debounce de 250 ms e "Mostrar arquivados".
export function AssetFilters({
  value,
  tags,
  onChange,
}: {
  value: AssetListFilters;
  tags: TagCount[];
  onChange: (next: AssetListFilters) => void;
}) {
  const [q, setQ] = useState(value.q);

  useEffect(() => {
    if (q === value.q) return;
    const t = window.setTimeout(() => onChange({ ...value, q }), 250);
    return () => window.clearTimeout(t);
  }, [q, value, onChange]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-48 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            type="search"
            aria-label="Buscar por nome ou tag"
            placeholder="Buscar por nome ou tag"
            className="pl-8"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2">
          <Switch
            id="assets-arquivados"
            checked={value.archived === "all"}
            onCheckedChange={(on) => onChange({ ...value, archived: on ? "all" : "false" })}
          />
          <Label htmlFor="assets-arquivados">Mostrar arquivados</Label>
        </div>
      </div>
      <div role="group" aria-label="Filtrar por tipo" className="flex flex-wrap gap-1.5">
        {TIPOS.map((tipo: AssetTipo) => (
          <Chip key={tipo} pressed={value.tipo.includes(tipo)} onClick={() => onChange({ ...value, tipo: toggle(value.tipo, tipo) })}>
            {tipoLabel[tipo]}
          </Chip>
        ))}
      </div>
      {tags.length > 0 && (
        <div role="group" aria-label="Filtrar por tag" className="flex flex-wrap gap-1.5">
          {tags.map((t) => (
            <Chip key={t.tag} pressed={value.tag.includes(t.tag)} onClick={() => onChange({ ...value, tag: toggle(value.tag, t.tag) })}>
              #{t.tag}
              <span className="opacity-70">{t.count}</span>
            </Chip>
          ))}
        </div>
      )}
    </div>
  );
}
