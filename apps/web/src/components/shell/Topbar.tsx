/*
 * Barra superior do painel (spec 005, US1): transparente sobre o fundo e fixa ao rolar.
 *
 * Props:
 *   onOpenMenu: () => void          abre a gaveta do menu (botão "Abrir menu", só abaixo de 1024 px)
 *   search?: { value: string; onChange: (value: string) => void; placeholder?: string }
 *                                   campo "Buscar" (opcional; sem a prop, o campo não aparece)
 *
 * À esquerda: trilha (Início › … › página) e o título da página, vindos de usePageMeta
 * (./page-meta.tsx) ou, sem ele, do item do menu que casa com a URL. O título NÃO é heading:
 * o <h1> continua na página.
 * À direita: busca, menu de conta ("Minha conta" e "Sair") e o botão "Sair" (o e2e usa
 * getByRole("button", { name: "Sair" })).
 */
import { CircleUser, LogOut, Menu, Search } from "lucide-react";
import { Fragment, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { logout } from "@/lib/authActions";
import { useAuth } from "@/lib/authStore";
import { navItemFor } from "./nav";
import { useCurrentPageMeta, type Crumb } from "./page-meta";

export interface TopbarSearch {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export interface TopbarProps {
  onOpenMenu: () => void;
  search?: TopbarSearch;
}

function useTrail(): { title: string; crumbs: Crumb[] } {
  const meta = useCurrentPageMeta();
  const { pathname } = useLocation();
  const home: Crumb = { label: "Início", to: "/app" };
  if (meta) {
    return { title: meta.title, crumbs: [home, ...(meta.breadcrumbs ?? [])] };
  }
  const item = navItemFor(pathname);
  if (!item || item.to === "/app") return { title: item?.label ?? "Início", crumbs: [] };
  return { title: item.label, crumbs: [home] };
}

export function Topbar({ onOpenMenu, search }: TopbarProps) {
  const navigate = useNavigate();
  const user = useAuth((s) => s.user);
  const [loggingOut, setLoggingOut] = useState(false);
  const { title, crumbs } = useTrail();

  async function onLogout() {
    setLoggingOut(true);
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <header className="sticky top-0 z-20 bg-background/80 backdrop-blur-sm">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
        <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Abrir menu" onClick={onOpenMenu}>
          <Menu aria-hidden="true" />
        </Button>

        <div className="min-w-0 flex-1">
          <Breadcrumb>
            <BreadcrumbList className="text-xs">
              {crumbs.map((crumb) => (
                <Fragment key={`${crumb.label}-${crumb.to ?? ""}`}>
                  <BreadcrumbItem>
                    {crumb.to ? (
                      <BreadcrumbLink asChild>
                        <Link to={crumb.to}>{crumb.label}</Link>
                      </BreadcrumbLink>
                    ) : (
                      crumb.label
                    )}
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                </Fragment>
              ))}
              <BreadcrumbItem>
                <BreadcrumbPage className="truncate">{title}</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
          <p className="truncate text-base font-bold">{title}</p>
        </div>

        <div className="flex items-center gap-1">
          {search && (
            <div className="relative mr-2 hidden sm:block">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                type="search"
                aria-label={search.placeholder ?? "Buscar"}
                placeholder={search.placeholder ?? "Buscar"}
                value={search.value}
                onChange={(e) => search.onChange(e.target.value)}
                className="w-56 bg-card pl-9"
              />
            </div>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Conta">
                <CircleUser className="size-5" aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              {user && (
                <>
                  <DropdownMenuLabel className="font-normal">
                    <span className="block truncate font-medium">{user.name}</span>
                    <span className="block truncate text-xs text-muted-foreground">{user.email}</span>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                </>
              )}
              <DropdownMenuItem asChild>
                <Link to="/app/conta">
                  <CircleUser aria-hidden="true" />
                  Minha conta
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem disabled={loggingOut} onSelect={() => void onLogout()}>
                <LogOut aria-hidden="true" />
                Sair
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button variant="ghost" size="sm" disabled={loggingOut} aria-busy={loggingOut} onClick={() => void onLogout()}>
            <LogOut aria-hidden="true" />
            <span className="max-sm:sr-only">Sair</span>
          </Button>
        </div>
      </div>
    </header>
  );
}
