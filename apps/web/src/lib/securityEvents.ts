import type { SecurityEvent } from "@sociman/contract";

// Rótulos dos tipos de evento de security_event (data-model.md), na ordem do filtro.
export const eventTypeLabel: Record<string, string> = {
  login_succeeded: "Login",
  login_failed: "Login recusado",
  logout: "Saída",
  refresh_reuse_detected: "Reuso de sessão detectado",
  password_reset_requested: "Recuperação pedida",
  password_reset_completed: "Senha redefinida",
  password_changed: "Senha trocada",
  password_set_by_owner: "Senha provisória definida",
  email_verification_sent: "Verificação enviada",
  email_verified: "E-mail verificado",
  user_created: "Usuário criado",
  user_updated: "Usuário editado",
  role_changed: "Papel alterado",
  email_changed: "E-mail alterado",
  user_deactivated: "Usuário desativado",
  user_reactivated: "Usuário reativado",
};

export const outcomeLabel: Record<SecurityEvent["outcome"], string> = { ok: "Ok", denied: "Negado" };

const actorKindLabel: Record<string, string> = { anonymous: "Anônimo", "system:cli": "CLI" };

export function actorText(event: SecurityEvent): string {
  return event.actorName ?? actorKindLabel[event.actorKind] ?? "—";
}

// "YYYY-MM-DD" do <input type="date"> é dia local; new Date("YYYY-MM-DD") seria UTC.
export function localDayBound(day: string, end: boolean): string | undefined {
  const [y, m, d] = day.split("-").map(Number);
  if (!y || !m || !d) return undefined;
  const date = end ? new Date(y, m - 1, d, 23, 59, 59, 999) : new Date(y, m - 1, d);
  return date.toISOString();
}
