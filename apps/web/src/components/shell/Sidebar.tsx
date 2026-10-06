/*
 * Menu lateral do painel (spec 005, US1; referência: docs/design/layout-referencia.md).
 *
 * <Sidebar />                          menu flutuante escuro, fixo à esquerda a partir de 1024 px (lg)
 * <MobileSidebar open onOpenChange />  o mesmo conteúdo numa gaveta (Sheet) abaixo de 1024 px
 *
 * Os itens vêm de ./nav.ts e são filtrados pelo papel (Usuários e Segurança só para o dono).
 * O item ativo é uma pílula com o tom primário (NavLink). No rodapé, o botão "Novo perfil".
 * Quem usa normalmente é o AppShell; as páginas não montam o Sidebar direto.
 */
import { Clapperboard, Plus } from "lucide-react";
import { Link, NavLink } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { useAnotacoesResumo } from "@/lib/anotacoes";
import { useAuth } from "@/lib/authStore";
import { cn } from "@/lib/utils";
import { navItems } from "./nav";

function Brand() {
  return (
    <Link to="/app" className="flex items-center gap-3 px-2 py-1 text-sidebar-foreground">
      <Clapperboard className="size-6" aria-hidden="true" />
      <span className="text-base font-bold tracking-wide">SociMan</span>
    </Link>
  );
}

// Conteúdo comum ao menu fixo e à gaveta. `onNavigate` fecha a gaveta ao clicar num item.
function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const isOwner = useAuth((s) => s.user?.role === "dono");
  const items = navItems.filter((item) => !item.ownerOnly || isOwner);
  // 009-mcp: propostas abertas dos agentes ao lado de "Propostas dos agentes".
  const propostas = useAnotacoesResumo();
  const contadores = { propostas: propostas.data?.abertas ?? 0 };

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <Brand />
      <div className="h-px bg-linear-to-r from-transparent via-sidebar-border to-transparent" />
      <nav aria-label="Menu principal" className="flex-1">
        <ul className="space-y-1">
          {items.map(({ label, to, icon: Icon, end, contador }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={end}
                onClick={onNavigate}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-lg px-4 py-2.5 text-sm transition-colors",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sidebar-ring",
                    isActive
                      ? "tone-primary font-medium"
                      : "text-sidebar-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                  )
                }
              >
                <Icon className="size-4.5 shrink-0" aria-hidden="true" />
                {label}
                {contador && contadores[contador] > 0 && (
                  <span className="ml-auto rounded-full bg-sidebar-accent px-2 text-xs font-semibold text-sidebar-accent-foreground">
                    {contadores[contador]}
                  </span>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <Button asChild className="tone-primary w-full text-xs font-bold tracking-wide uppercase">
        <Link to="/app/perfis/novo" onClick={onNavigate}>
          <Plus aria-hidden="true" />
          Novo perfil
        </Link>
      </Button>
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="fixed inset-y-4 left-4 z-30 hidden w-64 overflow-y-auto rounded-xl bg-sidebar-gradient shadow-float lg:block dark:border dark:border-sidebar-border">
      <SidebarContent />
    </aside>
  );
}

export function MobileSidebar({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="left"
        className="w-72 max-w-[85vw] border-none bg-sidebar-gradient p-0 text-sidebar-foreground [&>button]:text-sidebar-foreground"
      >
        <SheetTitle className="sr-only">Menu</SheetTitle>
        <SheetDescription className="sr-only">Navegação do SociMan</SheetDescription>
        <SidebarContent onNavigate={() => onOpenChange(false)} />
      </SheetContent>
    </Sheet>
  );
}
