import type { ImageRef } from "@sociman/contract";
import { useQuery } from "@tanstack/react-query";
import { Library, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { api } from "../../lib/api";
import { checkerClass, libraryImagesKey, tipoLabel, type AssetTipo, type LibraryImage } from "../../lib/assets";

// "Abrir biblioteca" dos seletores do kit (FR-006, R6): as imagens escolhíveis do perfil (arquivos
// ativos de assets ativos) dos tipos do seletor, com busca por nome ou tag e filtro de tipo.
export function LibraryImageDialog({
  perfilId,
  tipos,
  value,
  transparent,
  onPick,
}: {
  perfilId: string;
  tipos: readonly AssetTipo[];
  value: string | null;
  transparent?: boolean;
  // spec 010: o item inteiro (assetId, nome) vem como 2º argumento.
  onPick: (image: ImageRef, item: LibraryImage) => void;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [tipo, setTipo] = useState<AssetTipo | "todos">("todos");

  useEffect(() => {
    const t = window.setTimeout(() => setQ(text.trim()), 250);
    return () => window.clearTimeout(t);
  }, [text]);

  const chosen = tipo === "todos" ? tipos : [tipo];
  const images = useQuery({
    queryKey: libraryImagesKey(perfilId, chosen, q),
    queryFn: () => api.assets.images(perfilId, { tipo: [...chosen], q: q || undefined, limit: 60 }),
    enabled: open,
  });
  const items: LibraryImage[] = images.data?.items ?? [];

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" size="sm">
          <Library aria-hidden="true" />
          Abrir biblioteca
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Biblioteca do perfil</DialogTitle>
          <DialogDescription>{tipos.map((t) => tipoLabel[t]).join(" e ")}. Envie imagens novas pelo seletor ou pela aba Assets.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-48 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input
              type="search"
              aria-label="Buscar na biblioteca"
              placeholder="Buscar por nome ou tag"
              className="pl-8"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </div>
          <div role="group" aria-label="Tipo" className="flex gap-1">
            {(["todos", ...tipos] as const).map((t) => (
              <Button key={t} type="button" size="sm" variant={tipo === t ? "default" : "outline"} aria-pressed={tipo === t} onClick={() => setTipo(t)}>
                {t === "todos" ? "Todos" : tipoLabel[t]}
              </Button>
            ))}
          </div>
        </div>
        {images.isError && <ApiErrorAlert error={images.error} />}
        {images.isPending && open && (
          <p aria-live="polite" className="text-sm text-muted-foreground">
            Carregando…
          </p>
        )}
        {images.data && items.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma imagem encontrada.</p>}
        {items.length > 0 && (
          <ul aria-label="Imagens da biblioteca" className="grid max-h-[60vh] grid-cols-3 gap-3 overflow-y-auto p-1 sm:grid-cols-4 md:grid-cols-5">
            {items.map((item) => {
              const label = item.label ? `${item.assetName}: ${item.label}` : item.assetName;
              return (
                <li key={item.fileId}>
                  <button
                    type="button"
                    aria-label={`Escolher ${label}`}
                    aria-pressed={item.image.id === value}
                    onClick={() => {
                      onPick(item.image, item);
                      setOpen(false);
                    }}
                    className={cn(
                      "block w-full overflow-hidden rounded-md border text-left outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
                      item.image.id === value && "ring-2 ring-primary ring-offset-2",
                    )}
                  >
                    <span className={cn("block aspect-square bg-muted", (transparent || item.hasAlpha) && cn(checkerClass, "p-1"))}>
                      <img
                        src={item.image.urls.thumb}
                        alt=""
                        loading="lazy"
                        className={cn("size-full", transparent || item.hasAlpha ? "object-contain" : "object-cover")}
                      />
                    </span>
                    <span className="block truncate px-1.5 py-1 text-xs">
                      {label}
                      <span className="block text-muted-foreground">{tipoLabel[item.assetTipo]}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
