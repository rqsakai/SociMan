import { CalendarDays, CircleUser, House, LayoutGrid, Scissors, ShieldCheck, Sparkles, Tv, Users, type LucideIcon } from "lucide-react";

// Itens do menu lateral (spec 005, US1). `ownerOnly` some para o membro.
// `end`: só fica ativo na rota exata (senão "Início" ficaria ativo em /app/*).
export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  ownerOnly?: boolean;
  end?: boolean;
}

export const navItems: NavItem[] = [
  { label: "Início", to: "/app", icon: House, end: true },
  { label: "Perfis", to: "/app/perfis", icon: LayoutGrid },
  // 006-cortes-openshorts
  { label: "Canais-fonte", to: "/app/fontes", icon: Tv },
  { label: "Descobrir", to: "/app/descobrir", icon: Sparkles },
  { label: "Envios", to: "/app/envios", icon: Scissors },
  { label: "Calendário", to: "/app/calendario", icon: CalendarDays },
  { label: "Usuários", to: "/app/usuarios", icon: Users, ownerOnly: true },
  { label: "Segurança", to: "/app/seguranca", icon: ShieldCheck, ownerOnly: true },
  { label: "Minha conta", to: "/app/conta", icon: CircleUser },
];

// Trilha padrão quando a página não chama usePageMeta: o item do menu cujo
// caminho é o prefixo mais longo da URL atual.
export function navItemFor(pathname: string): NavItem | undefined {
  return [...navItems]
    .sort((a, b) => b.to.length - a.to.length)
    .find((item) => (item.end ? pathname === item.to : pathname === item.to || pathname.startsWith(`${item.to}/`)));
}
