import { Bot } from "lucide-react";
import { Badge } from "@/components/ui/badge";

// Selo "Agente: <nome>" (spec 009, FR-022): marca o que um cliente MCP gravou, no histórico e nas
// anotações. O nome é o do cliente MCP cadastrado pelo dono.
export function AgenteSelo({ nome }: { nome: string }) {
  return (
    <Badge variant="outline" className="gap-1 border-info/50 text-info">
      <Bot className="size-3" aria-hidden="true" />
      Agente: {nome}
    </Badge>
  );
}
