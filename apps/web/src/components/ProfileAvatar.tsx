import type { ImageRef } from "@sociman/contract";
import { initials } from "../lib/perfis";

const sizes = {
  sm: "size-9 text-xs",
  lg: "size-20 text-xl",
} as const;

// Logo do perfil em miniatura (URL do imgproxy em /img) ou, sem logo, as iniciais do nome sobre
// uma cor neutra (US3, cenário 4).
export function ProfileAvatar({
  name,
  logo,
  size = "sm",
}: {
  name: string;
  logo: ImageRef | null | undefined;
  size?: keyof typeof sizes;
}) {
  const box = `${sizes[size]} shrink-0 rounded-full border border-border`;
  if (logo) {
    return (
      <img
        src={size === "sm" ? logo.urls.thumb : logo.urls.medium}
        alt={`Logo de ${name}`}
        className={`${box} bg-surface object-cover`}
        loading="lazy"
      />
    );
  }
  return (
    <span aria-hidden="true" className={`${box} inline-flex items-center justify-center bg-border/60 font-semibold text-muted`}>
      {initials(name)}
    </span>
  );
}
