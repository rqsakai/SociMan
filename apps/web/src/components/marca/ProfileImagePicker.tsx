import type { ImageRef } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageUp, Loader2 } from "lucide-react";
import { useId, useRef, useState, type ChangeEvent } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { errorText } from "../../lib/perfis";

const MAX_BYTES = 5 * 1024 * 1024;

function imageSize(file: File): Promise<{ width: number; height: number } | null> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight });
      img.onerror = () => resolve(null);
      img.src = String(reader.result);
    };
    reader.onerror = () => resolve(null);
    reader.readAsDataURL(file);
  });
}

export interface ProfileImagePickerProps {
  value: string | null;
  onChange: (image: ImageRef) => void;
  error?: string;
}

// Imagens do perfil para escolher, mais o envio de uma nova (até 5 MB, conferida no navegador
// antes do envio; o servidor confere de novo). Enviar não altera o kit: a imagem nova fica
// escolhida no rascunho e entra no kit ao salvar. Base da marca d'água (T020) e do fundo (T033).
export function ProfileImagePicker({
  value,
  onChange,
  error,
  queryKey,
  list,
  upload,
  label,
  uploadLabel,
  hint,
  accepted,
  minSize,
  transparent = false,
}: ProfileImagePickerProps & {
  queryKey: readonly unknown[];
  list: () => Promise<{ items: ImageRef[] }>;
  upload: (file: File) => Promise<{ image: ImageRef }>;
  label: string;
  uploadLabel: string;
  hint: string;
  accepted: string[];
  minSize: number;
  // Miniaturas sobre xadrez (imagem com transparência) em vez de recortadas em cover.
  transparent?: boolean;
}) {
  const queryClient = useQueryClient();
  const images = useQuery({ queryKey, queryFn: list });
  const inputRef = useRef<HTMLInputElement>(null);
  const hintId = useId();
  const labelId = useId();
  const [busy, setBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploadError(null);
    if (!accepted.includes(file.type)) return setUploadError("Formato não aceito");
    if (file.size > MAX_BYTES) return setUploadError("Arquivo maior que 5 MB");
    const size = await imageSize(file);
    if (!size) return setUploadError("Formato não aceito");
    if (size.width < minSize || size.height < minSize) return setUploadError("Imagem pequena demais");
    setBusy(true);
    try {
      const { image } = await upload(file);
      await queryClient.invalidateQueries({ queryKey });
      onChange(image);
    } catch (err) {
      setUploadError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const items = images.data?.items ?? [];
  return (
    <div className="space-y-2">
      <p id={labelId} className="text-sm font-medium">
        {label}
      </p>
      {images.isError && <p className="text-sm text-destructive">{errorText(images.error)}</p>}
      {items.length > 0 ? (
        <div role="radiogroup" aria-labelledby={labelId} className="flex flex-wrap gap-2">
          {items.map((img, i) => (
            <button
              key={img.id}
              type="button"
              role="radio"
              aria-checked={img.id === value}
              aria-label={`Imagem ${i + 1}`}
              onClick={() => onChange(img)}
              className={cn(
                "size-16 overflow-hidden rounded-md border",
                transparent && "bg-[repeating-conic-gradient(#ddd_0_25%,#fff_0_50%)] bg-[length:12px_12px] p-1",
                img.id === value && "ring-2 ring-primary ring-offset-2",
              )}
            >
              <img src={img.urls.thumb} alt="" className={cn("size-full", transparent ? "object-contain" : "object-cover")} />
            </button>
          ))}
        </div>
      ) : (
        !images.isPending && <p className="text-sm text-muted-foreground">Nenhuma imagem enviada ainda.</p>
      )}
      <input
        ref={inputRef}
        type="file"
        accept={accepted.join(",")}
        className="sr-only"
        aria-hidden="true"
        tabIndex={-1}
        onChange={(e) => void onFile(e)}
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={busy}
        aria-busy={busy}
        aria-describedby={hintId}
        onClick={() => inputRef.current?.click()}
      >
        {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <ImageUp aria-hidden="true" />}
        {uploadLabel}
      </Button>
      <p id={hintId} className="text-xs text-muted-foreground">
        {hint}
      </p>
      {(uploadError ?? error) && (
        <p role="alert" className="text-sm text-destructive">
          {uploadError ?? error}
        </p>
      )}
    </div>
  );
}
