import type { ReactNode } from "react";

// Título visível da página dentro do AppShell (spec 005): o <h1> da página, com uma linha de
// descrição opcional. A barra superior mostra a trilha, mas não é heading.
export function PageHeading({ title, description }: { title: ReactNode; description?: ReactNode }) {
  return (
    <div className="min-w-0">
      <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
    </div>
  );
}
