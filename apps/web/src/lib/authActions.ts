import type { LoginRequest } from "@sociman/contract";
import { api, refreshSessionResult } from "./api";
import { useAuth } from "./authStore";

export async function login(body: LoginRequest): Promise<void> {
  const session = await api.auth.login(body);
  useAuth.getState().setSession(session.accessToken, session.user);
}

export async function logout(): Promise<void> {
  try {
    await api.auth.logout();
  } finally {
    useAuth.getState().clearSession();
  }
}

// Chamado no boot do app: restaura a sessão pelo cookie de refresh (o access
// token vive só em memória e morre a cada reload). Sem rede, o app mostra
// "Sem conexão" em vez do login; o botão "Tentar de novo" chama de novo.
export async function bootstrapSession(): Promise<"ok" | "guest" | "offline"> {
  const result = await refreshSessionResult();
  if (result.status === "ok") return "ok";
  if (result.status === "offline") {
    useAuth.getState().setOffline();
    return "offline";
  }
  useAuth.getState().clearSession();
  return "guest";
}
