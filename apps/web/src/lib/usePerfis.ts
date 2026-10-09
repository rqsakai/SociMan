import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

// Perfis não arquivados, em ordem alfabética: seletores de perfil da 006 (Descobrir, Envios,
// Calendário, ligação de canais). Mesma chave ["perfis", filtros] da lista de perfis.
export function usePerfisAtivos() {
  return useQuery({
    queryKey: ["perfis", {}],
    queryFn: () => api.perfis.list(),
    select: (data) => [...data.items].filter((p) => !p.archived).sort((a, b) => a.name.localeCompare(b.name, "pt-BR")),
    staleTime: 60_000,
  });
}

// Cor do perfil no calendário (R14): a 1ª cor da paleta do kit, que a API manda em `cor`; sem kit
// salvo, uma cor estável derivada do id.
const PALETTE = ["#e91e63", "#1a73e8", "#43a047", "#fb8c00", "#8e24aa", "#00897b", "#f4511e", "#3949ab", "#c0ca33", "#6d4c41"];
export function perfilColor(id: string, cor?: string | null): string {
  if (cor && /^#[0-9A-Fa-f]{6}$/.test(cor)) return cor;
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length]!;
}

// Texto legível sobre a cor (preto ou branco), pelo contraste WCAG com a luminância relativa.
export function textOn(hex: string): "#000000" | "#FFFFFF" {
  const n = Number.parseInt(hex.slice(1), 16);
  const lin = (c: number) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  const l = 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
  return (l + 0.05) / 0.05 >= 1.05 / (l + 0.05) ? "#000000" : "#FFFFFF";
}
