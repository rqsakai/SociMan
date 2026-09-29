import { ApiError, type ImageKind, type ImageRef, type Perfil } from "@sociman/contract";
import { CircleAlert, ImageUp, Loader2, Trash2 } from "lucide-react";
import { useId, useRef, useState, type ChangeEvent } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { api } from "../lib/api";
import { errorText } from "../lib/perfis";

const MAX_BYTES = 5 * 1024 * 1024;
const ACCEPTED = ["image/png", "image/jpeg", "image/webp"];
const TOO_BIG = "Arquivo maior que 5 MB";

// Limites da FR-008; o servidor confere de novo pelo conteúdo real do arquivo.
const config: Record<ImageKind, { title: string; minWidth: number; minHeight: number; frame: string }> = {
  logo: { title: "logo", minWidth: 200, minHeight: 200, frame: "size-32 rounded-full" },
  banner: { title: "banner", minWidth: 1000, minHeight: 250, frame: "aspect-[4/1] w-full rounded-lg" },
};

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function imageSize(src: string): Promise<{ width: number; height: number } | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight });
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

// Logo ou banner do perfil: escolhe o arquivo, mostra a prévia local e envia na hora
// (multipart com a versão do perfil). A prévia usa data: URL, que a CSP (img-src 'self' data:)
// já permite; blob: exigiria mudar a CSP.
export function ImageUpload({
  kind,
  perfil,
  onChanged,
}: {
  kind: ImageKind;
  perfil: Perfil;
  onChanged: (perfil: Perfil) => void;
}) {
  const { title, minWidth, minHeight, frame } = config[kind];
  const current: ImageRef | null = kind === "logo" ? perfil.logo : perfil.banner;
  const inputRef = useRef<HTMLInputElement>(null);
  const hintId = useId();
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"upload" | "clear" | null>(null);

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // permite escolher o mesmo arquivo de novo
    if (!file) return;
    setError(null);
    if (!ACCEPTED.includes(file.type)) return setError("Formato não aceito");
    if (file.size > MAX_BYTES) return setError(TOO_BIG);
    const dataUrl = await readAsDataUrl(file).catch(() => null);
    if (!dataUrl) return setError("Formato não aceito");
    const size = await imageSize(dataUrl);
    if (!size) return setError("Formato não aceito");
    if (size.width < minWidth || size.height < minHeight) return setError("Imagem pequena demais");

    setPreview(dataUrl);
    setBusy("upload");
    try {
      const { perfil: updated } = await api.perfis.uploadImage(perfil.id, kind, file, perfil.version);
      onChanged(updated);
    } catch (err) {
      // 413 vem do nginx (client_max_body_size), sem o envelope de erro da API.
      setError(err instanceof ApiError && err.status === 413 ? TOO_BIG : errorText(err));
    } finally {
      setPreview(null);
      setBusy(null);
    }
  }

  async function onClear() {
    setError(null);
    setBusy("clear");
    try {
      const { perfil: updated } = await api.perfis.clearImage(perfil.id, kind, perfil.version);
      onChanged(updated);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  }

  const shown = preview ?? current?.urls.medium ?? null;
  const label = kind === "logo" ? "Trocar logo" : "Trocar banner";

  return (
    <section className="space-y-3" aria-label={kind === "logo" ? "Logo" : "Banner"}>
      <h3 className="text-sm font-semibold">{kind === "logo" ? "Logo" : "Banner"}</h3>
      {shown ? (
        <img
          src={shown}
          alt={preview ? `Prévia do novo ${title}` : `${kind === "logo" ? "Logo" : "Banner"} de ${perfil.name}`}
          className={cn(frame, "border bg-muted object-cover shadow-card", preview && "opacity-60")}
        />
      ) : (
        <div className={cn(frame, "flex items-center justify-center border-2 border-dashed bg-muted/50 text-xs text-muted-foreground")}>
          Sem {title}
        </div>
      )}
      <p id={hintId} className="text-xs text-muted-foreground">
        PNG, JPG ou WebP até 5 MB; mínimo {minWidth}×{minHeight} px.
      </p>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED.join(",")}
        className="sr-only"
        // acionado pelo botão visível "{label}": fora da árvore de acessibilidade
        // para não haver dois controles com o mesmo nome
        aria-hidden="true"
        tabIndex={-1}
        onChange={(e) => void onFile(e)}
      />
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy !== null}
          aria-busy={busy === "upload"}
          aria-describedby={hintId}
          onClick={() => inputRef.current?.click()}
        >
          {busy === "upload" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <ImageUp aria-hidden="true" />}
          {label}
        </Button>
        {current && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-destructive hover:text-destructive"
            aria-label={`Remover ${title}`}
            disabled={busy !== null}
            aria-busy={busy === "clear"}
            onClick={() => void onClear()}
          >
            {busy === "clear" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Trash2 aria-hidden="true" />}
            Remover
          </Button>
        )}
      </div>
      {error && (
        <Alert variant="destructive">
          <CircleAlert aria-hidden="true" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </section>
  );
}
