import { TriangleAlert } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { GuiaConflito } from "@/lib/guia";

// Conflitos entre o guia do perfil e o da conta (spec 017): só avisos, vale a conta. O de
// `hashtagsFixas` é o estado inválido herdado (research R6): a IA usa as primeiras até o máximo.
export function GuiaConflitos({ conflitos }: { conflitos: GuiaConflito[] }) {
  if (conflitos.length === 0) return null;
  return (
    <Alert className="border-warning/60">
      <TriangleAlert className="text-warning" aria-hidden="true" />
      <AlertTitle>Conflitos com o guia do perfil</AlertTitle>
      <AlertDescription>
        <ul aria-label="Conflitos com o guia do perfil" className="list-disc space-y-1 pl-5">
          {conflitos.map((c, i) => (
            <li key={`${c.campo}-${i}`}>
              {c.mensagem}
              <span className="block text-xs text-muted-foreground">
                Perfil: {c.perfil || "—"} · Conta: {c.conta || "—"}
              </span>
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}
