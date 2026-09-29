import { Rocket } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

// Primitivas de layout do starter (§7). Só classes Tailwind sobre os tokens de
// tema — zero style inline (CSP estrita: style-src 'self').

export function Container({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`mx-auto w-full max-w-4xl px-4 ${className}`}>{children}</div>;
}

export function Card({ className = "", children }: { className?: string; children: ReactNode }) {
  return (
    <div className={`rounded-panel border border-border bg-surface p-6 shadow-sm ${className}`}>
      {children}
    </div>
  );
}

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
}

export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

function Brand({ to }: { to: string }) {
  return (
    <Link to={to} className="flex items-center gap-2 font-semibold">
      <Rocket className="size-5 text-primary" aria-hidden="true" />
      <span>SociMan</span>
    </Link>
  );
}

interface AppShellProps {
  nav?: ReactNode;
  children: ReactNode;
}

// Casca da área logada: header com marca + slot de navegação, main contido.
export function AppShell({ nav, children }: AppShellProps) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border bg-surface">
        <Container className="flex h-14 items-center justify-between">
          <Brand to="/app" />
          {nav && <nav className="flex items-center gap-2">{nav}</nav>}
        </Container>
      </header>
      <main className="flex-1">
        <Container className="py-8">{children}</Container>
      </main>
    </div>
  );
}

interface AuthLayoutProps {
  title: string;
  children: ReactNode;
}

// Layout das telas públicas de auth: marca no topo + cartão centralizado.
export function AuthLayout({ title, children }: AuthLayoutProps) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="mb-6">
        <Brand to="/" />
      </div>
      <Card className="w-full max-w-90">
        <h1 className="mb-5 text-xl font-semibold">{title}</h1>
        {children}
      </Card>
    </main>
  );
}
