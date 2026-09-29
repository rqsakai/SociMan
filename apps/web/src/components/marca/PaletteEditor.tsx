import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { colorKey, HEX_RE, kitFieldText, MAX_PALETTE, type Cor } from "../../lib/marca";

// Editor da paleta (1 a 12 cores com nome e hex). A chave de uma cor já salva é estável (renomear
// não quebra as referências `paleta:<chave>`); a de uma cor nova acompanha o nome até o
// salvamento, e `onRekey` avisa para o kit trocar as referências. Tirar uma cor em uso é
// bloqueado aqui, apontando onde ela é usada (a API recusa do mesmo jeito).
export function PaletteEditor({
  palette,
  savedKeys,
  usage,
  onChange,
  onRekey,
  errors,
}: {
  palette: Cor[];
  savedKeys: Set<string>;
  usage: (key: string) => string[];
  onChange: (palette: Cor[]) => void;
  onRekey: (from: string, to: string) => void;
  errors: Record<string, string>;
}) {
  const [blocked, setBlocked] = useState<string | null>(null);

  function update(index: number, patch: Partial<Cor>) {
    const next = palette.map((c, i) => (i === index ? { ...c, ...patch } : c));
    const current = palette[index];
    if (current && patch.nome !== undefined && !savedKeys.has(current.chave)) {
      const others = palette.filter((_, i) => i !== index).map((c) => c.chave);
      const key = colorKey(patch.nome, others);
      if (key !== current.chave) {
        next[index] = { ...next[index]!, chave: key };
        onChange(next);
        onRekey(current.chave, key);
        return;
      }
    }
    onChange(next);
  }

  function add() {
    const taken = palette.map((c) => c.chave);
    const nome = "Nova cor";
    onChange([...palette, { chave: colorKey(nome, taken), nome, valor: "#FF5FA2" }]);
  }

  function remove(index: number) {
    const cor = palette[index];
    if (!cor) return;
    const used = usage(cor.chave);
    if (used.length > 0) {
      setBlocked(`"${cor.nome}" está em uso (${used.map(kitFieldText).join(", ")}); troque antes de tirar da paleta.`);
      return;
    }
    setBlocked(null);
    onChange(palette.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-3">
      <ul className="space-y-2" aria-label="Cores da paleta">
        {palette.map((cor, index) => {
          const nameError = errors[`palette.${index}.nome`];
          const valueError = errors[`palette.${index}.valor`] ?? (HEX_RE.test(cor.valor) ? undefined : "Use #RRGGBB");
          return (
            <li key={index} className="flex flex-wrap items-start gap-2">
              <input
                type="color"
                aria-label={`Cor ${index + 1}: seletor`}
                value={HEX_RE.test(cor.valor) ? cor.valor.toLowerCase() : "#808080"}
                onChange={(e) => update(index, { valor: e.target.value.toUpperCase() })}
                className="h-9 w-12 shrink-0 cursor-pointer rounded-md border bg-transparent p-1"
              />
              <div className="min-w-40 flex-1">
                <Input
                  aria-label={`Cor ${index + 1}: nome`}
                  value={cor.nome}
                  maxLength={40}
                  aria-invalid={Boolean(nameError) || cor.nome.trim() === ""}
                  onChange={(e) => update(index, { nome: e.target.value })}
                />
                {nameError && <p className="mt-1 text-xs text-destructive">{nameError}</p>}
              </div>
              <div className="w-28">
                <Input
                  aria-label={`Cor ${index + 1}: hex`}
                  value={cor.valor}
                  maxLength={7}
                  spellCheck={false}
                  className="font-mono uppercase"
                  aria-invalid={Boolean(valueError)}
                  onChange={(e) => {
                    const v = e.target.value.startsWith("#") ? e.target.value : `#${e.target.value}`;
                    update(index, { valor: v.toUpperCase() });
                  }}
                />
                {valueError && <p className="mt-1 text-xs text-destructive">{valueError}</p>}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Remover ${cor.nome || `cor ${index + 1}`}`}
                disabled={palette.length <= 1}
                onClick={() => remove(index)}
              >
                <Trash2 aria-hidden="true" />
              </Button>
            </li>
          );
        })}
      </ul>
      {blocked && (
        <p role="alert" className="text-sm text-destructive">
          {blocked}
        </p>
      )}
      {errors.palette && (
        <p role="alert" className="text-sm text-destructive">
          {errors.palette}
        </p>
      )}
      <Button type="button" variant="outline" size="sm" disabled={palette.length >= MAX_PALETTE} onClick={add}>
        <Plus aria-hidden="true" />
        Adicionar cor
      </Button>
      <p className="text-xs text-muted-foreground">Até {MAX_PALETTE} cores. As cores da paleta aparecem nos seletores de cor do kit.</p>
    </div>
  );
}
