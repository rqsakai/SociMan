/*
 * Menu lateral do painel (spec 005, US1; referência: docs/design/layout-referencia.md).
 *
 * <Sidebar />                          menu flutuante escuro, fixo à esquerda a partir de 1024 px (lg)
 * <MobileSidebar open onOpenChange />  o mesmo conteúdo numa gaveta (Sheet) abaixo de 1024 px
 *
 * Os itens vêm de ./nav.ts e são filtrados pelo papel (Usuários e Segurança só para o dono).
 * Spec 024: os grupos (Cortes, Analytics, Configurações) recolhem; o aberto/fechado fica em
 * localStorage["sociman:menu:grupos"], e o grupo da rota atual abre sozinho. Grupo vazio some.
 * O item ativo é uma pílula com o tom primário (NavLink). No rodapé, o botão "Novo perfil".
 * Quem usa normalmente é o AppShell; as páginas não montam o Sidebar direto.
 */
import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, Clapperboard, Plus } from "lucide-react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { useAnotacoesResumo } from "@/lib/anotacoes";
import { useAuth } from "@/lib/authStore";
import { cn } from "@/lib/utils";
import { isNavGroup, navItemFor, navTree, type NavEntry, type NavGroup, type NavItem } from "./nav";

function Brand() {
  return (
    <Link to="/app" className="flex items-center gap-3 px-2 py-1 text-sidebar-foreground">
      <Clapperboard className="size-6" aria-hidden="true" />
      <span className="text-base font-bold tracking-wide">SociMan</span>
    </Link>
  );
}

type GruposAbertos = Record<NavGroup["id"], boolean>;

const GRUPOS_KEY = "sociman:menu:grupos";
// Primeira visita (ou sem localStorage): Cortes e Analytics abertos, Configurações fechado.
const GRUPOS_PADRAO: GruposAbertos = { cortes: true, analytics: true, config: false };

function lerGrupos(): GruposAbertos {
  try {
    const salvo: unknown = JSON.parse(localStorage.getItem(GRUPOS_KEY) ?? "null");
    if (!salvo || typeof salvo !== "object") return GRUPOS_PADRAO;
    const grupos = { ...GRUPOS_PADRAO };
    for (const id of Object.keys(grupos) as NavGroup["id"][]) {
      const valor = (salvo as Record<string, unknown>)[id];
      if (typeof valor === "boolean") grupos[id] = valor;
    }
    return grupos;
  } catch {
    return GRUPOS_PADRAO;
  }
}

function gravarGrupos(grupos: GruposAbertos): void {
  try {
    localStorage.setItem(GRUPOS_KEY, JSON.stringify(grupos));
  } catch {
    // sem localStorage (aba privada, bloqueado): o menu segue com o estado da sessão
  }
}

// Grupo que contém o item ativo da rota (o mesmo critério do breadcrumb).
function grupoDaRota(pathname: string): NavGroup["id"] | undefined {
  const item = navItemFor(pathname);
  return navTree.find((entry): entry is NavGroup => isNavGroup(entry) && !!item && entry.itens.includes(item))?.id;
}

// Abre o grupo da rota por cima do estado lembrado.
function comGrupoDaRota(grupos: GruposAbertos, pathname: string): GruposAbertos {
  const ativo = grupoDaRota(pathname);
  return ativo && !grupos[ativo] ? { ...grupos, [ativo]: true } : grupos;
}

function NavItemLink({
  item: { label, to, icon: Icon, end, contador },
  contadores,
  onNavigate,
}: {
  item: NavItem;
  contadores: Record<NonNullable<NavItem["contador"]>, number>;
  onNavigate?: () => void;
}) {
  return (
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
  );
}

// Conteúdo comum ao menu fixo e à gaveta. `onNavigate` fecha a gaveta ao clicar num item.
function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const isOwner = useAuth((s) => s.user?.role === "dono");
  const { pathname } = useLocation();
  // Papel primeiro; o grupo que fica sem itens visíveis some (FR-005).
  const entries = navTree
    .map((entry): NavEntry => (isNavGroup(entry) ? { ...entry, itens: entry.itens.filter((i) => !i.ownerOnly || isOwner) } : entry))
    .filter((entry) => (isNavGroup(entry) ? entry.itens.length > 0 : !entry.ownerOnly || isOwner));
  // 009-mcp: propostas abertas dos agentes ao lado de "Propostas dos agentes".
  const propostas = useAnotacoesResumo();
  const contadores = { propostas: propostas.data?.abertas ?? 0 };

  const idBase = useId();
  const [grupos, setGrupos] = useState(() => comGrupoDaRota(lerGrupos(), pathname));
  useEffect(() => {
    setGrupos((atual) => comGrupoDaRota(atual, pathname));
  }, [pathname]);
  // Com os grupos abertos o menu passa da altura da tela: mantém o item atual à vista.
  const navRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const ativo = navRef.current?.querySelector<HTMLElement>('[aria-current="page"]');
    ativo?.scrollIntoView?.({ block: "nearest" });
  }, [pathname, grupos]);

  function alternar(id: NavGroup["id"], aberto: boolean) {
    setGrupos((atual) => {
      const novo = { ...atual, [id]: aberto };
      gravarGrupos(novo);
      return novo;
    });
  }

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <Brand />
      <div className="h-px bg-linear-to-r from-transparent via-sidebar-border to-transparent" />
      <nav ref={navRef} aria-label="Menu principal" className="flex-1">
        <ul className="space-y-1">
          {entries.map((entry) =>
            isNavGroup(entry) ? (
              <li key={entry.id}>
                <Collapsible open={grupos[entry.id]} onOpenChange={(aberto) => alternar(entry.id, aberto)}>
                  <CollapsibleTrigger
                    aria-controls={`${idBase}-${entry.id}`}
                    className={cn(
                      "group flex w-full items-center gap-3 rounded-lg px-4 py-2.5 text-sm text-sidebar-muted-foreground transition-colors",
                      "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                      "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sidebar-ring",
                    )}
                  >
                    <entry.icon className="size-4.5 shrink-0" aria-hidden="true" />
                    {entry.label}
                    <ChevronDown
                      className="ml-auto size-4 shrink-0 transition-transform group-data-[state=open]:rotate-180"
                      aria-hidden="true"
                    />
                  </CollapsibleTrigger>
                  {/* forceMount + hidden + aria-controls próprios: fechado, os links ficam no DOM (ocultos) e
                      o botão aponta para eles mesmo assim; o Radix só faria isso com o grupo aberto.
                      O helper nav() dos e2e acha o grupo por aí. */}
                  <CollapsibleContent forceMount id={`${idBase}-${entry.id}`} hidden={!grupos[entry.id]}>
                    <ul className="mt-1 ml-4 space-y-1 border-l border-sidebar-border pl-2">
                      {entry.itens.map((item) => (
                        <li key={item.to}>
                          <NavItemLink item={item} contadores={contadores} onNavigate={onNavigate} />
                        </li>
                      ))}
                    </ul>
                  </CollapsibleContent>
                </Collapsible>
              </li>
            ) : (
              <li key={entry.to}>
                <NavItemLink item={entry} contadores={contadores} onNavigate={onNavigate} />
              </li>
            ),
          )}
        </ul>
      </nav>
      <Button asChild variant="band" className="w-full text-xs font-bold tracking-wide uppercase">
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
