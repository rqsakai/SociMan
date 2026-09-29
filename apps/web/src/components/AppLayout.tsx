import { LogOut } from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { logout } from "../lib/authActions";
import { useAuth } from "../lib/authStore";
import { AppShell } from "./layout";
import { Button } from "./ui";

function NavItem({ to, children }: { to: string; children: ReactNode }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `rounded-field px-3 py-2 text-sm font-medium hover:bg-border/40 ${isActive ? "text-primary" : "text-text"}`
      }
    >
      {children}
    </NavLink>
  );
}

// Casca da área logada com a navegação: "Perfis" para todos; "Usuários" e "Segurança" só para o dono.
export function AppLayout({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const isOwner = useAuth((s) => s.user?.role === "dono");
  const [loggingOut, setLoggingOut] = useState(false);

  async function onLogout() {
    setLoggingOut(true);
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <AppShell
      nav={
        <>
          <NavItem to="/app/perfis">Perfis</NavItem>
          {isOwner && <NavItem to="/app/usuarios">Usuários</NavItem>}
          {isOwner && <NavItem to="/app/seguranca">Segurança</NavItem>}
          <NavItem to="/app/conta">Minha conta</NavItem>
          <Button className="!w-auto" variant="ghost" loading={loggingOut} onClick={onLogout}>
            {!loggingOut && <LogOut className="size-4" aria-hidden="true" />}
            Sair
          </Button>
        </>
      }
    >
      {children}
    </AppShell>
  );
}
