/*
 * Layout das telas de acesso (spec 005, US3): fundo escuro em degradê e cartão branco central com
 * um cabeçalho colorido que sobe para fora do topo do cartão. Sem cadastro público, sem login social.
 *
 * Props:
 *   title: string            título no cabeçalho colorido (renderizado como <h1>)
 *   description?: ReactNode  linha menor abaixo do título, no cabeçalho
 *   tone?: Tone              cor do cabeçalho (padrão "primary"; ver ./tone.ts)
 *   children: ReactNode      formulário/conteúdo do cartão
 *   footer?: ReactNode       linha no pé do cartão (ex.: link "Esqueci a senha")
 *
 * Exemplo:
 *   <AuthShell title="Entrar" footer={<Link to="/forgot-password">Esqueci a senha</Link>}>
 *     <form>…</form>
 *   </AuthShell>
 */
import { Clapperboard } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { toneClass, type Tone } from "./tone";

export interface AuthShellProps {
  title: string;
  description?: ReactNode;
  tone?: Tone;
  children: ReactNode;
  footer?: ReactNode;
}

export function AuthShell({ title, description, tone = "primary", children, footer }: AuthShellProps) {
  return (
    <div className="flex min-h-screen flex-col bg-sidebar-gradient text-sidebar-foreground">
      <header className="px-4 pt-6 sm:px-8">
        <Link to="/" className="inline-flex items-center gap-2 font-bold tracking-wide">
          <Clapperboard className="size-5" aria-hidden="true" />
          SociMan
        </Link>
      </header>
      <main className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm rounded-xl bg-card text-card-foreground shadow-float">
          <div className={cn("-mt-8 mx-4 rounded-lg px-6 py-6 text-center", toneClass[tone])}>
            <h1 className="text-xl font-bold">{title}</h1>
            {description && <p className="mt-1 text-sm opacity-90">{description}</p>}
          </div>
          <div className="px-6 pt-8 pb-6">{children}</div>
          {footer && <div className="px-6 pb-6 text-center text-sm text-muted-foreground">{footer}</div>}
        </div>
      </main>
      <footer className="px-4 pb-6 text-center text-xs text-sidebar-muted-foreground sm:px-8">
        SociMan · uso interno da agência
      </footer>
    </div>
  );
}
