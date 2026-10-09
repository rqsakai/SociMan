import type { ImageRef } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageUp, Loader2 } from "lucide-react";
import { useId, useRef, useState, type ChangeEvent } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { LibraryImageDialog } from "../assets/LibraryImageDialog";
import { api } from "../../lib/api";
import {
  checkerClass,
  checkImageFile,
  fileBaseName,
  fileRule,
  uploadSingleAsset,
  type AssetTipo,
} from "../../lib/assets";
import { errorText } from "../../lib/perfis";
import type { PerfilFiltro } from "../../lib/estudio";
import { PerfilBaseFiltro } from "../estudio/PerfilBaseFiltro";
import { EmptyState } from "@/components/shell";

const RECENT = 12;

export interface ProfileImagePickerProps {
  value: string | null;
  onChange: (image: ImageRef) => void;
  error?: string;
}

// Seletor de imagem do kit pela biblioteca do perfil (spec 007, FR-006, R6): as 12 imagens mais
// recentes dos tipos do seletor, "Abrir biblioteca" (busca e filtro) e o envio de uma nova (até
// 20 MB, conferida no navegador antes; o servidor confere de novo), que entra na biblioteca como
// um asset de `uploadTipo`. Enviar não altera o kit: a imagem nova fica escolhida no rascunho e
// entra no kit ao salvar. Base da marca d'água e do fundo. Spec 029 (T032, FR-013): a lista vem da
// biblioteca da agência (`GET /api/assets/imagens`), com o filtro "Perfil base" começando no perfil
// do kit; a imagem nova nasce com o perfil do kit como perfil base.
export function ProfileImagePicker({
  perfilId,
  value,
  onChange,
  error,
  tipos,
  uploadTipo,
  label,
  uploadLabel,
  hint,
  transparent = false,
}: ProfileImagePickerProps & {
  perfilId: string;
  // Tipos de asset listados (fundo: fundos e cenários; marca d'água: marcas d'água e stickers).
  tipos: readonly AssetTipo[];
  uploadTipo: AssetTipo;
  label: string;
  uploadLabel: string;
  hint: string;
  // Miniaturas sobre xadrez (imagem com transparência) em vez de recortadas em cover.
  transparent?: boolean;
}) {
  const queryClient = useQueryClient();
  const [perfil, setPerfil] = useState<PerfilFiltro>(perfilId);
  const images = useQuery({
    queryKey: ["assets", "agencia", "imagens", perfil, [...tipos], "recentes"],
    queryFn: () => api.assets.imagensAgencia({ tipo: [...tipos], perfilId: perfil === "todos" ? undefined : perfil, limit: RECENT }),
  });
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
    const problem = await checkImageFile(file, uploadTipo);
    if (problem) return setUploadError(problem);
    setBusy(true);
    try {
      const { file: created } = await uploadSingleAsset(perfilId, uploadTipo, file, { name: fileBaseName(file.name) });
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
      onChange(created.image);
    } catch (err) {
      setUploadError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const items = images.data?.items ?? [];
  const chosenOutside = value !== null && images.data !== undefined && !items.some((i) => i.image.id === value);
  return (
    <div className="space-y-2">
      <p id={labelId} className="text-sm font-medium">
        {label}
      </p>
      <PerfilBaseFiltro valor={perfil} onChange={setPerfil} rotulo={`${label}: perfil base`} className="w-full sm:w-64" />
      {images.isError && <p className="text-sm text-destructive">{errorText(images.error)}</p>}
      {items.length > 0 ? (
        <div role="radiogroup" aria-labelledby={labelId} className="flex flex-wrap gap-2">
          {items.map((item) => (
            <button
              key={item.fileId}
              type="button"
              role="radio"
              aria-checked={item.image.id === value}
              aria-label={item.label ? `${item.assetName}: ${item.label}` : item.assetName}
              title={item.label ? `${item.assetName}: ${item.label}` : item.assetName}
              onClick={() => onChange(item.image)}
              className={cn(
                "size-16 overflow-hidden rounded-md border",
                (transparent || item.hasAlpha) && cn(checkerClass, "p-1"),
                item.image.id === value && "ring-2 ring-primary ring-offset-2",
              )}
            >
              <img
                src={item.image.urls.thumb}
                alt=""
                className={cn("size-full", transparent || item.hasAlpha ? "object-contain" : "object-cover")}
              />
            </button>
          ))}
        </div>
      ) : (
        !images.isPending && <EmptyState titulo="Nenhuma imagem na biblioteca ainda." className="items-start py-2 text-left" />
      )}
      {chosenOutside && <p className="text-xs text-muted-foreground">A imagem escolhida não está entre as {RECENT} mais recentes; veja em "Abrir biblioteca".</p>}
      <div className="flex flex-wrap gap-2">
        <LibraryImageDialog perfilId={perfilId} tipos={tipos} value={value} transparent={transparent} onPick={onChange} />
        <input
          ref={inputRef}
          type="file"
          accept={fileRule[uploadTipo].accepted.join(",")}
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
      </div>
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
