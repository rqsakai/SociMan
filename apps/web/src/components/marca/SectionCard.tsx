import { useId, type ReactNode } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

// Cartão de uma seção do kit (Legenda, Gancho, Marca d'água…). É uma região com o título como
// nome acessível (os e2e escopam os campos por ela). Com `enabled`, mostra o switch "Ligado";
// desligada, a seção continua editável (a API valida os campos mesmo desligados).
export function SectionCard({
  title,
  description,
  enabled,
  onEnabledChange,
  actions,
  children,
  className,
}: {
  title: string;
  description?: ReactNode;
  enabled?: boolean;
  onEnabledChange?: (enabled: boolean) => void;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const titleId = useId();
  const switchId = useId();
  return (
    <Card role="region" aria-labelledby={titleId} className={cn("gap-4 shadow-card", className)}>
      <CardHeader className="grid-cols-[1fr_auto]">
        <div className="space-y-1.5">
          <CardTitle>
            <h2 id={titleId}>{title}</h2>
          </CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </div>
        <div className="flex items-center gap-3">
          {actions}
          {enabled !== undefined && onEnabledChange && (
            <div className="flex items-center gap-2">
              <Switch id={switchId} checked={enabled} onCheckedChange={onEnabledChange} />
              <Label htmlFor={switchId}>Ligado</Label>
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className={cn("space-y-4", enabled === false && "opacity-70")}>{children}</CardContent>
    </Card>
  );
}
