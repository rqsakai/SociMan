/*
 * Cartão de métrica (spec 005, FR-006): cartão branco com um "selo" de ícone colorido que sai
 * para fora do topo; à direita o rótulo pequeno e o número grande; embaixo, separador e rodapé.
 *
 * Props:
 *   icon: LucideIcon      ícone do selo
 *   label: string         rótulo pequeno em cinza (ex.: "Perfis ativos")
 *   value: ReactNode      número em destaque (ex.: 12); use "—" enquanto carrega
 *   tone?: Tone           cor do selo (padrão "dark"; ver ./tone.ts)
 *   footer?: ReactNode    linha de baixo (ex.: <><strong className="text-success">+3</strong> esta semana</>)
 *   loading?: boolean     troca o número por um Skeleton
 *   className?: string
 *
 * Em grade, deixe espaço para o selo: <div className="grid gap-x-6 gap-y-10 pt-6 sm:grid-cols-2 xl:grid-cols-4">.
 */
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { toneClass, type Tone } from "./tone";

export interface MetricCardProps {
  icon: LucideIcon;
  label: string;
  value: ReactNode;
  tone?: Tone;
  footer?: ReactNode;
  loading?: boolean;
  className?: string;
}

export function MetricCard({ icon: Icon, label, value, tone = "dark", footer, loading, className }: MetricCardProps) {
  return (
    <div className={cn("relative rounded-xl bg-card px-4 pt-3 pb-3 text-card-foreground shadow-card", className)}>
      <div className="flex items-start justify-between gap-4">
        <div className={cn("-mt-7 grid size-16 shrink-0 place-items-center rounded-xl", toneClass[tone])}>
          <Icon className="size-6" aria-hidden="true" />
        </div>
        <div className="min-w-0 text-right">
          <p className="truncate text-sm text-muted-foreground">{label}</p>
          {loading ? (
            <Skeleton className="mt-1 ml-auto h-8 w-16" />
          ) : (
            <p className="text-2xl font-bold">{value}</p>
          )}
        </div>
      </div>
      {footer && (
        <>
          <div className="my-3 h-px bg-linear-to-r from-transparent via-border to-transparent" />
          <div className="text-sm text-muted-foreground">{footer}</div>
        </>
      )}
    </div>
  );
}
