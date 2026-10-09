import { Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/authStore";

// Selo "com ajuda da IA" de uma versão salva a partir do painel (`details.ia`, R10). O autor da
// versão continua o humano; para o dono, o selo leva à chamada no registro.
export function IaSelo({ chamadaId }: { chamadaId?: string | null }) {
  const isOwner = useAuth((s) => s.user?.role === "dono");
  const selo = (
    <Badge variant="outline" className="gap-1 border-primary/40 text-primary">
      <Sparkles className="size-3" aria-hidden="true" />
      com ajuda da IA
    </Badge>
  );
  if (!isOwner || !chamadaId) return selo;
  return (
    <Link to={`/app/assistente-ia?aba=registro&chamada=${chamadaId}`} title="Ver a chamada no registro da IA">
      {selo}
    </Link>
  );
}

// `details.ia` de uma versão: [{ campo, tipoCampo, chamadaId, desfecho, itens? }].
export function iaDaVersao(details: Record<string, unknown>): { chamadaId?: string }[] | null {
  const ia = details.ia;
  return Array.isArray(ia) && ia.length > 0 ? (ia as { chamadaId?: string }[]) : null;
}
