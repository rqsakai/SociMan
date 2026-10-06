import { Bot, CalendarDays, ChartLine, Inbox, Send, CircleUser, Clapperboard, House, LayoutGrid, Scissors, ShieldCheck, Sparkles, Tv, Users, WandSparkles, type LucideIcon } from "lucide-react";

// Itens do menu lateral (spec 005, US1). `ownerOnly` some para o membro.
// `end`: só fica ativo na rota exata (senão "Início" ficaria ativo em /app/*).
export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  ownerOnly?: boolean;
  end?: boolean;
  // 009-mcp: contador ao lado do rótulo (o Sidebar busca o número).
  contador?: "propostas";
}

export const navItems: NavItem[] = [
  { label: "Início", to: "/app", icon: House, end: true },
  { label: "Perfis", to: "/app/perfis", icon: LayoutGrid },
  // 006-cortes-openshorts
  { label: "Canais-fonte", to: "/app/fontes", icon: Tv },
  { label: "Descobrir", to: "/app/descobrir", icon: Sparkles },
  { label: "Gerar cortes", to: "/app/envios", icon: Scissors },
  // 014-central-de-conteudos
  { label: "Conteúdos", to: "/app/conteudos", icon: Clapperboard },
  { label: "Calendário", to: "/app/calendario", icon: CalendarDays },
  // 016-metricas-tiktok
  { label: "Métricas", to: "/app/metricas", icon: ChartLine },
  // 008-assistente-ia (registro e resumo só para o dono, dentro da tela)
  { label: "Assistente de IA", to: "/app/assistente-ia", icon: WandSparkles },
  // 009-mcp
  { label: "Propostas dos agentes", to: "/app/propostas", icon: Inbox, contador: "propostas" },
  { label: "Usuários", to: "/app/usuarios", icon: Users, ownerOnly: true },
  { label: "Segurança", to: "/app/seguranca", icon: ShieldCheck, ownerOnly: true },
  // 015-tiktok-rascunho
  { label: "Publicação automática", to: "/app/configuracoes/publicacao", icon: Send, ownerOnly: true },
  // 009-mcp
  { label: "Agentes (MCP)", to: "/app/configuracoes/agentes", icon: Bot, ownerOnly: true },
  { label: "Minha conta", to: "/app/conta", icon: CircleUser },
];

// Trilha padrão quando a página não chama usePageMeta: o item do menu cujo
// caminho é o prefixo mais longo da URL atual.
export function navItemFor(pathname: string): NavItem | undefined {
  return [...navItems]
    .sort((a, b) => b.to.length - a.to.length)
    .find((item) => (item.end ? pathname === item.to : pathname === item.to || pathname.startsWith(`${item.to}/`)));
}
