import { ImageUp, Loader2 } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { checkImageFile, fileRule, uploadAssetFile, type AssetTipo, type FileFields, type FileRole } from "../../lib/assets";

// Envio de um arquivo para um avatar ou cenário (POST /api/assets/{id}/arquivos, sem version: só
// acrescenta). Os campos dependem do papel: referência de avatar tem look e uso; referência de
// cenário, só uso; pose tem rótulo (obrigatório) e "quando usar".
export function AssetUpload({
  assetId,
  tipo,
  role,
  submitLabel,
  looks = [],
  disabled,
  onUploaded,
}: {
  assetId: string;
  tipo: AssetTipo;
  role: FileRole;
  submitLabel: string;
  // Looks já usados (sugestões do campo).
  looks?: string[];
  disabled?: boolean;
  onUploaded: () => Promise<void>;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [look, setLook] = useState("");
  const [uso, setUso] = useState("");
  const [label, setLabel] = useState("");
  const [quandoUsar, setQuandoUsar] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [labelError, setLabelError] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const rule = fileRule[tipo];
  const withLook = tipo === "avatar" && role === "referencia";
  const listId = `looks-${assetId}`;

  async function pick(f: File | null) {
    setFile(null);
    setFileError(null);
    if (!f) return;
    const problem = await checkImageFile(f, tipo);
    if (problem) return setFileError(problem);
    setFile(f);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!file) setFileError((prev) => prev ?? "Escolha uma imagem");
    const needsLabel = role === "pose" && !label.trim();
    setLabelError(needsLabel ? "Dê um rótulo à pose" : null);
    if (!file || needsLabel) return;
    const fields: FileFields = { role };
    if (withLook) fields.look = look.trim();
    if (role === "referencia") fields.uso = uso.trim();
    if (role === "pose") {
      fields.label = label.trim();
      fields.quandoUsar = quandoUsar.trim();
    }
    setProgress(0);
    try {
      await uploadAssetFile(assetId, file, fields, setProgress);
      toast.success(role === "pose" ? `Pose "${label.trim()}" enviada.` : "Imagem enviada.");
      setFile(null);
      setLabel("");
      setQuandoUsar("");
      setUso("");
      if (inputRef.current) inputRef.current.value = "";
      await onUploaded();
    } catch (err) {
      setError(err);
    } finally {
      setProgress(null);
    }
  }

  const busy = progress !== null;
  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-3 rounded-lg border border-dashed p-3" noValidate>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Imagem" error={fileError ?? undefined} hint={rule.hint}>
          {({ id, describedBy, invalid }) => (
            <Input
              ref={inputRef}
              id={id}
              type="file"
              accept={rule.accepted.join(",")}
              disabled={disabled || busy}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => void pick(e.target.files?.[0] ?? null)}
            />
          )}
        </Field>
        {withLook && (
          <Field label="Look" hint='Agrupa as referências. Ex.: "Cozinha, corpo inteiro".'>
            {({ id, describedBy }) => (
              <>
                <Input id={id} list={listId} value={look} maxLength={60} autoComplete="off" aria-describedby={describedBy} onChange={(e) => setLook(e.target.value)} />
                <datalist id={listId}>
                  {looks.map((l) => (
                    <option key={l} value={l} />
                  ))}
                </datalist>
              </>
            )}
          </Field>
        )}
        {role === "referencia" && (
          <Field label="Uso" hint='Ex.: "cenas de cozinha".'>
            {({ id, describedBy }) => (
              <Input id={id} value={uso} maxLength={200} autoComplete="off" aria-describedby={describedBy} onChange={(e) => setUso(e.target.value)} />
            )}
          </Field>
        )}
        {role === "pose" && (
          <>
            <Field label="Rótulo da pose" error={labelError ?? undefined}>
              {({ id, describedBy, invalid }) => (
                <Input
                  id={id}
                  value={label}
                  maxLength={60}
                  autoComplete="off"
                  aria-invalid={invalid}
                  aria-describedby={describedBy}
                  onChange={(e) => setLabel(e.target.value)}
                />
              )}
            </Field>
            <Field label="Quando usar">
              {({ id, describedBy }) => (
                <Input id={id} value={quandoUsar} maxLength={300} autoComplete="off" aria-describedby={describedBy} onChange={(e) => setQuandoUsar(e.target.value)} />
              )}
            </Field>
          </>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="sm" disabled={disabled || busy} aria-busy={busy}>
          {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <ImageUp aria-hidden="true" />}
          {submitLabel}
        </Button>
        {busy && (
          <progress className="h-2 w-40" max={1} value={progress} aria-label="Progresso do envio">
            {Math.round(progress * 100)}%
          </progress>
        )}
      </div>
      {error !== null && <ApiErrorAlert error={error} />}
    </form>
  );
}
