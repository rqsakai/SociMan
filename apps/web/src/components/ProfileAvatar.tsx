import type { ImageRef } from "@sociman/contract";
import { cn } from "@/lib/utils";
import { initials } from "../lib/perfis";

const sizes = {
  sm: "size-9 text-xs",
  lg: "size-20 text-xl",
} as const;

// Logo do perfil em miniatura (URL do imgproxy em /img) ou, sem logo, as iniciais do nome sobre
// o tom escuro do tema (US3, cenário 4).
export function ProfileAvatar({
  name,
  logo,
  size = "sm",
  className,
}: {
  name: string;
  logo: ImageRef | null | undefined;
  size?: keyof typeof sizes;
  className?: string;
}) {
  const box = cn(sizes[size], "shrink-0 rounded-full shadow-card", className);
  if (logo) {
    return (
      <img
        src={size === "sm" ? logo.urls.thumb : logo.urls.medium}
        alt={`Logo de ${name}`}
        className={cn(box, "bg-card object-cover")}
        loading="lazy"
      />
    );
  }
  return (
    <span aria-hidden="true" className={cn(box, "tone-dark inline-flex items-center justify-center font-semibold")}>
      {initials(name)}
    </span>
  );
}
