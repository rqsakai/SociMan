import type { ReactNode } from "react";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import type { IaAlvo, IaOnSave, TipoCampoId } from "@/lib/ia";
import { IaAssist } from "../ia/IaAssist";
import { CopyButton } from "./CopyButton";

export const PROMPT_MAX = 2000;

export interface PromptFields {
  prompt: string;
  voiceTone: string;
  imageRules: string;
}

// "Melhorar com IA" nos textos (spec 008): `onSave(campo)` salva só aquele campo.
export interface AvatarCamposIa {
  perfilId: string;
  alvo: IaAlvo;
  onSave: (campo: keyof PromptFields) => IaOnSave<string>;
  onReload?: () => void;
}

// Campos de texto do avatar (FR-002, FR-009) e do cenário (FR-003, só o prompt). O botão de copiar
// usa o texto salvo (`savedPrompt`), exatamente como está no banco, sem trim.
export function AvatarCampos({
  tipo,
  value,
  savedPrompt,
  disabled,
  onChange,
  ia,
}: {
  tipo: "avatar" | "cenario";
  value: PromptFields;
  savedPrompt: string | null;
  disabled?: boolean;
  onChange: (next: PromptFields) => void;
  ia?: AvatarCamposIa;
}) {
  const avatar = tipo === "avatar";
  // Sem `ia`, o campo sai como antes (sem botão).
  const comIa = (campo: keyof PromptFields, tipoCampo: TipoCampoId, nome: string, field: (botao?: ReactNode) => ReactNode) =>
    ia ? (
      <IaAssist
        tipo={tipoCampo}
        perfilId={ia.perfilId}
        alvo={ia.alvo}
        value={value[campo]}
        onSave={ia.onSave(campo)}
        campo={nome}
        disabled={disabled}
        onReload={ia.onReload}
      >
        {field}
      </IaAssist>
    ) : (
      field()
    );
  const over = value.prompt.length > PROMPT_MAX;
  const copyLabel = avatar ? "Copiar descrição para prompt" : "Copiar prompt";
  return (
    <div className="space-y-4">
      {comIa(
        "prompt",
        avatar ? "avatar.descricao_prompt" : "cenario.prompt_ambiente",
        avatar ? "Descrição para prompts" : "Prompt do ambiente",
        (botao) => (
          <Field
            label={avatar ? "Descrição para prompts" : "Prompt do ambiente"}
            action={botao}
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
        ),
      )}
      <CopyButton text={savedPrompt ?? ""} label={copyLabel} disabled={!savedPrompt} />
      {avatar && (
        <>
          {comIa("voiceTone", "avatar.tom_de_voz", "Tom de voz", (botao) => (
            <Field label="Tom de voz" action={botao} error={value.voiceTone.length > 500 ? "Até 500 caracteres" : undefined}>
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
          ))}
          {comIa("imageRules", "avatar.regras_imagem", "Regras de imagem", (botao) => (
            <Field
              label="Regras de imagem"
              action={botao}
              error={value.imageRules.length > PROMPT_MAX ? `Até ${PROMPT_MAX.toLocaleString("pt-BR")} caracteres` : undefined}
            >
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
          ))}
        </>
      )}
    </div>
  );
}
