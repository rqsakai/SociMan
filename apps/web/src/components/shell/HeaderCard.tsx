/*
 * Cartão com cabeçalho colorido (spec 005): uma faixa em degradê, arredondada e com sombra,
 * sobreposta ao topo do cartão branco. Serve para tabelas ("Perfis") e blocos de destaque.
 *
 * Props:
 *   title: string          título dentro da faixa (renderizado como <h2>)
 *   description?: ReactNode linha menor dentro da faixa
 *   tone?: Tone            cor da faixa (padrão "primary"; ver ./tone.ts)
 *   actions?: ReactNode    à direita da faixa (ex.: <Button variant="secondary" size="sm">Novo perfil</Button>)
 *   band?: ReactNode       conteúdo extra dentro da faixa, abaixo do título (ex.: um gráfico)
 *   children?: ReactNode   corpo do cartão (ex.: <DataTable … />)
 *   footer?: ReactNode     rodapé com separador (ex.: <><Clock /> atualizado há 4 min</>)
 *   className?: string
 *
 * Deixe espaço acima para a faixa: o cartão já tem mt-6 (a faixa sobe 1,5 rem).
 */
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { toneClass, type Tone } from "./tone";

export interface HeaderCardProps {
  title: string;
  description?: ReactNode;
  tone?: Tone;
  actions?: ReactNode;
  band?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  className?: string;
}

export function HeaderCard({
  title,
  description,
  tone = "primary",
  actions,
  band,
  children,
  footer,
  className,
}: HeaderCardProps) {
  return (
    <section className={cn("mt-6 min-w-0 rounded-xl bg-card text-card-foreground shadow-card", className)}>
      <div className={cn("relative -top-6 mx-4 -mb-2 rounded-lg px-4 py-4 sm:px-5", toneClass[tone])}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-lg font-bold">{title}</h2>
            {description && <p className="text-sm opacity-90">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
        {band && <div className="mt-3">{band}</div>}
      </div>
      {children && <div className="min-w-0 px-4 pb-4 sm:px-5">{children}</div>}
      {footer && (
        <div className="mx-4 flex items-center gap-1.5 border-t py-3 text-sm text-muted-foreground sm:mx-5 [&_svg]:size-4">
          {footer}
        </div>
      )}
    </section>
  );
}
