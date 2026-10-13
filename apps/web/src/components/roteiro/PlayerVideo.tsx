import { VideoEstavel } from "../midia/VideoEstavel";

// Player de uma tomada, de uma prévia ou do vídeo final (spec 011, T038): `<video>` nativo com o link de
// mídia estável (`useLinkEstavel`): o roteiro recarrega a cada 2 s e a API assina um link novo a cada
// resposta, então o player só troca de link quando é outro item (`chave` = o id do item), quando o
// link está para vencer ou quando não tocou (aí pede um novo pelo `onRenovar`). Nunca `key={url}`.
// Vídeo vertical: largura cheia, no máximo a altura da tela.
export function PlayerVideo({
  chave,
  url,
  expiresAt,
  miniaturaUrl,
  rotulo,
  onRenovar,
  className,
  testId = "player-video",
}: {
  chave: string;
  url: string;
  expiresAt?: string | null;
  miniaturaUrl?: string | null;
  rotulo: string;
  onRenovar?: () => void;
  className?: string;
  testId?: string;
}) {
  return (
    <VideoEstavel
      chave={chave}
      url={url}
      expiresAt={expiresAt}
      onRenovar={onRenovar}
      controls
      playsInline
      preload="metadata"
      poster={miniaturaUrl ?? undefined}
      aria-label={rotulo}
      data-testid={testId}
      className={className ?? "aspect-[9/16] max-h-[70vh] w-full rounded-lg bg-black object-contain"}
    />
  );
}
