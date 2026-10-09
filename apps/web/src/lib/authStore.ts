import { create } from "zustand";
import type { User } from "@sociman/contract";

// Access token vive SÓ aqui, em memória (§6.2): sem `persist`, sem localStorage.
// No reload a sessão é restaurada pelo cookie de refresh (bootstrapSession).
// "offline": o boot não alcançou o servidor (falha de rede, não 401).
type AuthStatus = "unknown" | "authenticated" | "guest" | "offline";

interface AuthState {
  accessToken: string | null;
  user: User | null;
  status: AuthStatus;
  // Incrementa a cada clearSession. Um refresh em voo compara o epoch de antes
  // e de depois: se mudou, houve logout no meio e a resposta é descartada —
  // senão ela re-aplicaria a sessão e "desfaria" o logout na UI.
  sessionEpoch: number;
  setSession(accessToken: string, user: User): void;
  clearSession(): void;
  // Boot sem rede: sem sessão, mas também sem mandar ao login.
  setOffline(): void;
  // A API respondeu 403 password_change_required: o RequireAuth passa a
  // mandar para /trocar-senha.
  requirePasswordChange(): void;
}

export const useAuth = create<AuthState>()((set) => ({
  accessToken: null,
  user: null,
  status: "unknown",
  sessionEpoch: 0,
  setSession: (accessToken, user) => set({ accessToken, user, status: "authenticated" }),
  clearSession: () =>
    set((state) => ({
      accessToken: null,
      user: null,
      status: "guest",
      sessionEpoch: state.sessionEpoch + 1,
    })),
  setOffline: () => set({ accessToken: null, user: null, status: "offline" }),
  requirePasswordChange: () =>
    set((state) => (state.user ? { user: { ...state.user, mustChangePassword: true } } : {})),
}));
