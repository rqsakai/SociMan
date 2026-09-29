import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { CopyButton } from "./CopyButton";

export const PROMPT_MAX = 2000;

export interface PromptFields {
  prompt: string;
  voiceTone: string;
  imageRules: string;
}

// Campos de texto do avatar (FR-002, FR-009) e do cenário (FR-003, só o prompt). O botão de copiar
// usa o texto salvo (`savedPrompt`), exatamente como está no banco, sem trim.
export function AvatarCampos({
  tipo,
  value,
  savedPrompt,
  disabled,
  onChange,
}: {
  tipo: "avatar" | "cenario";
  value: PromptFields;
  savedPrompt: string | null;
  disabled?: boolean;
  onChange: (next: PromptFields) => void;
}) {
  const avatar = tipo === "avatar";
  const over = value.prompt.length > PROMPT_MAX;
  const copyLabel = avatar ? "Copiar descrição para prompt" : "Copiar prompt";
  return (
    <div className="space-y-4">
      <Field
        label={avatar ? "Descrição para prompts" : "Prompt do ambiente"}
        error={over ? `Até ${PROMPT_MAX.toLocaleString("pt-BR")} caracteres` : undefined}
        hint={
          <span className="flex flex-wrap justify-between gap-2">
            <span>
              {avatar
                ? "Texto fixo, usado com as mesmas palavras em todas as gerações. É copiado exatamente como foi salvo."
                : 'Ex.: "1950s kitchen with mint-green countertops…". É copiado exatamente como foi salvo.'}
            </span>
            <span aria-live="polite" className={over ? "text-destructive" : undefined}>
              {value.prompt.length.toLocaleString("pt-BR")}/{PROMPT_MAX.toLocaleString("pt-BR")}
            </span>
          </span>
        }
      >
        {({ id, describedBy, invalid }) => (
          <Textarea
            id={id}
            rows={6}
            value={value.prompt}
            disabled={disabled}
            aria-invalid={invalid}
            aria-describedby={describedBy}
            className="font-mono text-sm"
            onChange={(e) => onChange({ ...value, prompt: e.target.value })}
          />
        )}
      </Field>
      <CopyButton text={savedPrompt ?? ""} label={copyLabel} disabled={!savedPrompt} />
      {avatar && (
        <>
          <Field label="Tom de voz" error={value.voiceTone.length > 500 ? "Até 500 caracteres" : undefined}>
            {({ id, describedBy, invalid }) => (
              <Textarea
                id={id}
                rows={2}
                value={value.voiceTone}
                disabled={disabled}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => onChange({ ...value, voiceTone: e.target.value })}
              />
            )}
          </Field>
          <Field label="Regras de imagem" error={value.imageRules.length > PROMPT_MAX ? `Até ${PROMPT_MAX.toLocaleString("pt-BR")} caracteres` : undefined}>
            {({ id, describedBy, invalid }) => (
              <Textarea
                id={id}
                rows={4}
                value={value.imageRules}
                disabled={disabled}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => onChange({ ...value, imageRules: e.target.value })}
              />
            )}
          </Field>
        </>
      )}
    </div>
  );
}
