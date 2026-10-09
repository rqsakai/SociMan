import { ShieldAlert, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { direitoLabel, type Direito } from "@/lib/canais";
import { cn } from "@/lib/utils";

const tone: Record<Direito | "avulso", string> = {
  proprio: "bg-success text-success-foreground",
  parceiro: "bg-info text-info-foreground",
  programa_de_cortes: "bg-info text-info-foreground",
  sem_acordo: "bg-warning text-warning-foreground",
  avulso: "bg-warning text-warning-foreground",
};

// Selo do status de direito (US1-4): "Sem acordo" e "Avulso" levam o ícone de aviso. É só
// informativo (princípio II): nada é bloqueado por ele.
export function DireitoBadge({ direito, className }: { direito: Direito | "avulso"; className?: string }) {
  const aviso = direito === "sem_acordo" || direito === "avulso";
  const label = direito === "avulso" ? "Avulso" : direitoLabel[direito];
  return (
    <Badge className={cn(tone[direito], className)} title={aviso ? "O direito autoral é responsabilidade do dono" : undefined}>
      {aviso ? <ShieldAlert aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
      {label}
    </Badge>
  );
}
