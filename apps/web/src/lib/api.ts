import { authSessionResponseSchema, createApiClient } from "@sociman/contract";
import { useAuth } from "./authStore";

// Refresh concorrente deduplicado: várias requisições que tomam 401 ao mesmo
// tempo compartilham UMA promessa de refresh (§7 do brief).
let refreshPromise: Promise<string | null> | null = null;

export function refreshSession(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

async function doRefresh(): Promise<string | null> {
  const epochAtStart = useAuth.getState().sessionEpoch;
  try {
    // fetch direto (não authFetch): refresh autentica pelo cookie, e passar
    // pelo interceptor causaria recursão no 401.
    const res = await fetch("/api/auth/refresh", { method: "POST" });
    if (!res.ok) return null;
    const data = authSessionResponseSchema.parse(await res.json());
    // Logout durante o refresh em voo: o epoch mudou → esta resposta pertence
    // a uma sessão que o usuário já encerrou. Aplicá-la "des-desfaria" o
    // logout na UI (até o próximo 401). Descarta.
    if (useAuth.getState().sessionEpoch !== epochAtStart) return null;
    useAuth.getState().setSession(data.accessToken, data.user);
    return data.accessToken;
  } catch {
    return null;
  }
}

// Interceptor: anexa o Bearer; num 401 de requisição autenticada, tenta refresh
// UMA vez e repete UMA vez; se o refresh falhar, derruba a sessão local.
const authFetch: typeof fetch = async (input, init) => {
  const token = useAuth.getState().accessToken;
  const headers = new Headers(init?.headers);
  if (token && !headers.has("authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(input, { ...init, headers });

  if (res.status === 401 && token) {
    const newToken = await refreshSession();
    if (!newToken) {
      useAuth.getState().clearSession();
      return res;
    }
    const retryHeaders = new Headers(init?.headers);
    retryHeaders.set("Authorization", `Bearer ${newToken}`);
    return fetch(input, { ...init, headers: retryHeaders });
  }

  return res;
};

export const api = createApiClient({ fetchFn: authFetch });
