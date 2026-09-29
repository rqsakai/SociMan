import type { LoginRequest, RegisterRequest } from "@sociman/contract";
import { api, refreshSession } from "./api";
import { useAuth } from "./authStore";

export async function login(body: LoginRequest): Promise<void> {
  const session = await api.auth.login(body);
  useAuth.getState().setSession(session.accessToken, session.user);
}

export async function register(body: RegisterRequest): Promise<void> {
  const session = await api.auth.register(body);
  useAuth.getState().setSession(session.accessToken, session.user);
}

export async function logout(): Promise<void> {
  try {
    await api.auth.logout();
  } finally {
    useAuth.getState().clearSession();
  }
}

// Chamado uma vez no boot do app: restaura a sessão pelo cookie de refresh
// (o access token vive só em memória e morre a cada reload).
export async function bootstrapSession(): Promise<void> {
  const token = await refreshSession();
  if (!token) useAuth.getState().clearSession();
}
