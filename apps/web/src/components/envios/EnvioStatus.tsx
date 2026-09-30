import {
  AudioLines,
  Captions,
  Circle,
  CircleAlert,
  CircleCheck,
  Clapperboard,
  Clock,
  Download,
  HardDriveDownload,
  Loader2,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ProgressBar } from "@/components/marca/CorteStatusBadge";
import {
  emAndamento,
  envioEtapaLabel,
  envioEtapasLista,
  envioProgressoTexto,
  envioStatusText,
  envioStatusTone,
  type Envio,
  type EnvioEtapa,
} from "@/lib/envios";
import { cn } from "@/lib/utils";

type EnvioLike = Pick<Envio, "status" | "queuePosition" | "progress" | "clipsTotal" | "clipsImportados">;
type EnvioComEtapa = EnvioLike & Pick<Envio, "etapa" | "etapaMensagem">;

// Status da geração (US3): "Na fila (2º)", "Pronto: 3 clipes", "Sem clipes", "Falhou".
export function EnvioStatusBadge({ envio, className }: { envio: EnvioLike; className?: string }) {
  return (
    <Badge className={cn(envioStatusTone[envio.status], className)}>
      {emAndamento(envio) && <Loader2 className="animate-spin" aria-hidden="true" />}
      {envioStatusText(envio)}
    </Badge>
  );
}

const etapaIcon: Record<EnvioEtapa, LucideIcon> = {
  fila: Clock,
  baixando: Download,
  transcrevendo: AudioLines,
  escolhendo_momentos: Sparkles,
  processando_clipes: Clapperboard,
  legendas: Captions,
  importando: HardDriveDownload,
  concluido: CircleCheck,
  erro: CircleAlert,
};

// Andamento (FR-010a), numa linha só com o % geral: ícone da etapa + "Processando 10% ·
// Transcrevendo o vídeo 25%" ou "Na fila do OpenShorts (2º)".
export function EnvioEtapaLinha({ envio, className }: { envio: EnvioComEtapa; className?: string }) {
  const texto = envioProgressoTexto(envio);
  if (!texto) return null;
  const Icon = envio.etapa ? etapaIcon[envio.etapa] : Loader2;
  return (
    <p className={cn("flex items-start gap-1.5 text-sm font-medium", className)} data-etapa={envio.etapa ?? "processando"}>
      <Icon className={cn("mt-0.5 size-4 shrink-0 text-info", !envio.etapa && "animate-spin")} aria-hidden="true" />
      <span>{texto}</span>
    </p>
  );
}

// Em andamento no OpenShorts: a linha da etapa + a barra do % geral; nos outros status, o badge.
export function EnvioStatus({ envio, className }: { envio: EnvioComEtapa; className?: string }) {
  const andamento = envio.status === "processando" || envio.status === "importando";
  return (
    <div className={cn("min-w-32 space-y-1", className)}>
      {andamento ? <EnvioEtapaLinha envio={envio} /> : <EnvioStatusBadge envio={envio} />}
      {andamento && <ProgressBar value={envio.progress / 100} label="Progresso da geração" className="h-1.5" />}
    </div>
  );
}

// Detalhe da geração: as etapas em ordem, com check nas concluídas e a atual destacada.
export function EnvioEtapas({ envio, legendaKit, className }: { envio: EnvioComEtapa; legendaKit: boolean; className?: string }) {
  const lista = envioEtapasLista(legendaKit);
  const atual: EnvioEtapa | null =
    envio.status === "pronto" ? "concluido" : envio.status === "na_fila" || envio.status === "aguardando_openshorts" ? "fila" : envio.etapa;
  if (!emAndamento(envio) && envio.status !== "pronto") return null;
  const idx = atual ? lista.indexOf(atual) : -1;
  return (
    <ol aria-label="Etapas da geração" className={cn("space-y-1 text-sm", className)}>
      {lista.map((etapa, i) => {
        const feita = i < idx || (etapa === "concluido" && atual === "concluido");
        const corrente = i === idx && etapa !== "concluido";
        const Icon = feita ? CircleCheck : corrente ? Loader2 : Circle;
        return (
          <li
            key={etapa}
            aria-current={corrente ? "step" : undefined}
            className={cn(
              "flex items-start gap-2 rounded-md px-2 py-1",
              corrente && "bg-info/10 font-semibold text-foreground",
              !feita && !corrente && "text-muted-foreground",
            )}
          >
            <Icon
              className={cn("mt-0.5 size-4 shrink-0", feita && "text-success", corrente && "animate-spin text-info")}
              aria-hidden="true"
            />
            <span>
              {envioEtapaLabel[etapa]}
              {corrente && envio.etapaMensagem && envio.etapaMensagem !== envioEtapaLabel[etapa] && (
                <span className="font-normal text-muted-foreground"> — {envio.etapaMensagem}</span>
              )}
              <span className="sr-only">{feita ? " (concluída)" : corrente ? " (em andamento)" : ""}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
