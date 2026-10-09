import { Bot, CalendarDays, ChartColumn, ChartLine, CircleUser, Clapperboard, Film, FolderInput, House, Image, Inbox, LayoutGrid, Lightbulb, Mic, Move, Package, Radar, Scissors, Send, Settings, ShieldCheck, ShoppingBag, Sparkles, Trees, Tv, UserRound, Users, Wand2, WandSparkles, type LucideIcon } from "lucide-react";

// Itens do menu lateral (spec 005, US1; agrupados na 024). `ownerOnly` some para o membro.
// `end`: só fica ativo na rota exata (senão "Início" ficaria ativo em /app/*).
export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  ownerOnly?: boolean;
  end?: boolean;
  // 009-mcp: contador ao lado do rótulo (o Sidebar busca o número).
  contador?: "propostas";
  // 029: outras rotas que marcam este item (o detalhe de cada tipo fica fora de /app/estudio)
  prefixos?: string[];
}

// Grupo recolhível do menu (spec 024, FR-001..005). O Sidebar lembra aberto/fechado por `id`.
export interface NavGroup {
  id: "estudio" | "cortes" | "analytics" | "config";
  label: string;
  icon: LucideIcon;
  itens: NavItem[];
}

export type NavEntry = NavItem | NavGroup;

export function isNavGroup(entry: NavEntry): entry is NavGroup {
  return "itens" in entry;
}

// Ordem do FR-001 da spec 024.
export const navTree: NavEntry[] = [
  { label: "Início", to: "/app", icon: House, end: true },
  { label: "Perfis", to: "/app/perfis", icon: LayoutGrid },
  // 029-ai-studio: a biblioteca da agência (itens de todos os perfis e sem perfil). O detalhe do
  // asset casa com "Assets" pela rota; o de avatar e o de cenário marcam o item certo pelo
  // `usePageMeta({ ativo })` da página.
  {
    id: "estudio",
    label: "AI Studio",
    icon: Wand2,
    itens: [
      { label: "Avatares", to: "/app/estudio/avatares", icon: UserRound },
      { label: "Cenários", to: "/app/estudio/cenarios", icon: Trees },
      { label: "Vozes", to: "/app/estudio/vozes", icon: Mic, prefixos: ["/app/vozes"] },
      { label: "Produtos", to: "/app/estudio/produtos", icon: Package, prefixos: ["/app/produtos"] },
      { label: "Cenas", to: "/app/estudio/cenas", icon: Clapperboard, prefixos: ["/app/cenas"] },
      { label: "Assets", to: "/app/estudio/assets", icon: Image, prefixos: ["/app/assets"] },
      { label: "Movimentos", to: "/app/estudio/movimentos", icon: Move },
    ],
  },
  // 006-cortes-openshorts
  {
    id: "cortes",
    label: "Cortes",
    icon: Film,
    itens: [
      { label: "Canais-fonte", to: "/app/fontes", icon: Tv },
      { label: "Descobrir", to: "/app/descobrir", icon: Sparkles },
      { label: "Gerar cortes", to: "/app/envios", icon: Scissors },
    ],
  },
  // 014-central-de-conteudos
  { label: "Conteúdos", to: "/app/conteudos", icon: Clapperboard },
  { label: "Calendário", to: "/app/calendario", icon: CalendarDays },
  // 009-mcp (fora de grupo: o contador nunca fica escondido, FR-006)
  { label: "Propostas dos agentes", to: "/app/propostas", icon: Inbox, contador: "propostas" },
  {
    id: "analytics",
    label: "Analytics",
    icon: ChartColumn,
    itens: [
      // 016-metricas-tiktok
      { label: "Métricas", to: "/app/metricas", icon: ChartLine },
      // 023-aprendizado
      { label: "Aprendizado", to: "/app/aprendizado", icon: Lightbulb },
      // 026-mercado-shop: o cockpit do TikTok Shop
      { label: "Mercado de produtos", to: "/app/mercado", icon: ShoppingBag },
      // 013-importacao (o membro vê o estado e a lista)
      { label: "Importar da agência", to: "/app/configuracoes/importacao", icon: FolderInput },
    ],
  },
  {
    id: "config",
    label: "Configurações",
    icon: Settings,
    itens: [
      // 008-assistente-ia (registro e resumo só para o dono, dentro da tela)
      { label: "Assistente de IA", to: "/app/assistente-ia", icon: WandSparkles },
      { label: "Usuários", to: "/app/usuarios", icon: Users, ownerOnly: true },
      { label: "Segurança", to: "/app/seguranca", icon: ShieldCheck, ownerOnly: true },
      // 015-tiktok-rascunho
      { label: "Publicação automática", to: "/app/configuracoes/publicacao", icon: Send, ownerOnly: true },
      // 009-mcp
      { label: "Agentes (MCP)", to: "/app/configuracoes/agentes", icon: Bot, ownerOnly: true },
      // 026-mercado-shop
      { label: "Coleta de mercado", to: "/app/configuracoes/coleta", icon: Radar, ownerOnly: true },
    ],
  },
  { label: "Minha conta", to: "/app/conta", icon: CircleUser },
];

// A lista plana (breadcrumb do Topbar).
export const navItems: NavItem[] = navTree.flatMap((entry) => (isNavGroup(entry) ? entry.itens : [entry]));

const casa = (pathname: string, to: string) => pathname === to || pathname.startsWith(`${to}/`);

// Trilha padrão quando a página não chama usePageMeta, e o item ativo do menu: o item cujo caminho
// (ou um dos `prefixos`) é o prefixo mais longo da URL atual. `ativo` (do usePageMeta) ganha de tudo.
export function navItemFor(pathname: string, ativo?: string): NavItem | undefined {
  if (ativo) {
    const escolhido = navItems.find((item) => item.to === ativo);
    if (escolhido) return escolhido;
  }
  const candidatos = navItems.flatMap((item) => [item.to, ...(item.prefixos ?? [])].map((to) => ({ item, to })));
  return candidatos
    .sort((a, b) => b.to.length - a.to.length)
    .find(({ item, to }) => (item.end && to === item.to ? pathname === to : casa(pathname, to)))?.item;
}
