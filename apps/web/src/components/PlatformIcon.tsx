import type { Platform } from "@sociman/contract";
import type { ReactNode } from "react";
import { platformLabel } from "../lib/perfis";

// Ícones das plataformas desenhados aqui (SVG em JSX, sem CDN nem fonte de ícones): a CSP
// estrita só aceita recursos do próprio domínio. Traços simples, na cor do texto.
const glyphs: Record<Platform, ReactNode> = {
  tiktok: <path d="M14 3v11.5a3.5 3.5 0 1 1-3.5-3.5M14 3c.5 2.6 2.4 4.3 5 4.5" />,
  youtube: (
    <>
      <rect x="2.5" y="5.5" width="19" height="13" rx="3.5" />
      <path d="m10 9 5 3-5 3z" />
    </>
  ),
  instagram: (
    <>
      <rect x="3.5" y="3.5" width="17" height="17" rx="5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.2" cy="6.8" r="0.6" />
    </>
  ),
  kwai: (
    <>
      <rect x="3.5" y="3.5" width="17" height="17" rx="5" />
      <path d="M9 7.5v9M15 7.5 9.5 12l5.5 4.5" />
    </>
  ),
  facebook: <path d="M14.5 21v-8h3l.5-3.5h-3.5V7.5c0-1 .4-1.8 1.8-1.8H18V2.6c-.4-.1-1.5-.2-2.7-.2-2.7 0-4.3 1.6-4.3 4.6v2.5H8V13h3v8" />,
  x: <path d="m4 4 16 16M20 4 4 20" />,
  outra: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3" />
    </>
  ),
};

export function PlatformIcon({
  platform,
  label,
  className = "size-4",
}: {
  platform: Platform;
  // Nome exibido (ex.: o nome livre de "Outra"); padrão: o rótulo da plataforma.
  label?: string;
  className?: string;
}) {
  const name = label ?? platformLabel[platform];
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label={name}
      className={`shrink-0 ${className}`}
    >
      <title>{name}</title>
      {glyphs[platform]}
    </svg>
  );
}
