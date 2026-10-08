/*
 * Casca do painel logado (spec 005, US1): Sidebar + Topbar + conteúdo + Footer.
 *
 * Props:
 *   children?: ReactNode   conteúdo da página; sem children, renderiza o <Outlet /> (rota de layout)
 *   search?: TopbarSearch  campo "Buscar" da barra superior (opcional, ver Topbar.tsx)
 *
 * Uso recomendado (rota de layout, o menu não remonta ao navegar):
 *   <Route element={<RequireAuth><AppShell /></RequireAuth>}>
 *     <Route path="/app" element={<Home />} />
 *     ...
 *   </Route>
 * Cada página define título e trilha com usePageMeta (./page-meta.tsx) e mantém o próprio <h1>.
 *
 * Layout: fundo cinza-claro (bg-background); a partir de 1024 px o menu fica fixo à esquerda e o
 * conteúdo ganha margem; abaixo disso o menu vira gaveta (botão "Abrir menu" na barra).
 * O conteúdo nunca rola na horizontal: tabelas largas rolam dentro do próprio cartão. A área de
 * conteúdo tem no máximo 1440 px, centralizada (spec 024, FR-032).
 */
import { useState, type ReactNode } from "react";
import { Outlet } from "react-router-dom";
import { Footer } from "./Footer";
import { PageMetaProvider } from "./page-meta";
import { MobileSidebar, Sidebar } from "./Sidebar";
import { Topbar, type TopbarSearch } from "./Topbar";

export interface AppShellProps {
  children?: ReactNode;
  search?: TopbarSearch;
}

export function AppShell({ children, search }: AppShellProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <PageMetaProvider>
      <div className="min-h-screen bg-background">
        <Sidebar />
        <MobileSidebar open={menuOpen} onOpenChange={setMenuOpen} />
        <div className="flex min-h-screen min-w-0 flex-col lg:pl-72">
          <Topbar onOpenMenu={() => setMenuOpen(true)} search={search} />
          <main className="min-w-0 flex-1 px-4 pt-4 pb-2 sm:px-6">
            <div className="mx-auto w-full max-w-[1440px]">{children ?? <Outlet />}</div>
          </main>
          <Footer />
        </div>
      </div>
    </PageMetaProvider>
  );
}
