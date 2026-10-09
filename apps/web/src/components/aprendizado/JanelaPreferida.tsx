/*
 * Dica "Janela preferida" no agendamento (spec 023, US3 cenário 6; FR-039): vem das preferências
 * efetivas do perfil e da conta (uma janela de horário aceita pelo dono). Só leitura: não preenche,
 * não agenda nem muda nada (princípio I). Sem janela aceita, não aparece.
 */
import { Lightbulb } from "lucide-react";
import { usePreferencias } from "@/lib/aprendizado";

export function JanelaPreferida({ perfilId, contaId }: { perfilId: string; contaId?: string }) {
  const prefs = usePreferencias(perfilId, contaId);
  const janela = prefs.data?.efetivas.janelaPreferida;
  if (!janela) return null;
  return (
    <p className="flex items-start gap-2 text-sm text-muted-foreground" data-janela-preferida>
      <Lightbulb className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>Janela preferida: {janela} (aprendizado do perfil; só uma dica).</span>
    </p>
  );
}
