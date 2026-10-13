import type { VideoHTMLAttributes } from "react";
import { useLinkEstavel } from "../../lib/linkEstavel";

// `<video>` com link de mídia estável (ver `useLinkEstavel`): recarregar a tela não corta o play.
export function VideoEstavel({ chave, url, expiresAt, onRenovar, ...props }: {
  chave: string;
  url: string;
  expiresAt?: string | null;
  onRenovar?: () => void;
} & Omit<VideoHTMLAttributes<HTMLVideoElement>, "src">) {
  const link = useLinkEstavel({ url, expiresAt }, chave, onRenovar);
  return <video key={chave} {...props} src={link.url ?? undefined} onError={link.onErro} />;
}
