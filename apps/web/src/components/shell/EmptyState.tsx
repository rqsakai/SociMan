/*
 * Estado vazio de lista (spec 024, R13): título, explicação e ação opcionais, centralizados.
 *
 * Props:
 *   titulo: string          mensagem principal (role="status", lida pelo leitor de tela)
 *   descricao?: ReactNode   explicação em uma ou duas linhas
 *   acao?: ReactNode        botão ou link (ex.: <Button size="sm">Limpar filtros</Button>)
 *   icone?: LucideIcon      ícone acima do título
 *   className?: string
 */
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface EmptyStateProps {
  titulo: string;
  descricao?: ReactNode;
  acao?: ReactNode;
  icone?: LucideIcon;
  className?: string;
}

export function EmptyState({ titulo, descricao, acao, icone: Icone, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center gap-2 py-10 text-center", className)}>
      {Icone && <Icone className="size-8 text-muted-foreground" aria-hidden="true" />}
      <p role="status" className="font-medium">
        {titulo}
      </p>
      {descricao && <p className="max-w-prose text-sm text-muted-foreground">{descricao}</p>}
      {acao && <div className="mt-2 flex flex-wrap items-center justify-center gap-2">{acao}</div>}
    </div>
  );
}
