import { Loader2 } from "lucide-react";
import { Field, NativeSelect } from "@/components/ui/field";
import { Switch } from "@/components/ui/switch";

export type PortaoId = "texto" | "narracao" | "keyframes" | "clipes" | "final";
export type ModoRoteiro = "revisar" | "automatico";
export type PortoesValor = Record<PortaoId, boolean>;

export const PORTOES: { id: PortaoId; rotulo: string; descricao: string }[] = [
  { id: "texto", rotulo: "Texto", descricao: "Parar para revisar as frases e as cenas" },
  { id: "narracao", rotulo: "Narração", descricao: "Parar para ouvir a narração" },
  { id: "keyframes", rotulo: "Keyframes", descricao: "Parar para escolher o keyframe de cada cena" },
  { id: "clipes", rotulo: "Clipes", descricao: "Parar para assistir aos clipes" },
  { id: "final", rotulo: "Final", descricao: "Parar para assistir à prévia antes do acabamento HD" },
];

// Os 5 portões e o modo (spec 011, US6, T048): no topo do roteiro e no padrão do perfil. Em `revisar`,
// o roteiro para nos portões ligados; em `automatico`, não para em nenhum e escolhe a opção 1 (com o
// autor "sistema (automático)"). Desligar o portão em que o roteiro está parado equivale a aprovar.
export function Portoes({
  modo,
  portoes,
  onChange,
  disabled,
  salvando,
  paradoEm,
}: {
  modo: ModoRoteiro;
  portoes: PortoesValor;
  onChange: (v: { modo: ModoRoteiro; portoes: PortoesValor }) => void;
  disabled?: boolean;
  salvando?: boolean;
  // o portão em que o roteiro está parado agora (desligar = aprovar)
  paradoEm?: PortaoId | null;
}) {
  const automatico = modo === "automatico";
  return (
    <div className="space-y-3" data-testid="portoes">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Modo" className="w-full sm:w-56" hint={automatico ? "Não para em nenhum portão; escolhe a opção 1 sozinho." : "Para nos portões ligados."}>
          {({ id, describedBy }) => (
            <NativeSelect
              id={id}
              value={modo}
              disabled={disabled}
              aria-describedby={describedBy}
              data-testid="modo-roteiro"
              onChange={(e) => onChange({ modo: e.target.value as ModoRoteiro, portoes })}
            >
              <option value="revisar">Revisar</option>
              <option value="automatico">Automático</option>
            </NativeSelect>
          )}
        </Field>
        {salvando && <Loader2 className="mb-2.5 size-4 animate-spin" aria-hidden="true" />}
      </div>
      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5" aria-label="Portões">
        {PORTOES.map((p) => (
          <li key={p.id} className="flex items-start gap-2 rounded-lg border p-2.5" data-testid={`portao-${p.id}`}>
            <Switch
              checked={portoes[p.id]}
              disabled={disabled || automatico}
              aria-label={`Portão ${p.rotulo}`}
              onCheckedChange={(on) => onChange({ modo, portoes: { ...portoes, [p.id]: on } })}
              className="mt-0.5"
            />
            <span className="min-w-0 text-sm">
              <span className="block font-medium">{p.rotulo}</span>
              <span className="block text-xs text-muted-foreground">
                {paradoEm === p.id && portoes[p.id] ? "Parado aqui: desligar aprova esta etapa." : p.descricao}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
