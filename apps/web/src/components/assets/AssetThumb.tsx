import type { AssetTipo, ImageRef } from "@sociman/contract";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import { checkerClass, isTransparentTipo } from "../../lib/assets";
import { initials } from "../../lib/perfis";

// Miniatura de um asset: a capa (imgproxy `medium`), sobre xadrez nos tipos com transparência, ou
// as iniciais do nome em cor neutra (avatar sem imagem, edge case da spec).
export function AssetThumb({
  name,
  tipo,
  cover,
  className,
}: {
  name: string;
  tipo: AssetTipo;
  cover: ImageRef | null | undefined;
  className?: string;
}) {
  if (!cover) {
    return (
      <Avatar className={cn("size-full rounded-none", className)}>
        <AvatarFallback className="rounded-none bg-muted text-2xl font-semibold text-muted-foreground" data-testid="asset-initials">
          {initials(name)}
        </AvatarFallback>
      </Avatar>
    );
  }
  const transparent = isTransparentTipo(tipo);
  return (
    <div className={cn("size-full overflow-hidden", transparent && cn(checkerClass, "p-2"), className)}>
      <img
        src={cover.urls.medium}
        alt=""
        loading="lazy"
        className={cn("size-full", transparent ? "object-contain" : "object-cover")}
      />
    </div>
  );
}
