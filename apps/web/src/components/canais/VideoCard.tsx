import { CircleAlert, ExternalLink, Film } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { formatCount, formatSeconds, videoWarning, type VideoFonte } from "@/lib/canais";
import { formatDateTime } from "@/lib/tz";
import { cn } from "@/lib/utils";
import { DireitoBadge } from "./DireitoBadge";

// Miniatura 16:9 do vídeo (URL do imgproxy em /img, R13) com a duração no canto; sem miniatura, o
// ícone de filme.
export function VideoThumb({ video, className }: { video: Pick<VideoFonte, "thumbnailUrl" | "durationS" | "title">; className?: string }) {
  return (
    <div className={cn("relative aspect-video w-32 shrink-0 overflow-hidden rounded-md bg-muted", className)}>
      {video.thumbnailUrl ? (
        <img src={video.thumbnailUrl} alt="" loading="lazy" className="size-full object-cover" />
      ) : (
        <Film className="absolute inset-0 m-auto size-6 text-muted-foreground" aria-hidden="true" />
      )}
      {video.durationS !== null && video.durationS !== undefined && (
        <span className="absolute right-1 bottom-1 rounded bg-black/75 px-1 text-[0.68rem] font-semibold text-white tabular-nums">
          {formatSeconds(video.durationS)}
        </span>
      )}
    </div>
  );
}

// Cartão do vídeo-fonte (US2-1): miniatura, título (link para o YouTube), canal com o selo de
// direito, publicação, views e views por hora; avisos de indisponível, ao vivo, > 3 h e < 45 s; e
// o selo "Já cortado" quando o perfil do filtro já tem envio desse vídeo.
export function VideoCard({ video, jaCortado, className }: { video: VideoFonte; jaCortado?: string | null; className?: string }) {
  const warning = videoWarning(video);
  return (
    <div className={cn("flex min-w-0 gap-3", className)}>
      <VideoThumb video={video} />
      <div className="min-w-0 flex-1 space-y-1">
        <a
          href={video.url}
          target="_blank"
          rel="noreferrer noopener"
          className="line-clamp-2 text-sm leading-snug font-semibold break-words hover:underline"
        >
          {video.title}
          <ExternalLink className="ml-1 inline size-3 text-muted-foreground" aria-hidden="true" />
        </a>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <span className="max-w-48 truncate">{video.canal.title}</span>
          {video.canal.direito === "sem_acordo" && <DireitoBadge direito="sem_acordo" />}
          <span aria-hidden="true">·</span>
          <time dateTime={video.publishedAt}>{formatDateTime(video.publishedAt)}</time>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          <span>
            <strong className="tabular-nums">{formatCount(video.views)}</strong> views
          </span>
          {video.vphRecente !== null && video.vphRecente !== undefined && (
            <span>
              <strong className="tabular-nums">{formatCount(Math.round(video.vphRecente))}</strong> views/h
            </span>
          )}
          {jaCortado && <Badge variant="secondary">{jaCortado}</Badge>}
          {warning && (
            <span className="inline-flex items-center gap-1 text-destructive">
              <CircleAlert className="size-3" aria-hidden="true" />
              {warning}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
